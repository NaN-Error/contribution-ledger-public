"""Explicit coordinated backup / isolated Docker restore. Read runbooks first.

Requires the project's Python cryptography dependency and a local built phase-14
API image. Scratch must be on an operator-protected encrypted disk: transient
plaintext cannot be securely erased by this program. Nothing resumes writers or
publishes ports automatically. Only the operator's trusted backups may be restored.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'apps/api'))
from app.operations.archive import create_bundle,unpack_bundle,validate_pair,keygen,read_key,BundleError
from app.security.secrets.encrypted import private_path
API_IMAGE='contribution-ledger-api:'+(ROOT/'VERSION').read_text(encoding='utf-8').strip()
DATA_VOLUMES={'evidence_data','ai_credentials'}
SECRET_VOLUMES={'auth_master','ai_master','github_secrets'}
KNOWN_VOLUMES=DATA_VOLUMES|SECRET_VOLUMES|{'postgres_data'}

class OperationError(RuntimeError):pass

def run(args,*,input_file=None,output_file=None,env=None,timeout=1800,fail_on_warning=False):
    # No shell, no secret command arguments, and no raw tool stderr in terminal logs.
    result=subprocess.run(args,stdin=input_file,stdout=output_file or subprocess.PIPE,stderr=subprocess.PIPE,
        env=env,timeout=timeout,check=False)
    if result.returncode or (fail_on_warning and result.stderr.strip()):raise OperationError('Operator command failed; services remain stopped and partial destinations are preserved.')
    return result.stdout if output_file is None else b''

def inspect(kind,name):return json.loads(run(['docker',kind,'inspect',name]))[0]
def project_name(value):
    if not re.fullmatch('[a-z][a-z0-9-]{2,48}',value):raise OperationError('Invalid deployment name')
    return value

def wait_for_database(name,attempts=60):
    # The official image briefly serves a Unix socket during initialization,
    # then stops that temporary server. TCP is enabled only by the final server.
    for attempt in range(attempts):
        try:
            run(['docker','exec',name,'sh','-c','pg_isready -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'],timeout=10)
            return
        except OperationError:time.sleep(1)
    raise OperationError('Isolated database did not become ready')

def labelled(kind,project):
    args=['docker',kind,'ls','-q','--filter','label=com.docker.compose.project='+project]
    if kind=='container':args.insert(3,'-a')
    return run(args).decode().split()

def environment(container):
    return dict(item.split('=',1) for item in container['Config'].get('Env',[]) if '=' in item)

def private_write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as dst:dst.write(data);dst.flush();os.fsync(dst.fileno())

def check_locations(key,scratch,output):
    for p in (key,scratch,output):
        private_path(p.absolute())
        if p.resolve().is_relative_to(ROOT.resolve()):raise OperationError('Recovery keys, archives and plaintext scratch must be outside the source repository')
    if key.resolve().is_relative_to(output.resolve()) or key.resolve().is_relative_to(scratch.resolve()):
        raise OperationError('Keep the recovery key outside the backup and temporary-data directories')
    if output.resolve().is_relative_to(scratch.resolve()) or scratch.resolve().is_relative_to(output.resolve()):
        raise OperationError('Use separate archive and plaintext scratch directories')

def transport(volume,action,path):
    args=['docker','run','--rm','-i','--pull','never','--network','none','--user','0:0','--read-only',
        '--cap-drop','ALL','--cap-add','DAC_OVERRIDE','--cap-add','CHOWN','--security-opt','no-new-privileges:true',
        '--pids-limit','64','--memory','512m','--tmpfs','/tmp',
        '--mount',f'type=volume,source={volume},target=/transfer'+(',readonly' if action=='export' else ''),
        API_IMAGE,'python','-m','app.operations.volume',action,'/transfer']
    with path.open('wb' if action=='export' else 'rb') as stream:
        try:
            run(args,output_file=stream if action=='export' else None,input_file=stream if action=='import' else None)
        except OperationError as exc:
            raise OperationError('Private volume '+action+' failed; target state is retained.') from exc
    if action=='export':path.chmod(0o600)

def backup(args):
    project=project_name(args.project)
    if args.confirm!='STOP-WRITERS:'+project:raise OperationError('Explicit project-specific stop confirmation required')
    check_locations(args.key_file,args.scratch,args.output)
    # Validate recovery inputs before stopping a healthy deployment.
    recovery_inputs={'config/environment.env':args.env_file}
    for entry in args.recovery_file:
        name,sep,path=entry.partition('=')
        if not sep or not re.fullmatch(r'[A-Za-z0-9_.-]{1,80}',name) or 'config/'+name in recovery_inputs:
            raise OperationError('Use distinct filename=path recovery inputs')
        recovery_inputs['config/'+name]=Path(path)
    for path in recovery_inputs.values():
        private_path(path.absolute())
        if not path.is_file() or path.stat().st_nlink!=1:raise OperationError('A required recovery configuration file is missing or unsafe')
    key=read_key(args.key_file);inspect('image',API_IMAGE)
    if args.output.exists():raise OperationError('Backup output must be a new directory')
    containers=[inspect('container',i) for i in labelled('container',project)]
    databases=[c for c in containers if c['Config'].get('Labels',{}).get('com.docker.compose.service')=='db']
    if len(databases)!=1 or not databases[0]['State']['Running']:raise OperationError('Exactly one running project database is required')
    db=databases[0];env=environment(db)
    if not re.fullmatch(r'postgres:17\.[0-9]+-bookworm',db['Config']['Image']):raise OperationError('Only the reviewed PostgreSQL 17 deployment is supported')
    for c in containers:
        settings=environment(c)
        if settings.get('CL_OBJECT_STORAGE_BACKEND','local')!='local':raise OperationError('External object storage needs a separate coordinated procedure; this is not a full S3 backup')
    volumes={}
    for name in labelled('volume',project):
        info=inspect('volume',name);role=info.get('Labels',{}).get('com.docker.compose.volume')
        if role not in KNOWN_VOLUMES or role in volumes:raise OperationError('Unrecognized or duplicate persistent volume; refuse an incomplete backup')
        volumes[role]=name
    if not {'postgres_data','evidence_data'}<=set(volumes):raise OperationError('Database and evidence volumes must both be present')
    writers=[c['Id'] for c in containers if c['Id']!=db['Id'] and c['State']['Running']]
    if writers:run(['docker','stop','--time','45',*writers])
    if any(inspect('container',i)['State']['Running'] for i in labelled('container',project) if i!=db['Id']):
        # IDs returned by docker may be short; compare resolved ID rather than strings.
        running=[inspect('container',i) for i in labelled('container',project)]
        if any(c['State']['Running'] and c['Id']!=db['Id'] for c in running):raise OperationError('A writer is still running')
    args.scratch.mkdir(parents=True,exist_ok=True,mode=0o700);args.output.mkdir(mode=0o700,parents=True)
    capture=str(uuid4());metadata={'source_project':project,'captured_at':datetime.now(timezone.utc).isoformat(),
        'helper_version':'0.16.2-phase16','postgres_image':db['Config']['Image'],
        'database_name':env.get('POSTGRES_DB',env.get('POSTGRES_USER','postgres')),
        'database_user':env.get('POSTGRES_USER','postgres'),'volumes':sorted(volumes),
        'writers_stopped':len(writers),'local_objects_only':True}
    with tempfile.TemporaryDirectory(prefix='ledger-capture-',dir=args.scratch) as temporary:
        temp=Path(temporary);data={};recovery={}
        dump=temp/'database.dump'
        with dump.open('xb') as dst:
            run(['docker','exec',db['Id'],'sh','-c','exec pg_dump -U "$POSTGRES_USER" -d "${POSTGRES_DB:-$POSTGRES_USER}" --format=custom --no-owner --no-acl'],output_file=dst,fail_on_warning=True)
        dump.chmod(0o600);data['database.dump']=dump
        for role,name in sorted(volumes.items()):
            if role=='postgres_data':continue
            path=temp/(role+'.tar');transport(name,'export',path)
            (data if role in DATA_VOLUMES else recovery)['volumes/'+role+'.tar']=path
        recovery.update(recovery_inputs)
        create_bundle(data,args.output/'data.clb',key,capture_id=capture,kind='data',metadata=metadata,scratch=args.scratch)
        create_bundle(recovery,args.output/'recovery.clb',key,capture_id=capture,kind='recovery',metadata=metadata,scratch=args.scratch)
        # Full authenticated reread, not just checking an encrypted file exists.
        a=unpack_bundle(args.output/'data.clb',temp/'verify-data',key,scratch=args.scratch)
        b=unpack_bundle(args.output/'recovery.clb',temp/'verify-recovery',key,scratch=args.scratch);validate_pair(a,b)
    report={'capture_id':capture,'archive_integrity_verified':True,'native_restore_verified':False,
        'writers_left_stopped':True,'required':['data.clb','separately stored recovery.clb','external recovery key'],
        'warning':'Move recovery material to separately controlled storage; plaintext scratch must have been on an encrypted disk.'}
    private_write(args.output/'capture.json',json.dumps(report,indent=2).encode())
    return report

def restore(args):
    project=project_name(args.target)
    if not project.startswith('ledger-restore-') or args.confirm!='RESTORE-ISOLATED:'+project:
        raise OperationError('Use a fresh ledger-restore-* target and its exact confirmation')
    check_locations(args.key_file,args.scratch,args.output)
    if args.output.exists() or labelled('container',project) or labelled('volume',project):raise OperationError('Restore never overwrites existing destinations')
    inspect('image',API_IMAGE);key=read_key(args.key_file)
    args.scratch.mkdir(parents=True,exist_ok=True,mode=0o700)
    with tempfile.TemporaryDirectory(prefix='ledger-restore-',dir=args.scratch) as temporary:
        temp=Path(temporary)
        data=unpack_bundle(args.data,temp/'data',key,scratch=args.scratch)
        recovery=unpack_bundle(args.recovery,temp/'recovery',key,scratch=args.scratch);validate_pair(data,recovery)
        meta=data['metadata'];roles=set(meta['volumes'])
        if not {'postgres_data','evidence_data'}<=roles or not roles<=KNOWN_VOLUMES or meta.get('local_objects_only') is not True:
            raise OperationError('Unsupported backup inventory')
        if not re.fullmatch(r'postgres:17\.[0-9]+-bookworm',meta['postgres_image']):raise OperationError('Unsupported database image')
        inspect('image',meta['postgres_image'])
        for field in ('database_name','database_user'):
            if not re.fullmatch(r'[a-z][a-z0-9_]{0,62}',meta[field]):raise OperationError('Invalid database identity')
        expected_data={'database.dump'}|{'volumes/'+x+'.tar' for x in roles&DATA_VOLUMES}
        expected_keys={'volumes/'+x+'.tar' for x in roles&SECRET_VOLUMES}
        if set(data['files'])!=expected_data or not expected_keys<=set(recovery['files']):raise OperationError('Incomplete component archive')
        volume_names={role:project+'_'+role for role in roles|{'auth_master'}}
        for name in volume_names.values():
            if run(['docker','volume','ls','-q','--filter','name=^'+name+'$']).strip():raise OperationError('A destination volume already exists')
        args.output.mkdir(parents=True,mode=0o700)
        for role,name in volume_names.items():
            run(['docker','volume','create','--label','com.docker.compose.project='+project,'--label','com.docker.compose.volume='+role,name])
        for role,name in volume_names.items():
            if role=='postgres_data':continue
            bundle='data' if role in DATA_VOLUMES else 'recovery';path=temp/bundle/'volumes'/(role+'.tar')
            if path.exists():transport(name,'import',path)
        password=os.urandom(32).hex();child=dict(os.environ,POSTGRES_PASSWORD=password,POSTGRES_USER=meta['database_user'],POSTGRES_DB=meta['database_name'])
        dbname=project+'-db'
        run(['docker','run','-d','--pull','never','--name',dbname,'--network','none',
            '--label','com.docker.compose.project='+project,'--label','com.docker.compose.service=db',
            '-e','POSTGRES_PASSWORD','-e','POSTGRES_USER','-e','POSTGRES_DB',
            '--mount','type=volume,source='+volume_names['postgres_data']+',target=/var/lib/postgresql/data',meta['postgres_image']],env=child)
        wait_for_database(dbname)
        with (temp/'data/database.dump').open('rb') as src:
            try:
                run(['docker','exec','-i',dbname,'sh','-c','exec pg_restore --exit-on-error --single-transaction --no-owner --no-privileges -U "$POSTGRES_USER" -d "$POSTGRES_DB"'],input_file=src)
            except OperationError as exc:
                raise OperationError('Isolated database dump restoration failed; source and partial destination are retained.') from exc
        config={'CL_ENVIRONMENT':'test','CL_DB_HOST':'127.0.0.1','CL_DB_NAME':meta['database_name'],'CL_DB_USER':meta['database_user'],'CL_DB_PASSWORD':password,
            'CL_OBJECT_STORAGE_ROOT':'/restore/evidence_data','CL_AI_CREDENTIAL_ROOT':'/restore/ai_credentials',
            'CL_AI_MASTER_KEY_FILE':'/restore/ai_master/master.key','CL_AUTH_MASTER_KEY_FILE':'/restore/auth_master/master.key',
            'CL_GITHUB_ENABLED':'false','CL_AI_DEPLOYMENT_MODE':'disabled','CL_AI_LIVE_ENABLED':'false'}
        env_path=args.output/'isolated-runtime.env';private_write(env_path,''.join(k+'='+v+'\n' for k,v in config.items()).encode())
        runner=['docker','run','--rm','--pull','never','--network','container:'+dbname,'--user','10001:10001','--read-only',
            '--security-opt','no-new-privileges:true','--cap-drop','ALL','--tmpfs','/tmp','--env-file',str(env_path)]
        for role,name in volume_names.items():
            if role!='postgres_data':runner+=['--mount',f'type=volume,source={name},target=/restore/{role},readonly']
        run([*runner,API_IMAGE,'python','-m','app.cli','migrate'])
        raw=run([*runner,API_IMAGE,'python','-m','app.operations.verify','--invalidate-access','--confirm','INVALIDATE-RESTORED-ACCESS'])
        report=json.loads(raw);report.update({'target':project,'ports_published':False,'workers_started':False,'native_restore_verified':True})
        private_write(args.output/'restore-report.json',json.dumps(report,indent=2).encode())
        # Keep original configuration protected for deliberate cutover, never autoapply it.
        shutil.copytree(temp/'recovery/config',args.output/'original-configuration')
        return report

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    k=sub.add_parser('keygen');k.add_argument('--key-file',type=Path,required=True)
    for action in ('backup','restore'):
        q=sub.add_parser(action);q.add_argument('--key-file',type=Path,required=True);q.add_argument('--scratch',type=Path,required=True)
        q.add_argument('--output',type=Path,required=True);q.add_argument('--confirm',required=True)
        if action=='backup':
            q.add_argument('--project',default='contribution-ledger');q.add_argument('--env-file',type=Path,default=ROOT/'.env');q.add_argument('--recovery-file',action='append',default=[])
        else:
            q.add_argument('--target',required=True);q.add_argument('--data',type=Path,required=True);q.add_argument('--recovery',type=Path,required=True)
    args=p.parse_args()
    try:
        if args.action=='keygen':
            if args.key_file.absolute().is_relative_to(ROOT):raise OperationError('Keep the recovery key outside the repository')
            keygen(args.key_file);result={'key_created':True,'secret_printed':False}
        else:result=backup(args) if args.action=='backup' else restore(args)
        print(json.dumps(result,indent=2));return 0
    except Exception as exc:
        result={'completed':False,'error_type':type(exc).__name__,'message':'Recovery operation failed. Writers are not automatically restarted; existing source volumes are never removed. Inspect protected local state before retrying.'}
        # Only our fixed operator messages are safe to display. Never expose
        # subprocess stderr, arbitrary exceptions, credentials or file contents.
        if isinstance(exc,OperationError):result['detail']=str(exc)
        print(json.dumps(result),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
