"""Provider contracts with injected transport only; no network or paid requests."""
import json
import pytest
from app.providers.contracts import *
from app.providers.openai import OpenAIProvider
from app.providers.anthropic import AnthropicProvider
from app.providers.gemini import GeminiProvider
from app.providers.mock import MockProvider
from app.providers.transport import JsonTransport

class Transport:
    def __init__(self,*responses): self.responses=list(responses);self.calls=[]
    def request(self,*args):
        self.calls.append(args);result=self.responses.pop(0)
        if isinstance(result,Exception):raise result
        return result

def request():return GenerationRequest('synthetic-model',PROBE_PROMPT,PROBE_SCHEMA,256)

def test_openai_discovery_does_not_infer_modality_or_price():
    t=Transport({'data':[{'id':'synthetic-model','owned_by':'fixture'}]})
    m=OpenAIProvider(t).list_models('synthetic-key')[0]
    assert m.text_generation is None and m.structured_output is None and m.input_limit is None
    assert 'price' not in m.document();assert t.calls[0][1:3]==('GET','/v1/models')

def test_openai_json_request_and_reasoning_discarded():
    t=Transport({'id':'resp_fixture','model':'resolved-version','status':'completed','output':[
        {'type':'reasoning','text':'private fixture'}, {'type':'message','content':[{'type':'output_text','text':'{"ok":true}'}]}],
        'usage':{'input_tokens':22,'output_tokens':15},'service_tier':'default'})
    result=OpenAIProvider(t).generate('synthetic-key',request());payload=t.calls[0][4]
    assert result.probe_passed();assert result.output_tokens==15;assert 'private' not in result.content
    assert payload['store'] is False and payload['text']['format']['strict'] is True
    assert payload['max_output_tokens']==256 and 'tools' not in payload

@pytest.mark.parametrize('status,details,content,expected',[
 ('incomplete',{'reason':'max_output_tokens'},[],'truncated'),
 ('completed',None,[{'type':'refusal','refusal':'fixture'}],'refused'),
 ('incomplete',{'reason':'content_filter'},[],'refused'),
 ('failed',None,[],'unexpected')])
def test_openai_finishes(status,details,content,expected):
    t=Transport({'status':status,'incomplete_details':details,'output':[{'type':'message','content':content}]})
    assert OpenAIProvider(t).generate('synthetic-key',request()).finish==expected

def test_anthropic_pages_capabilities_and_headers():
    t=Transport({'data':[{'id':'first','capabilities':{'structured_outputs':{'supported':False}},'max_input_tokens':5000}],
                 'has_more':True,'last_id':'first'}, {'data':[{'id':'second'}],'has_more':False})
    result=AnthropicProvider(t).list_models('synthetic-key')
    assert len(result)==2 and result[0].structured_output is False and result[1].structured_output is None
    assert 'after_id=first' in t.calls[1][2];assert t.calls[0][3]['anthropic-version']=='2023-06-01'

def test_anthropic_cache_reads_counted_at_conservative_full_rate():
    t=Transport({'model':'fixture','id':'msg_fixture','stop_reason':'end_turn','content':[
        {'type':'thinking','thinking':'private'},{'type':'text','text':'{"ok":true}'}],
        'usage':{'input_tokens':15,'cache_read_input_tokens':20,'output_tokens':12,'service_tier':'standard'}})
    result=AnthropicProvider(t).generate('synthetic-key',request())
    assert result.probe_passed() and result.input_tokens==35 and result.usage_supported
    assert t.calls[0][4]['output_config']['format']['type']=='json_schema'
    assert t.calls[0][4]['service_tier']=='standard_only'

@pytest.mark.parametrize('usage',[{'cache_creation_input_tokens':3},{'server_tool_use':{'web_search_requests':1}},{'service_tier':'priority'}])
def test_anthropic_unpriced_usage_stays_unknown(usage):
    t=Transport({'stop_reason':'end_turn','content':[{'type':'text','text':'{"ok":true}'}],
        'usage':{'input_tokens':10,'output_tokens':3,**usage}})
    assert not AnthropicProvider(t).generate('synthetic-key',request()).usage_supported

@pytest.mark.parametrize('stop,expected',[('refusal','refused'),('max_tokens','truncated'),('tool_use','unexpected')])
def test_anthropic_stop_reasons(stop,expected):
    assert AnthropicProvider(Transport({'stop_reason':stop})).generate('synthetic-key',request()).finish==expected

def test_gemini_pages_and_known_incompatibility():
    t=Transport({'models':[{'name':'models/embedding','supportedGenerationMethods':['embedContent']}],'nextPageToken':'next'},
        {'models':[{'name':'models/generative','supportedGenerationMethods':['generateContent'],'inputTokenLimit':2048,'outputTokenLimit':512}]})
    m=GeminiProvider(t).list_models('synthetic-key')
    assert m[0].text_generation is False and m[1].text_generation is None
    assert m[1].input_limit==2048 and 'pageToken=next' in t.calls[1][2]
    assert all('synthetic-key' not in call[2] for call in t.calls)

def test_gemini_includes_thinking_in_usage_but_not_text():
    t=Transport({'modelVersion':'fixture-version','responseId':'fixture-id','candidates':[{'finishReason':'STOP','content':{'parts':[
        {'thought':True,'text':'private fixture'},{'text':'{"ok":true}'}]}}],
        'usageMetadata':{'promptTokenCount':20,'candidatesTokenCount':5,'thoughtsTokenCount':19}})
    result=GeminiProvider(t).generate('synthetic-key',request())
    assert result.probe_passed() and result.output_tokens==24 and result.input_tokens==20
    assert t.calls[0][3]['x-goog-api-key']=='synthetic-key'
    assert t.calls[0][4]['generationConfig']['responseJsonSchema']==PROBE_SCHEMA

@pytest.mark.parametrize('reason,expected',[('SAFETY','refused'),('MAX_TOKENS','truncated'),('OTHER','unexpected')])
def test_gemini_finish(reason,expected):
    result=GeminiProvider(Transport({'candidates':[{'finishReason':reason}]})).generate('synthetic-key',request())
    assert result.finish==expected and not result.probe_passed()

@pytest.mark.parametrize('cls,body',[(OpenAIProvider,{'data':[],'has_more':True}),
 (AnthropicProvider,{'data':[],'has_more':True,'last_id':None}),
 (GeminiProvider,{'models':[{'name':'https://invalid'}]})])
def test_incomplete_catalog_is_not_a_success(cls,body):
    with pytest.raises(ProviderError):cls(Transport(body)).list_models('synthetic-key')

@pytest.mark.parametrize('value',['{"ok":false}','{"ok":1}','{"ok":true,"extra":1}','{"ok":true,"ok":true}',
 'NaN','```json\n{"ok":true}\n```','[true]','not json'])
def test_synthetic_result_is_exact(value):
    assert not GenerationResult(value,'model',None,'complete',1,1).probe_passed()

@pytest.mark.parametrize('value',['../escape','https://evil.test/x','x?api_key=fixture','x\nheader','',None])
def test_model_identifiers_are_bounded(value):
    with pytest.raises(ProviderError):model_id(value)

def test_mock_provider_has_no_transport():
    p=MockProvider();assert p.list_models('')[0].structured_output is True
    assert p.generate('',request()).probe_passed()

class Response:
    def __init__(self,status=200,raw=b'{"data":[]}',headers=None):
        self.status=status;self.raw=raw;self.headers={'Content-Type':'application/json',**(headers or {})}
    def getheader(self,k,default=None):return self.headers.get(k,default)
    def read(self,size):chunk=self.raw[:size];self.raw=self.raw[size:];return chunk
class Connection:
    def __init__(self,response,fail=None):self.response=response;self.calls=[];self.fail=fail;self.closed=False
    def connect(self):
        if self.fail=='connect':raise TimeoutError('secret should never escape')
    def request(self,*args,**kw):
        self.calls.append((args,kw))
        if self.fail=='send':raise TimeoutError('secret should never escape')
    def getresponse(self):return self.response
    def close(self):self.closed=True

def tx(response=None,fail=None):
    c=Connection(response or Response(),fail);hosts=[]
    def factory(host,**kwargs):hosts.append(host);return c
    return JsonTransport(factory),c,hosts

@pytest.mark.parametrize('status,code,ambiguous',[(400,'incompatible',False),(401,'authentication',False),(403,'permission',False),
 (404,'model_unavailable',False),(429,'rate_limited',False),(500,'provider_failure',True),(302,'provider_failure',True)])
def test_transport_error_classification_and_no_error_body(status,code,ambiguous):
    r=Response(status,b'private raw message');t,c,hosts=tx(r)
    with pytest.raises(ProviderError) as e:t.request('openai','POST','/v1/responses',{}, {})
    assert e.value.code==code and e.value.ambiguous==ambiguous and r.raw==b'private raw message'
    assert c.closed and len(c.calls)==1 and hosts==['api.openai.com']

@pytest.mark.parametrize('fail,method,ambiguous',[('connect','POST',False),('send','POST',True),('send','GET',False)])
def test_no_automatic_transport_retry(fail,method,ambiguous):
    t,c,_=tx(fail=fail)
    with pytest.raises(ProviderError) as e:t.request('openai',method,'/v1/models',{})
    assert e.value.ambiguous==ambiguous and 'secret' not in str(e.value) and len(c.calls)<=1

@pytest.mark.parametrize('path',['//evil.test/','https://evil.test/','/x#fragment','/x\\evil','/x\nheader'])
def test_transport_cannot_change_host(path):
    t,c,hosts=tx()
    with pytest.raises(ProviderError):t.request('openai','GET',path,{})
    assert not hosts

@pytest.mark.parametrize('raw,headers',[(b'NaN',{}),(b'{"x":1,"x":2}',{}),(b'[]',{}),
 (b'{}',{'Content-Type':'text/html'}),(b'{}',{'Content-Length':str(5*1024*1024)}),(b'{}',{'Content-Encoding':'gzip'})])
def test_transport_rejects_bad_json_without_refunding_ambiguous_generation(raw,headers):
    t,_,_=tx(Response(raw=raw,headers=headers))
    with pytest.raises(ProviderError) as e:t.request('openai','POST','/v1/responses',{})
    assert e.value.ambiguous
