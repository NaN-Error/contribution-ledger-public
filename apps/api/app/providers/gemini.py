from urllib.parse import urlencode, quote
from app.providers.contracts import ModelInfo, GenerationResult, ProviderError, model_id, number, text, safe_id
from app.providers.transport import JsonTransport

class GeminiProvider:
    def __init__(self,transport=None):self.transport=transport or JsonTransport()
    def headers(self,key):return {'x-goog-api-key':key} # never put credentials in a URL
    def list_models(self,credential):
        out=[];cursor=None;seen=set()
        for _ in range(20):
            path='/v1beta/models?'+urlencode({'pageSize':100,**({'pageToken':cursor} if cursor else {})})
            body=self.transport.request('gemini','GET',path,self.headers(credential));rows=body.get('models')
            if not isinstance(rows,list) or len(rows)>100:raise ProviderError('malformed')
            for r in rows:
                if not isinstance(r,dict):raise ProviderError('malformed')
                name=r.get('name','')
                if not isinstance(name,str) or not name.startswith('models/'):raise ProviderError('malformed')
                ident=model_id(name[7:]);methods=r.get('supportedGenerationMethods')
                if methods is not None and not isinstance(methods,list):raise ProviderError('malformed')
                # generateContent alone is not proof of text+schema output. Probe required.
                capable=None if methods is None or 'generateContent' in methods else False
                out.append(ModelInfo(ident,text(r.get('displayName')) or ident,number(r.get('inputTokenLimit')),
                    number(r.get('outputTokenLimit')),capable,None,
                    {'methods':[text(x,60) for x in (methods or [])][:20],'thinking':r.get('thinking') if type(r.get('thinking')) is bool else None}))
            cursor=body.get('nextPageToken')
            if not cursor:return out
            if not isinstance(cursor,str) or len(cursor)>2048 or cursor in seen:raise ProviderError('catalog_incomplete')
            seen.add(cursor)
        raise ProviderError('catalog_incomplete')
    def generate(self,credential,request):
        r=self.transport.request('gemini','POST','/v1beta/models/'+quote(request.model,safe='')+':generateContent',self.headers(credential),
            {**({'systemInstruction':{'parts':[{'text':request.instructions}]}} if request.instructions else {}),'contents':[{'role':'user','parts':[{'text':request.prompt}]}],
             'generationConfig':{'candidateCount':1,'maxOutputTokens':request.max_output_tokens,
                'responseMimeType':'application/json','responseJsonSchema':request.schema}})
        try:
            candidates=r.get('candidates') or [];candidate=candidates[0] if candidates else {}
            parts=(candidate.get('content') or {}).get('parts') or []
            content=''.join(p['text'] for p in parts if isinstance(p.get('text'),str) and not p.get('thought'))
            reason=candidate.get('finishReason');blocked=(r.get('promptFeedback') or {}).get('blockReason')
            finish='refused' if blocked or reason in {'SAFETY','BLOCKLIST','PROHIBITED_CONTENT','RECITATION','SPII'} else 'truncated' if reason=='MAX_TOKENS' else 'complete' if reason=='STOP' and len(candidates)==1 else 'unexpected'
            u=r.get('usageMetadata') or {};out=number(u.get('candidatesTokenCount'));thoughts=number(u.get('thoughtsTokenCount',0))
            return GenerationResult(content,safe_id(r.get('modelVersion')),safe_id(r.get('responseId')),finish,
                number(u.get('promptTokenCount')),out+thoughts if out is not None and thoughts is not None else None,
                not u.get('toolUsePromptTokenCount') and u.get('serviceTier') in {None,'STANDARD','SERVICE_TIER_UNSPECIFIED'})
        except (TypeError,AttributeError,KeyError):raise ProviderError('malformed',ambiguous=True) from None
