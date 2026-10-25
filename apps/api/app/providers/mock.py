"""Deterministic synthetic provider: no networking and no evaluation of merit."""
import json
from app.providers.contracts import ModelInfo, GenerationResult
class MockProvider:
    def list_models(self,credential=''):
        return [ModelInfo('synthetic-json-v1','Synthetic JSON test model',65536,8192,True,True)]
    def generate(self,credential,request):
        if request.instructions:
            packet=json.loads(request.prompt)['untrusted_evidence_packet']
            value={'schema_version':'evidence-assessment-v1',
                'summary':'Synthetic demonstration only. This provider does not judge evidence or determine whether work meets requirements.',
                'findings':[{'criterion_id':c['id'],'status':'insufficient',
                    'explanation':'This synthetic provider intentionally makes no evidence-quality judgment. An independent person must inspect the originals.',
                    'evidence_refs':[]} for c in packet['criteria']],
                'proposed_roles':[],'overlap_flags':[],
                'questions':['Which original artifacts independently demonstrate that each acceptance criterion was satisfied?']}
            text=json.dumps(value,separators=(',',':'))
            return GenerationResult(text,request.model,'synthetic-assessment','complete',len(request.prompt.encode()),len(text.encode()))
        return GenerationResult('{"ok":true}',request.model,'synthetic-response','complete',24,5)
