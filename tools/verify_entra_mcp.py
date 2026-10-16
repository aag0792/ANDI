import os,sys,types,time,json,asyncio
from pathlib import Path
from unittest.mock import patch
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
os.environ.update(SQL_DATABASE='test',SQL_USER='test',SQL_PASSWORD='test',ENTRA_TENANT_ID='2ad11a58-8b17-4771-afba-bca9807e7fd9',ENTRA_CLIENT_ID='199e0ed4-b5f5-4923-9582-7a87fca82c47',GATEWAY_AUTH_MODE='entra')
import config,auth_entra,jwt
from cryptography.hazmat.primitives.asymmetric import rsa
key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
validator=auth_entra.EntraAuth(None)
validator.keys.get_signing_key_from_jwt=lambda t:types.SimpleNamespace(key=key.public_key())
now=int(time.time())
claims=dict(ver='2.0',iss=f'https://login.microsoftonline.com/{config.ENTRA_TENANT_ID}/v2.0',aud=config.ENTRA_CLIENT_ID,tid=config.ENTRA_TENANT_ID,sub='test-user',iat=now,nbf=now,exp=now+300,scp='andi.access',azp=config.ENTRA_CLIENT_ID)
def token(c):return jwt.encode(c,key,algorithm='RS256',headers={'kid':'test'})
assert validator.validate(token(claims))['sub']=='test-user'
for name,changes in [('aud',{'aud':'otro'}),('issuer',{'iss':'otro'}),('tenant',{'tid':'otro'}),('vencido',{'exp':now-300}),('scope',{'scp':'otro'})]:
 try:validator.validate(token(claims|changes));raise AssertionError(name)
 except (jwt.PyJWTError,PermissionError):pass
other=rsa.generate_private_key(public_exponent=65537,key_size=2048)
try:validator.validate(jwt.encode(claims,other,algorithm='RS256'));raise AssertionError('firma')
except jwt.InvalidSignatureError:pass
v1=claims|dict(ver='1.0',iss=f'https://sts.windows.net/{config.ENTRA_TENANT_ID}/',aud=config.ENTRA_AUDIENCE_V1,appid=config.ENTRA_CLIENT_ID)
assert validator.validate(token(v1))['ver']=='1.0'
config.ENTRA_ALLOWED_USERS={'otro'}
try:validator.validate(token(claims));raise AssertionError('allowlist')
except PermissionError:pass
config.ENTRA_ALLOWED_USERS=set()
# Solo se sustituyen dependencias empresariales ausentes; MCP y Starlette son reales.
db=types.ModuleType('db');db.audit=lambda *a:None;db.call_procedure=lambda *a: (_ for _ in ()).throw(AssertionError('No consultar SQL'))
sys.modules['db']=db
agent=types.ModuleType('andi_agent')
for n in ['build_client_selection_message','build_email_for_quote','build_project_schedule','estimate_project','generate_pdf_proposal','generate_quote','list_quote_history','parse_user_request','save_quote_history','summarize_meeting']:setattr(agent,n,lambda *a,**k:{})
sys.modules['andi_agent']=agent
import main
from starlette.testclient import TestClient
with patch.object(auth_entra.PyJWKClient,'get_signing_key_from_jwt',lambda self,t:types.SimpleNamespace(key=key.public_key())):
 with TestClient(main.app, base_url="https://andi.and.cr") as client:
  assert client.get('/health').status_code==200
  assert client.get('/.well-known/oauth-protected-resource').status_code==200
  assert client.post('/mcp',json={}).status_code==401
  headers={'Authorization':'Bearer '+token(claims),'Accept':'application/json, text/event-stream'}
  r=client.post('/mcp',headers=headers,json={'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'test','version':'1'}}})
  assert r.status_code==200,(r.status_code,r.text)
  assert 'serverInfo' in r.json()['result']
  r=client.post('/mcp',headers=headers,json={'jsonrpc':'2.0','id':2,'method':'tools/list','params':{}})
  assert r.status_code==200,r.text
  tools=r.json()['result']['tools'];assert any(t['name']=='buscar_cliente' for t in tools)
  expected = {'listar_clientes', 'listar_facturas', 'listar_pedidos', 'factura_lineas', 'pedido_lineas'}
  assert expected.issubset({t['name'] for t in tools})
  from jsonschema import Draft202012Validator
  for tool in tools:
   Draft202012Validator.check_schema(tool['inputSchema'])
  # Parámetros inválidos prueban validación sin ejecutar procedimientos SQL.
  for name,args in [('listar_clientes', {'pagina':0}), ('listar_facturas', {'desde':'fecha-invalida'}),
                    ('listar_pedidos', {'tamano':201}), ('factura_lineas', {'tipo_documento':'', 'factura':''}),
                    ('pedido_lineas', {'pedido':''})]:
   result=client.post('/mcp',headers=headers,json={'jsonrpc':'2.0','id':3,'method':'tools/call',
                     'params':{'name':name,'arguments':args}})
   assert result.status_code==200,result.text
   payload=result.json()['result']
   assert not payload.get('isError'),result.text
   data=payload.get('structuredContent') or json.loads(payload['content'][0]['text'])
   assert 'error' in data,result.text
  assert client.get('/assets/config.py',headers=headers).status_code==404
  assert client.get('/assets/.env',headers=headers).status_code==404
print('OK: firma, issuer, audience, tenant, expiración, scope, allowlist, tokens v1/v2, 401 sin token, initialize y tools/list en /mcp, assets protegidos. SQL no consultado. Herramientas principales:',len(tools))
