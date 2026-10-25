"""Build a pristine, relocatable Windows distribution from a sanitized source tree.

The supplied Python site-packages are copied strictly through installed runtime
distribution RECORDs, excluding development tools. This builder does not download
or install anything. Missing Windows C++ runtime setup is separately pinned and
opened interactively by the user launcher; it is not bundled here.
"""
from pathlib import Path
import argparse, base64, hashlib, importlib.metadata, json, re, shutil, zipfile
from verify_release import verify


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--python-archive',type=Path,required=True)
    parser.add_argument('--node-archive',type=Path,required=True)
    parser.add_argument('--postgres-archive',type=Path,required=True)
    parser.add_argument('--site-packages',type=Path,required=True)
    parser.add_argument('--web-dist',type=Path,required=True)
    args=parser.parse_args()
    source=args.source.resolve();out=args.output.resolve()
    if out.exists():raise ValueError('Build output already exists; choose a new directory. No files were removed.')
    # Do not trust an input manifest to exclude local state or traversal paths.
    # Validate before creating output, reading runtime archives, or copying files.
    verification=verify(source)
    if not verification['file_consistency_passed']:
        raise ValueError('Source verification failed; no distribution was created.')
    manifest=json.loads((source/'release-manifest.json').read_bytes())
    locked=json.loads((source/'scripts/windows-runtime-lock.json').read_bytes())
    expected={item['filename']:item['sha256'] for item in locked['archives']}
    for archive in [args.python_archive,args.node_archive,args.postgres_archive]:
        if sha(archive)!=expected.get(archive.name):raise ValueError('Pinned runtime archive mismatch: '+archive.name)
    out.mkdir(parents=True)
    for item in manifest['files']:
        name=item['path'];p=source/name
        if sha(p)!=item['sha256']:raise ValueError('Source manifest mismatch: '+name)
        target=out/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
    shutil.copyfile(source/'release-manifest.json',out/'release-manifest.json')
    shutil.copytree(args.web_dist,out/'apps/web/dist')
    archives=[('python',args.python_archive,'https://www.python.org/downloads/release/python-31316/'),
        ('node',args.node_archive,'https://nodejs.org/en/blog/release/v22.23.0'),
        ('postgres',args.postgres_archive,'https://www.postgresql.org/download/windows/')]
    provenance=[]
    for kind,archive,url in archives:
        provenance.append({'component':kind,'archive':archive.name,'sha256':sha(archive),'official_reference':url})
        with zipfile.ZipFile(archive) as z:
            for info in z.infolist():
                parts=Path(info.filename).parts
                if info.is_dir():continue
                if '..' in parts or Path(info.filename).is_absolute():raise ValueError('Unsafe archive path')
                if kind=='node':
                    if len(parts)!=2 or parts[-1] not in {'node.exe','LICENSE','README.md','CHANGELOG.md'}:continue
                    rel=Path(parts[-1])
                elif kind=='postgres':
                    license_path=any('license' in part.lower() or 'copyright' in part.lower() or 'legalnotice' in part.lower() for part in parts)
                    if len(parts)<2 or parts[0]!='pgsql' or (parts[1] not in {'bin','lib','share'} and not license_path):continue
                    if parts[1] in {'bin','lib','share'}:
                        rel=Path(*parts)
                    else:
                        # Retain notices without shipping pgAdmin/developer directory trees.
                        label=hashlib.sha256(info.filename.encode()).hexdigest()[:16]+'-'+parts[-1][-100:]
                        rel=Path('licenses')/label
                else: rel=Path(info.filename)
                p=out/'runtime'/kind/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(z.read(info))
    # Embedded Python is isolated from installed Python, environment variables and user site.
    (out/'runtime/python/python313._pth').write_text('python313.zip\n.\nLib/site-packages\n../../apps/api\nimport site\n',encoding='utf-8')
    distributions={re.sub(r'[-_.]+','-',d.metadata['Name']).lower():d for d in importlib.metadata.distributions(path=[str(args.site_packages)])}
    packages=[]
    for line in (source/'apps/api/requirements.lock').read_text().splitlines():
        match=re.match(r'([A-Za-z0-9_.-]+)==([^ ;]+)',line)
        if not match:continue
        name,version=match.groups();dist=distributions[re.sub(r'[-_.]+','-',name).lower()]
        if dist.version!=version:raise ValueError('Runtime distribution version mismatch: '+name)
        packages.append({'name':name,'version':version})
        for item in dist.files or []:
            parts=item.parts
            if '..' in parts or '__pycache__' in parts or str(item).endswith('.pyc'):continue
            p=Path(dist.locate_file(item));target=out/'runtime/python/Lib/site-packages'/Path(str(item))
            if not p.is_file():raise ValueError('Installed runtime file missing: '+str(item))
            if item.hash:
                actual=base64.urlsafe_b64encode(hashlib.new(item.hash.mode,p.read_bytes()).digest()).decode().rstrip('=')
                if actual!=item.hash.value:raise ValueError('Installed runtime RECORD hash mismatch: '+str(item))
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
    # PostgreSQL's source license remains alongside its extracted runtime files.
    license_file=source/'docs/runtime-licenses/POSTGRESQL-LICENSE.txt'
    if not license_file.is_file():raise ValueError('PostgreSQL redistribution license is required.')
    shutil.copyfile(license_file,out/'runtime/postgres/LICENSE.txt')
    files=[]
    for p in sorted(out.rglob('*')):
        if p.is_file():files.append({'path':p.relative_to(out).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)})
    report={'application_version':manifest['version'],'platform':'Windows x64',
        'source_manifest_sha256':sha(source/'release-manifest.json'),'archives':provenance,
        'python_packages':packages,'files':files,'self_hash_excluded':True,
        'private_state_included':False,'startup_downloads':{'bundled_runtime_downloads':False,
            'optional_missing_windows_cpp_runtime':locked.get('optional_windows_prerequisite')},
        'windows_cpp_installer_bundled':False}
    (out/'runtime-manifest.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('Built pristine Windows package:',len(files)+1,'files; private state excluded.')


if __name__=='__main__': main()
