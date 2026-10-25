"""Run no-account, local test-candidate checks with explicit pass/fail evidence.

Requires already-installed project Python/Node dependencies. Never downloads
packages, runs migrations against a configured deployment, starts Docker, reads
.env, contacts a provider, or treats skipped native tests as a verified system.
Raw local logs may contain environment information; inspect before sharing.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def commands(root: Path, *, skip_backend: bool = False) -> list[tuple[str, list[str], Path]]:
    npm = shutil.which('npm') or 'npm'
    result = [('source_integrity', [sys.executable, 'scripts/verify_release.py'], root),
              ('source_structure', [sys.executable, 'scripts/verify_source.py'], root),
              ('synthetic_evaluation', [sys.executable, 'scripts/evaluate.py', 'mock', '--output',
                                       str(root / '.local' / 'candidate-eval' / str(time.time_ns()))], root)]
    if not skip_backend:
        result.append(('backend_regression', [sys.executable, '-m', 'pytest', '-q'], root / 'apps/api'))
    result.extend([('frontend_helpers', [npm, 'test'], root / 'apps/web'),
                   ('frontend_build', [npm, 'run', 'build'], root / 'apps/web')])
    return result


def safe_environment() -> dict[str, str]:
    # Application fixtures explicitly inject disposable databases. Do not inherit
    # a user's actual DB/provider configuration into generic regression commands.
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith('CL_')}
    env['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    return env


def execute(command: list[str], directory: Path, log: Path, timeout: int) -> dict:
    start = time.monotonic()
    with log.open('w', encoding='utf-8') as handle:
        try:
            kwargs = {'cwd': directory, 'env': safe_environment(), 'stdout': handle, 'stderr': subprocess.STDOUT}
            if os.name == 'posix':
                kwargs['start_new_session'] = True
            proc = subprocess.Popen(command, **kwargs)
            try:
                code = proc.wait(timeout=timeout)
                status = 'passed' if code == 0 else 'failed'
            except subprocess.TimeoutExpired:
                if os.name == 'posix':
                    os.killpg(proc.pid, signal.SIGKILL)
                elif os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'],
                                   stdout=handle, stderr=subprocess.STDOUT, check=False)
                else:
                    proc.kill()
                proc.wait(); code = None; status = 'timed_out'
        except OSError:
            handle.write('Required executable could not be started. Check installed local tools.\n')
            code = None; status = 'unavailable'
    return {'status': status, 'exit_code': code, 'duration_seconds': round(time.monotonic() - start, 3),
            'log': log.name}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='New directory; defaults below ignored .local/.')
    parser.add_argument('--skip-backend', action='store_true', help='Record backend as not run, never as passed.')
    parser.add_argument('--timeout', type=int, default=3600, help='Maximum seconds for each executed check.')
    args = parser.parse_args()
    if not 10 <= args.timeout <= 14400:
        parser.error('timeout must be between 10 and 14400 seconds')
    output = args.output or ROOT / '.local' / 'candidate-checks' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    if output.exists():
        parser.error('Use a new output directory; previous reports will not be overwritten.')
    output.mkdir(parents=True, mode=0o700)
    report = {'version': (ROOT / 'VERSION').read_text().strip(), 'checks': {},
        'native_postgresql_verified': False, 'docker_verified': False, 'browser_verified': False,
        'human_pilot_completed': False, 'real_use_authorized': False}
    if args.skip_backend:
        report['checks']['backend_regression'] = {'status': 'not_run'}
    for name, command, directory in commands(ROOT, skip_backend=args.skip_backend):
        print('Running ' + name, flush=True)
        report['checks'][name] = execute(command, directory, output / (name + '.log'), args.timeout)
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(name + ': ' + report['checks'][name]['status'], flush=True)
    report['all_selected_checks_passed'] = all(x['status'] == 'passed' for x in report['checks'].values())
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('Recorded local results. Native deployment, browser and human acceptance remain separate.')
    return 0 if report['all_selected_checks_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
