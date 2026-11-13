"""Experimento NF4 LoRA 4B/6B/Hunyuan7B. Requer GPU; zero fallback silencioso.

Somente texto; jamais faz deploy. Qualquer falha interrompe com log/erro.
Perfis experimentais dos 7B/9B exigem probe; treino não equivale a deploy.
"""
from __future__ import annotations
import argparse, json, math, os, random, time, uuid, signal
import contextlib, sys, subprocess,threading,shutil
from pathlib import Path

ALLOWED = {
    'alistair-qwen35-4b/hf': ('qwen3_5',True),
    'yi15-6b/hf': ('llama',False),
    'hunyuan-7b/hf': ('hunyuan_v1_dense',False),
    'modelos/qwen2.5-7b-hf-local': ('qwen2',False),
    'modelos/qwen3.5-9b-uncensored-hf': ('qwen3_5',True),
    'modelos/qwen3.5-9b-oficial-hf': ('qwen3_5',True),
}
TARGETS={'q_proj','k_proj','v_proj','o_proj','gate_proj','up_proj','down_proj',
         'in_proj_qkv','in_proj_a','in_proj_b','in_proj_z','out_proj'}
THERMAL_POLICY={'version':'amdgpu_junction_guard_v2','junction_max_c':105,
                'junction_margin_c':5,'other_max_c':100,'other_margin_c':10,
                'unknown_limit_c':95}

def type_for(path):
    keys='/'.join(path.parts[-2:])
    if keys not in ALLOWED:raise RuntimeError('Base desconhecida; não inferir compatibilidade pelo tamanho')
    return ALLOWED[keys]

def prepare_frozen_base(model,torch):
    """Evita o upcast FP32 de embeddings/head congelados (OOM de 1–2 GiB).

    Preserva NF4/BF16 originais em memória; só norms precisam de FP32. Não
    modifica arquivos base. Não reentrante permite gradientes dos LoRAs sem
    tornar o embedding treinável nem criar cópia FP32 de todo o vocabulário.
    """
    for name,param in model.named_parameters():
        param.requires_grad=False
        if 'norm' in name.lower() and param.dtype in (torch.float16,torch.bfloat16):
            param.data=param.data.to(torch.float32)
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False})
    return model

def pin_cpu_embedding(model):
    from accelerate.hooks import remove_hook_from_module
    emb=model.get_input_embeddings()
    remove_hook_from_module(emb)
    if emb.weight.device.type!='cpu':raise RuntimeError('Embedding CPU não comprovado')
    for hook in getattr(emb,'_lab_hooks',[]):hook.remove()
    emb._lab_hooks=[emb.register_forward_pre_hook(lambda _module,args:tuple(x.to('cpu') for x in args)),
                    emb.register_forward_hook(lambda _module,_args,out:out.to('cuda'))]

def pin_cpu_head(model):
    """Cabeça congelada CPU; LoRA/camadas continuam GPU. Sem migrar peso por turno."""
    from accelerate.hooks import remove_hook_from_module
    head=model.get_output_embeddings();remove_hook_from_module(head)
    if head.weight.device.type!='cpu':raise RuntimeError('Cabeça CPU não comprovada')
    # Ryzen/AVX2 não possui matmul BF16 nativo. FP32 só nesta matriz CPU
    # congelada; evita emulação lenta sem upcast/OOM dos pesos da GPU.
    head.weight.data=head.weight.data.float()
    for hook in getattr(head,'_lab_hooks',[]):hook.remove()
    head._lab_hooks=[head.register_forward_pre_hook(lambda _module,args:tuple(x.to(device='cpu',dtype=head.weight.dtype) for x in args)),
                     head.register_forward_hook(lambda _module,_args,out:out.to('cuda'))]


def frozen_offload(model_type,model_name,head_cpu):
    """Mesmo offload congelado, com nomes verificados de Qwen3.5/Qwen2.5/Yi."""
    # Yi-1.5 autorizado usa LlamaForCausalLM, model.embed_tokens e lm_head.
    # A allowlist type_for valida o caminho antes daqui.
    cpu_head_supported=model_type=='qwen2' or (model_type=='llama' and model_name=='hf')
    embedding_cpu=model_name in ('qwen3.5-9b-uncensored-hf','qwen3.5-9b-oficial-hf') or bool(head_cpu and cpu_head_supported)
    if head_cpu and not embedding_cpu:raise RuntimeError('Offload head sem arquitetura explicitamente suportada')
    mapping={'model.visual':'cpu','model.language_model':0,'lm_head':0} if model_type=='qwen3_5' else {'':0}
    allowed=('model.visual.',) if model_type=='qwen3_5' else ()
    if embedding_cpu:
        prefix='model.language_model' if model_type=='qwen3_5' else 'model'
        mapping={prefix+'.embed_tokens':'cpu',prefix+'.layers':0,prefix+'.norm':0,'lm_head':0}
        if model_type=='qwen3_5':mapping['model.visual']='cpu'
        allowed+=(prefix+'.embed_tokens.',)
    if head_cpu:mapping['lm_head']='cpu';allowed+=('lm_head.',)
    return embedding_cpu,mapping,allowed

def idle_metrics(gpu_metrics,*,timeout=10):
    """Absorve amostra transitória após unload; não preempta aplicação externa."""
    deadline=time.monotonic()+timeout
    while True:
        metrics=gpu_metrics.snapshot()
        if not metrics.get('known') or not metrics.get('stable') or metrics.get('utilization') is None:
            raise RuntimeError('Métricas AMD desconhecidas/instáveis; não apostar em VRAM')
        if metrics['utilization']<=10:return metrics
        if time.monotonic()>=deadline:
            raise RuntimeError('GPU ocupada por outra aplicação; não interromper terceiros')
        time.sleep(.5)

@contextlib.contextmanager
def hardware_lease(entity,model,*,teacher=False):
    """Mesmo RM/SQLite do projeto; sem concorrência ou margem menor no laboratório."""
    app=Path(__file__).resolve().parents[1]/'app'
    if str(app) not in sys.path:sys.path.insert(0,str(app))
    # O gate do professor já pode ter importado config/.env. Isolar o runtime
    # nativo ANTES do filho HIP; não mudar o ambiente dos serviços de produção.
    os.environ.pop('HSA_OVERRIDE_GFX_VERSION',None)
    from core import resource_manager,gpu_metrics,interentity
    # config carrega o .env de produção por compatibilidade. Seu override legado
    # não pode contaminar o processo ROCm nativo do laboratório.
    os.environ.pop('HSA_OVERRIDE_GFX_VERSION',None)
    if any((interentity.presence(e) or {}).get('status') in ('awake','starting','stopping')
           for e in ('hoshino','lilith','alistair')):
        raise RuntimeError('Entidade ativa: usar sono cooperativo autorizado antes do laboratório')
    metrics=idle_metrics(gpu_metrics);policy=resource_manager.gpu_policy()
    available=gpu_metrics.ram_available()
    minimum_ram=max(12*gpu_metrics.GIB,Path(model).stat().st_size+2*gpu_metrics.GIB) if teacher else 12*gpu_metrics.GIB
    if available is None or available<minimum_ram:raise RuntimeError('RAM física insuficiente; swap não é orçamento')
    workspace=256*1024**2
    budget=min(metrics['total_bytes'],gpu_metrics.HARD_LIMIT)-metrics['used_bytes']-policy['margin_bytes']-workspace
    if budget<4*gpu_metrics.GIB:raise RuntimeError('Sem VRAM para o preset; margem preservada')
    print('PREFLIGHT_AMD',json.dumps({'metrics':metrics,'ram_available':available,
          'training_budget':budget,'margin':policy['margin_bytes'],'teacher_gtt':teacher}),flush=True)
    with resource_manager.compute_lease('batch',entity=entity,model_key='laboratorio:'+str(model),
         vram_bytes=budget,workspace_bytes=workspace,priority=5,overlap_safe=False,
         cpu_fallback=False,wait=10,use_model_estimate=False) as acquired:
        if acquired['backend']!='gpu':raise RuntimeError('Lease GPU não confirmado')
        try:yield {'budget_bytes':budget,'initial':metrics,'margin_bytes':policy['margin_bytes']}
        finally:print('GPU_ANTES_DE_LIBERAR_LEASE',json.dumps(gpu_metrics.snapshot()),flush=True)
    print('LEASE_LIBERADO_AMD',json.dumps(gpu_metrics.snapshot()),flush=True)

def tokenize(tok,messages,identity=None,tools=None):
    # 12/11: formato compartilhado com o montador do banco (laboratorio/formato_treino.py). Texto continua igual;
    # exemplo com `tools` usa o modelo de chat real e treina também as chamadas de ferramenta.
    from .formato_treino import tokenize as _tokenize
    return _tokenize(tok,messages,identity,tools)

def corpus_has_tools(path):
    for line in Path(path).read_text(encoding='utf8').splitlines():
        if line.strip() and json.loads(line).get('tools'):return True
    return False

def load_samples(path,tok,identity=None):
    rows=[];allrows=0
    for line in path.read_text(encoding='utf8').splitlines():
        if not line.strip():continue
        allrows+=1
        row=json.loads(line);msg=row.get('messages',[])
        if isinstance(msg,list):
            x=tokenize(tok,msg,identity,row.get('tools'))
            if x is not None:rows.append(x)
    if len(rows)<2 or len(rows)!=allrows:
        raise RuntimeError(f'Corpus inválido ou com exemplos longos: {len(rows)}/{allrows} selecionados')
    return rows

def generation_inputs(tok,prompt,identity=None,tools=None):
    # Transformers atual retorna BatchEncoding, não um Tensor. Contrato explícito
    # evita confundir o contêiner com input_ids e perder a máscara de atenção.
    # 12/11: o contrato "tool_call" oferece a ferramenta no mesmo formato da inferência (modelo de chat do Qwen3.5).
    messages=([{'role':'system','content':identity}] if identity else [])+[{'role':'user','content':prompt}]
    return tok.apply_chat_template(messages,tools=tools,tokenize=True,
           add_generation_prompt=True,enable_thinking=False,return_tensors='pt',return_dict=True)

def load_existing_adapter(model,path,*,trainable):
    """Carrega só LoRA. Não redispatcha a base NF4/offload já validada.

    PeftModel.from_pretrained redispatcha pesos GPU/CPU e transforma estados
    NF4 em meta tensors no 9B deste runtime. O próprio get/set do PEFT mantém
    o mesmo mapa de dispositivos do treino e verifica chaves do adaptador.
    """
    from peft import LoraConfig,get_peft_model
    from peft.utils.save_and_load import load_peft_weights,set_peft_model_state_dict
    config=LoraConfig.from_pretrained(path,local_files_only=True)
    # save_pretrained publica inference_mode=True mesmo no snapshot de treino.
    # A retomada precisa reativar SOMENTE LoRA; a base continua congelada.
    config.inference_mode=not trainable
    wrapped=get_peft_model(model,config)
    state=load_peft_weights(str(path),device='cuda',local_files_only=True)
    result=set_peft_model_state_dict(wrapped,state)
    if result.unexpected_keys or any('lora_' in key for key in result.missing_keys):
        raise RuntimeError('Chaves LoRA ausentes/inesperadas; recarga recusada')
    if not trainable:
        for param in wrapped.parameters():param.requires_grad=False
    return wrapped

def trim_idle_allocator(torch,budget_bytes,*,eager=False):
    """Só cache inativo, nunca pesos/gradientes. A margem física não muda."""
    reserved=torch.cuda.memory_reserved()
    if (eager or reserved>budget_bytes-512*1024**2) and reserved>torch.cuda.memory_allocated():
        torch.cuda.empty_cache();return True
    return False

def physical_pressure(metrics,ram_available,margin_bytes):
    total=metrics.get('total_bytes');used=metrics.get('used_bytes')
    if not metrics.get('known') or total is None or used is None or ram_available is None:
        return 'Métricas físicas indisponíveis durante o job; parada conservadora'
    if used>min(total,8*1024**3)-margin_bytes or ram_available<4*1024**3:
        return 'Pressão física: parada cooperativa; não ampliar orçamento'
    return None

def training_options(raw=None):
    """Mesmo runner, opções explícitas; zero execução por preparar um plano."""
    raw={} if raw is None else raw
    limits={'optimization_seconds':(1,21600),'checkpoint_steps':(1,500),
            'validation_steps':(5,500),'patience':(2,20),'max_steps':(1,20000),'rank':(4,8),'head_cpu':(0,1)}
    if not isinstance(raw,dict) or set(raw)-set(limits):raise ValueError('Opções de treino desconhecidas')
    for key,value in raw.items():
        if type(value) is not int or not limits[key][0]<=value<=limits[key][1]:
            raise ValueError('Opção de treino inválida: '+key)
    if 'rank' in raw and raw['rank'] not in (4,8):raise ValueError('Rank não homologado')
    return dict(raw)

def optimization_due(steps,initial_steps,seconds,target,wall_elapsed,minutes,mode,max_steps=None):
    if max_steps is not None and steps>=max_steps:return False
    if mode=='smoke':return steps<2
    if target is not None:return seconds<target
    return wall_elapsed<minutes*60 or steps==initial_steps

def validation_progress(history,step,value,patience):
    if not math.isfinite(value):raise RuntimeError('Validação não finita')
    best=min((h['loss'] for h in history),default=float('inf'))
    bad=(history[-1].get('bad_checks',0)+1) if value>best*1.02 else 0
    history.append({'step':step,'loss':value,'bad_checks':bad})
    return bad>=patience

def sample_hardware(metrics,ram_available):
    """Mesma telemetria do executor, amdgpu/sysfs e /proc, sem daemon extra."""
    memory={}
    for line in Path('/proc/meminfo').read_text().splitlines():
        key,_,value=line.partition(':')
        if key in ('MemTotal','MemAvailable','SwapTotal','SwapFree'):memory[key]=int(value.split()[0])*1024
    temperatures={};critical={};power={};fans={}
    for card in Path('/sys/class/drm').glob('card[0-9]/device'):
        if not (card/'mem_info_vram_total').exists():continue
        for sensor in card.glob('hwmon/hwmon*/temp*_input'):
            try:
                prefix=sensor.name.replace('_input','')
                label=sensor.with_name(prefix+'_label')
                key=card.parent.name+':'+(label.read_text().strip() if label.exists() else prefix)
                temperatures[key]=int(sensor.read_text())/1000
                limit=sensor.with_name(prefix+'_crit')
                if limit.exists():critical[key]=int(limit.read_text())/1000
            except (OSError,ValueError):pass
        for sensor in card.glob('hwmon/hwmon*/power*_average'):
            try:power[card.parent.name]=int(sensor.read_text())/1000000
            except (OSError,ValueError):pass
        for sensor in card.glob('hwmon/hwmon*/fan*_input'):
            try:fans[card.parent.name]=int(sensor.read_text())
            except (OSError,ValueError):pass
    vm={}
    for line in Path('/proc/vmstat').read_text().splitlines():
        key,value=line.split()
        if key in ('pswpin','pswpout','pgmajfault'):vm[key]=int(value)
    return {'at':time.time(),'vram_bytes':metrics.get('used_bytes'),
            'gpu_busy_percent':metrics.get('utilization'),'ram_available':ram_available,
            'swap_used':memory.get('SwapTotal',0)-memory.get('SwapFree',0),
            'temperatures_c':temperatures,'temperature_critical_c':critical,'cpu_load_1m':os.getloadavg()[0],
            'power_watts':power,'fan_rpm':fans,'vm_counters':vm}

def thermal_ceiling(sample,sensor,*,junction_max_c=100):
    if type(junction_max_c) is not int or junction_max_c not in (100,105):
        raise ValueError('Limite junction deve preservar proteção térmica')
    crit=sample.get('temperature_critical_c',{}).get(sensor)
    if type(crit) not in (int,float) or not math.isfinite(crit) or crit<=10:
        return THERMAL_POLICY['unknown_limit_c']
    # Autorização de16/10: retirar o corte arbitrário100°C SOMENTE do
    # junction com limite crítico legível. Nunca modificar driver/VBIOS/fans.
    junction=str(sensor).rsplit(':',1)[-1]=='junction'
    margin=THERMAL_POLICY['junction_margin_c'] if junction_max_c==105 else 10
    return min(junction_max_c,crit-margin) if junction else min(
        THERMAL_POLICY['other_max_c'],crit-THERMAL_POLICY['other_margin_c'])


def thermal_pressure(sample,*,junction_max_c=100):
    temperatures=sample.get('temperatures_c',{})
    if not temperatures:return 'Sensores térmicos indisponíveis; parada conservadora'
    for sensor,value in temperatures.items():
        if type(value) not in (int,float) or not math.isfinite(value):
            return f'Sensor térmico inválido: {sensor}; parada conservadora'
        ceiling=thermal_ceiling(sample,sensor,junction_max_c=junction_max_c)
        if value>=ceiling:return f'Temperatura {sensor} {value}°C >= limite conservador {ceiling}°C'
    return None


def cool_before_work(sample,*,cancelled=lambda:False,clock=time.monotonic,wait=time.sleep,timeout=60,junction_max_c=100):
    """Ceder entre updates/amostras, não pausar kernels ou alterar hardware.

    O monitor pai continua impondo o corte térmico original. Histerese evita
    lançar outra unidade de compute já perto do corte; espera é limitada,
    cancelável e não conta como tempo de otimização.
    """
    start=clock();row=sample();temperatures=row.get('temperatures_c',{})
    if not any(v>=thermal_ceiling(row,k,junction_max_c=junction_max_c)-15 for k,v in temperatures.items()):return 0.
    print('RESFRIAMENTO_COOPERATIVO: aguardar entre etapas; limite térmico preservado',flush=True)
    while True:
        if cancelled():break
        if not temperatures:raise RuntimeError('Sensores desapareceram durante resfriamento; não prosseguir às cegas')
        if all(v<thermal_ceiling(row,k,junction_max_c=junction_max_c)-20 for k,v in temperatures.items()):break
        if clock()-start>=timeout:raise RuntimeError('Resfriamento excedeu 60s; verificar ventilação antes de retomar')
        wait(.5);row=sample();temperatures=row.get('temperatures_c',{})
    return clock()-start


def generation_end_tokens(tok,generation_config):
    """Preservar EOS da base e reconhecer o EOS nativo verificado do tokenizer.

    Alguns checkpoints Chat (Yi) conservam endoftext no generation_config,
    enquanto o template termina turnos com im_end. Não inventar stopwords nem
    modificar arquivos originais; usar o mesmo contrato na geração e auditoria.
    """
    configured=getattr(generation_config,'eos_token_id',None)
    tokens=[] if configured is None else list(configured) if isinstance(configured,(list,tuple)) else [configured]
    if any(type(token) is not int or token<0 or token>=len(tok) for token in tokens):
        raise ValueError('EOS da base inválido; não gerar com protocolo incerto')
    native=getattr(tok,'eos_token_id',None);text=getattr(tok,'eos_token',None)
    if native is not None:
        if (type(native) is not int or native<0 or native>=len(tok) or not text or
            native not in tok.all_special_ids or tok.convert_tokens_to_ids(text)!=native):
            raise ValueError('EOS nativo não confirmado pelo tokenizer')
        tokens.append(native)
    if not tokens:raise ValueError('Backend sem EOS confirmado')
    return list(dict.fromkeys(tokens))


class GenerationCoolingGate:
    """Critério do generate existente: checa entre tokens, sem mudar logits.

    Uma frase pode conter centenas de forwards. Checar só entre casos deixou
    a geração aquecer até o corte mesmo com os losses calculados normalmente.
    """
    def __init__(self,cool,cancelled=lambda:False):
        self.cool=cool;self.cancelled=cancelled;self.checks=0

    def __call__(self,input_ids,scores,**kwargs):
        if self.cancelled():return True
        self.cool();self.checks+=1
        return bool(self.cancelled())

def wait_owned_child(child,cancellation,*,clock=time.monotonic):
    """Mesmo prazo para SIGTERM manual ou pressão; apenas o filho criado aqui."""
    forced=False
    while child.poll() is None:
        try:child.wait(timeout=1)
        except subprocess.TimeoutExpired:
            if cancellation['at'] is not None and clock()-cancellation['at']>=60:
                child.kill();forced=True;child.wait(timeout=10)
    return child.returncode,forced

def run(args):
    run_started=time.monotonic()
    from .versionamento_lora import sha as code_sha,base_signature
    # Capturar na entrada, não atribuir a um processo antigo o código editado
    # durante seu trabalho. SHA é proveniência, não homologação de qualidade.
    runtime_code_sha256={p.name:code_sha(p) for p in
        (Path(__file__),Path(__file__).with_name('versionamento_lora.py'),Path(__file__).with_name('personalizacao.py'))}
    import torch
    from transformers import AutoConfig,AutoTokenizer,AutoModelForCausalLM,BitsAndBytesConfig,StoppingCriteriaList
    from peft import LoraConfig,TaskType,get_peft_model,PeftModel
    if os.getenv('HSA_OVERRIDE_GFX_VERSION'):raise RuntimeError('Override gfx não autorizado')
    if not torch.version.hip or not torch.cuda.is_available() or not torch.cuda.is_bf16_supported(including_emulation=False):
        raise RuntimeError('ROCm com BF16 nativo é obrigatório')
    signature=getattr(args,'benchmark_signature',None)
    if signature:
        sig=json.loads(signature)
        if any(sig.get(k)!=v for k,v in {'torch':torch.__version__,'rocm':torch.version.hip,'gpu':torch.cuda.get_device_name(0)}.items()):
            raise RuntimeError('Hardware/runtime mudou desde o benchmark; repetir probe')
    expected,multimodal=type_for(args.model)
    torch.manual_seed(247);random.seed(247)
    torch.set_num_threads(6)
    if args.model.parent.name=='alistair-qwen35-4b' and args.entity!='alistair':
        raise RuntimeError('Modelo 4B exclusivo de Alistair; não treinar com outro corpus')
    cfg=AutoConfig.from_pretrained(args.model,local_files_only=True,trust_remote_code=False)
    if cfg.model_type!=expected:raise RuntimeError('Arquitetura do checkpoint mudou')
    tok=AutoTokenizer.from_pretrained(args.model,local_files_only=True,trust_remote_code=False)
    from .personalizacao import dataset_profile,training_identity,training_context,artifact_context
    profile,profile_hash=dataset_profile(args.train,args.entity)
    context=training_context(args.entity,profile)
    resume=getattr(args,'resume',None);adapter=getattr(args,'adapter',None)
    if adapter or resume:
        provenance=Path(adapter)/'provenance.json' if adapter else Path(resume).parent.parent/'provenance.json'
        context=artifact_context(json.loads(provenance.read_text()),args.entity,profile)
    identity=training_identity(args.entity,profile,version=context['version'])
    print('TRAINING_CONTEXT',args.entity,json.dumps(context),flush=True)
    train=load_samples(args.train,tok,identity);validation=load_samples(args.validation,tok,identity)
    if multimodal:
        from transformers import Qwen3_5ForConditionalGeneration
        cls=Qwen3_5ForConditionalGeneration
    else:cls=AutoModelForCausalLM
    head_cpu=bool(getattr(args,'head_cpu',0))
    embedding_cpu,mapping,allowed=frozen_offload(expected,args.model.name,head_cpu)
    quant=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.bfloat16,llm_int8_enable_fp32_cpu_offload=multimodal or embedding_cpu)
    model=cls.from_pretrained(args.model,quantization_config=quant,device_map=mapping,
        local_files_only=True,trust_remote_code=False,dtype=torch.bfloat16,low_cpu_mem_usage=True)
    if multimodal or embedding_cpu:
        off=[n for n,p in model.named_parameters() if p.device.type!='cuda']
        if not off or any(not n.startswith(allowed) for n in off):
            raise RuntimeError('Offload visual não comprovado ou camada textual fora da GPU')
    if embedding_cpu:pin_cpu_embedding(model)
    if head_cpu:pin_cpu_head(model)
    model.config.use_cache=False
    load_gib=torch.cuda.memory_allocated()/1024**3
    print(f'MODELO {expected} carregado; VRAM {load_gib:.3f} GiB',flush=True)
    budget=getattr(args,'vram_budget_bytes',int(6.8*1024**3))/1024**3
    if load_gib>budget-0.35:raise RuntimeError('Modelo sem margem de VRAM antes do treino')
    model=prepare_frozen_base(model,torch)
    targets=[n for n,m in model.named_modules() if n.rsplit('.',1)[-1] in TARGETS and hasattr(m,'weight')
        and (not multimodal or '.language_model.' in '.'+n+'.')]
    if not targets:raise RuntimeError('LoRA textual não encontrado')
    rank=getattr(args,'rank',4)
    preset={'rank':rank,'learning_rate':3e-5,'seed':247,'memory_profile':'frozen_bf16_v17',
            'embedding_cpu':embedding_cpu,'max_length':256}
    if corpus_has_tools(args.train):
        # 12/11: com exemplos de ferramenta a sequência vai até 768 fichas; o preset muda e exige medição nova.
        from .formato_treino import max_length
        preset['max_length']=max_length(True);preset['tool_calls']='qwen35_chat_template_v1'
    optimization_target=getattr(args,'optimization_seconds',None)
    if optimization_target is not None:preset['sampling']='epoch_shuffle_v18'
    if head_cpu:preset.update(head_cpu=True,head_cpu_dtype='float32',memory_profile='frozen_bf16_v18_head_cpu')
    if adapter:
        from .versionamento_lora import verify
        verify(adapter,args.model)
        if json.loads((adapter/'micro_result.json').read_text())['entity']!=args.entity:
            raise RuntimeError('Adaptador de outra entidade')
        model=load_existing_adapter(model,adapter,trainable=False)
        if embedding_cpu:pin_cpu_embedding(model)
        if head_cpu:pin_cpu_head(model)
    elif resume:
        from .versionamento_lora import validate_resume
        validate_resume(resume,args.model,args.train,args.validation,entity=args.entity,preset=preset,context=context)
        model=load_existing_adapter(model,resume,trainable=True)
        if embedding_cpu:pin_cpu_embedding(model)
        if head_cpu:pin_cpu_head(model)
    else:
        model=get_peft_model(model,LoraConfig(task_type=TaskType.CAUSAL_LM,r=rank,lora_alpha=rank*2,
              lora_dropout=0.05,bias='none',target_modules=targets))
    pars=[p for p in model.parameters() if p.requires_grad]
    if args.mode!='evaluate' and (not pars or any(p.device.type!='cuda' for p in pars)):
        raise RuntimeError('Adaptadores fora da GPU')
    opt=torch.optim.AdamW(pars,lr=3e-5) if pars else None
    load_seconds=time.monotonic()-run_started
    # 05/11: o filho ROCm não passa por hardware_lease (o lease é do pai), então o app/ não estava
    # no sys.path e todo treino falhava aqui com ModuleNotFoundError desde 17/10.
    app_dir=Path(__file__).resolve().parents[1]/'app'
    if str(app_dir) not in sys.path:sys.path.insert(0,str(app_dir))
    from core import gpu_metrics
    thermal_wait_seconds=0.;stop_requested=False
    def thermal_gate():
        nonlocal thermal_wait_seconds
        thermal_wait_seconds+=cool_before_work(
            lambda:sample_hardware(gpu_metrics.snapshot(),gpu_metrics.ram_available()),
            cancelled=lambda:stop_requested,junction_max_c=THERMAL_POLICY['junction_max_c'])
    def tensors(ex):
        ids,labels=ex
        return {'input_ids':torch.tensor([ids],dtype=torch.long,device='cuda'),
                'labels':torch.tensor([labels],dtype=torch.long,device='cuda'), 'use_cache':False}
    eval_cache_evictions=0
    def evaluate(examples=None):
        nonlocal eval_cache_evictions
        model.eval();res=[]
        with torch.no_grad():
            sample=examples if examples is not None else [validation[round(j*(len(validation)-1)/5)] for j in range(6)]
            for ex in sample:
                thermal_gate()
                with torch.autocast('cuda',dtype=torch.bfloat16):v=model(**tensors(ex)).loss
                if not bool(torch.isfinite(v)):raise RuntimeError('Validação não finita')
                res.append(float(v.detach().cpu()))
                del v
                # Sequências variadas acumulam blocos reservados do allocator.
                # O ensaio 9B foi parado a 7,28 GiB físicos apesar de pesos
                # ativos menores. Liberar cache livre ANTES do limite, sem
                # reduzir a margem nem alterar amostras/labels da avaliação.
                # 9B: o driver mede buffers HIP/NF4 além do allocator Torch.
                # O segundo ensaio cruzou a margem mesmo com o corte tardio.
                # Neste perfil, não reter cache ocioso entre amostras variadas.
                if trim_idle_allocator(torch,int(budget*1024**3),eager=embedding_cpu):eval_cache_evictions+=1
        model.train();return sum(res)/len(res)
    if args.mode=='evaluate':
        if not adapter or not getattr(args,'holdout',None):raise RuntimeError('Recarga exige adaptador e holdout separado')
        from .versionamento_lora import sha,_write,behavior_cases,behavioral_audit,BEHAVIOR_VERSION
        holdout=load_samples(args.holdout,tok,identity)
        provenance=json.loads((adapter/'provenance.json').read_text())
        if provenance.get('cognitive_profile_sha256')!=profile_hash:
            raise RuntimeError('Perfil do corpus não corresponde ao adaptador')
        train_ids={tuple(ids) for ids,_ in train};val_ids={tuple(ids) for ids,_ in validation}
        if train_ids.intersection(tuple(ids) for ids,_ in holdout) or val_ids.intersection(tuple(ids) for ids,_ in holdout):
            raise RuntimeError('Holdout contaminado por treino/validação')
        started=time.monotonic()
        val=evaluate(validation);validation_seconds=time.monotonic()-started
        print('VALIDACAO_COMPLETA',len(validation),val,round(validation_seconds,2),flush=True)
        test_started=time.monotonic();test=evaluate(holdout);holdout_seconds=time.monotonic()-test_started
        print('HOLDOUT_COMPLETO',len(holdout),test,round(holdout_seconds,2),flush=True)
        model.gradient_checkpointing_disable()
        def dialogue_control(control):
            answers=[];model.eval()
            end_tokens=generation_end_tokens(tok,model.generation_config)
            # Mesmo contexto curto para base/candidata. Não injeta uma resposta
            # esperada nem características emocionais para fabricar aprovação.
            system=identity  # MESMO contexto do treino; legado sem system continua sem system
            for case in behavior_cases(args.entity):
                thermal_gate()
                inputs=generation_inputs(tok,case['prompt'],system,case.get('tools')).to('cuda');ids=inputs['input_ids']
                generate_started=time.monotonic()
                token_gate=GenerationCoolingGate(thermal_gate,lambda:stop_requested)
                print('AVALIACAO_CASO_INICIO',control,case['id'],flush=True)
                with torch.no_grad(),torch.autocast('cuda',dtype=torch.bfloat16):
                    response=model.generate(**inputs,max_new_tokens=160,do_sample=False,use_cache=True,
                        eos_token_id=end_tokens,
                        stopping_criteria=StoppingCriteriaList([token_gate]))
                text=tok.decode(response[0,ids.shape[-1]:],skip_special_tokens=True)
                answers.append({'id':case['id'],'prompt':case['prompt'],'text':text,
                                'generated_tokens':int(response.shape[-1]-ids.shape[-1]),
                                'seconds':round(time.monotonic()-generate_started,2),'generation_cache':True,
                                'generation_cooling':'per_token_v1','thermal_checks':token_gate.checks,
                                'eos_token_ids':end_tokens,
                                'finished':not stop_requested and int(response[0,-1]) in end_tokens})
                print('AVALIACAO_CASO_FIM',control,case['id'],json.dumps(
                    {k:answers[-1][k] for k in ('generated_tokens','seconds','finished','thermal_checks')}),flush=True)
                del response,inputs,ids
                trim_idle_allocator(torch,int(budget*1024**3),eager=embedding_cpu)
            return answers
        answers=dialogue_control('candidate')
        # Controle físico da mesma base/precisão/offload, LoRA desativado. Sem
        # segunda carga GPU e sem utilizar loss parcial do treino como baseline.
        with model.disable_adapter():
            base_val=evaluate(validation);base_holdout=evaluate(holdout)
            base_answers=dialogue_control('base')
        record={'entity':args.entity,'adapter_sha256':sha(adapter/'adapter_model.safetensors'),
                'holdout_sha256':sha(args.holdout),'validation_sha256':sha(args.validation),
                'physical_reload_verified':True,'finite_loss':True,'validation_loss':val,'holdout_loss':test,
                'validation_examples':len(validation),'holdout_examples':len(holdout),
                'responses':answers,'passed':False,'human_review_required':True,
                'behavior_version':BEHAVIOR_VERSION,'behavioral_audit':behavioral_audit(args.entity,answers),
                'cognitive_profile_sha256':profile_hash,
                'training_context':context,'evaluation_context_matches_training':True,
                'baseline':{'physical_base_control':True,'validation_loss':base_val,
                            'holdout_loss':base_holdout,'responses':base_answers},
                'duration_seconds':round(time.monotonic()-started,2),
                'validation_seconds':round(validation_seconds,2),'holdout_seconds':round(holdout_seconds,2),
                'load_seconds':round(load_seconds,2),'runtime_code_sha256':runtime_code_sha256,
                'thermal_wait_seconds':round(thermal_wait_seconds,3),
                'thermal_policy':dict(THERMAL_POLICY),
                'peak_vram_gib':torch.cuda.max_memory_allocated()/1024**3,
                'copy_policy':'sdma_disabled_lab_only',
                'eval_cache_evictions':eval_cache_evictions,
                'note':'Recarga e losses medidos; qualidade comportamental não aprovada automaticamente.'}
        _write(args.out,record)
        print('AVALIACAO_INDEPENDENTE',json.dumps(record,ensure_ascii=False),flush=True)
        return
    validation_started=time.monotonic()
    monitoring_validation=[validation[round(j*(len(validation)-1)/15)] for j in range(16)] if getattr(args,'validation_steps',None) else None
    baseline=evaluate(monitoring_validation);validation_seconds=time.monotonic()-validation_started
    baseline_validation_seconds=validation_seconds;intermediate_validation_seconds=0.
    print('LOSS_VAL_BASELINE',baseline,flush=True)
    seq=list(train);random.Random(247).shuffle(seq)
    # Base HF somente leitura. Checkpoints isolados por job, sem sobrescrita.
    from .versionamento_lora import create_workspace, save_checkpoint, finish_candidate
    workspace = create_workspace(args.out, args.model, args.train, args.validation,
                                 entity=args.entity,preset=preset,context=context) if args.mode=='train' else None
    start=time.monotonic();torch.cuda.reset_peak_memory_stats();steps=0;losses=[];train_cache_evictions=0
    optimization_seconds=0.;input_tokens=0;target_tokens=0;history=[]
    if resume:
        from .versionamento_lora import restore_training_state
        restored=restore_training_state(resume,opt,torch);steps=restored['step']
        progress=restored.get('metadata',{})
        if optimization_target is not None and 'optimization_seconds' not in progress:
            raise RuntimeError('Checkpoint legado sem relógio efetivo; não inventar horas já treinadas')
        optimization_seconds=float(progress.get('optimization_seconds',0))
        input_tokens=int(progress.get('input_tokens',0));target_tokens=int(progress.get('target_tokens',0))
        history=list(progress.get('validation_history',[]))
        population=16 if monitoring_validation is not None else 6
        if progress.get('validation_sample_count',6)!=population:
            print('VALIDACAO: população de monitoramento mudou; iniciar série comparável separada',flush=True)
            history=[]
        print('RETOMADA_CONFIRMADA passo',steps,flush=True)
    initial_steps=steps
    initial_optimization_seconds=optimization_seconds;initial_input_tokens=input_tokens;initial_target_tokens=target_tokens
    validation_checks_this_run=0
    checkpoint_steps=getattr(args,'checkpoint_steps',25)
    validation_steps=getattr(args,'validation_steps',None)
    patience=getattr(args,'patience',3);checkpoint_seconds=0.;checkpoint_sizes=[];early_stopped=False
    if not history:history=[{'step':steps,'loss':baseline,'bad_checks':0}]
    def checkpoint():
        nonlocal checkpoint_seconds
        before=time.monotonic()
        metadata={'optimization_seconds':optimization_seconds,'input_tokens':input_tokens,
                  'target_tokens':target_tokens,'validation_history':history,
                  'sampling':preset.get('sampling','fixed_v17'),'validation_sample_count':16 if monitoring_validation is not None else 6}
        save_checkpoint(workspace,model,opt,steps,losses[-1],torch,metadata=metadata)
        checkpoint_seconds+=time.monotonic()-before
        folder=workspace/'checkpoints'/f'passo-{steps:06d}'
        checkpoint_sizes.append(sum(p.stat().st_size for p in folder.iterdir() if p.is_file()))
        print('CHECKPOINT PARCIAL SALVO:',steps,'OTIMIZACAO',round(optimization_seconds,2),flush=True)
    def request_stop(signum,_frame):
        nonlocal stop_requested
        stop_requested=True;print('PARADA COOPERATIVA: salvar após update atual',signum,flush=True)
    for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,request_stop)
    max_steps=getattr(args,'max_steps',None)
    # Cada etapa é uma atualização completa. Não continuar após OOM.
    while (not stop_requested and optimization_due(steps,initial_steps,optimization_seconds,optimization_target,
                                                   time.monotonic()-start,args.minutes,args.mode,max_steps)):
        thermal_gate()
        if stop_requested:break
        if optimization_target is not None:
            epoch=steps//len(train);order=list(range(len(train)));random.Random(247+epoch).shuffle(order)
            ex=train[order[steps%len(train)]]
        else:ex=seq[steps%len(seq)]
        update_started=time.monotonic()
        model.train();opt.zero_grad(set_to_none=True)
        with torch.autocast('cuda',dtype=torch.bfloat16):loss=model(**tensors(ex)).loss
        if not bool(torch.isfinite(loss)):raise RuntimeError('Loss não finita')
        loss.backward()
        if any(p.grad is None or not bool(torch.isfinite(p.grad).all()) for p in pars):
            raise RuntimeError('Gradientes LoRA ausentes/não finitos')
        torch.nn.utils.clip_grad_norm_(pars,1.0,error_if_nonfinite=True)
        opt.step();torch.cuda.synchronize()
        optimization_seconds+=time.monotonic()-update_started
        input_tokens+=len(ex[0]);target_tokens+=sum(t!=-100 for t in ex[1])
        steps+=1;losses.append(float(loss.detach().cpu()))
        del loss
        if trim_idle_allocator(torch,int(budget*1024**3),eager=embedding_cpu):train_cache_evictions+=1
        if steps%5==0:print('PASSO',steps,'LOSS',round(losses[-1],5),'SEGUNDOS',round(time.monotonic()-start),flush=True)
        if validation_steps and steps%validation_steps==0:
            opt.zero_grad(set_to_none=True);before=time.monotonic()
            value=evaluate(monitoring_validation);spent=time.monotonic()-before
            validation_seconds+=spent;intermediate_validation_seconds+=spent
            validation_checks_this_run+=1
            early_stopped=validation_progress(history,steps,value,patience)
            print('VALIDACAO_INTERMEDIARIA',json.dumps(history[-1]),flush=True)
        if workspace is not None and (steps%checkpoint_steps==0 or early_stopped):checkpoint()
        if early_stopped:break
        if steps>20000:break
    if steps==initial_steps:raise RuntimeError('Nenhuma atualização executada nesta execução')
    if workspace is not None and not (workspace/'checkpoints'/f'passo-{steps:06d}').exists():checkpoint()
    opt.zero_grad(set_to_none=True);before=time.monotonic()
    # Se este update já foi validado, não repetir os mesmos 16 exemplos.
    # Além da latência, duplicação atrasava a parada cooperativa sem nova evidência.
    val=history[-1]['loss'] if history and history[-1]['step']==steps else evaluate(monitoring_validation)
    final_validation_seconds=time.monotonic()-before
    validation_seconds+=final_validation_seconds
    peak=torch.cuda.max_memory_allocated()/1024**3
    if peak>budget:raise RuntimeError('Pico de VRAM acima do orçamento medido: %.2fGiB'%peak)
    record={'entity':args.entity,'steps':steps,'baseline_val_loss':baseline,'after_val_loss':val,
            'training_context':context,
            'base_config_sha256':code_sha(args.model/'config.json'),
            'base_weights_signature':base_signature(args.model),
            'train_sha256':code_sha(args.train),'validation_sha256':code_sha(args.validation),
            'peak_vram_gib':peak,'duration_seconds':round(time.monotonic()-start,2),
            'model':str(args.model),'architecture':cfg.model_type,'rank':rank,'preset':preset,
            'resume_source':str(resume) if resume else None,'initial_steps':initial_steps,
            'updates_this_run':steps-initial_steps,'cancelled':stop_requested,
            'optimization_seconds':optimization_seconds,'optimization_seconds_this_run':optimization_seconds-initial_optimization_seconds,
            'input_tokens':input_tokens,'target_tokens':target_tokens,
            'input_tokens_this_run':input_tokens-initial_input_tokens,'target_tokens_this_run':target_tokens-initial_target_tokens,
            'updates_per_optimization_hour':(steps-initial_steps)*3600/(optimization_seconds-initial_optimization_seconds),
            'input_tokens_per_optimization_hour':(input_tokens-initial_input_tokens)*3600/(optimization_seconds-initial_optimization_seconds),
            'target_tokens_per_optimization_hour':(target_tokens-initial_target_tokens)*3600/(optimization_seconds-initial_optimization_seconds),
            'load_seconds':load_seconds,'validation_seconds':validation_seconds,'checkpoint_seconds':checkpoint_seconds,
            'thermal_wait_seconds':round(thermal_wait_seconds,3),
            'thermal_policy':dict(THERMAL_POLICY),
            'baseline_validation_seconds':baseline_validation_seconds,'intermediate_validation_seconds':intermediate_validation_seconds,
            'final_validation_seconds':final_validation_seconds,'validation_sample_count':16 if monitoring_validation is not None else 6,
            'validation_checks_this_run':validation_checks_this_run,
            'checkpoint_steps':checkpoint_steps,'checkpoint_bytes':checkpoint_sizes,'validation_history':history,
            'early_stopped':early_stopped,'optimization_target_seconds':optimization_target,
            'epochs_processed':steps/len(train),'train_examples':len(train),'validation_examples':len(validation),
            'optimization_target_reached':optimization_target is not None and optimization_seconds>=optimization_target,
            'termination_reason':'cancelled' if stop_requested else 'validation_deterioration' if early_stopped else
                'max_steps' if max_steps is not None and steps>=max_steps else 'optimization_target' if optimization_target is not None else 'wall_budget',
            'torch':torch.__version__,'rocm':torch.version.hip,'gpu':torch.cuda.get_device_name(0),
            'copy_policy':'sdma_disabled_lab_only',
            'train_cache_evictions':train_cache_evictions,'eval_cache_evictions':eval_cache_evictions,
            'note':'Ensaio limitado; validação amostral, não holdout completo; inferência/deploy não aprovados.'}
    record['runtime_code_sha256']=runtime_code_sha256
    if args.mode=='smoke':
        report=args.out.with_suffix('.json');report.parent.mkdir(parents=True,exist_ok=True)
        if report.exists():raise RuntimeError('Relatório existente, não sobrescrever')
        report.write_text(json.dumps(record,indent=2,ensure_ascii=False),encoding='utf8')
        print('PROBE 2 UPDATES PASSOU:',json.dumps(record,ensure_ascii=False),flush=True)
    else:
        if workspace is None:raise RuntimeError('Workspace de checkpoint ausente')
        finish_candidate(workspace,args.out,model,record)
        print('CANDIDATO TREINADO SALVO (NAO HOMOLOGADO):',json.dumps(record,ensure_ascii=False),flush=True)


def cli():
    # Fault SDMA0 observado no amdgpu em 12/10 durante carga do 9B.
    # Somente subprocessos deste laboratório; não altera .env/driver/produção.
    os.environ['HSA_ENABLE_SDMA']='0'
    p=argparse.ArgumentParser();p.add_argument('--model',type=Path,required=True)
    p.add_argument('--train',type=Path,required=True);p.add_argument('--validation',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--entity',choices=('alistair','hoshino','lilith'),required=True)
    p.add_argument('--minutes',type=int,default=10)
    p.add_argument('--mode',choices=('smoke','train','evaluate'),default='train')
    p.add_argument('--resume',type=Path)
    p.add_argument('--adapter',type=Path);p.add_argument('--holdout',type=Path)
    p.add_argument('--max-steps',type=int)
    p.add_argument('--rank',type=int,choices=(4,8),default=4)
    p.add_argument('--optimization-seconds',type=int)
    p.add_argument('--checkpoint-steps',type=int,default=25)
    p.add_argument('--validation-steps',type=int)
    p.add_argument('--patience',type=int,default=3)
    p.add_argument('--head-cpu',type=int,choices=(0,1),default=0)
    p.add_argument('--owned-run',action='store_true',help=argparse.SUPPRESS)
    p.add_argument('--vram-budget-bytes',type=int,help=argparse.SUPPRESS)
    p.add_argument('--benchmark-signature',help=argparse.SUPPRESS)
    a=p.parse_args();a.model=a.model.expanduser().resolve();a.out=a.out.expanduser().absolute()
    training_options({k:getattr(a,k) for k in ('optimization_seconds','checkpoint_steps','validation_steps','patience','max_steps','rank','head_cpu') if getattr(a,k) is not None})
    if not 1<=a.minutes<=(360 if a.optimization_seconds is not None else 90):raise ValueError('Duração inválida')
    if a.max_steps is not None and not 1<=a.max_steps<=20000:raise ValueError('Limite de passos inválido')
    if a.out.exists():raise RuntimeError('Saída já existe')
    # Saídas novas podem ainda não ter pasta; o filesystem ancestral é a fonte.
    ancestor=a.out.parent
    while not ancestor.exists():ancestor=ancestor.parent
    if shutil.disk_usage(ancestor).free<5*1024**3:raise RuntimeError('Menos de 5GiB livres: treino recusado antes da carga')
    if a.owned_run:
        parent=Path('/proc')/str(os.getppid())
        command=(parent/'cmdline').read_bytes().replace(b'\0',b' ')
        if (parent.stat().st_uid!=os.getuid() or b'laboratorio.treino_nf4_curto' not in command or
            a.vram_budget_bytes is None or not 0<a.vram_budget_bytes<8*1024**3):
            raise RuntimeError('Executor isolado sem dono/orçamento do laboratório')
        run(a)
        return
    # O lease pertence ao pai e só acaba DEPOIS da saída do processo ROCm.
    # empty_cache não garante liberar contextos HIP/Accelerate após um OOM.
    # A morte normal do filho é a confirmação forte; não anunciar GPU livre antes.
    with hardware_lease(a.entity,a.model) as lease:
        from core import gpu_metrics
        samples=[];monitor_stop=threading.Event();pressure=[];holder={'child':None};cancellation={'at':None}
        def forward(sig,_frame):
            if cancellation['at'] is None:cancellation['at']=time.monotonic()
            child=holder['child']
            if child is not None and child.poll() is None:
                try:child.send_signal(sig)
                except ProcessLookupError:pass
        def monitor():
            while not monitor_stop.wait(.5):
                metrics=gpu_metrics.snapshot()
                samples.append(sample_hardware(metrics,gpu_metrics.ram_available()))
                samples[-1]['disk_free_bytes']=shutil.disk_usage(ancestor).free
                reason=physical_pressure(metrics,samples[-1]['ram_available'],lease['margin_bytes'])
                reason=thermal_pressure(samples[-1],junction_max_c=THERMAL_POLICY['junction_max_c']) or reason
                if samples[-1]['disk_free_bytes']<2*1024**3:
                    reason='Menos de 2GiB livres: salvar checkpoint e encerrar cooperativamente'
                if not pressure and reason:
                    pressure.append(reason)
                    forward(signal.SIGTERM,None)
        observer=threading.Thread(target=monitor,name='lab-existing-metrics',daemon=True)
        child_started=time.monotonic()
        child=subprocess.Popen([sys.executable,'-u','-m','laboratorio.treino_nf4_curto',
              *sys.argv[1:],'--owned-run','--vram-budget-bytes',str(lease['budget_bytes'])])
        holder['child']=child
        handlers={sig:signal.getsignal(sig) for sig in (signal.SIGTERM,signal.SIGINT)}
        for sig in handlers:signal.signal(sig,forward)
        observer.start()  # Filho/handlers existem antes de qualquer alerta.
        forced=False
        try:
            # Pai permanece vivo com o lease até confirmar saída HIP.
            code,forced=wait_owned_child(child,cancellation)
        finally:
            for sig,handler in handlers.items():signal.signal(sig,handler)
            monitor_stop.set();observer.join(timeout=2)
        # amdgpu pode refletir a liberação do processo com pequeno atraso.
        # O pai ainda mantém o lease durante essa estabilização observável.
        until=time.monotonic()+5
        while time.monotonic()<until:
            now=gpu_metrics.snapshot()
            if now.get('known') and now['used_bytes']<=lease['initial']['used_bytes']+256*1024**2:break
            time.sleep(.1)
        metrics={'before':lease['initial'],'after':gpu_metrics.snapshot(),'samples':samples,
                 'child_wall_seconds':round(time.monotonic()-child_started,2),
                 'forced_owned_child_stop':forced,'checkpoint_verified_after_force':False if forced else None,
                 'vram_budget_bytes':lease['budget_bytes'],'margin_bytes':lease['margin_bytes'],
                 'thermal_policy':dict(THERMAL_POLICY),
                 'child_exit_code':code,'pressure':pressure,'physical_gpu':'AMD/ROCm; torch.cuda API é HIP',
                 'peak_observed_vram_bytes':max((s['vram_bytes'] for s in samples if s['vram_bytes'] is not None),default=None)}
        from .versionamento_lora import _write
        destination=(a.out/'hardware_metrics.json') if a.mode=='train' and a.out.is_dir() else a.out.with_suffix('.hardware.json')
        destination.parent.mkdir(parents=True,exist_ok=True);_write(destination,metrics)
    if code:raise SystemExit(code)
if __name__=='__main__':cli()
