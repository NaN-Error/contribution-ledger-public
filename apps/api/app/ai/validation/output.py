"""A closed output language. No scores, commands, monetary values or arbitrary IDs."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from app.providers.contracts import parse_json

SCHEMA_VERSION = 'evidence-assessment-v1'

class Closed(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, hide_input_in_errors=True)

class Citation(Closed):
    source_id: str = Field(pattern=r'^E[1-9][0-9]{0,2}$')
    start_line: int = Field(ge=1, le=200)
    end_line: int = Field(ge=1, le=200)

class Finding(Closed):
    criterion_id: str = Field(pattern=r'^C[1-9][0-9]{0,2}$')
    status: Literal['supported', 'contradicted', 'insufficient']
    explanation: str = Field(min_length=8, max_length=1200)
    evidence_refs: list[Citation] = Field(max_length=8)

class Role(Closed):
    contributor_alias: str = Field(pattern=r'^contributor_[1-9][0-9]{0,2}$')
    role: Literal['implementation', 'design', 'testing', 'review', 'documentation', 'research', 'other']
    explanation: str = Field(min_length=8, max_length=800)
    evidence_refs: list[Citation] = Field(min_length=1, max_length=8)

class Overlap(Closed):
    explanation: str = Field(min_length=8, max_length=800)
    evidence_refs: list[Citation] = Field(min_length=2, max_length=8)

class Assessment(Closed):
    schema_version: Literal['evidence-assessment-v1']
    summary: str = Field(min_length=8, max_length=1800)
    findings: list[Finding] = Field(min_length=1, max_length=64)
    proposed_roles: list[Role] = Field(max_length=30)
    overlap_flags: list[Overlap] = Field(max_length=12)
    questions: list[str] = Field(max_length=20)


def response_schema():
    # Inline schema uses a deliberately small common provider subset. The application
    # applies stronger bounds and cross-reference checks after generation.
    def obj(fields):
        return {'type':'object','properties':fields,'required':list(fields),'additionalProperties':False}
    def arr(item): return {'type':'array','items':item}
    string = {'type':'string'}
    citation = obj({'source_id':string,'start_line':{'type':'integer'},'end_line':{'type':'integer'}})
    return obj({'schema_version':{'type':'string','enum':[SCHEMA_VERSION]},'summary':string,
        'findings':arr(obj({'criterion_id':string,'status':{'type':'string','enum':['supported','contradicted','insufficient']},
            'explanation':string,'evidence_refs':arr(citation)})),
        'proposed_roles':arr(obj({'contributor_alias':string,'role':{'type':'string','enum':['implementation','design','testing','review','documentation','research','other']},
            'explanation':string,'evidence_refs':arr(citation)})),
        'overlap_flags':arr(obj({'explanation':string,'evidence_refs':arr(citation)})), 'questions':arr(string)})


class InvalidAssessment(ValueError):
    """Fixed failure codes only. Do not retain/log the untrusted raw result."""


def validate_output(content: str, packet: dict) -> dict:
    if not isinstance(content,str) or len(content.encode('utf-8')) > 65536:
        raise InvalidAssessment('output_size')
    try:
        parsed = Assessment.model_validate(parse_json(content))
    except (ValidationError, ValueError, TypeError, RecursionError):
        raise InvalidAssessment('invalid_schema') from None
    criteria = {c['id'] for c in packet['criteria']}
    ids = [f.criterion_id for f in parsed.findings]
    if len(ids) != len(set(ids)) or set(ids) != criteria:
        raise InvalidAssessment('invalid_criteria')
    sources = {s['id']:s for s in packet['sources']}
    aliases = {p['alias'] for p in packet['contributors']}
    def refs(items):
        seen=set()
        for ref in items:
            source=sources.get(ref.source_id)
            key=(ref.source_id,ref.start_line,ref.end_line)
            if source is None or ref.start_line>ref.end_line or ref.end_line>len(source['lines']) or key in seen:
                raise InvalidAssessment('invalid_evidence_reference')
            seen.add(key)
    for finding in parsed.findings:
        refs(finding.evidence_refs)
        if finding.status!='insufficient' and not finding.evidence_refs:
            raise InvalidAssessment('evidence_required')
    role_keys=set()
    for role in parsed.proposed_roles:
        if role.contributor_alias not in aliases or (role.contributor_alias,role.role) in role_keys:
            raise InvalidAssessment('invalid_contributor')
        role_keys.add((role.contributor_alias,role.role));refs(role.evidence_refs)
    for overlap in parsed.overlap_flags:
        refs(overlap.evidence_refs)
        if len({r.source_id for r in overlap.evidence_refs})<2:
            raise InvalidAssessment('invalid_overlap')
    if any(not 8<=len(q)<=800 for q in parsed.questions):
        raise InvalidAssessment('invalid_question')
    return parsed.model_dump(mode='json')
