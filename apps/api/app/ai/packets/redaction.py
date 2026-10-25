"""Best-effort data minimization, NOT a universal secret/PII detector.

Explicit field/path exclusion and human packet review are primary controls.
No network calls, evaluation, execution, archive extraction or OCR are performed.
"""
import fnmatch
import re
import unicodedata

REDACTION_VERSION='bounded-redaction-v1'
DEFAULT_EXCLUDED_PATHS = ('**/.env*','**/secrets/**','**/credentials/**','**/*.pem','**/*.key',
    '**/id_rsa*','**/.git/**','**/node_modules/**','**/package-lock.json','**/*.lock',
    '**/*payroll*','**/*salary*','**/*revenue_share*')
PATTERNS = (
    (re.compile(r'-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|\Z)',re.S),'private_key'),
    (re.compile(r'(?im)^.*\b(?:api[_ -]?key|access[_ -]?token|auth(?:orization)?|password|passwd|client[_ -]?secret|salary|payroll|revenue[_ -]?share|bank[_ -]?account)\b\s*[:=].*$'),'sensitive_assignment'),
    (re.compile(r'\b(?:sk-(?:proj-)?|ghp_|github_pat_|AIza)[A-Za-z0-9_\-]{12,}\b'),'credential_pattern'),
    (re.compile(r'\bAKIA[A-Z0-9]{16}\b'),'credential_pattern'),
    (re.compile(r'\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\b'),'token_pattern'),
    (re.compile(r'\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b',re.I),'email'),
    (re.compile(r'https?://[^\s<>"\']+',re.I),'external_url'),
    (re.compile(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b',re.I),'identifier'),
)


def excluded_path(path, patterns=DEFAULT_EXCLUDED_PATHS):
    if not isinstance(path,str) or not path: return True
    value=unicodedata.normalize('NFKC',path).replace('\\','/').lower()
    while value.startswith('./'): value=value[2:]
    if value.startswith('/') or '\x00' in value or '..' in value.split('/') or ':' in value: return True
    return any(fnmatch.fnmatchcase(value,p.lower()) or (p.startswith('**/') and fnmatch.fnmatchcase(value,p[3:].lower())) for p in patterns)


def redact(value, identities=()):
    text=unicodedata.normalize('NFKC',str(value or ''))
    text=''.join(c for c in text if c in '\n\t' or (ord(c)>=32 and unicodedata.category(c)!='Cf'))
    counts={}
    for pattern,name in PATTERNS:
        text,n=pattern.subn('[redacted]',text)
        if n: counts[name]=counts.get(name,0)+n
    for label,alias in sorted(identities,key=lambda v:len(v[0]),reverse=True):
        if label and len(label)>=3:
            text,n=re.subn(r'(?<!\w)'+re.escape(label)+r'(?!\w)',alias,text,flags=re.I)
            if n: counts['contributor_identity']=counts.get('contributor_identity',0)+n
    return text,counts


def bounded_lines(value, *, byte_limit=6000, line_limit=120):
    lines=[];used=0;truncated=False
    for raw in value.splitlines() or ['']:
        # Very long lines are omitted in full; never present a sliced statement as complete.
        size=len(raw.encode('utf-8'))+1
        if size>1000 or used+size>byte_limit or len(lines)>=line_limit:
            truncated=True;continue
        used+=size;lines.append(raw)
    return lines,truncated
