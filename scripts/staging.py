"""Opt-in restricted synthetic staging. No domain, certificate or hosting is purchased.

Creates a separate configuration and Compose project, not an upgrade of the
local pilot. A supplied trusted certificate, completed dependency/build checks,
and an explicitly acknowledged readiness checklist are required to start.
"""
import argparse
from datetime import datetime,timezone
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/'.local/staging/operator.env'

def write_exclusive(path,data):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w',encoding='utf-8',newline='\n') as f:f.write(data)

def validate_network(host,bind,cidrs):
    if not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]{1,250}[a-z0-9])?',host) or '..' in host or '.' not in host:raise ValueError('Use a literal DNS hostname')
    address=ipaddress.ip_address(bind)
    if address.version!=4 or address.is_unspecified or not (address.is_private or address.is_loopback):raise ValueError('Bind to loopback or an explicitly private IPv4 address')
    values=cidrs.split()
    if not values or len(values)>12:raise ValueError('Specify a bounded list of approved client ranges')
    for raw in values:
        network=ipaddress.ip_network(raw,strict=True)
        if not (network.is_private or network.is_loopback) or network.prefixlen==0:raise ValueError('Public or unrestricted client ranges are not accepted')
    return values

def config_values():
    values={}
    for line in CONFIG.read_text().splitlines():
        if not line or line.startswith('#'):continue
        key,sep,value=line.partition('=')
        if not sep or key in values:raise ValueError('Invalid staging configuration')
        values[key]=value
    validate_network(values['CL_STAGING_HOST'],values['CL_STAGING_BIND'],values['CL_STAGING_CIDRS'])
    if values['CL_RUNTIME_DB_PASSWORD']==values['CL_STAGING_DB_PASSWORD']:raise ValueError('The API and operator passwords must differ')
    return values

def compose(*args):
    env={k:v for k,v in os.environ.items() if not k.startswith('CL_')}
    subprocess.run(['docker','compose','--project-directory',str(ROOT),'--env-file',str(CONFIG),
        '--project-name','contribution-ledger-staging','-f',str(ROOT/'compose.staging.yaml'),*args],cwd=ROOT,env=env,check=True)

def certificate(host):
    import ssl
    from cryptography import x509
    cert=ROOT/'.local/staging/tls/server.crt';key=ROOT/'.local/staging/tls/server.key'
    for path in (cert,key):
        if not path.is_file() or path.is_symlink():raise ValueError('Supply the operator TLS certificate and key')
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(cert,key)
    parsed=x509.load_pem_x509_certificate(cert.read_bytes());instant=datetime.now(timezone.utc)
    names=parsed.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName)
    if host not in names or not parsed.not_valid_before_utc<=instant<parsed.not_valid_after_utc:raise ValueError('Certificate must be valid now and name the exact configured host')

def readiness():
    document=json.loads((ROOT/'.local/staging/readiness.json').read_text())
    if document.get('scope')!='restricted-synthetic-staging' or not isinstance(document.get('reviewed_by'),str) or len(document['reviewed_by'].strip())<2:raise ValueError('Record the operator readiness review')
    for key in ('clean_build_verified','native_database_verified','restore_drill_verified','mfa_browser_verified','tls_and_network_verified','dependency_review_completed'):
        if document.get(key) is not True:raise ValueError('A mandatory staging verification is still open')
    # An attestation records a human decision, not cryptographic certification.
    return document

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['init','prepare','drill','start','stop','status','setup-owner']);p.add_argument('--host');p.add_argument('--bind',default='127.0.0.1');p.add_argument('--cidrs',default='127.0.0.0/8');p.add_argument('--confirm',default='');a=p.parse_args()
    try:
        if a.action=='init':
            validate_network(a.host or '',a.bind,a.cidrs)
            data={'CL_STAGING_HOST':a.host,'CL_STAGING_BIND':a.bind,'CL_STAGING_CIDRS':a.cidrs,
                'CL_STAGING_DB_PASSWORD':os.urandom(32).hex(),'CL_RUNTIME_DB_PASSWORD':os.urandom(32).hex()}
            write_exclusive(CONFIG,''.join(k+'='+v+'\n' for k,v in data.items()))
            (CONFIG.parent/'tls').mkdir(mode=0o700,exist_ok=True)
            sample={'scope':'restricted-synthetic-staging','reviewed_by':'','clean_build_verified':False,
                'native_database_verified':False,'restore_drill_verified':False,'mfa_browser_verified':False,
                'tls_and_network_verified':False,'dependency_review_completed':False}
            write_exclusive(CONFIG.parent/'readiness.json',json.dumps(sample,indent=2))
            print('Separate staging configuration created. No services started. Supply trusted TLS material and complete the runbook.');return 0
        values=config_values()
        if a.action=='prepare':
            if a.confirm!='PREPARE-ISOLATED-STAGING':raise ValueError('Explicit preparation confirmation required')
            # Prepares database only. No web port or gateway is published.
            compose('stop','gateway','web','api')
            compose('build','api','web','operator');compose('up','-d','--wait','db')
            compose('run','--rm','--no-deps','operator','python','-m','app.cli','migrate')
            compose('run','--rm','--no-deps','operator','python','-m','app.cli','init-security')
            compose('run','--rm','--no-deps','operator','python','-m','app.cli','provision-runtime')
        elif a.action=='drill':
            if a.confirm!='START-LOOPBACK-ONLY-DRILL':raise ValueError('Explicit local drill confirmation required')
            if values['CL_STAGING_BIND']!='127.0.0.1':
                raise ValueError('A pre-readiness drill must use only a loopback host binding')
            for value in values['CL_STAGING_CIDRS'].split():
                network=ipaddress.ip_network(value)
                if not network.is_loopback and network.prefixlen!=network.max_prefixlen:
                    raise ValueError('A non-loopback NAT peer for the local drill must be one explicit private host, not a broad network')
            certificate(values['CL_STAGING_HOST'])
            # Deliberately does not mark readiness. Allows actual browser/TLS/MFA
            # verification before an operator attests to the private-network gate.
            compose('up','-d','--wait','api','web','gateway')
            print('Loopback-only synthetic drill started. No readiness flag changed. Stop it explicitly after the drill.')
        elif a.action=='start':
            if a.confirm!='START-RESTRICTED-SYNTHETIC-STAGING':raise ValueError('Explicit staging start confirmation required')
            certificate(values['CL_STAGING_HOST']);readiness()
            compose('up','-d','--wait','api','web','gateway')
        elif a.action=='stop':compose('stop','gateway','web','api')
        elif a.action=='status':compose('ps')
        elif a.action=='setup-owner':
            compose('run','--rm','--no-deps','operator','python','-m','app.cli','setup-token')
        return 0
    except Exception as exc:
        print('Staging command refused or failed ('+type(exc).__name__+'). Inspect the protected configuration and runbook; no readiness step is assumed complete.',file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
