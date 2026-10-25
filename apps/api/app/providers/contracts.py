"""Bounded, provider-neutral JSON generation contracts; no tools or secret fields."""
from dataclasses import dataclass, field
from typing import Protocol
import json
import re

PROBE_VERSION = 'synthetic-json-probe-v1'
PROBE_PROMPT = 'Connection compatibility test using synthetic data only. Return exactly the JSON object {"ok": true}.'
PROBE_SCHEMA = {'type':'object', 'properties':{'ok':{'type':'boolean'}}, 'required':['ok'], 'additionalProperties':False}
PROVIDERS = ('mock', 'openai', 'anthropic', 'gemini')
ADAPTER_VERSION = 'text-json-v1'

class ProviderError(Exception):
    """Fixed codes only: never retain a raw response, credential, URL or SDK exception."""
    def __init__(self, code: str, *, ambiguous: bool=False, retry_after: int=60):
        allowed={'authentication','permission','model_unavailable','incompatible','rate_limited',
                 'timeout','transport','provider_failure','malformed','catalog_incomplete','disabled'}
        self.code=code if code in allowed else 'provider_failure'
        self.ambiguous=ambiguous
        self.retry_after=max(10,min(86400,retry_after))
        super().__init__(self.code)

def model_id(value) -> str:
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:/-]{0,199}',value) or '..' in value or '://' in value:
        raise ProviderError('malformed')
    return value

def number(value) -> int | None:
    return value if type(value) is int and 0<=value<=10**9 else None

def text(value, limit=200):
    return value[:limit] if isinstance(value,str) else ''

def safe_id(value):
    return value if isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_.:/-]{1,200}',value) else None

def parse_json(value: str):
    def reject(_): raise ValueError('Nonfinite JSON')
    def unique(pairs):
        d={}
        for k,v in pairs:
            if k in d: raise ValueError('Duplicate JSON field')
            d[k]=v
        return d
    return json.loads(value,parse_constant=reject,object_pairs_hook=unique)

@dataclass(frozen=True)
class ModelInfo:
    id: str
    name: str
    input_limit: int | None = None
    output_limit: int | None = None
    text_generation: bool | None = None
    structured_output: bool | None = None
    metadata: dict = field(default_factory=dict)
    def __post_init__(self):
        model_id(self.id)
        if not isinstance(self.name,str) or len(self.name)>200:
            raise ProviderError('malformed')
        for value in (self.input_limit,self.output_limit):
            if value is not None and number(value) is None:raise ProviderError('malformed')
        if any(value is not None and type(value) is not bool for value in (self.text_generation,self.structured_output)):
            raise ProviderError('malformed')
        try:
            if not isinstance(self.metadata,dict) or len(json.dumps(self.metadata,allow_nan=False).encode('utf-8'))>4096:
                raise ProviderError('malformed')
        except (ValueError,TypeError,RecursionError):raise ProviderError('malformed') from None
    def document(self):
        return {'id':self.id,'name':self.name,'input_limit':self.input_limit,'output_limit':self.output_limit,
                'text_generation':self.text_generation,'structured_output':self.structured_output,'metadata':self.metadata}

@dataclass(frozen=True)
class GenerationRequest:
    model: str
    prompt: str
    schema: dict
    max_output_tokens: int = 256
    instructions: str | None = None
    def __post_init__(self):
        model_id(self.model)
        if self.instructions is not None and (not isinstance(self.instructions,str) or not 1<=len(self.instructions.encode('utf-8'))<=8192):
            raise ValueError('Bounded system instructions required')
        if not isinstance(self.prompt,str) or not 1<=len(self.prompt.encode('utf-8'))<=65536:
            raise ValueError('Bounded text required')
        if type(self.max_output_tokens) is not int or not 16<=self.max_output_tokens<=8192:
            raise ValueError('Bounded output required')
        if not isinstance(self.schema,dict) or len(json.dumps(self.schema,allow_nan=False))>16384:
            raise ValueError('Bounded schema required')

@dataclass(frozen=True)
class GenerationResult:
    # Content is only in memory. Phase 10 persists probe validity, not model prose.
    content: str = field(repr=False)
    model: str | None
    request_id: str | None
    finish: str
    input_tokens: int | None
    output_tokens: int | None
    usage_supported: bool = True
    def probe_passed(self) -> bool:
        if self.finish!='complete':return False
        try:
            obj=parse_json(self.content)
            return isinstance(obj,dict) and set(obj)=={'ok'} and obj['ok'] is True
        except (ValueError,TypeError,RecursionError): return False

class Provider(Protocol):
    def list_models(self, credential: str) -> list[ModelInfo]: ...
    def generate(self, credential: str, request: GenerationRequest) -> GenerationResult: ...
