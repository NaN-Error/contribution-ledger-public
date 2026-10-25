"""Actual Windows batch/bundled-runtime/browser acceptance with explicit disposable data.

Run with --package, --data, --output and --allow-synthetic. Never selects the real
default personal directory. No evaluated code or private/paid integration runs.
"""
from pathlib import Path
import argparse, hashlib, json, os, subprocess, sys


def main():
    from playwright.sync_api import sync_playwright,expect
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['package','data','output']:parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--allow-synthetic',action='store_true')
    parser.add_argument('--startup-timeout',type=int,default=900)
    parser.add_argument('--stop-timeout',type=int,default=360)
    args=parser.parse_args();package=args.package.resolve();data=args.data.resolve();output=args.output.resolve()
    if not 150 <= args.startup_timeout <= 3600 or not 60 <= args.stop_timeout <= 600:raise ValueError('Use bounded startup/stop observation deadlines.')
    if os.name!='nt' or not args.allow_synthetic or data.exists():raise ValueError('Fresh explicitly authorized Windows synthetic data directory required.')
    real=Path(os.environ['LOCALAPPDATA'])/'ContributionLedger/Personal'
    if data==real or real in data.parents or data in real.parents:raise ValueError('Never test in or above the real personal directory.')
    for path in [package,data,output]:
        if any(ch in str(path) for ch in ['"','%','!','&','|','<','>']):raise ValueError('Use uncomplicated test paths.')
    output.mkdir(parents=True,exist_ok=False)
    env={k:v for k,v in os.environ.items() if not k.startswith('CL_')}
    env['PATH']=os.environ['SystemRoot']+'\\System32;'+os.environ['SystemRoot']+';'+os.environ['SystemRoot']+'\\System32\\WindowsPowerShell\\v1.0'
    env['PYTHONHOME']='C:\\does-not-exist';env['PYTHONPATH']='C:\\does-not-exist'
    report={'platform':'Windows x64','synthetic_only':True,'startup_browser_suppressed':True,'checks':{}}
    powershell=str(Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe')
    def run_start(label):
        command='cmd.exe /d /s /c ""'+str(package/'Start.cmd')+'" -DataDirectory "'+str(data)+'" -NoBrowser"'
        with (output/(label+'.log')).open('w',encoding='utf-8') as log:
            proc=subprocess.Popen(command,cwd=package,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
            code=proc.wait(timeout=args.startup_timeout)
        if code:raise RuntimeError('Batch startup failed; inspect '+label+'.log')
    def stop():
        with (output/'stop.log').open('a',encoding='utf-8') as log:
            proc=subprocess.Popen([powershell,'-NoProfile','-ExecutionPolicy','Bypass','-File',str(package/'scripts/portable.ps1'),
                '-Action','stop','-DataDirectory',str(data)],env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
            if proc.wait(timeout=args.stop_timeout):raise RuntimeError('Personal stop failed. Saved data was retained.')
    def api_env():
        ports=json.loads((data/'ports.json').read_text(encoding='utf-8-sig'))
        settings={k:v for k,v in env.items() if not k.startswith('CL_')}
        settings.update(CL_ENVIRONMENT='development',CL_DESKTOP_ENABLED='true',CL_DB_HOST='127.0.0.1',CL_DB_PORT=str(ports['db']),
            CL_DB_NAME='contribution_ledger_desktop',CL_DB_USER='ledger_desktop',CL_DB_PASSWORD=(data/'postgres-password.txt').read_text().strip(),
            CL_ALLOWED_ORIGINS=json.dumps(['http://127.0.0.1:'+str(ports['web'])]),CL_ALLOWED_HOSTS='["127.0.0.1","localhost"]',
            CL_AUTH_MASTER_KEY_FILE=str(data/'auth-master/master.key'),CL_OBJECT_STORAGE_ROOT=str(data/'evidence'),
            CL_AI_CREDENTIAL_ROOT=str(data/'ai-credentials'),CL_AI_MASTER_KEY_FILE=str(data/'ai-master/master.key'))
        return settings,'http://127.0.0.1:'+str(ports['web'])
    def ticket():
        settings,_=api_env()
        proc=subprocess.run([str(package/'runtime/python/python.exe'),'-m','app.cli','desktop-ticket'],cwd=package/'apps/api',
            env=settings,stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)
        if proc.returncode:raise RuntimeError('Desktop ticket issuance failed; credentials are not printed.')
        return json.loads(proc.stdout)['desktop_ticket']
    def identity():
        settings,_=api_env()
        code="from app.core.config import get_settings;from app.db.session import Database;from sqlalchemy import text;import json;d=Database(get_settings());c=d.engine.connect();print(json.dumps({t: [list(map(str,r)) for r in c.execute(text('SELECT * FROM '+t)).all()] for t in ['users','workspaces','projects']}));c.close();d.dispose()"
        proc=subprocess.run([str(package/'runtime/python/python.exe'),'-c',code],env=settings,cwd=package/'apps/api',capture_output=True,text=True,timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)
        if proc.returncode:raise RuntimeError('Could not inspect disposable personal identities.')
        return json.loads(proc.stdout)
    def protected_hashes():
        return {str(p.relative_to(data)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [data/'postgres-password.txt',data/'auth-master/master.key',data/'ports.json',data/'personal-installation.json']}
    try:
        run_start('fresh-start');report['checks']['actual_Start_cmd_with_no_developer_tools']='passed'
        settings,base=api_env();initial=identity()
        assert len(initial['users'])==len(initial['workspaces'])==len(initial['projects'])==1
        assert initial['projects'][0][2]=='My repositories'
        with sync_playwright() as p:
            browser=p.chromium.launch();context=browser.new_context(viewport={'width':1365,'height':900});page=context.new_page()
            token=ticket();page.goto(base+'/#desktop/'+token)
            expect(page.get_by_role('heading',name='Repository dashboard',exact=True)).to_be_visible(timeout=30000)
            assert token not in page.url and page.url.endswith('#analysis')
            expect(page.get_by_label('GitHub repository links',exact=True)).to_be_visible()
            page.screenshot(path=str(output/'repository-input.png'),full_page=True)
            report['checks']['browser_personal_handoff_no_signup_no_token_pasting']='passed'
            assert page.locator('input[type="password"]').count()==0
            page.get_by_text('Create another project',exact=True).click()
            page.get_by_label('New project name',exact=True).fill('Portable restart check')
            page.get_by_role('button',name='Create project',exact=True).click()
            expect(page.get_by_role('heading',name='Portable restart check',exact=True)).to_be_visible()
            page.set_viewport_size({'width':390,'height':844})
            page.screenshot(path=str(output/'repository-input-mobile.png'),full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
            report['checks']['repository_input_and_project_creation_desktop_mobile']='passed'
            before=identity();hashes=protected_hashes();first_state=json.loads((data/'processes.json').read_text(encoding='utf-8-sig'))
            run_start('warm-start');second_state=json.loads((data/'processes.json').read_text(encoding='utf-8-sig'))
            assert first_state['api']==second_state['api'] and first_state['web']==second_state['web']
            assert before==identity() and hashes==protected_hashes()
            report['checks']['warm_start_reuses_owned_services_and_personal_identity']='passed'
            stop();run_start('restart')
            assert before==identity() and hashes==protected_hashes()
            fresh=browser.new_context();fresh_page=fresh.new_page();fresh_page.goto(base+'/#desktop/'+ticket())
            expect(fresh_page.get_by_role('heading',name='Repository dashboard',exact=True)).to_be_visible(timeout=30000)
            expect(fresh_page.get_by_label('Project',exact=True)).to_contain_text('Portable restart check')
            report['checks']['stop_restart_preserves_projects_credentials_and_master']='passed'
            fresh.close();context.close();browser.close()
        # Tickets are purpose-hashed; no raw secret may appear in public logs/artifacts.
        for log in list(output.glob('*.log'))+list(data.glob('*.log')):
            assert token not in log.read_text(encoding='utf-8',errors='replace'), 'Launch credential leaked to a log'
        report['checks']['launch_ticket_absent_from_logs']='passed'
        report['status']='passed'
    finally:
        stop()
        (output/'results.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('PASS:',len(report['checks']),'portable batch/browser/preservation checks. No private/paid calls.')


if __name__=='__main__': main()
