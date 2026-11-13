"""Adaptadores de UI no backend existente; sem scheduler, banco ou IA novos.

Consultas mentais são read-only e limitadas. Escritas são allowlisted, atômicas,
com backup/revisão e exclusão com o lifecycle. Nenhuma consulta inicia serviço.
"""
from __future__ import annotations
import contextlib
import ast
import fcntl
import hashlib
import json
import math
import os
import re
import shutil
import sqlite3
import stat
import tempfile
import threading
import time
import uuid
from pathlib import Path
from datetime import datetime
from functools import lru_cache

from entity_paths import carregar_entidade
from core import diagnostics, history, interentity, resource_manager, job_bus, ui_policy
from core.tts_router import STANDARD_PT_BR
from core import neural9b_modes

ENTITIES = ('hoshino', 'lilith', 'alistair')
CLIPBOARD_ATTACHMENT = re.compile(r'\b[0-9a-f]{12}-clipboard-(?:texto\.txt|print\.png)\b')
STORES = {'hoshino':'ollama', 'lilith':'ollama-lilith', 'alistair':'ollama-alistair'}
ENV_FIELDS = {'HOSHINO_MODEL','HOSHINO_CONTEXT_TOKENS','HOSHINO_NUM_CTX','HOSHINO_NUM_PREDICT',
              'HOSHINO_ADAPTIVE_CONTEXT',
              'HOSHINO_WHISPER','HOSHINO_WHISPER_BEAM','HOSHINO_AUDIO_VAD',
              'HOSHINO_MC_BRIDGE_PORT','HOSHINO_OLLAMA_URL'}
# 06/11 (pedido humano): alerta na tela quando a entidade não consegue a GPU por falta de VRAM.
# Sem outro modelo do projeto na placa nada libera sozinho: alerta logo. Com o modelo de outra entidade, a troca
# cooperativa do RM (sticky 90 s / espera justa) já devia ter acontecido perto do fim da espera de 120 s.
GPU_ALERT_SECONDS = 15
GPU_ALERT_PEER_SECONDS = 100
MIB_BYTES = 1024 ** 2
APP_LABELS = {'firefox-bin': 'Firefox', 'firefox': 'Firefox', 'chrome': 'Chrome', 'chromium': 'Chromium', 'brave': 'Brave',
              'kclock': 'KClock', 'steam': 'Steam', 'steamwebhelper': 'Steam', 'java': 'Java/Minecraft', 'Discord': 'Discord',
              'discord': 'Discord', 'obs': 'OBS', 'vlc': 'VLC', 'mpv': 'mpv', 'cinnamon': 'área de trabalho',
              'Xorg': 'servidor gráfico', 'Xwayland': 'servidor gráfico'}
ARTICLES = {'hoshino': 'a', 'lilith': 'a', 'alistair': 'o'}
POSSESSIVE = {'hoshino': 'dela', 'lilith': 'dela', 'alistair': 'dele'}


def _mib(value):
    return f'{int(value) // MIB_BYTES:,} MiB'.replace(',', '.')


def _model_entity(cmd):
    """De qual entidade é o llama-server, pelo diretório do modelo que ele abriu."""
    for entity, store in STORES.items():
        if f'/compartilhado/modelos/{store}/' in (cmd or ''):
            return entity
    return None


MODEL_DEFAULTS = {'hoshino':'hf.co/ccharnkij/Qwen3.5-9B-Uncensored-GGUF:Q4_K_M',
                  'lilith':'lilith-qwen3.5-9b:latest', 'alistair':'alistair-qwen3.5-4b:latest'}


def redact(value):
    value = diagnostics._redact(value, truncate=False)
    # Outros segredos exportados (Discord etc.) também podem aparecer em logs
    # legados. Valores não são armazenados nem enviados pela UI.
    def visit(v):
        if isinstance(v, str):
            for key, secret in os.environ.items():
                if secret and len(secret) >= 6 and any(s in key.lower() for s in diagnostics.SENSIVE):
                    v = v.replace(secret, '[REDACTED]')
            return v
        if isinstance(v, dict):
            return {k:visit(x) for k,x in v.items() if k.lower() not in {'thinking','analysis','reasoning','scratchpad','messages','prompt'}}
        if isinstance(v, list):
            return [visit(x) for x in v]
        return v
    return visit(value)


def json_file(path, default=None):
    if not path.is_file():
        return {} if default is None else default
    if path.stat().st_size > 1024**2:
        raise ValueError('Configuração acima do limite de leitura.')
    return json.loads(path.read_text(encoding='utf-8'))


def revision(path):
    return hashlib.sha256(path.read_bytes() if path.exists() else b'').hexdigest()


def atomic_save(path, content, expected):
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError('Configuração por link não pode ser alterada pela central.')
    if expected != revision(path):
        raise ValueError('Configuração mudou; recarregue antes de salvar.')
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_name(path.name+'.backup-'+uuid.uuid4().hex[:12])
        backup_fd=os.open(backup,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with path.open('rb') as original,os.fdopen(backup_fd,'wb') as output:
            shutil.copyfileobj(original,output);output.flush();os.fsync(output.fileno())
    fd, name = tempfile.mkstemp(prefix='.central-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as out:
            os.fchmod(out.fileno(), 0o600)
            out.write(content)
            out.flush(); os.fsync(out.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        Path(name).unlink(missing_ok=True)
    return revision(path)


def replace_env(content, updates):
    """Preserva comentários/linhas desconhecidas; nunca eval/source no servidor."""
    lines, found = [], set()
    for line in content.splitlines():
        match = re.match(r'^(\s*(?:export\s+)?)([A-Z_][A-Z0-9_]*)\s*=', line)
        if match and match[2] in updates:
            # Valores vêm de enum ou inteiro; sem shell interpolation.
            line = f'{match[1]}{match[2]}="{updates[match[2]]}"'
            found.add(match[2])
        lines.append(line)
    lines.extend(f'{key}="{value}"' for key,value in updates.items() if key not in found)
    return '\n'.join(lines)+'\n'


class Control:
    def __init__(self, root, supervisor, audio):
        self.root, self.supervisor, self.audio = Path(root).resolve(), supervisor, audio
        self.lock = threading.RLock()
        self.cpu_previous = None
        self.transfers = {}
        self.transfer_threads = []
        self.overlay_process = None
        self.native_process = None
        self.focus_clients = {}
        self.focus_active = None  # 07/11 (pedido humano): só a última janela que recebeu foco comanda
        self.entity_cache = (0, None)
        self.password_failures=[]
        self.memory_grants={}
        self.gpu_alert_lock = threading.Lock()
        self.gpu_blocks = {}

    def unlock_memories(self,data):
        import secrets
        if set(data)!={'entity','password'}:raise ValueError('Entidade e senha são obrigatórias.')
        entity=data.get('entity');self.paths(entity)
        with self.lock:
            self._check_password(data.get('password'))
            now=time.monotonic();security=revision(self.root/'compartilhado/config/central_security.json')
            self.memory_grants={k:v for k,v in self.memory_grants.items() if v['expires']>now and v['security']==security}
            if len(self.memory_grants)>=64:raise ValueError('Muitas sessões de memórias abertas; bloqueie as anteriores.')
            token=secrets.token_urlsafe(32)
            self.memory_grants[hashlib.sha256(token.encode()).hexdigest()]=dict(entity=entity,expires=now+300,security=security)
        return dict(unlocked=True,entity=entity,access_token=token,expires_in=300)

    def require_memories(self,entity,token):
        self.paths(entity)
        if not isinstance(token,str) or not 32<=len(token)<=100:raise PermissionError('Memórias bloqueadas. Digite a senha para abrir.')
        key=hashlib.sha256(token.encode()).hexdigest()
        with self.lock:
            grant=self.memory_grants.get(key)
            if (not grant or grant['entity']!=entity or grant['expires']<=time.monotonic() or
                grant['security']!=revision(self.root/'compartilhado/config/central_security.json')):
                if grant and grant['expires']<=time.monotonic():self.memory_grants.pop(key,None)
                raise PermissionError('Memórias bloqueadas ou acesso expirado. Digite a senha novamente.')

    def lock_memories(self,entity,token):
        self.paths(entity)
        if isinstance(token,str):
            key=hashlib.sha256(token.encode()).hexdigest()
            with self.lock:
                if self.memory_grants.get(key,{}).get('entity')==entity:self.memory_grants.pop(key,None)
        return dict(locked=True,entity=entity)

    def paths(self, entity):
        if entity not in ENTITIES:
            raise ValueError('Entidade inválida.')
        return carregar_entidade(self.root, entity)

    def save_chat_feedback(self, data):
        required = {'entity', 'message_id', 'decision', 'note', 'text_sha256', 'expected_revision'}
        if set(data) != required:
            raise ValueError('Campos inválidos na avaliação da conversa.')
        self.paths(data['entity'])
        if not isinstance(data['note'], str) or len(data['note']) > 600:
            raise ValueError('Observação inválida.')
        result = interentity.save_human_feedback(data['entity'], data['message_id'],
            data['decision'], redact(data['note']), text_sha256=data['text_sha256'],
            expected_revision=data['expected_revision'])
        diagnostics.emit('central.chat_feedback_saved', entity=data['entity'],
                         message_id=data['message_id'], decision=data['decision'],
                         feedback_revision=result['feedback']['revision'], training_started=False)
        return result

    def env_path(self, entity):
        paths = self.paths(entity)
        primary = paths.config / (entity+'.env')
        return paths.config/'hoshino_v32.env' if entity=='hoshino' and not primary.exists() else primary

    def env(self, entity):
        path = self.env_path(entity)
        result = {}
        for line in path.read_text().splitlines() if path.exists() else []:
            match = re.match(r'^\s*(?:export\s+)?([A-Z_][A-Z0-9_]*)\s*=\s*(.*?)\s*$',line)
            if match and match[1] in ENV_FIELDS:
                result[match[1]] = match[2].strip('"\'')
        return result

    @contextlib.contextmanager
    def idle_entity(self, entity, *, long_operation=False):
        # Mesmo lock usado para start e pelo processo real. Nada de medir ativo
        # e só então escrever, deixando uma janela de corrida com wake.
        with contextlib.ExitStack() as stack:
            stack.enter_context(self.supervisor.lock)
            if self.supervisor.closing:
                raise ValueError('Central encerrando.')
            paths = self.paths(entity)
            paths.runtime.mkdir(parents=True, exist_ok=True)
            with (paths.runtime/'entity.lock').open('a+') as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise ValueError('Entidade ativa; coloque-a para dormir antes de alterar o executor.') from None
                presence = interentity.presence(entity) or {}
                proc = self.supervisor.processes.get(entity)
                if (presence.get('status') not in {None,'offline','sleeping'} or
                    (proc and proc.poll() is None) or
                    any(j['entity']==entity for j in job_bus.status(active_only=True)) or
                    any(l['entity']==entity for l in resource_manager.status())):
                    raise ValueError('Entidade/trabalho/lease ativo. Aguarde sono confirmado.')
                if long_operation:
                    # entity.lock continua retido: start recusa só Alistair.
                    # Não congela tick/sono das demais entidades por um hash2GB.
                    stack.close()
                yield

    def neural9b_status(self, entity):
        self.paths(entity)
        return neural9b_modes.status(self.root, entity)

    def save_neural9b_mode(self, data):
        if set(data) != {'entity','mode','revision'} or data['entity'] not in neural9b_modes.ENTITIES:
            raise ValueError('Campos inválidos para seletor Neural 9B.')
        if data['mode'] not in ('original','neural9b'):
            raise ValueError('Modo desconhecido.')
        entity=data['entity']
        with self.lock, self.idle_entity(entity):
            status=neural9b_modes.status(self.root,entity)
            if data['revision']!=status['revision']:
                raise ValueError('Seleção de executor mudou. Recarregue antes de salvar.')
            if data['mode']=='neural9b' and not status['neural_ready']:
                raise ValueError('Neural 9B ainda não instalado. Pesos HF não são um alias GGUF Ollama.')
            selections=neural9b_modes.read_document(self.root)
            selections[entity]=data['mode']
            selections.get('executor_versions',{}).pop(entity,None)
            target=neural9b_modes.path(self.root)
            new_rev=atomic_save(target,json.dumps(selections,sort_keys=True,indent=2)+'\n',data['revision'])
            diagnostics.emit('central.neural9b_mode_saved',entity=entity,mode=data['mode'],apply='requires_sleep_wake')
            return dict(saved=True, mode=data['mode'],revision=new_rev,apply='requires_sleep_wake')

    def model_versions(self, entity):
        self.paths(entity)
        from laboratorio.recuperacao_modelos import versions_catalog
        return versions_catalog(self.root/'laboratorio-local',self.root,entity)

    def change_model_version(self, data, prepare=False):
        from laboratorio import recuperacao_modelos as recovery,treinos_unificados as lab
        fields={'entity','model_id','kind','ref','revision','experimental_consent'}
        if not isinstance(data,dict) or set(data)!=fields or type(data['experimental_consent']) is not bool:
            raise ValueError('Campos inválidos para versão do executor.')
        entity=data['entity'];self.paths(entity);home=self.root/'laboratorio-local'
        with self.lock,self.idle_entity(entity):
            if lab._busy() or any(j['state'] in ('started','running','cancel_requested') for j in lab.jobs(home)) or resource_manager.status():
                raise ValueError('Laboratório/recurso ocupado. Aguarde liberação confirmada.')
            entry=recovery.find_version(home,self.root,entity,data['model_id'],data['kind'],data['ref'],data['revision'])
            if entry['experimental'] and not data['experimental_consent']:
                raise ValueError('Candidato experimental exige confirmação; não é versão estável.')
            if prepare:
                records=[recovery._json(path) for path in (lab._registry(home)/'jobs').glob('*.json')]
                previous=[j for j in records if j.get('action')=='recover' and j.get('entity')==entity and
                          j.get('plan',{}).get('source_sha256')==entry['source_sha256']]
                if previous and not entry['ready']:
                    raise ValueError('Preparação anterior não confirmada. Confira o job existente antes de tentar novamente.')
                return lab.start(home,self.root,data['model_id'],entity,90,'recover','EXECUTAR_RECUPERACAO_LOCAL',
                    options=dict(version_kind=data['kind'],version_ref=data['ref'],source_sha256=entry['source_sha256'],
                                 experimental_consent=data['experimental_consent']))
            if not entry['ready'] or not entry['manifest_sha256']:
                raise ValueError('Prepare a versão e aguarde o teste físico antes de selecionar.')
            doc=neural9b_modes.read_document(self.root);revision=neural9b_modes.revision(self.root)
            row={k:entry[k] for k in ('entity','model_id','kind','ref','source_sha256','alias','manifest_sha256','experimental')}
            selection=doc.setdefault('executor_versions',{}).setdefault(entity,{'primary':data['model_id'],'models':{}})
            selection['primary']=data['model_id'];selection['models'][data['model_id']]=row
            atomic_save(neural9b_modes.path(self.root),json.dumps(doc,indent=2,sort_keys=True)+'\n',revision)
            diagnostics.emit('central.executor_version_saved',entity=entity,model=data['model_id'],kind=data['kind'],alias=row['alias'])
            return dict(saved=True,entity=entity,alias=row['alias'],experimental=entry['experimental'],
                quality_approved=entry['quality_approved'],apply='requires_sleep_wake',training_started=False)

    def models(self, entity):
        self.paths(entity)
        storage = self.root/'compartilhado/modelos'/STORES[entity]
        rows = []
        directory = storage/'manifests'
        for path in sorted(directory.rglob('*')) if directory.is_dir() else []:
            if not path.is_file() or len(rows)>=100 or not path.resolve().is_relative_to(storage.resolve()):
                continue
            try:
                manifest = json_file(path)
                blobs = [manifest['config'], *manifest['layers']]
                if not all(re.fullmatch('sha256:[a-f0-9]{64}', b['digest']) and isinstance(b['size'],int) and b['size']>=0 for b in blobs):
                    continue
                parts = path.relative_to(directory).parts
                name = '/'.join(parts[:-1])+':'+parts[-1]
                if name.startswith('registry.ollama.ai/library/'): name=name[len('registry.ollama.ai/library/'):]
                installed = resource_manager.local_model_installed(name, storage)
                rows.append(dict(model=name,size_bytes=sum(b['size'] for b in blobs),installed=installed,
                                 backend='ollama',quantization='Q4_K_M' if 'q4_k_m' in (name+json.dumps(manifest)).lower() else 'não confirmada',
                                 path=str(path),hash=revision(path),hash_kind='manifesto, não pesos completos',
                                 files=[dict(path=str(storage/'blobs'/b['digest'].replace(':','-')),size_bytes=b['size'],sha256=b['digest']) for b in blobs]))
            except (OSError,ValueError,KeyError,TypeError):
                continue
        return rows

    def model_settings(self, entity):
        env=self.env(entity); original=env.get('HOSHINO_MODEL',MODEL_DEFAULTS[entity])
        primary=neural9b_modes.startup_override(self.root,entity) or original
        catalog=self.models(entity)
        # Apenas aliases existentes da mesma entidade/família aprovada. Outros
        # modelos instalados continuam inspecionáveis, não adotados às cegas.
        approved={primary,MODEL_DEFAULTS[entity]}
        if entity in {'hoshino','lilith'}: approved.add(entity+'-qwen3.5-9b:latest')
        choices=[m for m in catalog if m['model'] in approved and m['installed']]
        light=json_file(self.paths(entity).config/'executores.json').get('light') if entity!='alistair' else None
        companion=json_file(self.paths(entity).config/'executores.json').get('companion') if entity!='alistair' else None
        ctx=int(env.get('HOSHINO_CONTEXT_TOKENS',env.get('HOSHINO_NUM_CTX',16384 if entity!='alistair' else 8192)))
        if primary not in {m['model'] for m in choices}:choices.extend(m for m in catalog if m['model']==primary and m['installed'])
        maxctx=neural9b_modes.context_limit(self.root,entity)
        context_step=1
        note='Contexto adaptativo: janela dimensionada por pedido, até o teto configurado; não corta mensagens. Pesos + KV cache + staging; margem AMD/RM preservada.'
        output_default=4096
        if entity=='alistair':
            from core import alistair_execution as execution, xbox_alistair as xbox
            if execution.destination(self.root)=='xbox':
                maxctx=min(maxctx,xbox.CTX);context_step=xbox.CONTEXT_STEP;output_default=768
                note=('Xbox: contexto sincronizado com a janela real do console ao acordar Alistair ou conferir/sincronizar dormindo. '
                      f'Faixa validada {xbox.CONTEXT_MIN}–{maxctx}, passos de{context_step} tokens. '
                      'Limite de saída enviado a cada pedido; o teto inclui entrada e saída. '
                      'Mudanças não interrompem uma resposta; camadasGPU/LoRA e margens de segurança permanecem no perfil medido.')
        return dict(entity=entity,primary=primary,light=light,companion=companion,context=min(ctx,maxctx),output=min(int(env.get('HOSHINO_NUM_PREDICT',output_default)),maxctx-512),
                    gpu_layers=self.gpu_layers(entity),prompt_identity=self.prompt_identity(entity),
                    adaptive_context=env.get('HOSHINO_ADAPTIVE_CONTEXT','1')!='0',
                    options=choices,catalog=catalog,revision=revision(self.env_path(entity)),
                    context_min=2048,context_max=maxctx,context_step=context_step,output_max=min(8192,maxctx-512),
                    residency=[r for r in resource_manager.residency() if r.get('model') in {primary,(light or {}).get('model'),(companion or {}).get('model')}],
                    apply='requires_sleep_wake',light_context=8192 if light else None,
                    impact_note=note)

    def gpu_layers(self, entity):
        """Divisão de camadas do 9B entre GPU e CPU (pedido humano 06/11).

        Só os degraus medidos na placa: a VRAM de cada um foi medida com KV e buffers
        (resource_manager.OFFLOAD_LADDER_9B). None = escada automática pela VRAM livre.
        O Alistair usa o 4B inteiro no destino dele e não entra aqui.
        """
        if entity not in {'hoshino','lilith'}:return None
        path=self.paths(entity).config/'executores.json'
        fixed=json_file(path).get('gpu_layers_fixed')
        measured=sorted(n for n,_ in resource_manager.OFFLOAD_LADDER_9B)
        return dict(fixed=fixed if type(fixed) is int and fixed in measured else None,
                    measured=measured,total=max(measured),revision=revision(path),apply='requires_sleep_wake')

    def prompt_identity(self, entity):
        """Qual prompt a entidade vai receber com a versão selecionada (só leitura)."""
        if entity not in {'hoshino','lilith'}:return None
        family=neural9b_modes.primary_family(self.root,entity)
        row=neural9b_modes.selected_version(self.root,entity,family) if family else None
        dataset=''
        if row and row.get('kind') in ('trained','checkpoint'):
            job=json_file(self.root/'laboratorio-local/controle-laboratorio/treinamento-unificado/jobs'/
                          (str(row.get('ref','')).split(':',1)[0]+'.json'))
            dataset=str((job.get('plan') or {}).get('dataset') or '')
        from laboratorio import corpus_atual
        reduced=dataset==corpus_atual.dataset_id(entity)
        forced=self.env(entity).get('HOSHINO_PROMPT_IDENTIDADE','auto')
        return dict(mode='reduzido' if (reduced and forced!='completo') or forced=='reduzido' else 'completo',
                    trained_corpus=corpus_atual.CORPUS if reduced else None,override=forced)

    def alistair_execution(self):
        """Só estado local; abrir o painel não conecta, acorda ou sincroniza."""
        from core import alistair_execution as execution, xbox_alistair as xbox
        settings=execution.settings(self.root)
        state=xbox.read_json(xbox.state_path(self.root))
        last=state.get('observed_at')
        status={k:state.get(k) for k in ('state','pending','pid','package','model_alias','context','host_mode',
                'app_limit_bytes','app_headroom_bytes','gpu_headroom_bytes','observed_at','error_type','reason','last_finish','context_verified') if k in state}
        status['fresh']=bool(last and time.time()-last<30)
        try:
            configured=xbox.model_limits(self.root);limits_error=None
        except (OSError,ValueError)as exc:
            configured=None;limits_error=str(exc)
        limits=dict(configured=configured,applied=state.get('model_limits'),
                    pending=configured is None or configured!=state.get('model_limits'),error=limits_error)
        pc2=json_file(self.root/'compartilhado/config/alistair_pc2.json')
        certificate=self.root/'compartilhado/config/xbox-root.pem'
        secret=xbox.secret_path(self.root)
        return dict(settings=settings,revision=revision(execution.path(self.root)),
                    destinations=execution.DESTINATIONS,pc2_configured=pc2.get('enabled')is True,
                    credentials_configured=secret.is_file() and not secret.is_symlink() and not(secret.stat().st_mode&0o077),
                    certificate_configured=certificate.is_file() and not certificate.is_symlink(),
                    xbox=status,model_limits=limits,apply='requires_sleep_wake',
                    note='Xbox executa somente4B. Banco, identidade, histórico e ferramentas ficam noPC. '
                         'Inicialização automática ao acordar Alistair, com console ligado emDevMode/Game. '
                         'API de inferência HTTP, sem autenticação própria: use somenteLAN de confiança. '
                         'Não há wake-on-LAN, instalação de app, treino ou troca silenciosa de máquina.')

    def save_alistair_execution(self,data):
        from core import alistair_execution as execution, xbox_alistair as xbox
        allowed={'settings','revision','username','password','certificate_pem'}
        if not isinstance(data,dict) or set(data)-allowed or not isinstance(data.get('settings'),dict):
            raise ValueError('Campos de localização inválidos.')
        supplied=data['settings']
        if set(supplied)!={'destination','xbox_ip','auto_start','auto_sync','trusted_lan'}:
            raise ValueError('Preencha as opções de execução.')
        from pc2_protocol import lan_ip
        lan_ip(supplied['xbox_ip'])
        if supplied['destination']not in execution.DESTINATIONS or any(type(supplied[k])is not bool for k in ('auto_start','auto_sync','trusted_lan')):
            raise ValueError('Destino/opções inválidos.')
        with self.lock,self.idle_entity('alistair'):
            p=execution.path(self.root)
            if revision(p)!=data.get('revision'):raise ValueError('Destino mudou; atualize antes de salvar.')
            state=xbox.read_json(xbox.state_path(self.root))
            if state.get('pending'):raise ValueError('Xbox com operação pendente. Reconcilie antes de trocar destino.')
            if supplied['destination']=='pc2' and not json_file(self.root/'compartilhado/config/alistair_pc2.json').get('enabled'):
                raise ValueError('PC2 preservado, mas ainda não está pareado/habilitado.')
            secret=None
            if 'username'in data or 'password'in data:
                secret=xbox.credential_value(data.get('username'),data.get('password'))
            cert=self.root/'compartilhado/config/xbox-root.pem'
            pem=data.get('certificate_pem')
            if supplied['destination']=='xbox' and not pem and not cert.exists():pem=xbox.known_root_pem()
            if pem:
                import ssl
                if not isinstance(pem,str) or len(pem)>16384 or hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).hexdigest()!=xbox.ROOT_PIN:
                    raise ValueError('Certificado não é a raiz do Xbox já verificada. Sem confiança automática.')
            if supplied['destination']=='xbox':
                xbox.model_limits(self.root)
                if not supplied['trusted_lan']:raise ValueError('Confirme a rede local de confiança; a inferência usaHTTP.')
                if secret is None:xbox.secrets(self.root)
                if not pem and not cert.is_file():raise ValueError('Importe o certificado público do Xbox.')
                xbox.local_bundle(self.root)  # Só versão local íntegra, sem rede ou carga.
            if secret is not None:xbox.save_secret(self.root,**secret)
            if pem:atomic_save(cert,pem,revision(cert))
            rev=atomic_save(p,json.dumps(supplied,ensure_ascii=False,indent=2)+'\n',data['revision'])
            diagnostics.emit('central.alistair_destination_saved',destination=supplied['destination'],apply='requires_sleep_wake')
            return dict(saved=True,revision=rev,apply='requires_sleep_wake',note='Destino salvo. Sincronização/início ocorrerão ao acordar Alistair; bancos continuam noPC.')

    def check_alistair_execution(self,data):
        from core import alistair_execution as execution, xbox_alistair as xbox
        if set(data)!={'action','revision'} or data['action']not in ('prepare','reconcile'):
            raise ValueError('Escolha conferir/sincronizar ou reconciliar, sem replay.')
        with self.idle_entity('alistair',long_operation=True):
            if data['revision']!=revision(execution.path(self.root)):raise ValueError('Destino mudou; recarregue.')
            if execution.destination(self.root)!='xbox':raise ValueError('Selecione e salve Xbox primeiro.')
            client=xbox.Client(self.root)
            with resource_manager.lease('alistair_remote','sync',entity='alistair'):
                result=client.prepare() if data['action']=='prepare' else client.reconcile()
            # Não exportar recibo interno/fingerprint/valores de autenticação.
            return dict(state=result.get('state'),replayed=False,status=self.alistair_execution()['xbox'])

    def save_model(self, data):
        entity=data.get('entity'); self.paths(entity)
        if set(data)-{'entity','model','context','output','revision','gpu_layers','layers_revision'}:
            raise ValueError('Campo não suportado.')
        if ('gpu_layers' in data)!=('layers_revision' in data):
            raise ValueError('Camadas exigem a revisão do catálogo de executores.')
        with self.lock, self.idle_entity(entity):
            current=self.model_settings(entity)
            if data.get('model') not in {m['model'] for m in current['options']}:
                raise ValueError('Modelo não está instalado/compatível com esta entidade.')
            for key,low,high in [('context',current['context_min'],current['context_max']),('output',128,current['output_max'])]:
                if type(data.get(key)) is not int or not low<=data[key]<=high:
                    raise ValueError(f'{key} deve ser inteiro entre {low} e {high}.')
            # O teto inclui entrada, margem e saída. Não persistir uma
            # configuração que não deixa sequer espaço mínimo para o prompt;
            # o pedido real ainda é validado pelo contexto adaptativo do RM.
            if data['context']-data['output']<512:
                raise ValueError('Reserve ao menos 512 tokens de contexto para entrada e margem.')
            if entity=='alistair':
                from core import alistair_execution as execution,xbox_alistair as xbox
                if execution.destination(self.root)=='xbox':
                    if xbox.read_json(xbox.state_path(self.root)).get('pending'):
                        raise ValueError('Xbox com operação pendente. Reconcilie antes de alterar o modelo.')
                    xbox.validate_limits(data['context'],data['output'])
            path=self.env_path(entity)
            if neural9b_modes.primary_family(self.root,entity) and data['model']!=current['primary']:
                raise ValueError('Altere o executor pelo seletor de versões.')
            layers_doc=None
            if 'gpu_layers' in data:
                layers=current['gpu_layers']
                if layers is None:raise ValueError('Esta entidade não usa a divisão de camadas do 9B.')
                value=data['gpu_layers']
                if value is not None and (type(value) is not int or value not in layers['measured']):
                    raise ValueError('Escolha um degrau medido: '+', '.join(map(str,layers['measured']))+'.')
                executors=self.paths(entity).config/'executores.json'
                if data['layers_revision']!=revision(executors):
                    raise ValueError('Catálogo de executores mudou; recarregue antes de salvar.')
                if revision(path)!=data.get('revision'):
                    raise ValueError('Configuração mudou; recarregue antes de salvar.')
                layers_doc=json_file(executors)
                layers_doc.pop('gpu_layers_fixed',None);layers_doc.pop('gpu_layers_fixed_reason',None)
                if value is not None:
                    layers_doc['gpu_layers_fixed']=value
                    layers_doc['gpu_layers_fixed_reason']=(
                        f"Escolha humana na Central em {time.strftime('%d/%m/%Y %H:%M')}: {value} camadas na GPU e "
                        f"{layers['total']-value} na CPU (degrau medido).")
            updates={'HOSHINO_CONTEXT_TOKENS':str(data['context']),
                     'HOSHINO_NUM_PREDICT':str(data['output'])}
            if not neural9b_modes.primary_family(self.root,entity):updates['HOSHINO_MODEL']=data['model']
            if layers_doc is not None:
                atomic_save(executors,json.dumps(layers_doc,ensure_ascii=False,indent=2)+'\n',data['layers_revision'])
                diagnostics.emit('central.gpu_layers_saved',entity=entity,layers=data['gpu_layers'],apply='requires_sleep_wake')
            rev=atomic_save(path,replace_env(path.read_text() if path.exists() else '',updates),data.get('revision'))
            diagnostics.emit('central.config_saved',entity=entity,category='executor',apply='requires_sleep_wake')
            return dict(saved=True,revision=rev,apply='requires_sleep_wake')

    def audio_settings(self):
        path=self.root/'compartilhado/config/audio.json'; settings=json_file(path)
        providers={}
        for provider,default in [('elevenlabs','ELEVENLABS_API_KEY'),('azure','AZURE_SPEECH_KEY')]:
            row=settings.get(provider,{})
            providers[provider]=dict(enabled=row.get('enabled',False),key_configured=bool(os.environ.get(row.get('key_env',default))),
                                     voices=row.get('voices',{}),model=row.get('model_id'),timeout_seconds=row.get('timeout_seconds'),
                                     connection='não testada nesta consulta')
            if provider=='azure':providers[provider]['voices']={'hoshino':'pt-BR-FranciscaNeural','lilith':'pt-BR-BrendaNeural'}|providers[provider]['voices']
        return dict(preferred_provider=settings.get('preferred_provider','qwen3_tts'),local_backend=settings.get('backend'),
                    providers=providers,local_voices=settings.get('voices',{}),revision=revision(path),
                    eleven_models=['eleven_multilingual_v2','eleven_flash_v2_5','eleven_turbo_v2_5'],
                    azure_voices=sorted(STANDARD_PT_BR),asr={'configuration':self.env('hoshino'),'apply':'read_only_requires_restart'})

    def save_audio(self, data):
        if set(data)-{'entity','preferred_provider','enabled','voices','revision','model_id'}:
            raise ValueError('Campo não suportado; chaves somente no ambiente.')
        provider=data.get('preferred_provider')
        if provider not in {'elevenlabs','azure','qwen3_tts','kokoro'}:
            raise ValueError('Provider desconhecido.')
        if type(data.get('enabled')) is not bool:
            raise ValueError('enabled deve ser booleano.')
        voices=data.get('voices',{})
        if not isinstance(voices,dict) or set(voices)-{'hoshino','lilith'}:
            raise ValueError('Vozes inválidas.')
        for v in voices.values():
            if not isinstance(v,str) or (provider=='azure' and v not in STANDARD_PT_BR) or not re.fullmatch('[A-Za-z0-9_-]{1,128}',v):
                raise ValueError('Voice ID inválido.')
        path=self.root/'compartilhado/config/audio.json'
        model=data.get('model_id')
        if model is not None and (provider!='elevenlabs' or model not in self.audio_settings()['eleven_models']):
            raise ValueError('Modelo TTS não suportado por este painel.')
        with self.lock, self.audio.lock:
            if self.audio.cancels or self.audio.pending.qsize():
                raise ValueError('Áudio ativo; interrompa e aguarde antes de trocar provider.')
            settings=json_file(path)
            settings['preferred_provider']=provider
            # Qwen permanece fallback obrigatório. Kokoro apenas rota legada.
            for remote in ('azure','elevenlabs'):
                settings.setdefault(remote,{})['enabled']=data['enabled'] if remote==provider else False
            if provider in {'azure','elevenlabs'}:
                settings[provider].setdefault('voices',{}).update(voices)
            if model is not None:settings['elevenlabs']['model_id']=model
            if provider=='kokoro' and settings.get('backend')!='kokoro':
                raise ValueError('Kokoro preservado, mas troca de worker exige restart/configuração local; painel somente leitura.')
            rev=atomic_save(path,json.dumps(settings,ensure_ascii=False,indent=2)+'\n',data.get('revision'))
            self.audio.reload_routing(settings)
            diagnostics.emit('central.config_saved',category='tts',provider=provider,enabled=data['enabled'])
            return dict(saved=True,revision=rev,apply='immediate',quota_used=False)

    def read_db(self, path, table, limit=100):
        if not path.is_file(): return []
        with contextlib.closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=2)) as db:
            db.row_factory=sqlite3.Row; db.execute('PRAGMA query_only=ON')
            if not db.execute('SELECT 1 FROM sqlite_master WHERE type="table" AND name=?',(table,)).fetchone():return []
            # table provém somente de constantes internas, nunca SQL de cliente.
            return [dict(r) for r in db.execute(f'SELECT * FROM "{table}" ORDER BY rowid DESC LIMIT ?',(limit,))]

    def password_state(self):
        path=self.root/'compartilhado/config/central_security.json'
        return dict(configured=bool(json_file(path).get('password_hash')))

    def _check_password(self,password):
        import secrets
        now=time.monotonic();self.password_failures=[t for t in self.password_failures if now-t<300]
        if len(self.password_failures)>=5:raise ValueError('Muitas tentativas. Aguarde 5 minutos.')
        settings=json_file(self.root/'compartilhado/config/central_security.json')
        if not settings.get('password_hash'):raise ValueError('Defina uma senha de exclusão primeiro.')
        if not isinstance(password,str) or len(password)>200:raise ValueError('Senha inválida.')
        expected=hashlib.scrypt(password.encode(),salt=bytes.fromhex(settings['salt']),n=16384,r=8,p=1).hex()
        if not secrets.compare_digest(expected,settings['password_hash']):
            self.password_failures.append(now);raise ValueError('Senha incorreta.')
        self.password_failures.clear()

    def set_password(self,data):
        if set(data)-{'password','password_confirm','old_password'}:raise ValueError('Campo inválido.')
        password=data.get('password')
        if not isinstance(password,str) or not 8<=len(password)<=200 or password!=data.get('password_confirm'):raise ValueError('Use uma senha de 8–200 caracteres e confirme-a.')
        with self.lock:
            path=self.root/'compartilhado/config/central_security.json'
            if self.password_state()['configured']:self._check_password(data.get('old_password',''))
            salt=os.urandom(16)
            settings=json_file(path);settings.update(salt=salt.hex(),password_hash=hashlib.scrypt(password.encode(),salt=salt,n=16384,r=8,p=1).hex(),algorithm='scrypt-16384-8-1')
            atomic_save(path,json.dumps(settings,indent=2)+'\n',revision(path))
            self.memory_grants.clear()
            return dict(configured=True)

    def memory_preview(self,data):
        from core import memory_maintenance
        if set(data)-{'entity','targets','all'}:raise ValueError('Campo inválido.')
        paths=self.paths(data.get('entity'))
        return memory_maintenance.plan(paths,data.get('targets'),data.get('all',False),shared_path=interentity.DB_PATH)

    def delete_memory(self,data):
        from core import memory_maintenance
        if set(data)-{'entity','targets','all','scope','fingerprint','password','confirm','request_id'}:raise ValueError('Campo inválido.')
        entity=data.get('entity');paths=self.paths(entity);identifier=data.get('request_id','')
        if data.get('confirm') is not True or not re.fullmatch('memory-[a-f0-9]{32}',identifier):raise ValueError('Exclusão requer confirmação e request ID.')
        if data.get('all')is True and data.get('scope')!=memory_maintenance.EXPERIENCE_SCOPE:
            raise ValueError('A limpeza completa agora inclui chat e conhecimento. Reabra a Central e confirme a nova prévia.')
        with self.lock:
            self._check_password(data.get('password',''))
            old=job_bus.get(identifier,entity)
            if old:
                if old['details'].get('fingerprint')!=data.get('fingerprint'):raise ValueError('Request ID já pertence a outra operação.')
                if data.get('all')is True and old['details'].get('scope')!=memory_maintenance.EXPERIENCE_SCOPE:
                    raise ValueError('Recibo antigo não comprova o novo escopo de limpeza.')
                if old['status']=='done':return old['details']['result']
                raise ValueError('Operação anterior não confirmada; não repetir. Consulte diagnóstico/backup.')
            with contextlib.ExitStack()as stack:
                for target in ENTITIES if data.get('all')is True else (entity,):stack.enter_context(self.idle_entity(target))
                if data.get('all')is True and job_bus.unresolved_maintenance(entity,memory_maintenance.EXPERIENCE_SCOPE):
                    raise ValueError('Limpeza completa anterior incerta; verificar backup/diagnóstico antes de nova tentativa.')
                preview=memory_maintenance.plan(paths,data.get('targets'),data.get('all',False),shared_path=interentity.DB_PATH)
                if preview['fingerprint']!=data.get('fingerprint'):raise ValueError('Memórias mudaram; refaça a prévia antes de apagar.')
                job_bus.publish(identifier,entity,'running',kind='memory_maintenance',fingerprint=preview['fingerprint'],scope=preview.get('scope','memories'),auto_retry=False)
                try:
                    result=memory_maintenance.delete(paths,preview)
                    job_bus.publish(identifier,entity,'done',kind='memory_maintenance',result=result,verified=True)
                    diagnostics.emit('central.memory_deleted',entity=entity,request_id=identifier,counts=result['counts'],verified=True)
                    return result
                except Exception as exc:
                    job_bus.publish(identifier,entity,'interrupted',kind='memory_maintenance',outcome='uncertain',error=type(exc).__name__,auto_retry=False)
                    diagnostics.persistence_failure('central.memory_delete',memory_maintenance.db_path(paths),exc,committed=True,request_id=identifier)
                    raise ValueError('Exclusão não confirmada; resultado possivelmente parcial. Não repita automaticamente. Consulte Diagnóstico e memory-backups da entidade.') from None

    def logic_models(self,entity,query):
        from memory import cognitive_notes
        paths=self.paths(entity)
        database=paths.memory/'sqlite'/('hoshino.db' if entity=='hoshino' else entity+'.db')
        if not database.exists():return dict(entity=entity,items=[],available=False)
        with cognitive_notes.administrative_scope(database,entity):
            return cognitive_notes.models(query.get('id'))

    def save_logic_model(self,data):
        from memory import cognitive_notes
        cognitive_notes.validate_graph(data.get('diagrama'))
        paths=self.paths(data.get('entity'))
        database=paths.memory/'sqlite'/('hoshino.db' if paths.id=='hoshino' else paths.id+'.db')
        if not database.exists():raise ValueError('Banco da entidade ainda não foi inicializado; não criar outro banco.')
        with self.idle_entity(paths.id):
            with cognitive_notes.administrative_scope(database,paths.id):
                cognitive_notes.model_evidence(data.get('evidencias'),data.get('modo','fundamentado'))
                if data.get('anterior'):cognitive_notes.models(data['anterior'])
            if shutil.disk_usage(paths.runtime).free < database.stat().st_size+1024**3:
                raise ValueError('Espaço insuficiente para backup e margem de 1 GiB.')
            backup_dir=paths.runtime/'memory-backups'/('logic-'+uuid.uuid4().hex)
            backup_dir.mkdir(parents=True,mode=0o700)
            with contextlib.closing(sqlite3.connect(database)) as original, contextlib.closing(sqlite3.connect(backup_dir/database.name)) as snapshot:
                original.backup(snapshot)
            os.chmod(backup_dir/database.name,0o600)
            with cognitive_notes.administrative_scope(database,paths.id):
                result=cognitive_notes.save_model(data.get('titulo'),data.get('diagrama'),data.get('evidencias'),
                    previous=data.get('anterior'),reason=data.get('motivo',''),mode=data.get('modo','fundamentado'))
        return dict(result,entity=paths.id,backup=str(backup_dir),apply='next_context',operator_edit=True)

    def memory(self, entity, query):
        if query.get('confidence') is not None:
            confidence=float(query['confidence'])
            if not math.isfinite(confidence) or not 0<=confidence<=1:raise ValueError('Confiança mínima deve ficar entre 0 e 1.')
        paths=self.paths(entity); path=paths.memory/'sqlite'/('hoshino.db' if entity=='hoshino' else entity+'.db')
        from memory.records import registro
        rows=[]
        chat_only=query.get('scope')=='chat'
        for table in (('episodes','context_summaries','alistair_turns') if chat_only else ('memories','properties','episodes','reflections','procedures','context_summaries','alistair_turns')):
            for raw in self.read_db(path,table,300):
                if table=='reflections' and raw.get('tipo')=='diario':continue  # explicit private reader only
                row=registro(raw) if table in {'memories','properties'} else dict(raw,tipo={'episodes':'episodio','reflections':'reflexao','procedures':'procedimento','context_summaries':'resumo','alistair_turns':'historico'}[table],evidencias=raw.get('context',raw.get('evidencias',raw.get('source_id'))))
                row.update(table=table,entity=entity,id=raw.get('id',raw.get('source_id')))
                if table=='properties': row['tipo']='propriedade'
                if query.get('type') and row['tipo']!=query['type']:continue
                text=json.dumps(row,ensure_ascii=False).casefold()
                if any(query.get(k) and str(query[k]).casefold() not in text for k in ('q','author','turn','source')):continue
                if query.get('confidence') is not None and row.get('confianca') is not None and row['confianca']<float(query['confidence']):continue
                rows.append(row)
        if chat_only:
            for raw in self.read_db(paths.runtime/'history.sqlite3','messages',150):
                if query.get('q') and str(query['q']).casefold() not in json.dumps(raw,ensure_ascii=False).casefold():continue
                rows.append(dict(raw,table='messages',entity=entity,tipo='historico_chat'))
        return dict(entity=entity,read_only=True,items=redact(rows[:150]),bounded_scan=True,
                    note='Até 300 registros recentes por categoria; ausente não significa inexistente. Origem antiga não é fabricada.')

    def knowledge(self, entity, query):
        """Read-only cards projected from this entity's existing semantic data.

        No LLM extraction, new database, identity inference, or diary access.
        """
        paths=self.paths(entity);database=paths.memory/'sqlite'/(entity+'.db')
        from core import knowledge_editor as editor
        from memory.records import card_targets, default_tier
        search=str(query.get('q','')).strip().casefold();kind=query.get('type','')
        if len(search)>200 or kind not in ('',*editor.KINDS):raise ValueError('Filtro de conhecimento inválido.')
        try:page=int(query.get('page',0))
        except (ValueError,TypeError):raise ValueError('Página inválida.') from None
        if not 0<=page<=10000:raise ValueError('Página inválida.')
        cards={};people={};names={};scanned={}
        def rows(table):
            values=self.read_db(database,table,300);scanned[table]=len(values)
            return [r for r in values if r.get('status','active')=='active']
        def card(identifier,title,category):
            return cards.setdefault(identifier,dict(id=identifier,title=str(title),kind=category,entity=entity,entries=[]))
        def entry(row,table,text,category,*,label='',resolution=None):
            confidence=row.get('confidence',row.get('confianca'))
            if type(confidence) not in (int,float) or not math.isfinite(confidence) or not 0<=confidence<=1:confidence=None
            refs=row.get('links',row.get('evidencias',[]))
            if isinstance(refs,str):
                try:refs=json.loads(refs)
                except ValueError:refs=[]
            if isinstance(refs,dict):refs=refs.get('sources',[])
            provenance=[{k:v for k,v in ref.items() if k in {'id','table','turn_id','author_id','sujeito_id','message_id'}}
                        for ref in refs if isinstance(ref,dict)] if isinstance(refs,list) else []
            return dict(table=table,record_id=row.get('id'),text=str(text or ''),type=category,label=label,
                        revision=editor.digest(row),fields=editor.editable(row,table),
                        confidence=confidence,source=row.get('source') or 'Origem não registrada',
                        created_at=row.get('created_at'),evidence=provenance,subject_resolution=resolution)
        for row in rows('people'):
            people[row['id']]=row;names.setdefault(str(row.get('nome','')).casefold(),[]).append(row['id'])
            c=card('person:'+row['id'],row.get('nome') or 'Pessoa sem nome','person')
            c['entries'].append(entry(row,'people',row.get('nome'),'nome',label='Nome',resolution='person_id'))
            for key,label in (('papel','Relação / papel registrado'),('apelidos','Outros nomes'),('notas','Observações registradas')):
                if row.get(key):c['entries'].append(entry(row,'people',row[key],'perfil',label=label,resolution='person_id'))
        for row in rows('properties'):
            title=str(row.get('entity') or 'Assunto não identificado');c=card('topic:'+title.casefold(),title,'item')
            c['entries'].append(entry(row,'properties',str(row.get('valor') or '')+(' '+str(row['unidade']) if row.get('unidade') else ''),'propriedade',label=row.get('chave','')))
        for row in rows('memories'):
            if row.get('type') in ('diario','private') or row.get('source')=='diario':continue
            targets=card_targets(row,people,names)
            for identifier,title,category,resolution in targets:
                c=card(identifier,title,category)
                c['entries'].append(entry(row,'memories',row.get('content'),row.get('type') or 'registro',resolution=resolution))
        for row in rows('procedures'):
            c=card('procedure:'+str(row['id']),row.get('nome') or 'Procedimento','procedure')
            for key,label in (('objetivo','Objetivo'),('precondicoes','Condições'),('passos','Passos'),('resultado_esperado','Resultado esperado')):
                if row.get(key):c['entries'].append(entry(row,'procedures',row[key],'procedimento',label=label))
        tiers=editor.tiers(database)
        for c in cards.values():
            c['importance']=tiers.get(c['id'],default_tier(c['id']))
            c['card_revision']=editor.card_revision(c)
        values=sorted(cards.values(),key=lambda c:(-editor.TIERS.index(c['importance']),c['kind'],c['title'].casefold(),c['id']))
        if query.get('id'):values=[c for c in values if c['id']==query['id']]
        values=[c for c in values if (not kind or c['kind']==kind) and (not search or search in json.dumps(c,ensure_ascii=False).casefold())]
        total=len(values);start=page*24
        return dict(entity=entity,items=redact(values[start:start+24]),total=total,page=page,has_more=start+24<total,
                    read_only=True,editable=True,bounded_scan=True,scanned=scanned,
                    note='Até 300 registros recentes por tabela. Cartões organizam registros, não confirmam fatos. Referência por nome não prova identidade. Diários e históricos brutos não são consultados.')

    def save_knowledge(self,data):
        from core import knowledge_editor
        paths=self.paths(data.get('entity'))
        with self.lock,self.idle_entity(paths.id):
            if data.get('action')=='importance':
                if set(data)!={'entity','action','card_id','card_revision','importance'}:raise ValueError('Alteração de importância inválida.')
                if not isinstance(data.get('card_id'),str) or not 1<=len(data['card_id'])<=1024:raise ValueError('Identificador do cartão inválido.')
                cards=self.knowledge(paths.id,{'id':data.get('card_id')})['items']
                if len(cards)!=1 or cards[0]['card_revision']!=data.get('card_revision'):raise ValueError('Cartão mudou; atualize antes de alterar a importância.')
                return knowledge_editor.set_importance(paths,data)
            if data.get('action')=='delete':self._check_password(data.get('password',''))
            if data.get('action')=='delete' and data.get('card_id'):
                cards=self.knowledge(paths.id,{'id':data['card_id']})['items']
                if len(cards)!=1 or cards[0]['card_revision']!=data.get('card_revision'):raise ValueError('Cartão mudou; atualize antes de apagar.')
                expected={(r['table'],r['record_id']) for r in cards[0]['entries']}
                selected={(r.get('table'),r.get('id')) for r in data.get('records',[]) if isinstance(r,dict)}
                if selected!=expected:raise ValueError('Seleção não corresponde aos registros do cartão.')
            result=knowledge_editor.mutate(paths,{k:v for k,v in data.items() if k!='password'})
        diagnostics.emit('central.knowledge_edited',entity=paths.id,action=data.get('action'),operator_edit=True)
        return result

    def timeline(self, entity, query):
        paths = self.paths(entity)
        kind = query.get('kind', '')
        level = query.get('level', '')
        if kind not in {'', 'message', 'event'} or level not in {'', 'INFO', 'WARN', 'ERROR', 'DEBUG'}:
            raise ValueError('Filtro de tipo ou nível inválido.')
        if (query.get('channel') and (level or kind == 'event')) or (level and kind == 'message'):
            raise ValueError('Canal filtra mensagens e nível filtra eventos.')
        page_size = self.ui_settings()['settings'].get('timeline_page_size', 50)
        if type(page_size) is not int or page_size not in {25, 50, 100}:
            page_size = 50
        @lru_cache(maxsize=64)
        def copied_text(name):
            try:
                data, _ = self.clipboard_attachment(entity, name)
                return data.decode('utf-8').casefold()
            except (OSError, ValueError):
                return ''

        def search_linked_text(source, folded):
            return any(folded in copied_text(name) for name in CLIPBOARD_ATTACHMENT.findall(source)
                       if name.endswith('.txt'))

        result = history.daily_records(
            query.get('day') or None, limit=page_size,
            offset=int(query.get('offset', 0)), query=query.get('q', '')[:200],
            channel=query.get('channel', ''), include_messages=kind != 'event' and not level,
            include_events=kind != 'message', severity=level, newest_first=True,
            search_linked_text=search_linked_text,
            db_path=paths.runtime / 'history.sqlite3', entity=entity,
            hide_routine=query.get('rotina') != '1',
        )
        return redact(dict(result, page_size=page_size))

    def activity(self, entity, query):
        since = history.timestamp_order(query['since']) if query.get('since') else None
        until = history.timestamp_order(query['until']) if query.get('until') else None
        if any(value is not None and not math.isfinite(value) for value in (since, until)):
            raise ValueError('Filtro temporal inválido; use data/hora ISO.')
        rows=[]
        # Central escreve no diagnóstico do processo hospedante, mas data.entity
        # identifica a entidade controlada. Consulta todos e filtra por autoria,
        # em vez de confundir diretório do logger com destinatário da operação.
        selected=ENTITIES
        for name in selected:
            paths=self.paths(name)
            for r in self.read_db(paths.runtime/'history.sqlite3','events',300):
                try:data=json.loads(r.get('data') or '{}')
                except ValueError:data={}
                rows.append(dict(entity=data.get('entity',name),id=r['id'],ts=r['ts'],event=r['kind'],level=r['severity'],turn_id=r.get('turn_id'),
                                 diagnostic_id=data.get('_diagnostic_id'),data=data))
            # Diagnostic logs têm lease/executor/audio quando history não tem.
            for path in sorted((paths.runtime/'diagnostics').glob('*.jsonl'))[-2:]:
                with path.open('rb') as log:
                    size=path.stat().st_size; log.seek(max(0,size-512*1024))
                    if size>512*1024:log.readline()
                    for line in log:
                        try:r=json.loads(line)
                        except ValueError:continue
                        if not isinstance(r,dict):continue
                        r['entity']=r.get('data',{}).get('entity',name);rows.append(r)
        rows=redact(rows)
        result=[];seen=set()
        for r in sorted(rows,key=lambda r:history.timestamp_order(r.get('ts','')),reverse=True):
            if entity and r.get('entity')!=entity:continue
            if query.get('level') and r.get('level')!=query['level']:continue
            if query.get('rotina')!='1' and history.evento_rotineiro(r.get('event'),r.get('data')):continue
            instant=history.timestamp_order(r.get('ts',''))
            if since is not None and instant<since:continue
            if until is not None and instant>until:continue
            if any(query.get(k) and str(query[k]).casefold() not in json.dumps(r,ensure_ascii=False).casefold() for k in ('q','turn','tool','origin')):continue
            ref=r.get('diagnostic_id')
            if ref and ref in seen:continue
            if ref:seen.add(ref)
            r['timestamp']=history.timestamp_details(r.get('ts',''))
            result.append(r)
        return dict(items=result[:200],bounded_scan=True,global_causal_order=False,
                    legacy_timezone_unknown=any(not r['timestamp']['timezone_known'] for r in result[:200]))

    def commands(self, entity):
        """Comandos da entidade: jobs em segundo plano, comandos rápidos do PC1 e pedidos feitos ao PC2 (06/11)."""
        paths=self.paths(entity); rows=[]
        for path in sorted((paths.runtime/'jobs').glob('job-*.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:30]:
            try:
                raw=json_file(path);log=paths.runtime/'jobs'/(path.stem+'.log');text=''
                if raw.get('entity') not in {None,entity}:continue
                if log.exists() and not log.is_symlink():
                    with log.open('rb') as f:
                        size=log.stat().st_size;f.seek(max(0,size-32768));text=f.read(32768).decode('utf-8','replace')
                rows.append({k:raw.get(k) for k in ('id','pid','comando','cwd','inicio','fim','codigo','status') }|dict(entity=entity,output=text,onde='PC1',stream='stdout+stderr combinados',read_only=True))
            except (OSError,ValueError):continue
        for path in sorted((paths.runtime/'comandos_recentes').glob('job-*.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:40]:
            try:
                raw=json_file(path)
                if raw.get('entity') not in {None,entity}:continue
                rows.append({k:raw.get(k) for k in ('id','comando','cwd','inicio','fim','codigo','status')}|dict(
                    entity=entity,output=raw.get('saida') or '',onde='PC1',stream='stdout+stderr combinados',read_only=True))
            except (OSError,ValueError):continue
        from core import pc2_remoto
        try:
            with pc2_remoto._conn(self.root) as conn:
                pc2_rows=[dict(r) for r in conn.execute("SELECT * FROM comandos WHERE entidade=? ORDER BY criado DESC LIMIT 30",(entity,))]
        except sqlite3.Error:
            pc2_rows=[]
        for r in pc2_rows:
            comando='(print da tela)' if r.get('tipo')=='tela' else r['comando']
            rows.append(dict(id=r['id'],comando=comando,cwd='~ (PC2)',inicio=datetime.fromtimestamp(r['criado']).isoformat(),
                             fim=datetime.fromtimestamp(r['terminado']).isoformat() if r.get('terminado') else None,
                             codigo=r.get('codigo'),status=r['status'],entity=entity,onde='PC2',
                             output=(r.get('saida') or '') if r.get('tipo')!='tela' else (r.get('saida') or ''),
                             stream='stdout+stderr combinados',read_only=True))
        rows.sort(key=lambda r:str(r.get('inicio') or ''),reverse=True)
        return dict(items=redact(rows[:60]),cancel='solicite à entidade pelo chat; sem terminal irrestrito')

    def resource_profile_observations(self):
        """Última escolha na cauda limitada dos diagnósticos, não estado vivo.

        Só projeta campos técnicos conhecidos; não retorna mensagens/diários e
        não cria decisão ao abrir a aba de Recursos.
        """
        from core.resource_profiles import PROFILES
        observations = {}
        for entity in ENTITIES:
            found = None
            for path in sorted((self.paths(entity).runtime/'diagnostics').glob('*.jsonl'))[-2:]:
                try:
                    with path.open('rb') as log:
                        size = path.stat().st_size; log.seek(max(0, size-128*1024))
                        if size > 128*1024: log.readline()
                        for line in log:
                            try: row = json.loads(line)
                            except ValueError: continue
                            if not isinstance(row, dict) or row.get('event') != 'executor.selected': continue
                            data = row.get('data') or {}
                            if not isinstance(data, dict) or data.get('entity') != entity: continue
                            profile = data.get('resource_profile')
                            if not isinstance(profile, dict): continue
                            identifier = profile.get('id')
                            preset = PROFILES.get(identifier) if isinstance(identifier,str) else None
                            if not preset: continue
                            found = dict(entity=entity, ts=row.get('ts'), model=data.get('model'), tier=data.get('tier'),
                                         id=preset.id, label=preset.label,
                                         reason=profile.get('reason'), requested=profile.get('requested'),
                                         held=profile.get('held') is True)
                except OSError: continue
            observations[entity] = found
        return observations

    def gpu_alerts(self):
        """Alerta na tela (pedido humano 06/11): entidade acordada sem conseguir a GPU por falta de VRAM.

        Só leitura: a mesma decisão do RM (assess_gpu) sobre o pedido real da fila, sem compute ativo, como a
        manutenção exclusiva. Nunca fecha app, descarrega modelo ou muda configuração. O alerta continua entre
        as tentativas (a espera de 120 s expira e a próxima iniciativa volta minutos depois) até a VRAM que falta
        aparecer, a entidade conseguir a GPU ou dormir.
        """
        try:
            return self._gpu_alerts(time.time())
        except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
            return dict(alerts=[], unavailable=type(exc).__name__)

    def _awake(self, entity):
        proc = getattr(self.supervisor, 'processes', {}).get(entity)
        if proc is not None and proc.poll() is None:
            return True
        return (interentity.presence(entity) or {}).get('status') not in {None, 'offline', 'sleeping', 'stopping'}

    def _gpu_alerts(self, now):
        from core import gpu_metrics, vram_guard
        state = resource_manager.gpu_state()
        metrics, policy, models = state['metrics'], state['policy'], state['residency']
        if not metrics.get('known') or not metrics.get('total_bytes'):
            return dict(alerts=[], unavailable='vram_desconhecida')
        users = None

        def card():
            nonlocal users
            if users is None:
                pdev = vram_guard.gpu_pdev(metrics)
                users = [dict(u, entity=_model_entity(u.pop('cmd', ''))) for u in vram_guard.gpu_users(pdev=pdev)] if pdev else []
            return users
        waiting = {}
        for row in state['queue']:
            req = row.get('request') or {}
            if row.get('state') == 'waiting' and req.get('owner') in {'llm', 'vision'} and req.get('entity') in ENTITIES:
                waiting.setdefault(req['entity'], []).append(row)
        running = {r.get('entity') for r in state['compute']}
        with self.gpu_alert_lock:
            for entity in ENTITIES:
                block = self.gpu_blocks.get(entity)
                if entity in running or not self._awake(entity):
                    self.gpu_blocks.pop(entity, None)
                    continue
                rows = waiting.get(entity, [])
                if not rows:
                    # Entre tentativas: some quando a VRAM que faltava aparecer (app fechado, modelo descarregado).
                    if block and vram_guard.deficit_bytes(dict(additional_bytes=block['additional']), metrics, policy) <= 0:
                        self.gpu_blocks.pop(entity, None)
                    elif block:
                        block['message_waiting'] = False
                    continue
                oldest = min(rows, key=lambda r: r['enqueued_at'])
                req = oldest['request']
                peers = [m for m in models if m.get('model_key') != req.get('model_key') and m.get('vram_bytes')]
                if block is None and now - oldest['enqueued_at'] < (GPU_ALERT_PEER_SECONDS if peers else GPU_ALERT_SECONDS):
                    continue
                # Modelo inteiro já na placa: prova do RM (≤15 s) ou o próprio llama-server visto no fdinfo agora.
                whole = bool(req.get('resident_full')) and (
                    resource_manager.resident_whole(models, req.get('model_key'), req.get('resident_ctx')) or
                    any(u['kind'] == 'modelo' and u['entity'] == entity and u['vram_bytes'] >= 0.9 * req['vram_bytes']
                        for u in card()))
                decision = resource_manager.assess_gpu(dict(req, resident_full=whole), metrics, (), models, policy, now=now)
                if decision['reason'] == 'uncertain_vram':
                    continue
                if decision['reason'] not in resource_manager._MEMORY_REASONS:
                    self.gpu_blocks.pop(entity, None)
                    continue
                message = any(r['priority'] <= 1 for r in rows)
                self.gpu_blocks[entity] = dict(
                    since=(block or {}).get('since', oldest['enqueued_at']), additional=decision['additional_bytes'],
                    reason=decision['reason'], budget=req['vram_bytes'], waiting_since=oldest['enqueued_at'],
                    message_waiting=message, message_seen=message or (block or {}).get('message_seen', False))
            blocks = {e: dict(b) for e, b in self.gpu_blocks.items()}
        alerts = [self._gpu_alert(entity, block, metrics, policy, card(), now) for entity, block in blocks.items()]
        return dict(alerts=alerts, checked_at=now)

    def _gpu_alert(self, entity, block, metrics, policy, users, now):
        from core import gpu_metrics, vram_guard
        name, art = entity.capitalize(), ARTICLES[entity]
        limit = min(gpu_metrics.HARD_LIMIT, metrics['total_bytes'])
        margin = policy['margin_bytes']
        missing = vram_guard.deficit_bytes(dict(additional_bytes=block['additional']), metrics, policy)
        lines = []
        if block['reason'] == 'estimate_exceeds_hard_limit':
            lines.append(f'{name} pede mais VRAM do que a placa comporta ({_mib(block["budget"] + margin)} com a margem, '
                         f'de {_mib(limit)}).')
        else:
            lines.append(f'{name} não consegue usar a GPU: faltam {_mib(missing)} para manter a margem de segurança '
                         f'de {_mib(margin)}.')
        if block['message_waiting']:
            lines.append(f'Sua mensagem está esperando há {int(now - block["waiting_since"])} s.')
        elif block['message_seen']:
            lines.append('Uma mensagem sua ficou sem resposta por isso.')
        parts = []
        for u in users[:6]:
            if u['kind'] == 'modelo':
                label = f'modelo d{ARTICLES[u["entity"]]} {u["entity"].capitalize()}' if u['entity'] else 'outro modelo'
            else:
                label = APP_LABELS.get(u['name'], u['name'])
            parts.append(f'{label} {_mib(u["vram_bytes"])}')
        if parts:
            lines.append('Na placa: ' + ' · '.join(parts) + f' (livre {_mib(max(0, limit - metrics["used_bytes"]))}).')
        fixes, close, layers = [], [], None
        apps = sorted((u for u in users if u['kind'] == 'app'), key=lambda u: -u['vram_bytes'])
        if block['reason'] == 'vram_pressure' and missing and sum(u['vram_bytes'] for u in apps) >= missing:
            freed = 0
            for u in apps:
                close.append(APP_LABELS.get(u['name'], u['name'])); freed += u['vram_bytes']
                if freed >= missing:
                    break
            fixes.append(f'feche {" e ".join(close)} (libera {_mib(freed)})')
        for u in users:
            if u['kind'] == 'modelo' and u['entity'] and u['entity'] != entity:
                other = u['entity'].capitalize()
                fixes.append(f'faça {ARTICLES[u["entity"]]} {other} dormir (o modelo {POSSESSIVE[u["entity"]]} ocupa {_mib(u["vram_bytes"])})')
        choice = self.gpu_layers(entity)
        if choice:
            env = self.env(entity)
            context = int(env.get('HOSHINO_CONTEXT_TOKENS', env.get('HOSHINO_NUM_CTX', 16384)))
            ladder = dict(resource_manager.offload_ladder_9b(context))
            fixed = choice['fixed']
            if fixed in ladder:
                lower = [n for n in sorted(ladder, reverse=True)
                         if n < fixed and (ladder[fixed] - ladder[n]) * gpu_metrics.GIB >= missing + 64 * MIB_BYTES]
                if lower:
                    layers = lower[0]
                    saved = f'{ladder[fixed] - ladder[layers]:.1f}'.replace('.', ',')
                    fixes.append(f'faça {art} {name} dormir, escolha {layers} camadas na GPU na aba Modelos e acorde-{art} '
                                 f'(o degrau fixo de {fixed} camadas não recua sozinho; libera cerca de {saved} GiB)')
            elif fixed is None:
                fixes.append(f'faça {art} {name} dormir e acordar (no automático o degrau é escolhido pela VRAM livre)')
        if block['reason'] == 'vram_pressure' and missing:
            lower = [m for m in resource_manager.MARGIN_OPTIONS_MIB if m * MIB_BYTES <= margin - missing]
            if lower:
                fixes.append(f'baixe a margem de VRAM em Configurações para {max(lower)} MiB')
        if not fixes:
            fixes.append(f'faça {art} {name} dormir e reduza o contexto na aba Modelos')
        lines.append('Para resolver: ' + '; ou '.join(fixes) + '.')
        return dict(entity=entity, key=f'{entity}:{int(block["since"])}', since=block['since'],
                    title=f'{name} está sem VRAM', text='\n'.join(lines), reason=block['reason'],
                    missing_mib=missing // MIB_BYTES, message_waiting=block['message_waiting'],
                    message_missed=block['message_seen'] and not block['message_waiting'],
                    close_apps=close, suggested_layers=layers)

    def vram_settings(self):
        """Margem de VRAM (pedido humano 06/11): quanto da placa os modelos podem usar. Vale no próximo pedido de GPU."""
        from core import gpu_metrics
        path = self.root / 'compartilhado/config/gpu.json'
        metrics = gpu_metrics.snapshot()
        margin = resource_manager.gpu_policy()['margin_bytes']
        total = metrics.get('total_bytes') if metrics.get('known') else None
        limit = min(gpu_metrics.HARD_LIMIT, total) if total else None
        mib = lambda v: None if v is None else int(v) // MIB_BYTES
        return dict(margin_mib=mib(margin), options=list(resource_manager.MARGIN_OPTIONS_MIB),
                    minimum_mib=mib(resource_manager.MARGIN_MIN_BYTES), default_mib=768,
                    total_mib=mib(total), used_mib=mib(metrics.get('used_bytes')) if total else None,
                    usable_mib=mib(limit - margin) if limit else None, revision=revision(path), apply='immediate')

    def save_vram(self, data):
        if set(data) - {'margin_mib', 'revision'}:
            raise ValueError('Campo inválido.')
        value = data.get('margin_mib')
        if type(value) is not int or value not in resource_manager.MARGIN_OPTIONS_MIB:
            raise ValueError('Escolha uma margem entre ' + ', '.join(map(str, resource_manager.MARGIN_OPTIONS_MIB)) + ' MiB.')
        path = self.root / 'compartilhado/config/gpu.json'
        with self.lock:
            if revision(path) != data.get('revision'):
                raise ValueError('Configuração de GPU mudou; recarregue antes de salvar.')
            doc = json_file(path)
            if not isinstance(doc, dict):
                raise ValueError('compartilhado/config/gpu.json inválido; nada foi gravado.')
            previous = doc.get('margin_bytes')
            doc['margin_bytes'] = value * MIB_BYTES
            atomic_save(path, json.dumps(doc, ensure_ascii=False, indent=2) + '\n', data.get('revision'))
            diagnostics.emit('central.vram_margin_saved', margin_mib=value,
                             previous_mib=int(previous) // MIB_BYTES if isinstance(previous, (int, float)) else None)
        return dict(self.vram_settings(), saved=True)

    def api_settings(self):
        """APIs de modelo (pedido humano 07/11): cadastro e quem usa qual. A chave nunca volta: só "salva" ou não."""
        from core import executor_api as ea
        cadastro = ea.carregar()
        situacao = ea.situacao()
        apis = [dict(id=i, nome=a['nome'], provedor=a['provedor'], rotulo=ea.PROVEDORES[a['provedor']]['rotulo'],
                     situacao=situacao.get(i),
                     url=a['url'], modelo=ea.modelo_de(a), url_efetiva=ea.url_de(a),
                     tem_chave=bool(ea.chave_de(i, a['provedor'])),
                     usada_por=[e for e, x in cadastro['entidades'].items() if x == i])
                for i, a in sorted(cadastro['apis'].items())]
        provedores = [dict(id=p, rotulo=c['rotulo'], modelo=c['modelo'], url=c['url']) for p, c in ea.PROVEDORES.items()]
        return dict(apis=apis, entidades=cadastro['entidades'], provedores=provedores,
                    revision=revision(ea.ARQUIVO_ESCOLHA), apply='immediate',
                    aviso='Com uma API escolhida, as conversas e memórias daquela entidade saem deste PC. Se a API '
                          'falhar ou a cota acabar, a entidade volta sozinha para o modelo local.')

    def save_api(self, data):
        from core import executor_api as ea
        acao = data.get('action')
        permitidos = {'salvar': {'action', 'revision', 'id', 'nome', 'provedor', 'url', 'modelo', 'chave'},
                      'remover': {'action', 'revision', 'id'},
                      'atribuir': {'action', 'revision', 'entity', 'id'},
                      'apagar_chave': {'action', 'revision', 'id'}}
        if acao not in permitidos or set(data) - permitidos[acao]:
            raise ValueError('Pedido de API inválido.')
        with self.lock:
            if revision(ea.ARQUIVO_ESCOLHA) != data.get('revision'):
                raise ValueError('As APIs mudaram; recarregue antes de salvar.')
            cadastro = ea.carregar()
            ident = data.get('id')
            if acao == 'salvar':
                provedor = data.get('provedor')
                if provedor not in ea.PROVEDORES:
                    raise ValueError('Provedor inválido.')
                nome = str(data.get('nome') or '').strip()[:60]
                modelo = str(data.get('modelo') or '').strip()[:120]
                url = str(data.get('url') or '').strip()[:300]
                if not nome:
                    raise ValueError('Dê um nome para a API.')
                if url and not re.fullmatch(r'https?://[^\s]+', url):
                    raise ValueError('Endereço inválido (use http:// ou https://).')
                if not (url or ea.PROVEDORES[provedor]['url']):
                    raise ValueError('Para "Outra", informe o endereço (…/v1/chat/completions).')
                if not (modelo or ea.PROVEDORES[provedor]['modelo']):
                    raise ValueError('Informe o modelo.')
                if not ident:
                    import unicodedata
                    simples = ''.join(ch for ch in unicodedata.normalize('NFKD', nome.lower()) if not unicodedata.combining(ch))
                    base = re.sub(r'[^a-z0-9]+', '-', simples).strip('-')[:30] or provedor
                    ident = base
                    n = 2
                    while ident in cadastro['apis']:
                        ident = f'{base}-{n}'; n += 1
                elif ident not in cadastro['apis']:
                    raise ValueError('API não encontrada.')
                cadastro['apis'][ident] = dict(nome=nome, provedor=provedor, url=url, modelo=modelo)
                chave = data.get('chave')
                if isinstance(chave, str) and chave.strip():
                    ea.guardar_chave(ident, chave.strip())
            elif acao == 'remover':
                if ident not in cadastro['apis']:
                    raise ValueError('API não encontrada.')
                del cadastro['apis'][ident]
                cadastro['entidades'] = {e: (None if x == ident else x) for e, x in cadastro['entidades'].items()}
                ea.guardar_chave(ident, None)
            elif acao == 'apagar_chave':
                if ident not in cadastro['apis']:
                    raise ValueError('API não encontrada.')
                ea.guardar_chave(ident, None)
            else:
                entidade = data.get('entity')
                if entidade not in ea.ENTIDADES:
                    raise ValueError('Entidade inválida.')
                if ident is not None and ident not in cadastro['apis']:
                    raise ValueError('API não encontrada.')
                cadastro['entidades'][entidade] = ident
            ea.gravar(cadastro)
            diagnostics.emit('central.api_saved', action=acao, api=ident, entity=data.get('entity'),
                             key_changed=bool(acao == 'salvar' and str(data.get('chave') or '').strip()))
        return dict(self.api_settings(), saved=True)

    def system(self):
        memory={}
        try:
            memory={p[0].rstrip(':'):int(p[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines() if len(p:=line.split())>=2}
        except (OSError,ValueError):pass
        cpu=None
        try:
            values=[int(v) for v in Path('/proc/stat').read_text().splitlines()[0].split()[1:9]]
            total,idle=sum(values),values[3]+values[4]
            if self.cpu_previous and total>self.cpu_previous[0]:cpu=round(100*(1-(idle-self.cpu_previous[1])/(total-self.cpu_previous[0])),1)
            self.cpu_previous=(total,idle)
        except (OSError,ValueError,IndexError):pass
        gpu=resource_manager.gpu_state()
        leases=[dict(r,lease_id=r.get('token')) for r in resource_manager.status()]
        gpu['queue']=[dict(r,request_id=r.get('token')) for r in gpu.get('queue',[])]
        gpu['compute']=[dict(r,lease_id=r.get('token')) for r in gpu.get('compute',[])]
        from core.resource_profiles import catalog
        return dict(cpu_percent=cpu,ram_total=memory.get('MemTotal'),ram_available=memory.get('MemAvailable'),
                    swap_total=memory.get('SwapTotal'),swap_free=memory.get('SwapFree'),
                    disk_free=shutil.disk_usage(self.root).free,gpu=gpu,leases=leases,
                    resource_profiles=dict(available=catalog(), observations=self.resource_profile_observations(),
                                           state='last_observed_not_live', boundary='next_inference_cycle',
                                           basis='heuristic_not_benchmark'),
                    ram_prompt_cache=resource_manager.ram_prompt_cache_plan(memory={
                        'total_bytes':memory.get('MemTotal'), 'available_bytes':memory.get('MemAvailable')}))

    def capabilities(self,entity='hoshino'):
        # Exposição de catálogo, não implantação de ferramentas pela central.
        from core.capabilities import READ_ONLY, VERIFY
        self.paths(entity)
        # Lê declarações existentes sem importar dispatch (que abre componentes
        # mentais/integrações). Não cria outro registro de execução de ferramentas.
        app=Path(__file__).resolve().parents[1]
        source=app/'alistair_runner.py' if entity=='alistair' else app/'core/dispatch.py'
        function='_tool' if entity=='alistair' else '_f'
        tree=ast.parse(source.read_text());declared={call.args[0].value for call in ast.walk(tree)
                if isinstance(call,ast.Call) and isinstance(call.func,ast.Name) and call.func.id==function
                and call.args and isinstance(call.args[0],ast.Constant) and isinstance(call.args[0].value,str)}
        names=sorted(declared); groups={};observations={}
        for owner in (entity,):
            for event in self.activity(owner,{'q':'tool.'})['items']:
                name=event.get('data',{}).get('tool')
                if name and name not in observations:observations[name]=dict(entity=owner,ts=event.get('ts'),event=event.get('event'),data=event.get('data'))
        for name in names:
            category=('Minecraft' if name.startswith('minecraft') else 'Discord' if name.startswith('discord') else
                      'Imagem' if name in {'gerar_imagem','estado_imagem'} else
                      'Memória' if any(w in name for w in ('memoria','conhecimento','propriedade','lembr','historico')) else
                      'Áudio' if any(w in name for w in ('voz','audio','microfone','ouvir','escuta')) else
                      'Entidades/recursos' if name.startswith(('entidades','recursos')) else 'Arquivos/sistema/ferramentas')
            groups.setdefault(category,[]).append(dict(name=name,enabled=ui_policy.allowed(self.root,entity,name),contract='read_only' if name in READ_ONLY else 'requires_verification' if name in VERIFY else 'contract_in_backend',
                                                     last_observation=observations.get(name)))
        legacy=ui_policy.disabled(self.root,entity);controls=[]
        for key,label,description in ui_policy.CAPABILITIES:
            related={name for name in names if key in ui_policy.requirements(name)}
            if not related and key!='ambient':continue
            restricted=len(related&legacy) if '*' not in legacy else len(related) or 1
            controls.append(dict(key=key,label=label,description=description,
                enabled=ui_policy.capability_allowed(self.root,entity,key),legacy_restrictions=restricted))
        return dict(entity=entity,groups=groups,controls=controls,revision=revision(self.root/'compartilhado/config/interface.json'),
            note='Permissões da entidade selecionada. Memórias, personalidade e conversa local não são ferramentas e ficam fora desta aba. Desativar bloqueia novos usos; não cancela efeito já iniciado. Reativar não liga serviços nem captura áudio sozinho.')

    def save_tools(self,data):
        entity=data.get('entity');self.paths(entity)
        if set(data)-{'entity','disabled','capabilities','revision'}:raise ValueError('Campo não suportado.')
        if 'capabilities' in data:
            if 'disabled' in data:raise ValueError('Use somente um formato de política.')
            changes=data['capabilities'];catalog=self.capabilities(entity)
            known={item['key'] for item in catalog['controls']}
            if not isinstance(changes,dict) or not changes or any(k not in known or type(v) is not bool for k,v in changes.items()):
                raise ValueError('Escolha capacidades válidas e valores ligado/desligado.')
            with self.lock:
                path=self.root/'compartilhado/config/interface.json';settings=self.ui_settings()['settings']
                legacy=ui_policy.disabled(self.root,entity)
                if '*' in legacy:raise ValueError('Política antiga inválida; confira a configuração antes de habilitar capacidades.')
                blocked=ui_policy.disabled_capabilities(self.root,entity)
                if 'workspace' in legacy and {'read','write'}&changes.keys():
                    blocked.update(('read','write'));legacy.remove('workspace')
                for key,value in changes.items():
                    if value:
                        blocked.discard(key)
                        legacy={name for name in legacy if key not in ui_policy.requirements(name)}
                    else:blocked.add(key)
                settings.setdefault('disabled_tools',{})[entity]=sorted(legacy)
                settings.setdefault('disabled_capabilities',{})[entity]=sorted(blocked)
                rev=atomic_save(path,json.dumps(settings,ensure_ascii=False,indent=2)+'\n',data.get('revision'))
                diagnostics.emit('central.capabilities_saved',entity=entity,changes=changes)
                return dict(saved=True,revision=rev,apply='next_tool_call',cancel_running=False)
        names=ui_policy.validate_names(data.get('disabled'))
        known={t['name'] for tools in self.capabilities(entity)['groups'].values() for t in tools}
        if any(n not in known and not n.startswith('propria_') for n in names):raise ValueError('Ferramenta desconhecida.')
        with self.lock:
            path=self.root/'compartilhado/config/interface.json';settings=self.ui_settings()['settings']
            settings.setdefault('disabled_tools',{})[entity]=names
            rev=atomic_save(path,json.dumps(settings,ensure_ascii=False,indent=2)+'\n',data.get('revision'))
            diagnostics.emit('central.tools_saved',entity=entity,disabled_count=len(names))
            return dict(saved=True,revision=rev,apply='next_tool_call',cancel_running=False)

    def microphone(self):
        defaults=dict(mode='command',source='',output='',threshold=.012,silence_ms=2000,segment_seconds=8,auto_send=False,output_volume=100,hotkey_enabled=False,hotkey='Ctrl+Alt+Space')
        defaults.update(self.ui_settings()['settings'].get('microphone',{}))
        defaults['mode']={'manual':'command','open':'detection'}.get(defaults['mode'],defaults['mode'])
        return dict(settings=defaults,revision=self.ui_settings()['revision'],
                    ambient_allowed={e:ui_policy.capability_allowed(self.root,e,'ambient') for e in ENTITIES},
                    note='Captura só após clique. Detecção por energia; ASR/VAD existentes validam a transcrição. Rascunho por padrão.')

    def save_microphone(self,data):
        if set(data)-{'settings','revision'}:raise ValueError('Campo não suportado.')
        settings=data.get('settings')
        if not isinstance(settings,dict) or set(settings)-{'mode','source','output','threshold','silence_ms','segment_seconds','auto_send','output_volume','hotkey_enabled','hotkey'}:raise ValueError('Configuração inválida.')
        current=self.microphone()['settings'];current.update(settings)
        if current['mode'] not in {'command','detection'}:raise ValueError('Modo inválido; escolha comando ou detecção.')
        for key in ('source','output'):
            if not isinstance(current[key],str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{0,250}',current[key]):raise ValueError('Dispositivo inválido.')
        if type(current['threshold']) not in {float,int} or not math.isfinite(current['threshold']) or not .002<=current['threshold']<=.2:raise ValueError('Limiar entre 0,002 e 0,2.')
        for key,low,high in [('silence_ms',300,3000),('segment_seconds',3,45)]:
            if type(current[key]) is not int or not low<=current[key]<=high:raise ValueError('Duração inválida.')
        if type(current['auto_send']) is not bool:raise ValueError('Envio automático deve ser booleano.')
        if type(current['hotkey_enabled']) is not bool:raise ValueError('Habilitação do atalho deve ser booleana.')
        from tools.microfone_controle import central_hotkey
        central_hotkey(current['hotkey'])
        if type(current['output_volume']) is not int or not 0<=current['output_volume']<=100:raise ValueError('Volume deve ser inteiro entre 0 e 100%.')
        with self.lock:
            path=self.root/'compartilhado/config/interface.json';out=self.ui_settings()['settings'];out['microphone']=current
            rev=atomic_save(path,json.dumps(out,ensure_ascii=False,indent=2)+'\n',data.get('revision'))
            return dict(saved=True,revision=rev,apply='next_capture')

    def entities(self):
        with self.lock:
            if time.monotonic()-self.entity_cache[0]<10 and self.entity_cache[1]:return self.entity_cache[1]
            result={};audio=self.audio_settings()
            for entity in ENTITIES:
                paths=self.paths(entity);events=self.activity(entity,{})['items'];env=self.env(entity)
                llm=next((r for r in events if r.get('event') in {'llm.start','executor.selected','alistair.llm_start'}),None)
                error=next((r for r in events if r.get('level')=='ERROR'),None)
                psych=json_file(paths.runtime/'estado_psicologico.json',None)
                mental=json_file(paths.runtime/'estado_mente.json',None)
                from core import activity_context
                from mind import emotions
                last_action=next((r for r in events if r.get('event','').startswith(('tool.','minecraft.','voice.'))),None)
                result[entity]=dict(configured_primary=env.get('HOSHINO_MODEL',MODEL_DEFAULTS[entity]),
                                    configured_light=json_file(paths.config/'executores.json').get('light'),
                                    configured_companion=json_file(paths.config/'executores.json').get('companion'),
                                    executor_observation=llm,last_action=last_action,last_error=error,
                                    psychological_state=psych or None,
                                    activity_context=activity_context.view(mental,entity=entity),
                                    expression_profile=emotions.visual_profile(mental) if entity!='alistair' else {'available':False,'voice_modulation_applied':False},
                                    pending_messages=len(interentity.inbox(entity,limit=200)),queue_count_bounded=True,
                                    tts='text_only' if entity=='alistair' else dict(preferred=audio['preferred_provider'],providers=audio['providers']),
                                    minecraft='consulte recibos/atividade; conexão não sondada nesta consulta' if entity!='alistair' else 'não se aplica',
                                    discord='consulte atividade; conexão não confirmada pela presença')
            self.entity_cache=(time.monotonic(),result)
            return redact(result)

    def ui_settings(self):
        path=self.root/'compartilhado/config/interface.json'
        return dict(settings=json_file(path,dict(overlay_enabled=False,always_on_top=True,balloons=True,balloon_seconds=7,silent=False)),revision=revision(path))

    def save_ui(self,data):
        if set(data)-{'entity','revision','settings'}:raise ValueError('Campo inválido.')
        supplied=data.get('settings');allowed={'overlay_enabled','always_on_top','balloons','balloon_seconds','silent','positions','reduced_motion','orb_styles','clipboard_import','clipboard_auto','timeline_page_size'}
        if not isinstance(supplied,dict) or set(supplied)-allowed:raise ValueError('Configuração de interface inválida.')
        for k,v in supplied.items():
            if k=='orb_styles':
                if not isinstance(v,dict) or set(v)-set(ENTITIES):raise ValueError('Entidade de orb inválida.')
                for style in v.values():
                    if not isinstance(style,dict) or set(style)-{'mode','base_color','image_path','mood_tint'}:raise ValueError('Estilo de orb inválido.')
                    if style.get('mode','energy') not in {'energy','image'}:raise ValueError('Modo de orb inválido.')
                    if not re.fullmatch(r'#[0-9a-fA-F]{6}',style.get('base_color','#c6a3ed')):raise ValueError('Cor de orb inválida.')
                    if type(style.get('mood_tint',True)) is not bool:raise ValueError('Humor visual deve ser booleano.')
                    image=style.get('image_path','')
                    if not isinstance(image,str) or len(image)>4096:raise ValueError('Imagem inválida.')
                    if image:
                        image_path=Path(image)
                        if not image_path.is_absolute() or image_path.suffix.lower() not in {'.png','.jpg','.jpeg','.webp'}:raise ValueError('Use imagem local PNG, JPEG ou WebP.')
                        if not image_path.is_file() or image_path.stat().st_size>10*1024**2:raise ValueError('Imagem ausente ou acima de 10 MiB.')
            if k in {'overlay_enabled','always_on_top','balloons','silent','reduced_motion','clipboard_import','clipboard_auto'} and type(v) is not bool:raise ValueError('Valor deve ser booleano.')
            if k=='timeline_page_size' and (type(v) is not int or v not in {25, 50, 100}):
                raise ValueError('Escolha 25, 50 ou 100 registros por página.')
            if k=='balloon_seconds' and (type(v) is not int or not 2<=v<=20):raise ValueError('Duração entre 2 e 20 segundos.')
            if k=='positions':
                if not isinstance(v,dict) or set(v)-set(ENTITIES):raise ValueError('Posições inválidas.')
                for pos in v.values():
                    if not isinstance(pos,list) or len(pos)!=2 or any(type(x) is not int or not -20000<=x<=20000 for x in pos):raise ValueError('Posição inválida.')
        with self.lock:
            path=self.root/'compartilhado/config/interface.json';settings=self.ui_settings()['settings'];settings.update(supplied)
            rev=atomic_save(path,json.dumps(settings,ensure_ascii=False,indent=2)+'\n',data.get('revision'))
            return dict(saved=True,revision=rev,apply='immediate')

    def model_files(self):
        rows={}
        base=self.root/'compartilhado/modelos'
        def add(path,consumer=None,sha=None):
            if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(base.resolve()):return
            rel=str(path.relative_to(base));identifier=hashlib.sha256(rel.encode()).hexdigest()[:24]
            row=rows.setdefault(identifier,dict(id=identifier,path=str(path),name=path.name,size_bytes=path.stat().st_size,
                                               sha256=sha,hash_verified=False,consumers=[]))
            if consumer and consumer not in row['consumers']:row['consumers'].append(consumer)
        for entity in ENTITIES:
            for model in self.models(entity):
                for file in model['files']:add(Path(file['path']),entity,file['sha256'])
        for folder in ('imagem','voz','importados'):
            directory=base/folder
            for path in sorted(directory.rglob('*')) if directory.is_dir() else []:
                if len(rows)>=250:break
                if path.suffix in {'.gguf','.safetensors','.onnx','.pt'}:add(path)
        return dict(items=list(rows.values()),disk_free=shutil.disk_usage(self.root).free,
                    reserve_bytes=4*1024**3,note='Hash de manifesto é esperado, não verificação integral. Importados não são novos executores. Sem exclusão automática.')

    def file_path(self, identifier):
        row=next((r for r in self.model_files()['items'] if r['id']==identifier),None)
        if not row:raise ValueError('Arquivo não pertence ao inventário local.')
        return Path(row['path'])

    def begin_import(self,data):
        if set(data)-{'entity','name','size','sha256'}:raise ValueError('Campo inválido.')
        entity=data.get('entity','hoshino');self.paths(entity)
        name=data.get('name','');size=data.get('size');sha=data.get('sha256')
        if not isinstance(name,str) or not re.fullmatch(r'[\w .-]{1,150}\.gguf',name) or '..' in name:
            raise ValueError('Importação aceita nome local GGUF sem caminho.')
        if type(size) is not int or not 8<=size<=12*1024**3:raise ValueError('Tamanho GGUF inválido (até 12 GiB).')
        if sha is not None and not re.fullmatch('[a-f0-9]{64}',str(sha)):raise ValueError('SHA-256 inválido.')
        with self.lock:
            if any(t['state'] in {'receiving','copying','verifying'} for t in self.transfers.values()):raise ValueError('Uma transferência por vez para preservar disco/RAM.')
            directory=self.root/'compartilhado/modelos/importados';directory.mkdir(parents=True,exist_ok=True)
            if directory.is_symlink() or not directory.resolve().is_relative_to(self.root):raise ValueError('Diretório importado não pode apontar para fora do projeto.')
            if shutil.disk_usage(directory).free<size+4*1024**3:raise ValueError('Espaço insuficiente; reserva obrigatória de 4 GiB.')
            target=directory/name
            if target.exists():raise ValueError('Arquivo já existe. Nada será sobrescrito.')
            identifier='transfer-'+uuid.uuid4().hex
            part=directory/('.'+identifier+'.part')
            with part.open('xb'):pass
            self.transfers[identifier]=dict(id=identifier,entity=entity,state='receiving',part=part,target=target,size=size,offset=0,
                                            expected_hash=sha,hasher=hashlib.sha256(),cancel=threading.Event())
            self._transfer_event(identifier)
            return dict(id=identifier,chunk_bytes=2*1024**2)

    def _transfer_event(self,identifier,error=None):
        t=self.transfers[identifier];state=t['state']
        status='done' if state=='done' else 'interrupted' if state=='cancelled' else 'error' if state=='error' else 'running'
        job_bus.publish(identifier,t['entity'],status,kind='model_file_transfer',phase=state,completed_bytes=t['offset'],
                        total_bytes=t['size'],path=str(t['target']) if state=='done' else None,
                        sha256=t.get('hash'),verified=state=='done',error=error)

    def import_chunk(self,identifier,offset,data):
        with self.lock:
            t=self.transfers.get(identifier)
            if not t or t['state']!='receiving':raise ValueError('Transferência não está recebendo dados.')
            if offset!=t['offset'] or not 0<len(data)<=2*1024**2 or offset+len(data)>t['size']:
                raise ValueError('Offset/tamanho fora de ordem; não repetir fragmento silenciosamente.')
            if shutil.disk_usage(t['part'].parent).free<len(data)+4*1024**3:raise ValueError('Disco atingiu reserva; cancele/retome manualmente.')
            with t['part'].open('ab') as out:out.write(data)
            with t['part'].open('rb') as stored:
                stored.seek(offset)
                if stored.read(len(data))!=data:
                    t['state']='error';self._transfer_event(identifier,'chunk_integrity_failed')
                    raise ValueError('Fragmento gravado não passou verificação; staging preservado.')
            t['hasher'].update(data);t['offset']+=len(data);self._transfer_event(identifier)
            return dict(id=identifier,offset=t['offset'])

    def finish_import(self,identifier):
        with self.lock:
            t=self.transfers.get(identifier)
            if not t or t['state']!='receiving':raise ValueError('Transferência não está recebendo.')
            if t['offset']!=t['size']:raise ValueError('Arquivo incompleto.')
            with t['part'].open('rb') as file:
                magic=file.read(4)
            digest=t['hasher'].hexdigest()
            if magic!=b'GGUF' or (t['expected_hash'] and digest!=t['expected_hash']):
                t['state']='error';self._transfer_event(identifier,'integridade/assinatura GGUF inválida')
                raise ValueError('Integridade não confirmada; staging preservado, executor não alterado.')
            with t['part'].open('rb') as file:os.fsync(file.fileno())
            # link é commit no-clobber atômico mesmo contra outro processo.
            os.link(t['part'],t['target']);t['part'].unlink()
            t.update(state='done',hash=digest);self._transfer_event(identifier)
            return dict(id=identifier,path=str(t['target']),sha256=digest,verified=True,
                        compatible_executor=False,note='Arquivo arquivado; não valida arquitetura/checkpoint nem autoriza novo LLM.')

    def cancel_transfer(self,identifier):
        with self.lock:
            t=self.transfers.get(identifier)
            if not t:raise ValueError('Transferência não pertence a esta central.')
            if t['state']=='done':return dict(cancelled=False,status='done')
            t['cancel'].set()
            if t['state'] in {'receiving','error'}:
                t['part'].unlink(missing_ok=True);t['state']='cancelled'
                # Job error já terminal não pode voltar a interrupted.
                old=job_bus.get(identifier)
                if old and old['status']!='error':self._transfer_event(identifier)
            return dict(cancelled=True,partial_only=True,note='Somente staging desta transferência; nenhum peso existente removido.')

    def export_file(self,data):
        entity=data.get('entity','hoshino');paths=self.paths(entity);source=self.file_path(data.get('id'))
        with self.lock:
            if any(t['state'] in {'receiving','copying','verifying'} for t in self.transfers.values()):raise ValueError('Aguarde transferência atual.')
            directory=paths.runtime/'entregas/saida';directory.mkdir(parents=True,exist_ok=True)
            if not directory.resolve().is_relative_to(paths.runtime.resolve()):raise ValueError('Destino de exportação fora do runtime.')
            size=source.stat().st_size
            if shutil.disk_usage(directory).free<size+4*1024**3:raise ValueError('Exportação precisa de espaço + 4 GiB de reserva.')
            identifier='transfer-'+uuid.uuid4().hex;target=directory/(identifier+'-'+source.name);part=directory/('.'+identifier+'.part')
            t=dict(id=identifier,entity=entity,state='copying',part=part,target=target,size=size,offset=0,cancel=threading.Event())
            self.transfers[identifier]=t;self._transfer_event(identifier)
            def copy():
                try:
                    h=hashlib.sha256()
                    with source.open('rb') as original,part.open('xb') as out:
                        while block:=original.read(2*1024**2):
                            if t['cancel'].is_set():break
                            if shutil.disk_usage(directory).free<len(block)+4*1024**3:raise ValueError('reserve_reached')
                            out.write(block);h.update(block);t['offset']+=len(block);self._transfer_event(identifier)
                        out.flush();os.fsync(out.fileno())
                    if t['cancel'].is_set():
                        part.unlink(missing_ok=True);t['state']='cancelled';self._transfer_event(identifier);return
                    if t['offset']!=size:raise ValueError('source_changed')
                    # Segunda leitura verifica o arquivo escrito, não só input.
                    t['state']='verifying';self._transfer_event(identifier);check=hashlib.sha256()
                    with part.open('rb') as output:
                        while block:=output.read(2*1024**2):
                            if t['cancel'].is_set():break
                            check.update(block)
                    if t['cancel'].is_set():
                        part.unlink(missing_ok=True);t['state']='cancelled';self._transfer_event(identifier);return
                    if check.hexdigest()!=h.hexdigest():raise ValueError('copy_hash_mismatch')
                    os.link(part,target);part.unlink();t.update(state='done',hash=h.hexdigest());self._transfer_event(identifier)
                except Exception as exc:
                    t['state']='error';self._transfer_event(identifier,type(exc).__name__)
                    diagnostics.emit('central.export_failed',entity=entity,error_type=type(exc).__name__,job_id=identifier)
            thread=threading.Thread(target=copy,name='central-file-export',daemon=True);self.transfer_threads.append(thread);thread.start()
            return dict(id=identifier,accepted=True,path=str(target),verified=False)

    def overlay_state(self):
        # Sem processos/modelos iniciados por consultas do overlay.
        return dict(closing=self.supervisor.closing,presence=interentity.presence()['entities'],jobs=job_bus.status(),
                    replies={e:interentity.user_conversation(e,6) for e in ENTITIES},
                    interface=self.ui_settings(),
                    entity_details=self.entities(),
                    process_alive=bool(self.overlay_process and self.overlay_process.poll() is None),central_focus=self.focus_state())

    def start_native(self,data):
        import subprocess
        entity=data.get('entity','hoshino');self.paths(entity)
        if set(data)-{'entity'}:raise ValueError('Campo inválido.')
        env={k:v for k,v in os.environ.items() if k in {'PATH','HOME','LANG','DISPLAY','WAYLAND_DISPLAY','XAUTHORITY','XDG_RUNTIME_DIR','DBUS_SESSION_BUS_ADDRESS','QT_QPA_PLATFORM'}}
        env['QT_OPENGL']='software'
        log=self.root/'compartilhado/runtime/launcher/central-native.log';log.parent.mkdir(parents=True,exist_ok=True)
        with log.open('ab') as output:
            self.native_process=subprocess.Popen(['/usr/bin/python3',str(self.root/'app/ui/central_native.py'),'--root',str(self.root),'--entity',entity],
                                                  env=env,cwd=self.root,stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
        return dict(accepted=True,verified=False,note='Janela nativa solicitada; instância existente é focada, sem reiniciar backend.')

    def focus_state(self):
        now=time.time()
        with self.lock:
            self.focus_clients={k:v for k,v in self.focus_clients.items() if v.get('closed') or now-v['at']<30}
            only_closed=bool(self.focus_clients) and all(v.get('closed') for v in self.focus_clients.values())
            return dict(focused=any(v['focused'] for v in self.focus_clients.values()),
                        at=now if only_closed else max((v['at'] for v in self.focus_clients.values()),default=0),
                        known=bool(self.focus_clients),basis='explicit_pagehide' if only_closed else 'native_focus_report' if self.focus_clients and all(v.get('client')=='native' for v in self.focus_clients.values()) else 'browser_focus_report')

    def focus(self,data):
        identifier=data.get('client_id')
        if not re.fullmatch('[A-Za-z0-9_-]{8,100}',str(identifier)) or type(data.get('focused')) is not bool or type(data.get('closed',False)) is not bool:
            raise ValueError('Relato de foco inválido.')
        if data.get('client','browser') not in ('browser','native'):raise ValueError('Cliente de foco inválido.')
        with self.lock:
            self.focus_state()
            if identifier not in self.focus_clients and len(self.focus_clients)>=20:
                closed=next((k for k,v in self.focus_clients.items() if v.get('closed')),None)
                if closed:self.focus_clients.pop(closed)
                else:raise ValueError('Limite de abas excedido.')
            self.focus_clients[identifier]=dict(focused=data['focused'] and not data.get('closed'),at=time.time(),closed=data.get('closed',False),client=data.get('client','browser'))
            if self.focus_clients[identifier]['focused']:self.focus_active=identifier
            elif data.get('closed') and self.focus_active==identifier:self.focus_active=None
            return dict(recorded=True,active=self.window_may_command(identifier))

    def window_may_command(self,client):
        """Duas janelas (PC1 e PC2) não comandam ao mesmo tempo: vale a última que recebeu foco (07/11).

        Sem identificação (painel web ou cliente antigo) não há como saber; passa. Janela ativa fechada ou sumida
        (sem sinal há 30 s) libera a vez para a próxima que comandar."""
        if not client:return True
        with self.lock:
            self.focus_state()
            ativa=self.focus_active
            if ativa is None or ativa not in self.focus_clients or self.focus_clients[ativa].get('closed'):
                self.focus_active=client;return True
            return ativa==client

    def start_overlay(self):
        import subprocess
        with self.lock:
            if not self.ui_settings()['settings'].get('overlay_enabled'):
                raise ValueError('Ative overlay nas preferências antes de abrir.')
            if self.overlay_process and self.overlay_process.poll() is None:return dict(accepted=True,already_running=True)
            python=Path('/usr/bin/python3');script=self.root/'app/ui/overlay.py'
            if not python.is_file() or not script.is_file():raise ValueError('Runtime Qt local indisponível.')
            # Não repassa credenciais de IA/Discord nem token em argv.
            env={k:v for k,v in os.environ.items() if k in {'PATH','HOME','LANG','DISPLAY','WAYLAND_DISPLAY','XAUTHORITY','XDG_RUNTIME_DIR','DBUS_SESSION_BUS_ADDRESS','QT_QPA_PLATFORM'}}
            env['QT_OPENGL']='software'
            log=self.root/'compartilhado/runtime/launcher/overlay.log';log.parent.mkdir(parents=True,exist_ok=True)
            with log.open('ab') as output:
                self.overlay_process=subprocess.Popen([str(python),str(script),'--root',str(self.root)],cwd=self.root,
                                                       env=env,stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
            diagnostics.emit('central.overlay_started',pid=self.overlay_process.pid)
            return dict(accepted=True,pid=self.overlay_process.pid,healthy=False,note='Processo iniciado; observe a janela/log para confirmar funcionamento.')

    def close(self):
        # Disposable UI child owned by this instance, never a process by name.
        process=self.overlay_process
        if process and process.poll() is None:
            process.terminate()
            try:process.wait(timeout=3)
            except __import__('subprocess').TimeoutExpired:return False
        return True

    def social(self,data):
        entity=data.get('entity');self.paths(entity)
        if data.get('interaction')!='carinho' or not re.fullmatch('[A-Za-z0-9_-]{8,100}',str(data.get('submission_id',''))):
            raise ValueError('Interação/ID inválido.')
        return interentity.send('usuario',entity,'[Interação no overlay] O usuário faz um carinho em você.',wake=False,
                                metadata={'source':'overlay_social','interaction':'carinho','author_id':'usuario'},
                                dedupe_key='overlay:'+entity+':'+data['submission_id'])

    def attachment(self,entity,name,data):
        paths=self.paths(entity)
        if not isinstance(name,str) or not re.fullmatch(r'[\w .()-]{1,150}',name) or name.startswith('.') or '..' in name:
            raise ValueError('Nome de anexo inválido.')
        from tools.entrega import _seguro
        if not _seguro(name)[0] or name.lower().endswith('.env'):raise ValueError('Arquivo com aparência de segredo não pode ser anexado.')
        if not 0<len(data)<=8*1024**2:raise ValueError('Anexo entre 1 byte e 8 MiB.')
        clipboard = name in {'clipboard-texto.txt', 'clipboard-print.png'}
        if clipboard:
            if self.ui_settings()['settings'].get('clipboard_import', True) is not True:
                raise ValueError('Importação da área de transferência desativada.')
            if name.endswith('.png'):
                width = int.from_bytes(data[16:20], 'big')
                height = int.from_bytes(data[20:24], 'big')
                if not data.startswith(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR') or not (0 < width * height <= 16_000_000):
                    raise ValueError('O print deve ser um PNG de até 16 milhões de pixels.')
            if name.endswith('.txt'):
                if len(data) > 128 * 1024:
                    raise ValueError('Texto copiado acima de 128 KiB.')
                data.decode('utf-8')
        directory=paths.runtime/'entregas/entrada';directory.mkdir(parents=True,exist_ok=True)
        if not directory.resolve().is_relative_to(paths.runtime.resolve()):raise ValueError('Entrada fora do runtime.')
        if shutil.disk_usage(directory).free<len(data)+128*1024**2:raise ValueError('Espaço insuficiente para anexo.')
        identifier=uuid.uuid4().hex[:12];target=directory/(identifier+'-'+name)
        fd,temp=tempfile.mkstemp(prefix='.upload-',dir=directory)
        try:
            with os.fdopen(fd,'wb') as file:file.write(data);file.flush();os.fsync(file.fileno())
            os.link(temp,target)
        finally:Path(temp).unlink(missing_ok=True)
        source = {'source': 'clipboard', 'attachment_name': target.name} if clipboard else {}
        diagnostics.emit('central.attachment_received',entity=entity,file_id=identifier,size_bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),**source)
        return dict(entity=entity,name=target.name,path=str(target),received=True,message_sent=False)

    def clipboard_capture(self, kind, data, origem='pc1'):
        """06/11 (pedido humano): cada cópia vai sozinha para compartilhado/area_de_transferencia.

        A janela da Central (aqui ou no PC2) manda o que o sistema avisou que foi copiado; as entidades leem
        pela ferramenta area_de_transferencia quando pedirem. Desligável em Configurações."""
        if self.ui_settings()['settings'].get('clipboard_auto', True) is not True:
            raise ValueError('Guardar cópias automaticamente está desligado.')
        from core import area_transferencia
        row = area_transferencia.save(self.root, kind, data, origem=origem)
        if not row.get('duplicate'):
            diagnostics.emit('central.clipboard_saved', kind=row['kind'], item=row['id'], size_bytes=row['bytes'])
        return dict(saved=not row.get('duplicate'), duplicate=bool(row.get('duplicate')), id=row['id'], kind=row['kind'])

    def clipboard_capture_state(self):
        from core import area_transferencia
        rows = area_transferencia.items(self.root)
        return dict(enabled=self.ui_settings()['settings'].get('clipboard_auto', True) is True, count=len(rows),
                    latest=[area_transferencia.describe(r) for r in rows[:5]],
                    folder=str(area_transferencia.folder(self.root)))

    def clipboard_attachment(self, entity, name):
        paths = self.paths(entity)
        if not CLIPBOARD_ATTACHMENT.fullmatch(name):
            raise ValueError('Identificador de conteúdo copiado inválido.')
        directory = paths.runtime / 'entregas' / 'entrada'
        path = directory / name
        if not directory.resolve().is_relative_to(paths.runtime.resolve()) or path.is_symlink() or not path.is_file():
            raise ValueError('Conteúdo copiado indisponível.')
        limit = 8 * 1024**2 if name.endswith('.png') else 128 * 1024
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except OSError as exc:
            raise ValueError('Conteúdo copiado indisponível.') from exc
        with os.fdopen(fd, 'rb') as file:
            if not stat.S_ISREG(os.fstat(file.fileno()).st_mode):
                raise ValueError('Conteúdo copiado indisponível.')
            data = file.read(limit + 1)
        if not 0 < len(data) <= limit:
            raise ValueError('Tamanho de conteúdo copiado inválido.')
        mime = 'image/png' if name.endswith('.png') else 'text/plain; charset=utf-8'
        return data, mime
