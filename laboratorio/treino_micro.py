#!/usr/bin/env python3
"""Microbenchmark SFT LoRA BF16 em 0.8B local, com visao congelada.
Sem download, sem fallback CPU, sem alterar entidade, sem deploy.
Benchmark: até 4 updates, sem salvar pesos. Treino curto é opcional e isolado.
"""
from __future__ import annotations
import argparse, hashlib, json, math, os, random, shutil, sys, time, uuid
from pathlib import Path

TEXT_TYPES={'qwen3_5','qwen3','qwen2'}
TARGETS={'q_proj','k_proj','v_proj','o_proj','in_proj_qkv','in_proj_a','in_proj_b','in_proj_z','out_proj'}


def is_multimodal_config(cfg):
    """Do not classify a Qwen3.5 multimodal checkpoint as a text-only CausalLM."""
    arch = getattr(cfg, 'architectures', None) or []
    return (getattr(cfg,'vision_config',None) is not None or
            any('ConditionalGeneration' in str(a) for a in arch))


def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def tokenize(tok,messages,limit):
    if not isinstance(messages,list) or len(messages)<2 or messages[-1].get('role')!='assistant':return None
    if any(msg.get('role') not in ('user','assistant') or not isinstance(msg.get('content'),str) for msg in messages):return None
    opts={'enable_thinking':False,'tokenize':False}
    prefix=tok.apply_chat_template(messages[:-1],add_generation_prompt=True,**opts)
    full=tok.apply_chat_template(messages,add_generation_prompt=False,**opts)
    a=tok(prefix,add_special_tokens=False).input_ids
    b=tok(full,add_special_tokens=False).input_ids
    if b[:len(a)]!=a:raise RuntimeError('Chat template nao preserva fronteira de rotulo; abortando')
    if len(b)>limit:return None
    labels=[-100]*len(a)+b[len(a):]
    if not any(x>=0 for x in labels):return None
    return b,labels


def dataset(path,tok,limit):
    items=[];dropped=0
    for line in path.read_text(encoding='utf8').splitlines():
        if not line.strip():continue
        record=json.loads(line)
        item=tokenize(tok,record['messages'],limit)
        if item is None:dropped+=1
        else:items.append(item)
    if len(items)<25:raise RuntimeError(f'Dataset insuficiente: {len(items)} exemplos')
    if dropped/(len(items)+dropped)>.05:raise RuntimeError(f'Truncamento excessivo: {dropped} exemplos excluidos')
    return items,dropped


def run(args):
    import torch
    from transformers import AutoConfig,AutoTokenizer,AutoModelForCausalLM
    from peft import LoraConfig,get_peft_model,TaskType
    if os.getenv('HSA_OVERRIDE_GFX_VERSION'):
        raise RuntimeError('HSA_OVERRIDE_GFX_VERSION deve estar ausente')
    if not torch.version.hip or not torch.cuda.is_available() or not torch.cuda.is_bf16_supported(including_emulation=False):
        raise RuntimeError('Treino somente ROCm BF16 nativo, sem fallback silencioso')
    if not args.model.is_dir() or not args.model.joinpath('config.json').is_file():
        raise RuntimeError('Modelo HF local ausente')
    weights=list(args.model.glob('*.safetensors'))
    if not weights or sum(f.stat().st_size for f in weights)>4*1024**3:
        raise RuntimeError('Microtreino exige pesos textuais Safetensors locais <=4 GiB; 9B/7B proibidos neste perfil')
    cfg=AutoConfig.from_pretrained(args.model,local_files_only=True,trust_remote_code=False)
    multimodal = is_multimodal_config(cfg)
    if cfg.model_type not in TEXT_TYPES:
        raise RuntimeError('Arquitetura nao homologada para microtreino')
    if multimodal and cfg.model_type != 'qwen3_5':
        raise RuntimeError('Modelo multimodal fora da familia Qwen3.5; bloqueado')
    # Avoid accidentally loading 7B+ in full BF16 on 8 GiB.
    nparams=(getattr(cfg,'num_hidden_layers',0) or 0)*(getattr(cfg,'hidden_size',0) or 0)**2*16
    if nparams>2_800_000_000:
        raise RuntimeError('Estimativa >2B: este runner e exclusivamente para micro-modelos. Use outro perfil.')
    tok=AutoTokenizer.from_pretrained(args.model,local_files_only=True,trust_remote_code=False)
    train,drop=dataset(args.data/f'{args.entity}_train.jsonl',tok,args.max_length)
    valid,vdrop=dataset(args.data/f'{args.entity}_validation.jsonl',tok,args.max_length)
    if multimodal:
        from transformers import Qwen3_5ForConditionalGeneration
        factory = Qwen3_5ForConditionalGeneration
    else:
        factory = AutoModelForCausalLM
    model=factory.from_pretrained(args.model,local_files_only=True,
              trust_remote_code=False,torch_dtype=torch.bfloat16,device_map={'':0})
    if multimodal:
        model.model.visual.requires_grad_(False)
        print('QWEN3.5: visao congelada; LoRA SOMENTE nos modulos textuais',flush=True)
    model.config.use_cache=False
    model.requires_grad_(False)
    selected=[n for n,m in model.named_modules()
              if n.rsplit('.',1)[-1] in TARGETS and hasattr(m,'weight')
              and (not multimodal or '.language_model.' in '.' + n + '.')]
    if multimodal and any('.visual.' in '.'+n+'.' for n in selected):
        raise RuntimeError('LoRA visual selecionado indevidamente')
    if not selected:raise RuntimeError('Nenhum modulo textual suportado para LoRA')
    model=get_peft_model(model,LoraConfig(task_type=TaskType.CAUSAL_LM,r=args.rank,
         lora_alpha=2*args.rank,lora_dropout=0.05,bias='none',target_modules=selected))
    model.train()
    pars=[p for p in model.parameters() if p.requires_grad]
    if not pars or any(p.device.type!='cuda' for p in pars):raise RuntimeError('LoRA nao esta na GPU')
    optim=torch.optim.AdamW(pars,lr=5e-5)
    def inputs(ex):
        ids,labels=ex
        return dict(input_ids=torch.tensor([ids],dtype=torch.long,device='cuda'),
               labels=torch.tensor([labels],dtype=torch.long,device='cuda'),use_cache=False)
    def validation():
        model.eval();vals=[]
        # holdout fixo, amostragem deterministica por abrangencia
        with torch.no_grad():
            for k in range(6):
                ex=valid[round(k*(len(valid)-1)/5)]
                with torch.autocast('cuda',dtype=torch.bfloat16):loss=model(**inputs(ex)).loss
                v=float(loss.detach().cpu())
                if not math.isfinite(v):raise RuntimeError('Validacao nao-finita')
                vals.append(v)
        model.train();return sum(vals)/len(vals)
    torch.cuda.reset_peak_memory_stats()
    baseline=validation()
    seq=list(train);random.Random(2807).shuffle(seq)
    start=time.monotonic();steps=0;losses=[]
    maxsteps=4 if args.mode=='benchmark' else 100000
    while steps<maxsteps and (args.mode=='benchmark' or time.monotonic()-start<args.minutes*60):
        ex=seq[steps%len(seq)]
        with torch.autocast('cuda',dtype=torch.bfloat16):loss=model(**inputs(ex)).loss
        if not bool(torch.isfinite(loss)):raise RuntimeError('Loss nao-finita')
        loss.backward()
        if not all(p.grad is not None and bool(torch.isfinite(p.grad).all()) for p in pars):
            raise RuntimeError('Gradientes ausentes ou nao finitos')
        torch.nn.utils.clip_grad_norm_(pars,1.0,error_if_nonfinite=True)
        optim.step();optim.zero_grad(set_to_none=True)
        steps+=1;losses.append(float(loss.detach().cpu()))
        if steps%4==0:print(f'UPDATE {steps} CE={losses[-1]:.4f}',flush=True)
    torch.cuda.synchronize();elapsed=time.monotonic()-start
    current=validation()
    peak=torch.cuda.max_memory_allocated()/1024**3
    if peak>7.75:raise RuntimeError(f'Pico VRAM inseguro: {peak:.2f}GiB')
    record={'ok':True,'entity':args.entity,'mode':args.mode,'rank':args.rank,
        'max_length':args.max_length,'steps':steps,'seconds':elapsed,
        'steps_per_second':steps/max(elapsed,0.001),'baseline_val_loss':baseline,
        'after_val_loss':current,'val_improvement':baseline-current,
        'peak_vram_gib':peak,'gpu':torch.cuda.get_device_name(0),
        'rocm':torch.version.hip,'torch':torch.__version__,'train_sha256':sha256(args.data/f'{args.entity}_train.jsonl'),
        'model_config_sha256':sha256(args.model/'config.json'),
        'model':str(args.model),'train_dropped':drop,'val_dropped':vdrop,
        'architecture':'qwen3_5_multimodal' if multimodal else cfg.model_type,
        'note':'Microteste curto; nao valida personalidade nem qualidade final do 9B.'}
    if args.mode=='mini-train':
        tmp=args.out.with_name(args.out.name+'.tmp-'+uuid.uuid4().hex[:8]);tmp.mkdir(parents=True)
        model.save_pretrained(tmp,safe_serialization=True)
        if not (tmp/'adapter_model.safetensors').is_file():raise RuntimeError('Falha em salvar adaptador')
        (tmp/'micro_result.json').write_text(json.dumps(record,indent=2))
        tmp.rename(args.out) # refuses existing target by explicit precheck below
        print('ADAPTADOR ISOLADO:',args.out,flush=True)
    else:
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(json.dumps(record,indent=2),encoding='utf8')
    print('MICROTREINO CONCLUIDO:',json.dumps(record,ensure_ascii=False),flush=True)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--mode',choices=('benchmark','mini-train'),required=True)
    p.add_argument('--entity',choices=('hoshino','lilith'),required=True)
    p.add_argument('--model',type=Path,required=True)
    p.add_argument('--data',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--rank',type=int,choices=(4,8),default=4)
    p.add_argument('--max-length',type=int,choices=(128,160,256),default=256)
    p.add_argument('--minutes',type=int,default=3)
    a=p.parse_args()
    a.model=a.model.expanduser().resolve();a.data=a.data.expanduser().resolve();a.out=a.out.expanduser().absolute()
    if a.out.exists():p.error('Saida ja existe. Use nova pasta para preservar resultados')
    if a.mode=='mini-train' and not 2<=a.minutes<=15:p.error('Treinos curtos: de 2 a 15 minutos')
    if shutil.disk_usage(a.out.parent if a.out.parent.exists() else Path.home()).free<2*1024**3:
        p.error('Menos de 2GiB livres')
    try:run(a)
    except Exception as e:
        print(f'MICROTREINO FALHOU: {type(e).__name__}: {e}',file=sys.stderr)
        return 1
    return 0
if __name__=='__main__':raise SystemExit(main())
