"""Executor 4B gerenciado pelo PC. Sem banco/identidade/ferramentas no Xbox.

WDP autenticado e TLS fixado para controle/arquivos; inferência HTTP somente
em LAN de confiança explicitamente aceita. Sem downloads ou instalação de apps.
O recibo de intenção no PC impede replay após timeout, inclusive após reboot.
"""
from __future__ import annotations
import base64
import contextlib
import copy
import fcntl
import hashlib
import http.cookiejar
import io
import json
import math
import os
from pathlib import Path
import re
import ssl
import subprocess
import tempfile
import threading
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, ProxyHandler, HTTPSHandler, HTTPCookieProcessor, HTTPRedirectHandler
import uuid

from core import alistair_execution
from core.alistair_backend import RemotePending, RemoteUnavailable

PFN = 'Atominen.Xllama4BGPU_1.6.0.7_x64__pj67f1fcj4n14'
AUMID = 'Atominen.Xllama4BGPU_pj67f1fcj4n14!xllama'
MODEL = 'alistair-qwen35-4b-trained'
ROOT_PIN = 'c95d67b5fee5a7920044855bc6d324134c2b99948bcca660ddb1c6b1288c72a3'
BASE_SHA = 'c4e293fb72d47b5d6dc0ddc8b08a4c367eadfd0ddf1e2151cb39b792268a2308'
BASE_SIZE = 2708804000
CTX = 8192
CONTEXT_MIN = 2048
CONTEXT_STEP = 256
LOCAL = '\\LocalState'
MODEL_DIR = LOCAL+'\\models\\'+MODEL
CONTROLS = {'manifest.json', 'api.flag', 'api-port.txt', 'gguf_gpu_layers.txt', 'gguf_lora_host.flag', 'resource-probe.flag'}
SECRETS = 'alistair_xbox_secret.json'
LIMIT = 8*1024**2


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def read_json(path, default=None):
    if path.is_symlink():
        raise ValueError('Arquivo técnico por link recusado.')
    if not path.exists():
        return {} if default is None else default
    if path.stat().st_size > LIMIT:
        raise ValueError('Arquivo técnico excessivo.')
    return json.loads(path.read_bytes())


def write_json(path, value):
    """Recibo atômico privado; sem prompt, resposta ou segredo no recibo técnico."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError('Destino técnico por link recusado.')
    fd, name = tempfile.mkstemp(prefix='.xbox-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as output:
            os.fchmod(output.fileno(), 0o600)
            output.write(encode(value)); output.flush(); os.fsync(output.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        Path(name).unlink(missing_ok=True)


def state_path(root):
    return Path(root)/'compartilhado/runtime/alistair-execution/xbox.json'


def secret_path(root):
    return Path(root)/'compartilhado/config'/SECRETS


def secrets(root):
    p = secret_path(root)
    if not p.is_file() or p.is_symlink() or p.stat().st_mode & 0o077:
        raise ValueError('Configure o acesso remoto do Xbox na Central (arquivo privado 600).')
    value = read_json(p)
    if (set(value) != {'username', 'password'} or not all(isinstance(v, str) and v for v in value.values())
            or ':' in value['username'] or any(c in value['username']+value['password'] for c in '\r\n\0')):
        raise ValueError('Acesso remoto inválido.')
    return value


def credential_value(username, password):
    if (not isinstance(username, str) or not isinstance(password, str) or not username or not password
            or len(username)>200 or len(password)>512 or ':' in username
            or any(c in username+password for c in '\r\n\0')):
        raise ValueError('Preencha usuário e senha do acesso remoto do Xbox, não da conta Microsoft.')
    return dict(username=username,password=password)


def save_secret(root, username, password):
    write_json(secret_path(root),credential_value(username,password))


def known_root_pem():
    """Reutiliza só o certificado público já fixado, sem confiar em raiz nova."""
    p=Path.home()/'Downloads/rootcertificate.cer'
    if p.is_symlink() or not p.is_file() or p.stat().st_size>16384:return None
    raw=p.read_bytes()
    try:
        pem=raw.decode('ascii') if b'BEGIN CERTIFICATE'in raw else ssl.DER_cert_to_PEM_cert(raw)
        return pem if hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).hexdigest()==ROOT_PIN else None
    except (ValueError,UnicodeError):return None


def local_bundle(root):
    """Somente os blobs textuais da versão pinada; projector/identidade não saem."""
    from core import neural9b_modes
    from laboratorio.recuperacao_modelos import manifest_path
    root = Path(root)
    alias = neural9b_modes.startup_override(root, 'alistair')
    if not alias:
        env = root/'entidades/alistair/config/alistair.env'
        text = env.read_text() if env.is_file() else ''
        found = re.findall(r'^\s*(?:export\s+)?HOSHINO_MODEL=["\']?([^"\'\s]+)', text, re.M)
        alias = found[-1] if found else 'alistair-qwen3.5-4b:latest'
    store = root/'compartilhado/modelos/ollama-alistair'
    manifest = manifest_path(store, alias)
    data = read_json(manifest)
    layers = data.get('layers', [])
    selected = [r for r in layers if r.get('mediaType') in {'application/vnd.ollama.image.model', 'application/vnd.ollama.image.adapter'}]
    if sum(r.get('mediaType').endswith('.model') for r in selected)!=1 or len(selected)>2:
        raise ValueError('Versão 4B não tem um par textual compatível.')
    files = []
    for row in selected:
        digest = row.get('digest', '')
        if not re.fullmatch(r'sha256:[a-f0-9]{64}', digest) or type(row.get('size')) is not int:
            raise ValueError('Digest/tamanho do modelo inválido.')
        adapter = row['mediaType'].endswith('.adapter')
        if (not adapter and (digest[7:]!=BASE_SHA or row['size']!=BASE_SIZE)) or (adapter and not 0<row['size']<=128*1024**2):
            raise ValueError('Pesos fora do perfil 4B medido; não converter nem instalar automaticamente.')
        source = store/'blobs'/digest.replace(':', '-')
        if source.is_symlink() or not source.is_file() or source.stat().st_size!=row['size']:
            raise ValueError('Blob selecionado ausente/divergente no PC.')
        files.append(dict(name='adapter.gguf' if adapter else 'model.gguf', source=str(source), sha256=digest[7:], size=row['size']))
    # Nome por conteúdo impede sobrescrever pesos já usados por outra versão.
    fingerprint = hashlib.sha256(encode([{k:f[k] for k in ('name','sha256','size')} for f in files])).hexdigest()
    return dict(alias=alias, manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(), files=files, fingerprint=fingerprint)


def model_limits(root):
    """Mesma fonte da aba Modelos; só literais, nunca source/eval do .env."""
    path=Path(root)/'entidades/alistair/config/alistair.env'
    if path.is_symlink() or (path.exists() and path.stat().st_size>1024**2):
        raise ValueError('Configuração de modelo inválida.')
    values={}
    for line in path.read_text().splitlines() if path.exists() else []:
        match=re.match(r'^\s*(?:export\s+)?(HOSHINO_CONTEXT_TOKENS|HOSHINO_NUM_CTX|HOSHINO_NUM_PREDICT)\s*=\s*(.*?)\s*$',line)
        if match:values[match[1]]=match[2].strip('"\'')
    context=values.get('HOSHINO_CONTEXT_TOKENS',values.get('HOSHINO_NUM_CTX',str(CTX)))
    output=values.get('HOSHINO_NUM_PREDICT','768')
    if not all(re.fullmatch(r'[0-9]+',v) for v in (context,output)):
        raise ValueError('Contexto/saída devem ser inteiros literais.')
    return validate_limits(int(context),int(output))


def validate_limits(context,output):
    if type(context)is not int or not CONTEXT_MIN<=context<=CTX or context%CONTEXT_STEP:
        raise ValueError(f'Xbox: contexto entre {CONTEXT_MIN} e {CTX}, em passos de {CONTEXT_STEP} tokens.')
    if type(output)is not int or not 128<=output<=context-512:
        raise ValueError('Xbox: saída mínima de128 tokens e reserva mínima de512 tokens para entrada.')
    return dict(context=context,output=output)


def controls(bundle, model=MODEL, *, context=CTX):
    validate_limits(context,128)
    entry = dict(name=model, display='Alistair 4B · executor da Central', kind='gguf', n_ctx=context,
                 gpu_layers=33, files=[dict(filename=f['name'], sha256=f['sha256'], approx_bytes=f['size']) for f in bundle['files']])
    adapter=next((f for f in bundle['files']if f['name']!='model.gguf'),None)
    if adapter:entry.update(lora=adapter['name'], lora_scale=1.0)
    return {'manifest.json':encode({'models':[entry]}), 'api.flag':b'enabled', 'api-port.txt':b'11434',
            'gguf_gpu_layers.txt':b'33\n', 'gguf_lora_host.flag':b'1\n'if adapter else b'0\n', 'resource-probe.flag':b'0\n'}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('Redirecionamento do executor recusado.')


def tls_context(ip, root_file):
    """Só material público antes da autenticação; folha assinada pela raiz fixada."""
    root_pem = Path(root_file).read_bytes()
    if hashlib.sha256(ssl.PEM_cert_to_DER_cert(root_pem.decode('ascii'))).hexdigest()!=ROOT_PIN:
        raise ValueError('Raiz do Xbox mudou. Repareamento explícito necessário.')
    public = subprocess.run(['openssl','s_client','-connect',f'{ip}:11443','-CAfile',str(root_file),
                             '-verify_return_error','-verify_ip',ip,'-showcerts'],input=b'',capture_output=True,timeout=10,check=False)
    certificates = re.findall(rb'-----BEGIN CERTIFICATE-----[\s\S]+?-----END CERTIFICATE-----', public.stdout[:65536])
    if not certificates:
        raise ValueError('Xbox sem certificado verificável; nenhuma senha enviada.')
    pem = certificates[0]
    # Node crypto é o verificador público já usado no ensaio. Evita instalar
    # bibliotecas no Python principal e não recebe credenciais/identidades.
    verify=r'''
const {X509Certificate}=require('node:crypto');
const fs=require('node:fs');const d=JSON.parse(fs.readFileSync(0,'utf8'));
const root=new X509Certificate(d.root),leaf=new X509Certificate(d.leaf),now=Date.now();
const checks=[root.ca===true,leaf.ca===false,root.verify(root.publicKey),leaf.verify(root.publicKey),
  root.subject===leaf.issuer,leaf.checkIP(d.ip)===d.ip,
  Date.parse(root.validFrom)<=now,now<Date.parse(root.validTo),
  Date.parse(leaf.validFrom)<=now,now<Date.parse(leaf.validTo)];
process.stdout.write(JSON.stringify(checks));process.exitCode=checks.every(v=>v===true)?0:2;
'''
    checked=subprocess.run(['node','-e',verify],input=encode(dict(root=root_pem.decode('ascii'),leaf=pem.decode('ascii'),ip=ip)),capture_output=True,timeout=5,check=False)
    if checked.returncode!=0 or len(checked.stdout)>4096 or json.loads(checked.stdout)!=[True]*10:
        raise ValueError('Assinatura/IP/validade do certificado não aprovados. Nenhuma senha enviada.')
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.load_verify_locations(cadata=pem.decode('ascii'))
    context.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN
    return context, hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem.decode('ascii'))).hexdigest()


def file_route(kind='file', directory=LOCAL, name=None):
    if kind not in {'file','files','folder'} or not (directory==LOCAL or re.fullmatch(r'\\LocalState\\models(?:\\alistair-[a-z0-9-]+)?',directory)):
        raise ValueError('Diretório fora do executor 4B.')
    query = dict(knownfolderid='LocalAppData',packagefullname=PFN,path=directory)
    if name is not None:
        allowed = CONTROLS|{'xllama.log'} if directory==LOCAL else {'model.gguf','adapter.gguf'}
        if name not in allowed and not(directory==MODEL_DIR and re.fullmatch(r'adapter-[a-f0-9]{64}\.gguf',name)):
            raise ValueError('Arquivo fora da lista técnica.')
        query['filename']=name
    return '/api/filesystem/apps/'+kind+'?'+urlencode(query)


def items(value):
    if not isinstance(value,dict) or value.get('Success') is False or not isinstance(value.get('Items'),list):
        raise ValueError('Listagem do Xbox não confirmada.')
    rows=value['Items']
    if any(not isinstance(r,dict) or not isinstance(r.get('Name'),str) for r in rows):
        raise ValueError('Listagem incompleta.')
    return {r['Name']:r for r in rows}


class Portal:
    def __init__(self, root, settings):
        self.ip=settings['xbox_ip']; self.base='https://'+self.ip+':11443'
        context,self.leaf=tls_context(self.ip,Path(root)/'compartilhado/config/xbox-root.pem')
        secret=secrets(root)
        self.auth='Basic '+base64.b64encode((secret['username']+':'+secret['password']).encode()).decode()
        self.cookies=http.cookiejar.CookieJar()
        self.opener=build_opener(ProxyHandler({}),NoRedirect(),HTTPCookieProcessor(self.cookies),HTTPSHandler(context=context))
        self.csrf=None

    def open(self, method, target, data=None, headers=None, timeout=15):
        return self.opener.open(Request(self.base+target,method=method,data=data,
            headers={'Authorization':self.auth,**(headers or {})}),timeout=timeout)

    def get_bytes(self, target, limit=LIMIT):
        with self.open('GET',target) as response:
            raw=response.read(limit+1)
            if response.status!=200 or len(raw)>limit:raise ValueError('Leitura técnica incompleta/excessiva.')
            return raw

    def get(self,target):return json.loads(self.get_bytes(target))

    def read(self,name,directory=LOCAL):
        try:return self.get_bytes(file_route(directory=directory,name=name))
        except HTTPError as exc:
            if exc.code==404:return None
            raise

    def inventory(self, *, stopping=False):
        packages=self.get('/api/app/packagemanager/packages').get('InstalledPackages')
        processes=self.get('/api/resourcemanager/processes').get('Processes')
        if not isinstance(packages,list) or not isinstance(processes,list):raise ValueError('Estado de processos desconhecido.')
        own=[p for p in packages if 'xllama' in str(p.get('PackageFullName','')).lower()]
        if len(own)!=1 or own[0].get('PackageFullName')!=PFN:raise ValueError('Pacote mudou/duplicado. Sem instalação automática.')
        scoped=[p for p in processes if 'xllama' in (str(p.get('PackageFullName',''))+str(p.get('ImageName',''))).lower()]
        # WDP inclui o RuntimeBroker do mesmo pacote: ele não é uma segunda
        # instância do executor e pode permanecer depois de xllama.exe fechar.
        # Só este auxiliar conhecido é aceito; imagem/pacote/PID desconhecidos
        # continuam bloqueando. A telemetria nativa confirma o PID xllama real.
        if any(p.get('PackageFullName')!=PFN or type(p.get('ProcessId'))is not int or p['ProcessId']<=0
               or type(p.get('IsRunning'))is not bool or p.get('ImageName','').lower()not in {'xllama.exe','runtimebroker.exe'} for p in scoped):
            raise ValueError('Executor concorrente ou processo incerto.')
        if len({p['ProcessId']for p in scoped})!=len(scoped):raise ValueError('Processos duplicados no inventário.')
        running=[p for p in scoped if p['ImageName'].lower()=='xllama.exe']
        if len(running)>1:raise ValueError('Executor concorrente ou processo incerto.')
        # DELETE pode tornar IsRunning=false antes de retirar a linha doPID.
        # Na espera de fechamento, ainda devolver oPID: só confirmar saída
        # quando a linha desaparecer, não apenas quando a flag mudar.
        if running and not running[0]['IsRunning'] and not stopping:
            raise ValueError('Executor em transição; aguarde fechamento confirmado.')
        return running[0]['ProcessId'] if running else None

    def csrf_token(self):
        if self.csrf:return
        with self.open('GET','/') as response:
            if len(response.read(524289))>524288:raise ValueError('Portal excessivo.')
        tokens=[c.value for c in self.cookies if c.name.lower()=='csrf-token' and c.domain in (self.ip,'.'+self.ip) and c.path=='/']
        if len(tokens)!=1 or not tokens[0] or any(c in tokens[0] for c in '\r\n'):raise ValueError('CSRF indisponível.')
        self.csrf=tokens[0]

    def mutate(self,method,target,data=None,headers=None):
        self.csrf_token()
        with self.open(method,target,data,{'X-CSRF-Token':self.csrf,**(headers or {})},timeout=60) as response:
            raw=response.read(65537)
            if response.status!=200 or len(raw)>65536:raise RemotePending('Aceite do Xbox incerto; não repetir.')
        result=json.loads(raw) if raw.strip() else {}
        if result.get('Success')is False or result.get('ErrorMessage') or result.get('Code',0)!=0:raise RemotePending('Operação do Xbox não confirmada.')

    def upload(self,name,source,size,sha,directory=LOCAL):
        # Chamador confirma parado e grava intenção antes. Streaming sem cópia2GB.
        file_route(directory=directory,name=name)  # Valida também o nome multipart.
        boundary='centralxbox'+uuid.uuid4().hex
        head=(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\nContent-Type: application/octet-stream\r\n\r\n').encode()
        tail=f'\r\n--{boundary}--\r\n'.encode()
        def body():
            yield head
            count=0; digest=hashlib.sha256();began=time.monotonic()
            stream=io.BytesIO(source) if isinstance(source,bytes) else Path(source).open('rb')
            with stream:
                while chunk:=stream.read(1024**2):
                    count+=len(chunk);digest.update(chunk)
                    if count>size or time.monotonic()-began>900:raise ValueError('Fonte/prazo mudou durante cópia.')
                    yield chunk
            if count!=size or digest.hexdigest()!=sha:raise ValueError('Fonte/hash mudou durante cópia.')
            yield tail
        # WDP: GET /apps/files lista; POST /apps/file recebe o upload.
        self.mutate('POST',file_route('file',directory)+'&extract=false',body(),{'Content-Type':'multipart/form-data; boundary='+boundary,'Content-Length':str(len(head)+size+len(tail))})

    def mkdir(self,parent,name):
        if (parent,name)not in ((LOCAL,'models'),(LOCAL+'\\models',MODEL)):raise ValueError('Pasta fora do executor4B.')
        target=file_route('folder',parent)+'&'+urlencode(dict(newfoldername=name))
        self.mutate('POST',target)

    def hash_file(self,name,size,directory):
        digest=hashlib.sha256();count=0;began=time.monotonic()
        with self.open('GET',file_route(directory=directory,name=name),timeout=60)as response:
            while chunk:=response.read1(1024**2):
                count+=len(chunk);digest.update(chunk)
                if count>size or time.monotonic()-began>900:raise ValueError('Hash físico excedeu o limite.')
        if count!=size:raise ValueError('Peso incompleto no Xbox.')
        return digest.hexdigest()

    def close(self):self.auth=None;self.cookies.clear();self.csrf=None


def log_current(portal):
    raw=portal.read('xllama.log')
    if raw is None:raise ValueError('Log físico indisponível.')
    return raw.decode('utf8',errors='replace').rsplit('App::OnLaunched',1)[-1]


def idle(log):
    if len(re.findall(r'\bprefill starting:',log))!=len(re.findall(r'\bsession generate:',log)):
        raise RemotePending('Inferência anterior sem término confirmado; não reiniciar.')


def confirm_profile(log,host_on,context=None,*,allow_lazy_context=False):
    if 'offloaded 33/33 layers to GPU'not in log:raise ValueError('33camadasGPU não confirmadas.')
    context_verified=False
    if context is not None:
        # Base fixada porSHA:8camadas full-attention,4cabeçasKV,256+256,F16.
        # Passos de256 também respeitam o padding do cache; nunca extrapolar8K.
        validate_limits(context,128)
        kv=re.search(r'CPU KV buffer size\s*=\s*([0-9.]+) MiB',log)
        # Session carrega os pesos antes de criar o KV, que nasce no primeiro
        # generate(). Aceitar apenas esse estado sem gerações na preparação;
        # a resposta/ferramenta nunca sai doPC sem verificar o KV depois.
        lazy=(not kv and allow_lazy_context and not re.search(r'\bprefill starting:|\bsession generate:',log))
        if not lazy and (not kv or float(kv[1])!=context/32):
            raise ValueError('CacheKV físico não corresponde ao contexto salvo. Resposta não liberada.')
        context_verified=not lazy
    if not host_on:
        if 'LoRA host placement: OFF (baseline)'not in log:raise ValueError('Perfil Original não confirmado.')
        return context_verified
    if ('LoRA host placement: opt-in ON'not in log or
            not re.search(r'D3D12 LoRA host placement: [1-9][0-9]* F16 pairs, unchanged values',log) or
            not re.search(r'CPU(?:_[A-Za-z]+)? LoRA buffer size\s*=\s*[0-9.]+ MiB',log) or
            'D3D12_Weights LoRA buffer size'in log):
        raise ValueError('Alocação física otimizada doLoRA não confirmada.')
    return context_verified


def resource_guard(raw,pid,diagnostic=False):
    if (not isinstance(raw,dict) or raw.get('schema_version')!=1 or raw.get('service')!='xllama-resource-probe'
            or raw.get('package_full_name')!=PFN or type(raw.get('process_id'))is not int or raw['process_id']!=pid
            or raw.get('diagnostics_only')is not diagnostic or raw.get('snapshot_not_atomic')is not True
            or raw.get('ram_gpu_pools_may_overlap')is not True):raise ValueError('PID/pacote/modo do Xbox divergiu.')
    def counter(value):
        if not isinstance(value,str) or not re.fullmatch(r'0|[1-9][0-9]{0,19}',value) or int(value)>=2**64:raise ValueError('Contador nativo inválido.')
        return int(value)
    sequence=counter(raw.get('sequence'));tick=counter(raw.get('monotonic_ms'))
    if not sequence:raise ValueError('Telemetria sem sequência.')
    app=raw.get('app_memory',{});gpu=raw.get('gpu_memory',{})
    if (app.get('supported')is not True or app.get('source')!='Windows.System.MemoryManager'
            or gpu.get('enumeration_complete')is not True or gpu.get('source')!='IDXGIAdapter3.QueryVideoMemoryInfo'):raise ValueError('Orçamento nativo desconhecido.')
    limit=counter(app.get('limit_bytes'));headroom=counter(app.get('headroom_bytes'));usage=counter(app.get('usage_bytes'))
    if headroom!=max(0,limit-usage):raise ValueError('Memória do app inconsistente.')
    adapters=gpu.get('adapters',[])
    if limit<5*1024**3 or headroom<512*1024**2 or not isinstance(adapters,list) or len(adapters)!=1:raise ValueError('Xbox não está em Game ou margem RAM insuficiente.')
    for adapter in adapters:
        local=adapter.get('local',{})
        budget=counter(local.get('budget_bytes'));used=counter(local.get('usage_bytes'));free=counter(local.get('headroom_bytes'))
        if free!=max(0,budget-used) or adapter.get('supported')is not True or local.get('supported')is not True or free<768*1024**2:
            raise ValueError('Margem GPU do Xbox insuficiente/desconhecida.')
    if type(app.get('usage_level'))is not int or app['usage_level']not in (0,1):raise ValueError('Pressão de memória no Xbox.')
    return dict(pid=pid,app_limit_bytes=limit,app_headroom_bytes=headroom,
                gpu_headroom_bytes=min(int(a['local']['headroom_bytes'])for a in adapters),observed_at=time.time(),sequence=sequence,tick=tick)


def translate(payload, *, context_limit=CTX, output_limit=None):
    """Preserva autoria/ordem/recibos; ids nativos OpenAI no encadeamento de tools."""
    from pc2_protocol import request_id
    if not isinstance(payload,dict) or payload.get('stream',False)is not False or payload.get('think',False)is not False:
        raise ValueError('Xbox aceita somente texto sem streaming/thinking nesta integração.')
    if set(payload)-{'model','messages','tools','stream','think','keep_alive','options'}:raise ValueError('Pedido com campos não suportados.')
    opts=payload.get('options',{})
    if set(opts)-{'num_ctx','num_predict','num_gpu','num_thread','temperature'}:raise ValueError('Opções não suportadas no Xbox.')
    if output_limit is None:output_limit=context_limit-512
    validate_limits(context_limit,output_limit)
    output=opts.get('num_predict',min(768,output_limit));context=opts.get('num_ctx',context_limit);temperature=opts.get('temperature',.45)
    if (type(context)is not int or not 512<=context<=context_limit or type(output)is not int
            or not 1<=output<=output_limit or output>=context):
        raise ValueError('Contexto/saída excede configuração aplicada noXbox; sem redução silenciosa.')
    if type(temperature)not in (int,float) or not math.isfinite(temperature) or not 0<=temperature<=2:raise ValueError('Temperatura inválida.')
    incoming=payload.get('messages');tools=copy.deepcopy(payload.get('tools',[]))
    if not isinstance(incoming,list) or not incoming or len(incoming)>64 or not isinstance(tools,list) or len(tools)>16:raise ValueError('Transcrição/ferramentas inválidas.')
    messages=[];pending=[];used=set()
    for index,source in enumerate(incoming):
        if not isinstance(source,dict) or set(source)-{'role','content','tool_calls','tool_name','tool_call_id','thinking'}:raise ValueError('Somente transcrição textual.')
        role=source.get('role');content=source.get('content','')
        if role not in {'system','user','assistant','tool'} or not isinstance(content,str):raise ValueError('Papel/conteúdo inválido.')
        message={'role':role,'content':content}
        if source.get('thinking'):raise ValueError('Thinking não pode ser descartado silenciosamente.')
        if role=='tool':
            if not pending:raise ValueError('Recibo sem chamada precedente.')
            call=pending.pop(0)
            if source.get('tool_name')!=call['function']['name'] or (source.get('tool_call_id') and source['tool_call_id']!=call['id']):raise ValueError('Recibo não corresponde à chamada.')
            # OpenAI associa o recibo peloID; nome/argumentos permanecem na
            # chamada assistant validada acima. Repetir "name" no recibo aciona
            # falso negativo no detector de schemas do xllama/Qwen: o template
            # não imprime esse campo, mas o detector o conta na transcrição.
            message.update(tool_call_id=call['id'])
        elif pending:raise ValueError('Faltam recibos de ferramentas; sem descarte.')
        calls=source.get('tool_calls',[])
        if not isinstance(calls,list) or len(calls)>16:raise ValueError('Chamadas inválidas.')
        if calls:
            if role!='assistant':raise ValueError('Autoria da chamada inválida.')
            message['tool_calls']=[]
            for n,call in enumerate(calls):
                function=call.get('function',{})
                identifier=call.get('id') or f'central_{index}_{n}'
                request_id(identifier)
                if identifier in used:raise ValueError('IDs de ferramenta repetidos.')
                used.add(identifier)
                arguments=function.get('arguments',{})
                if isinstance(arguments,str):arguments=json.loads(arguments)
                if not isinstance(arguments,dict) or not isinstance(function.get('name'),str):raise ValueError('Argumentos de ferramenta inválidos.')
                result={'id':identifier,'type':'function','function':{'name':function['name'],'arguments':encode(arguments).decode()}}
                pending.append(result);message['tool_calls'].append(result)
        messages.append(message)
    if pending or messages[-1]['role'] not in {'user','tool'}:raise ValueError('Transcrição sem entrada/recibo final.')
    result=dict(model=MODEL,messages=messages,stream=False,max_completion_tokens=output,temperature=temperature,
                chat_template_kwargs=dict(enable_thinking=False))
    if tools:result['tools']=tools
    if any(m['role']=='tool' for m in messages) and not tools:raise ValueError('Recibos exigem schemas preservados.')
    if len(encode(result))>512*1024:raise ValueError('Contexto textual excessivo.')
    return result


def response_message(value,tools):
    if not isinstance(value,dict) or value.get('model')!=MODEL:raise ValueError('Resposta de outro modelo.')
    choices=value.get('choices')
    if not isinstance(choices,list) or len(choices)!=1:raise ValueError('Resposta incompleta.')
    choice=choices[0];message=choice.get('message',{});finish=choice.get('finish_reason')
    if finish not in ('stop','tool_calls') or message.get('role')!='assistant':raise ValueError('Resposta truncada/sem término; não entregar nem executar ferramentas.')
    content=message.get('content')
    calls=message.get('tool_calls',[])
    if content is not None and not isinstance(content,str):raise ValueError('Conteúdo inválido.')
    if isinstance(content,str) and re.search(r'(?m)^\s*</?think>\s*$',content):
        raise ValueError('Executor expôs marcadores de raciocínio apesar de think=false; não publicar como fala.')
    if not isinstance(calls,list) or len(calls)>4 or bool(calls)!=(finish=='tool_calls'):raise ValueError('Chamadas incompletas.')
    allowed={t['function']['name'] for t in tools}
    seen=set();out=[]
    for call in calls:
        fn=call.get('function',{});identifier=call.get('id')
        if not isinstance(identifier,str) or not identifier or identifier in seen or fn.get('name')not in allowed:raise ValueError('Chamada não ofertada/ID inválido.')
        seen.add(identifier);args=fn.get('arguments')
        if isinstance(args,str):args=json.loads(args)
        if not isinstance(args,dict):raise ValueError('Argumentos inválidos.')
        out.append(dict(id=identifier,type='function',function=dict(name=fn['name'],arguments=args)))
    if not out and not (content or '').strip():raise ValueError('Resposta vazia.')
    return dict(role='assistant',content=content or '',**({'tool_calls':out}if out else {}))


class Client:
    strict=True  # Seleção explícita nunca troca de máquina no meio de uma resposta.
    def __init__(self,root,settings=None,portal_factory=Portal):
        self.root=Path(root);self.settings=settings or alistair_execution.settings(root)
        self.portal_factory=portal_factory;self.path=state_path(root)
        self.opener=build_opener(ProxyHandler({}),NoRedirect())
        self.url='http://'+self.settings['xbox_ip']+':11434'

    @contextlib.contextmanager
    def locked(self):
        self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        with (self.path.parent/'node.lock').open('a+')as lock:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise RemotePending('Xbox em sincronização/inferência; aguarde.')from None
            state=read_json(self.path)
            if state.get('pending') or state.get('state')=='blocked':raise RemotePending('Xbox bloqueado/operação incerta; confira e reconcilie, sem repetir.')
            yield state

    def api(self,target,body=None,timeout=10):
        data=None if body is None else encode(body)
        began=time.monotonic()
        with self.opener.open(Request(self.url+target,data=data,headers={'Content-Type':'application/json'}),timeout=timeout)as response:
            raw=bytearray()
            while chunk:=response.read1(min(65536,LIMIT+1-len(raw))):
                raw.extend(chunk)
                if len(raw)>LIMIT or time.monotonic()-began>timeout:raise ValueError('Resposta do Xbox excessiva/lenta.')
            if response.status!=200:raise ValueError('Resposta do Xbox incompleta.')
            return json.loads(raw)

    def observe(self,portal,diagnostic=False):
        pid=portal.inventory()
        if pid is None:raise RemoteUnavailable('App Xbox fechado; nenhuma inferência enviada.')
        checked=resource_guard(self.api('/v1/diagnostics/resources'),pid,diagnostic)
        previous=getattr(self,'previous_resource',None)
        if previous and previous['pid']==pid and (checked['sequence']<=previous['sequence'] or checked['tick']<previous['tick']):
            raise ValueError('Telemetria antiga/repetida; sem inferência.')
        self.previous_resource=checked
        return checked

    def ready(self):
        state=read_json(self.path)
        try:limits=model_limits(self.root)
        except (OSError,ValueError):return False
        return (state.get('state')=='ready' and not state.get('pending')
                and state.get('model_limits')==limits and state.get('context')==limits['context']
                and time.time()-state.get('observed_at',0)<30)

    def intent(self,state,operation,**info):
        state.update(state='working',pending={'operation':operation,**info},updated_at=time.time())
        write_json(self.path,state)

    def done(self,state):
        state.update(pending=None,updated_at=time.time());write_json(self.path,state)

    def start(self,portal,state,diagnostic=False):
        self.intent(state,'start_app',diagnostic=diagnostic)
        target='/api/taskmanager/app?'+urlencode({k:base64.b64encode(v.encode()).decode()for k,v in {'appid':AUMID,'package':PFN}.items()})
        portal.mutate('POST',target)
        deadline=time.monotonic()+120
        while time.monotonic()<deadline:
            try:
                observation=self.observe(portal,diagnostic)
                log=log_current(portal)
                if diagnostic or ('offloaded 33/33 layers to GPU'in log and 'runtime LoRA adapter applied'in log):
                    state.update(managed_pid=observation['pid']);self.done(state);return observation
                # Original sem adaptador também é válido, sem inventar aplicaçãoLoRA.
                if not diagnostic and 'offloaded 33/33 layers to GPU'in log and 'GGUF model loaded'in log:
                    state.update(managed_pid=observation['pid']);self.done(state);return observation
            except (OSError, ValueError, RemoteUnavailable):pass
            time.sleep(.5)
        raise RemotePending('Partida do Xbox não confirmada; não repetir.')

    def stop(self,portal,state):
        idle(log_current(portal));self.observe(portal)
        self.intent(state,'stop_owned_app')
        target='/api/taskmanager/app?'+urlencode(dict(package=base64.b64encode(PFN.encode()).decode()))
        portal.mutate('DELETE',target)
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            if portal.inventory(stopping=True)is None:self.done(state);return
            time.sleep(.25)
        raise RemotePending('Fechamento do executor não confirmado; sem force-stop.')

    def put_control(self,portal,state,name,value):
        if portal.inventory()is not None:raise ValueError('App deve estar fechado para sincronizar.')
        if name not in CONTROLS:raise ValueError('Controle não permitido.')
        if portal.read(name)==value:return
        self.intent(state,'sync_control',name=name,sha256=hashlib.sha256(value).hexdigest())
        portal.upload(name,value,len(value),hashlib.sha256(value).hexdigest())
        if portal.read(name)!=value:raise RemotePending('Configuração não confirmada no Xbox.')
        self.done(state)

    def prepare(self):
        if not self.settings['trusted_lan']:raise ValueError('Confirme a LAN de confiança: a API de inferência do Xbox usa HTTP, sem TLS/autenticação própria.')
        with self.locked()as state:
            limits=model_limits(self.root)  # Antes de conectar ou alterar o console.
            portal=self.portal_factory(self.root,self.settings)
            try:
                bundle=local_bundle(self.root)
                current={n:portal.read(n) for n in CONTROLS}
                manifest=json.loads(current['manifest.json'] or b'{}')
                entry=next((e for e in manifest.get('models',[])if e.get('name')==MODEL),{})
                if len(manifest.get('models',[]))>1 or (manifest.get('models') and not entry):
                    raise ValueError('Catálogo contém outro modelo; não sobrescrever.')
                local_items=items(portal.get(file_route('files',LOCAL)))
                if 'models'in local_items:
                    model_dirs=items(portal.get(file_route('files',LOCAL+'\\models')))
                    listing=items(portal.get(file_route('files',MODEL_DIR))) if MODEL in model_dirs else {}
                else:model_dirs={};listing={}
                # Adaptadores são imutáveis/endereçados porSHA; nunca sobrescrever
                # a versão anterior para sincronizar um novo checkpoint.
                known=state.setdefault('verified_files',{})
                for f in bundle['files']:
                    if f['name']=='model.gguf':continue
                    prior=next((row['filename']for row in entry.get('files',[])if row.get('sha256')==f['sha256'] and row.get('approx_bytes')==f['size']),None)
                    cached=next((name for name,row in known.items()if row.get('sha256')==f['sha256'] and row.get('size')==f['size']),None)
                    f['name']=prior or cached or 'adapter-'+f['sha256']+'.gguf'
                    file_route(directory=MODEL_DIR,name=f['name'])
                wanted=controls(bundle,context=limits['context'])
                missing=[]
                for f in bundle['files']:
                    row=listing.get(f['name'])
                    if row is None:missing.append(f);continue
                    if row.get('FileSize')!=f['size'] or row.get('Type',0)&16:raise ValueError('Peso existente incompleto/divergente. Não sobrescrever; reconciliação manual necessária.')
                    stamp={k:v for k,v in row.items()if 'access'not in k.lower()}
                    cached=known.get(f['name'],{})
                    if cached!={'sha256':f['sha256'],'size':f['size'],'stamp':stamp}:
                        if portal.hash_file(f['name'],f['size'],MODEL_DIR)!=f['sha256']:raise ValueError('SHA físico do Xbox divergiu; sem carga.')
                        known[f['name']]={'sha256':f['sha256'],'size':f['size'],'stamp':stamp}
                        write_json(self.path,state)
                changed=bool(missing) or any(current[n]!=v for n,v in wanted.items())
                pid=portal.inventory()
                # Toda partida fria confirma Game antes de carregar pesos,
                # mesmo quando catálogo/limites já coincidem. Alternar somente
                # a flag diagnóstica não altera a configuração de modelo.
                if changed or (pid is None and self.settings['auto_start']):
                    if changed and not self.settings['auto_sync']:raise ValueError('Configuração técnica divergiu; habilite sincronização ou confira manualmente.')
                    if not self.settings['auto_start']:raise ValueError('Preparação exige abrir diagnóstico. Habilite inicialização automática ou configure o app manualmente.')
                    if pid is not None:
                        if not self.settings['auto_start']:raise ValueError('Feche o app antes de sincronizar.')
                        self.stop(portal,state)
                    # Diagnóstico vem antes do novo contexto/perfil; nunca carrega modelo.
                    self.put_control(portal,state,'resource-probe.flag',b'1\n')
                    self.put_control(portal,state,'api.flag',wanted['api.flag'])
                    self.put_control(portal,state,'api-port.txt',wanted['api-port.txt'])
                    self.start(portal,state,True)
                    self.intent(state,'stop_owned_diagnostic')
                    portal.mutate('DELETE','/api/taskmanager/app?'+urlencode(dict(package=base64.b64encode(PFN.encode()).decode())))
                    deadline=time.monotonic()+20
                    while portal.inventory(stopping=True)is not None:
                        if time.monotonic()>deadline:raise RemotePending('Diagnóstico não fechou; sem repetição.')
                        time.sleep(.25)
                    self.done(state)
                    state['previous_manifest_base64']=base64.b64encode(current['manifest.json']or b'').decode()
                    write_json(self.path,state)
                    for parent,name,exists in ((LOCAL,'models','models'in local_items),(LOCAL+'\\models',MODEL,MODEL in model_dirs)):
                        if exists:continue
                        self.intent(state,'create_model_folder',parent=parent,name=name)
                        portal.mkdir(parent,name)
                        if name not in items(portal.get(file_route('files',parent))):raise RemotePending('Pasta não confirmada.')
                        self.done(state)
                    for f in missing:
                        if portal.inventory()is not None:raise ValueError('App voltou a abrir durante sincronização.')
                        # A falha de espaço/upload preserva catálogo anterior e
                        # flag diagnóstica. Nenhum parcial pode ser carregado.
                        self.intent(state,'copy_model_file',name=f['name'],bytes=f['size'],sha256=f['sha256'])
                        portal.upload(f['name'],f['source'],f['size'],f['sha256'],MODEL_DIR)
                        if portal.hash_file(f['name'],f['size'],MODEL_DIR)!=f['sha256']:raise RemotePending('Hash do arquivo copiado não confirmou.')
                        row=items(portal.get(file_route('files',MODEL_DIR))).get(f['name'],{})
                        if row.get('FileSize')!=f['size']:raise RemotePending('Tamanho copiado não confirmou.')
                        known[f['name']]={'sha256':f['sha256'],'size':f['size'],'stamp':{k:v for k,v in row.items()if 'access'not in k.lower()}}
                        self.done(state)
                    # Catálogo só depois dosSHA físicos, execução normal por último.
                    for n in ('api.flag','api-port.txt','gguf_gpu_layers.txt','gguf_lora_host.flag','manifest.json','resource-probe.flag'):
                        self.put_control(portal,state,n,wanted[n])
                    pid=None
                if pid is None:
                    if not self.settings['auto_start']:raise RemoteUnavailable('Abra o app Xbox em Game para usar o executor.')
                    observation=self.start(portal,state)
                else:observation=self.observe(portal)
                log=log_current(portal);idle(log)
                host_on=wanted['gguf_lora_host.flag']==b'1\n'
                context_verified=confirm_profile(log,host_on,limits['context'],allow_lazy_context=True)
                if model_limits(self.root)!=limits:
                    raise RemotePending('Configuração mudou durante preparação. Confira antes de usar; sem nova partida automática.')
                state.update(state='ready',pending=None,**observation,package=PFN,model_alias=bundle['alias'],
                             fingerprint=bundle['fingerprint'],context=limits['context'],model_limits=limits,
                             context_verified=context_verified,host_mode=int(host_on),tls_leaf_sha256=portal.leaf)
                if 'error_type'in state or 'reason'in state:
                    state.setdefault('resolved_errors',[]).append(dict(error_type=state.pop('error_type',None),
                        reason=state.pop('reason',None),resolved_at=time.time(),resolution='prepared_after_explicit_reconciliation'))
                write_json(self.path,state);return dict(state)
            except Exception as exc:
                state.update(state='blocked',error_type=type(exc).__name__,reason=str(exc)[:300],updated_at=time.time())
                write_json(self.path,state);raise
            finally:portal.close()

    def infer(self,identifier,payload):
        from pc2_protocol import request_id
        request_id(identifier)
        with self.locked()as state:
            if state.get('state')!='ready':raise RemoteUnavailable('Xbox precisa sincronizar e iniciar antes da inferência.')
            limits=model_limits(self.root)
            if state.get('model_limits')!=limits or state.get('context')!=limits['context']:
                raise RemoteUnavailable('Configuração salva ainda não foi aplicada aoXbox. Durma/acorde Alistair antes de usar.')
            body=translate(payload,context_limit=limits['context'],output_limit=limits['output'])
            if payload.get('model')!=state.get('model_alias'):raise ValueError('Versão selecionada mudou. Durma/acorde Alistair; não trocar no meio da resposta.')
            receipt=self.path.parent/'requests'/(hashlib.sha256(identifier.encode()).hexdigest()+'.json')
            if receipt.exists() or receipt.is_symlink():raise RemotePending('ID já enviado aoXbox; não repetir mesmo após reiniciar.')
            portal=self.portal_factory(self.root,self.settings)
            try:
                before=self.observe(portal);log=log_current(portal);idle(log)
                self.intent(state,'infer',id=identifier,payload_sha256=hashlib.sha256(encode(body)).hexdigest(),pid=before['pid'])
                request_record=dict(id=identifier,payload_sha256=hashlib.sha256(encode(body)).hexdigest(),state='attempted',at=time.time())
                write_json(receipt,request_record)
                # Uma tentativa. Timeout deixa o recibo pendente e bloqueia TODO novo envio.
                answer=self.monitored_request(portal,body)
                after=self.observe(portal)
                new_log=log_current(portal)
                if before['pid']!=after['pid'] or not new_log.startswith(log):raise RemotePending('Executor/log mudou durante a resposta.')
                delta=new_log[len(log):];idle(new_log)
                if 'api: dropped 'in delta:raise ValueError('Xbox cortou contexto. Resposta rejeitada; nada foi executado.')
                if len(re.findall(r'\bprefill starting:',delta))!=1 or len(re.findall(r'\bsession generate:',delta))!=1:
                    raise RemotePending('Contagem de gerações divergiu; possível concorrência no Xbox.')
                confirm_profile(new_log,bool(state.get('host_mode')),limits['context'])
                tokens=answer.get('usage',{}).get('completion_tokens')
                prompt_tokens=answer.get('usage',{}).get('prompt_tokens')
                if (type(tokens)is not int or not 0<tokens<body['max_completion_tokens'] or type(prompt_tokens)is not int
                        or not 0<prompt_tokens<limits['context'] or prompt_tokens+tokens>limits['context']):
                    raise ValueError('Contagens/término sem folga não confirmados; resposta rejeitada.')
                message=response_message(answer,body.get('tools',[]))
                # xllama sintetiza call_1 novamente em cada geração. IDs da
                # transcrição inteira precisam ser únicos; argumentos/autoria
                # ficam intactos e os recibos usam estes mesmos IDs canônicos.
                for call in message.get('tool_calls',[]):
                    call['id']='xbox_'+hashlib.sha256((identifier+'\0'+call['id']).encode()).hexdigest()[:32]
                request_record.update(state='completed_no_replay',finish=answer['choices'][0]['finish_reason'],completed_at=time.time(),output_tokens=tokens)
                write_json(receipt,request_record)
                state.update(state='ready',context_verified=True,last_request_id=identifier,last_finish=answer['choices'][0]['finish_reason'],**after)
                self.done(state)
                return dict(message=message,done=True,eval_count=answer.get('usage',{}).get('completion_tokens'),executor='xbox')
            except Exception as exc:
                state.update(state='blocked',error_type=type(exc).__name__,reason=str(exc)[:300],updated_at=time.time())
                write_json(self.path,state)
                raise RemotePending('Resposta Xbox não confirmada/aprovada pelo protocolo. Sem replay ou fallback. Consulte o estado do executor.')from exc
            finally:portal.close()

    def monitored_request(self,portal,body):
        """Uma geração; pressão não mata nem autoriza replay de trabalho ativo."""
        complete=threading.Event();result={};errors=[]
        def send():
            try:result['answer']=self.api('/v1/chat/completions',body,timeout=600)
            except Exception as exc:result['error']=exc
            finally:complete.set()
        worker=threading.Thread(target=send,daemon=True,name='alistair-xbox-http');worker.start()
        began=time.monotonic()
        while not complete.wait(5):
            try:self.observe(portal)
            except Exception as exc:errors.append(type(exc).__name__)
            if time.monotonic()-began>610:raise RemotePending('Inferência Xbox sem término; execução não será repetida.')
        if 'error'in result:raise result['error']
        if errors:raise RemotePending('Pressão/telemetria incerta durante inferência: '+','.join(sorted(set(errors))))
        return result['answer']

    def unload(self):
        with self.locked()as state:
            portal=self.portal_factory(self.root,self.settings)
            try:
                pid=portal.inventory()
                if pid is None:
                    state.update(state='sleeping',pending=None,updated_at=time.time());write_json(self.path,state);return True
                if pid!=state.get('managed_pid'):return False
                self.stop(portal,state)
                state.update(state='sleeping',pending=None,managed_pid=None,updated_at=time.time());write_json(self.path,state)
                return True
            finally:portal.close()

    def reconcile(self):
        """Somente por clique humano: confirma ociosidade, não repete a operação."""
        p=self.path.parent/'node.lock';p.parent.mkdir(parents=True,exist_ok=True)
        with p.open('a+')as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            state=read_json(self.path);portal=self.portal_factory(self.root,self.settings)
            try:
                pid=portal.inventory()
                if pid is not None:self.observe(portal);idle(log_current(portal))
                old=state.get('pending')
                if old:
                    state.setdefault('unconfirmed_operations',[]).append(dict(operation=old.get('operation'),id=old.get('id'),reconciled_at=time.time(),result='not_replayed_no_result_adopted'))
                state.update(state='needs_prepare',pending=None,updated_at=time.time())
                write_json(self.path,state)
                return dict(state='needs_prepare',replayed=False,note='Ociosidade confirmada. Pedido anterior não foi repetido nem considerado concluído; prepare novamente antes de usar.')
            finally:portal.close()
