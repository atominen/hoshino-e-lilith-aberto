#!/usr/bin/env python3
"""Experimental TEXT LoRA on MULTIMODAL Qwen3.5 for independent entity corpora.

NOT proven on RX 6650 XT (8 GiB). This program fails closed when the ROCm
backend, QLoRA or memory budget cannot support a complete backward pass.
It never opens or modifies the project's real Ollama models, memory or identities.
The LoRA is tied to the exact UNCENSORED Safetensors model revision, and
NOT automatically deployable to the existing Ollama GGUF.
The full multimodal architecture is preserved; adaptation trains TEXT paths only.
Vision weights stay frozen. Runtime multimodal quality needs a separate test.
"""
import argparse
import contextlib
import hashlib
import json
import math
import os
from pathlib import Path
import random
import signal
import shutil
import sys
import time


STOP_REQUESTED = False

def request_stop(signum, frame):
    global STOP_REQUESTED
    STOP_REQUESTED = True
    print(f"SINAL {signum}: parar após a etapa atual e salvar checkpoint.", flush=True)


def atomic_json(path, data):
    tmp = path.with_suffix(path.suffix + '.tmp')
    with tmp.open('w', encoding='utf8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


def fingerprint(args):
    path = args.model / 'config.json'
    data = path.read_bytes()
    rev_file = args.model / 'lab_revision.json'
    rev_sha = hashlib.sha256(rev_file.read_bytes()).hexdigest() if rev_file.is_file() else 'REVISION_UNTRACKED'
    dataset = args.data / f'{args.entity}_train.jsonl'
    return dict(model=str(args.model.resolve()), config_sha256=hashlib.sha256(data).hexdigest(),
                revision_metadata_sha256=rev_sha,
                dataset_sha256=hashlib.sha256(dataset.read_bytes()).hexdigest(),
                entity=args.entity, max_length=args.max_length, lora_rank=args.rank,
                vision_cpu=bool(args.vision_cpu), activation_cpu=bool(args.activation_cpu),
                embedding_cpu=bool(args.embedding_cpu), optimizer_probe=True, offload_audit='v095_selective_128MiB_12steps')


def preflight(args):
    if os.environ.get('HSA_OVERRIDE_GFX_VERSION'):
        raise RuntimeError('Use env -u HSA_OVERRIDE_GFX_VERSION; nunca altere ~/.bashrc automaticamente')
    if args.embedding_cpu and not args.vision_cpu:
        raise RuntimeError('Offload de embedding exige --vision-cpu.')
    if args.activation_cpu and not args.vision_cpu:
        raise RuntimeError('Offload de ativacoes exige --vision-cpu: evitar visao inteira na VRAM.')
    if args.activation_cpu and not hasattr(__import__('torch').autograd.graph, 'saved_tensors_hooks'):
        raise RuntimeError('PyTorch nao oferece torch.autograd.graph.saved_tensors_hooks')
    if args.vision_cpu:
        # Mixed map is opt-in and only the frozen vision path may reside on CPU.
        try:
            available_kib = next(int(x.split()[1]) for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:'))
        except (OSError, StopIteration, ValueError, IndexError) as exc:
            raise RuntimeError('Não consegui verificar RAM disponível para encoder visual CPU.') from exc
        if available_kib < 4*1024*1024:
            raise RuntimeError('Offload visual CPU exige ao menos 4 GiB de RAM disponível.')
    if not args.model.is_dir() or not (args.model/'config.json').is_file():
        raise RuntimeError(f'Checkpoint HF completo não encontrado: {args.model}')
    if not (args.data/f'{args.entity}_train.jsonl').is_file():
        raise RuntimeError('Dataset v2 extraído não encontrado. Veja --data.')
    if not (args.data/f'{args.entity}_validation.jsonl').is_file():
        raise RuntimeError('Validação v2 não encontrada.')
    if args.out.resolve().is_relative_to(args.model.resolve()):
        raise RuntimeError('Saída não pode ficar dentro dos pesos-base.')
    if args.rank not in (4, 8, 16) or not 96 <= args.max_length <= 1024:
        raise RuntimeError('Use rank 4/8/16 e sequência 96–1024, após validação de VRAM.')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(args.out.parent).free < 2 * 1024**3:
        raise RuntimeError('Menos de 2GiB de disco livre para checkpoints. Interrompido.')
    import torch
    if not torch.version.hip or not torch.cuda.is_available():
        raise RuntimeError('GPU ROCm indisponível; não utilizar fallback CPU.')
    major, minor = torch.cuda.get_device_capability(0)
    print(f'GPU={torch.cuda.get_device_name(0)} ROCm={torch.version.hip} PyTorch={torch.__version__}; capability={major}.{minor}', flush=True)
    if not torch.cuda.is_bf16_supported(including_emulation=False):
        raise RuntimeError('BF16 GPU nativo não confirmado; interrompido.')
    x = torch.ones(64, 64, dtype=torch.bfloat16, device='cuda', requires_grad=True)
    y = (x @ x).float().square().mean()
    y.backward()
    torch.cuda.synchronize()
    if not torch.isfinite(y) or not torch.isfinite(x.grad).all():
        raise RuntimeError('Teste BF16/backward não finito.')
    del x, y
    print('ROCm BF16 forward/backward básico: PASSOU', flush=True)


def tokenize(tok, messages, limit):
    # No educational system/persona prompt. Qwen3.5's native format is required.
    if not isinstance(messages, list) or len(messages) < 2 or messages[-1].get('role') != 'assistant':
        raise RuntimeError('Exemplo sem mensagens válidas/target assistant.')
    if any(m.get('role') not in {'assistant', 'user'} for m in messages):
        raise RuntimeError('Dataset incluiu role de system/tool: interrompido.')
    opts = dict(tokenize=False, enable_thinking=False)
    prefix = tok.apply_chat_template(messages[:-1], add_generation_prompt=True, **opts)
    full = tok.apply_chat_template(messages, add_generation_prompt=False, **opts)
    if not isinstance(prefix, str) or not isinstance(full, str) or not full.startswith(prefix):
        raise RuntimeError('Template Qwen3.5 não preserva o prefixo: inspecione-o antes de treinar.')
    prefix_ids = tok(prefix, add_special_tokens=False).input_ids
    full_ids = tok(full, add_special_tokens=False).input_ids
    if full_ids[:len(prefix_ids)] != prefix_ids:
        raise RuntimeError('Fronteira BPE/tokenizer incorreta: não mascarar automaticamente.')
    if len(full_ids) > limit:
        return None
    labels = [-100]*len(prefix_ids) + full_ids[len(prefix_ids):]
    if not any(v >= 0 for v in labels):
        raise RuntimeError('Exemplo sem tokens alvo de assistant.')
    return full_ids, labels


def load_data(tok, args, split):
    source = args.data/f'{args.entity}_{split}.jsonl'
    examples, dropped = [], 0
    for i, line in enumerate(source.read_text(encoding='utf8').splitlines(), 1):
        if not line.strip(): continue
        record = json.loads(line)
        item = tokenize(tok, record['messages'], args.max_length)
        if item is None:
            dropped += 1
            continue
        examples.append(item)
    if len(examples) < 25:
        raise RuntimeError(f'{split}: apenas {len(examples)} exemplos elegíveis; interrompido.')
    total = len(examples)+dropped
    print(f'{split}: {len(examples)} elegíveis; {dropped} excedem {args.max_length} tokens ({dropped/total:.0%}).', flush=True)
    if split == 'train' and dropped/total > .35:
        raise RuntimeError('Mais de 35% do treino não cabe no orçamento. Rever length/corpus; não treinar seletivamente.')
    return examples


def audit_offloaded_parameters(outside, vision_cpu=False, embedding_cpu=False):
    """Verify allowed CPU/meta subtrees without confusing vision and input embeddings.

    This checks what was actually placed outside CUDA, not only the requested map.
    All other text parameters must remain on GPU; LoRA placements are checked after
    PEFT attachment separately.
    """
    visual = [name for name in outside if name.startswith('model.visual.')]
    embeddings = [name for name in outside
                  if name.startswith('model.language_model.embed_tokens.')]
    unexpected = [name for name in outside if not (
        (vision_cpu and name.startswith('model.visual.')) or
        (embedding_cpu and name.startswith('model.language_model.embed_tokens.')))]
    if unexpected:
        raise RuntimeError('Parâmetros TEXTUAIS fora da GPU: ' + repr(unexpected[:8]))
    if vision_cpu and not visual:
        raise RuntimeError('Offload visual não comprovado. GPU insuficiente: não prosseguir.')
    if embedding_cpu and not embeddings:
        raise RuntimeError('Embeddings não foram descarregados da VRAM; bloqueado.')
    return visual, embeddings


def load_model(args):
    import torch
    from transformers import AutoTokenizer, BitsAndBytesConfig, Qwen3_5ForConditionalGeneration, AutoConfig
    from peft import LoraConfig, get_peft_model
    cfg = AutoConfig.from_pretrained(str(args.model), local_files_only=True, trust_remote_code=False)
    if cfg.model_type != "qwen3_5" or not hasattr(cfg,"vision_config"):
        raise RuntimeError("Checkpoint não é Qwen3.5 multimodal com vision_config")
    if args.embedding_cpu and bool(getattr(cfg,'tie_word_embeddings',False)):
        raise RuntimeError('Embeddings e lm_head compartilham pesos (tied); offload misto bloqueado.')
    if not any((args.model / filename).is_file() for filename in ('processor_config.json','preprocessor_config.json')):
        raise RuntimeError('Falta processor_config.json/preprocessor_config.json da modalidade visual')
    tok = AutoTokenizer.from_pretrained(str(args.model), local_files_only=True, trust_remote_code=False)
    if not tok.chat_template:
        raise RuntimeError('Tokenizer sem chat template nativo.')
    # Workaround observed in the SEPARATE Qwen2.5 7B ROCm laboratory; 9B not validated.
    if args.disable_warmup:
        import transformers.modeling_utils as utils
        if not hasattr(utils, 'caching_allocator_warmup'):
            raise RuntimeError('Workaround de warmup incompatível com esta versão do Transformers.')
        utils.caching_allocator_warmup = lambda *a, **kw: None
        print('AVISO: workaround experimental de warmup do Transformers ativado.', flush=True)
    quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type='nf4',
                               bnb_4bit_use_double_quant=True,
                               bnb_4bit_compute_dtype=torch.bfloat16,
                               llm_int8_enable_fp32_cpu_offload=args.vision_cpu)
    # Qwen3.5 multimodal: frozen vision and optionally frozen INPUT EMBEDDINGS
    # live on CPU. Every transformer block, lm_head and trainable LoRA stays on GPU.
    # Explicit leaf subtree entries avoid ambiguous CPU-vs-GPU parent mappings.
    if args.embedding_cpu:
        mapping = {
            'model.visual': 'cpu',
            'model.language_model.embed_tokens': 'cpu',
            'model.language_model.layers': 0,
            'model.language_model.norm': 0,
            'lm_head': 0,
        }
    elif args.vision_cpu:
        mapping = {'model.visual': 'cpu', 'model.language_model': 0, 'lm_head': 0}
    else:
        mapping = {'': 0}
    model = Qwen3_5ForConditionalGeneration.from_pretrained(str(args.model), local_files_only=True,
                        quantization_config=quant, dtype=torch.bfloat16,
                        device_map=mapping, low_cpu_mem_usage=True, trust_remote_code=False)
    outside = [n for n,p in model.named_parameters() if p.device.type != 'cuda']
    visual_offloaded, embedding_offloaded = audit_offloaded_parameters(
        outside, vision_cpu=args.vision_cpu, embedding_cpu=args.embedding_cpu)
    if args.vision_cpu:
        if not hasattr(model.model, 'visual') or not hasattr(model.model, 'language_model'):
            raise RuntimeError('Estrutura multimodal Qwen3.5 mudou; verificação de offload falhou.')
        if getattr(model, 'hf_device_map', {}).get('model.visual') != 'cpu':
            raise RuntimeError('hf_device_map não confirma visual CPU; bloqueado.')
        print(f'OFFLOAD: encoder visual fora da GPU ({len(visual_offloaded)} parâmetros); '
              'camadas textuais na GPU.', flush=True)
    if args.embedding_cpu:
        emb = model.get_input_embeddings()
        head = model.get_output_embeddings()
        if emb is None or head is None or not hasattr(emb, 'weight') or not hasattr(head, 'weight'):
            raise RuntimeError('Nao localizei embeddings de entrada/saida; offload nao comprovado.')
        if emb.weight.device.type not in ('cpu','meta') or head.weight.device.type != 'cuda':
            raise RuntimeError('Embedding CPU e head GPU nao foram comprovados; bloqueado.')
        device_map = getattr(model, 'hf_device_map', {})
        if device_map.get('model.language_model.embed_tokens') != 'cpu':
            raise RuntimeError('hf_device_map nao confirma embedding CPU; bloqueado.')
        if not embedding_offloaded:
            raise RuntimeError('Embeddings nao foram descarregados da VRAM; bloqueado.')
        print('OFFLOAD EMBEDDING: input embeddings congelados CPU; lm_head e LoRA ROCm GPU.', flush=True)
        print('MATRIZ EMBEDDING: shape=%s, dtype=%s, %.2f GiB no CPU.' % (
            tuple(emb.weight.shape), emb.weight.dtype,
            emb.weight.numel()*emb.weight.element_size()/1024**3), flush=True)
    print('Modelo carregado. VRAM reservada: %.2fGiB; alocada: %.2fGiB; livre: %.2fGiB' %
          (torch.cuda.memory_reserved()/1024**3,torch.cuda.memory_allocated()/1024**3,
           torch.cuda.mem_get_info()[0]/1024**3),flush=True)
    model.requires_grad_(False)
    model.config.use_cache = False
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False})
    if hasattr(model,'enable_input_require_grads'): model.enable_input_require_grads()
    expected = {'q_proj','k_proj','v_proj','o_proj',
                'in_proj_qkv','in_proj_a','in_proj_b','in_proj_z','out_proj',
                'gate_proj','up_proj','down_proj'}
    found = {n.rsplit('.',1)[-1] for n,m in model.named_modules()
             if n.rsplit('.',1)[-1] in expected and hasattr(m,'weight')}
    if 'up_proj' not in found or 'down_proj' not in found or 'in_proj_qkv' not in found:
        raise RuntimeError('Arquitetura híbrida inesperada; inspeção manual de LoRA targets necessária: '+repr(sorted(found)))
    selected = [n for n,m in model.named_modules()
                if "language_model" in n and n.rsplit(".",1)[-1] in found and hasattr(m,"weight")]
    if not selected:
        raise RuntimeError("Impossível localizar camadas textuais; recuso adaptar módulos visuais")
    print(f"Módulos LoRA textuais: {len(selected)}; visão congelada", flush=True)
    model = get_peft_model(model, LoraConfig(task_type='CAUSAL_LM',r=args.rank,lora_alpha=args.rank,
                                            lora_dropout=0.05,bias='none',target_modules=selected))
    model.print_trainable_parameters()
    extra = [n for n,p in model.named_parameters() if p.requires_grad and p.device.type != 'cuda']
    if extra: raise RuntimeError('LoRA treinável fora da GPU: '+repr(extra[:8]))
    return model,tok



# v0.9.5: save_on_cpu moved the frozen 1.89 GiB output projection
# out of VRAM and tried to restore a SECOND 1.89 GiB copy during
# backward, causing OOM on the second training example. Keep large
# tensors where they already live; offload only smaller activations.
ACTIVATION_CPU_LIMIT_BYTES = 128 * 1024 * 1024

def activation_storage_policy(device_type, nbytes):
    if device_type != 'cuda' or nbytes >= ACTIVATION_CPU_LIMIT_BYTES:
        return 'resident'
    return 'cpu'

def selective_save_on_cpu(torch):
    counters = {'cpu': 0, 'resident_large': 0, 'offloaded_bytes': 0}
    def pack(t):
        nbytes = t.numel() * t.element_size()
        policy = activation_storage_policy(t.device.type, nbytes)
        if policy == 'resident':
            if t.device.type == 'cuda' and nbytes >= ACTIVATION_CPU_LIMIT_BYTES:
                counters['resident_large'] += 1
            return ('resident', t)
        counters['cpu'] += 1
        counters['offloaded_bytes'] += nbytes
        return ('cpu', t.device, t.to('cpu', non_blocking=False))
    def unpack(item):
        kind, *rest = item
        if kind == 'resident':
            return rest[0]
        if kind == 'cpu':
            device, tensor = rest
            return tensor.to(device, non_blocking=False)
        raise RuntimeError('Formato de tensor salvo inesperado')
    return torch.autograd.graph.saved_tensors_hooks(pack, unpack), counters

def run_one(model, example, optimizer=None, activation_cpu=False):
    import torch
    ids, labels = example
    model.train()
    data = dict(input_ids=torch.tensor([ids],dtype=torch.long,device='cuda'),
                attention_mask=torch.ones((1,len(ids)),device='cuda',dtype=torch.long),
                labels=torch.tensor([labels],dtype=torch.long,device='cuda'),use_cache=False)
    # Save intermediate tensors in system RAM; rehydrate onto the original GPU
    # during backward. This is storage offload, NOT CPU neural computation.
    # Surround both forward and backward because checkpointing may recompute in backward.
    if activation_cpu:
        saver, counters = selective_save_on_cpu(torch)
    else:
        saver, counters = contextlib.nullcontext(), None
    with saver:
        with torch.autocast('cuda',dtype=torch.bfloat16):
            loss = model(**data).loss
        if not bool(torch.isfinite(loss)):
            raise RuntimeError('CE não finita.')
        loss.backward()
    torch.cuda.synchronize()
    grads=[p.grad for p in model.parameters() if p.requires_grad and p.grad is not None]
    if not grads or not all(bool(torch.isfinite(g).all()) for g in grads):
        raise RuntimeError('Gradientes LoRA ausentes/não finitos.')
    if optimizer is not None:
        torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad],1.,error_if_nonfinite=True)
        optimizer.step()
        optimizer.zero_grad(set_to_none=True)
    return float(loss.detach().cpu())


def evaluate(model, examples, n=16):
    import torch
    model.eval(); values=[]
    with torch.no_grad():
        # Uniformly sample across the holdout file; avoid judging only its first category.
        indices = [int(i*(len(examples)-1)/max(1,min(n,len(examples))-1))
                   for i in range(min(n,len(examples)))]
        for idx in indices:
            ids,labels=examples[idx]
            x=torch.tensor([ids],device='cuda',dtype=torch.long)
            y=torch.tensor([labels],device='cuda',dtype=torch.long)
            with torch.autocast('cuda',dtype=torch.bfloat16):
                loss=model(input_ids=x,labels=y,use_cache=False).loss
            if not bool(torch.isfinite(loss)):raise RuntimeError('Validação não finita.')
            values.append(float(loss.detach()))
    return sum(values)/len(values)


def probe_visual_forward(model, args):
    """Minimal genuine image forward; image encoder is not fine-tuned here."""
    import torch
    from PIL import Image
    from transformers import AutoProcessor
    processor = AutoProcessor.from_pretrained(str(args.model), local_files_only=True, trust_remote_code=False)
    image = Image.new('RGB', (64, 64), color=(218, 42, 32))
    messages = [{'role': 'user', 'content': [
        {'type': 'image', 'image': image},
        {'type': 'text', 'text': 'Qual é a cor predominante na imagem?'}]}]
    inputs = processor.apply_chat_template(messages, tokenize=True, add_generation_prompt=True,
                                           enable_thinking=False, return_dict=True, return_tensors='pt')
    if not hasattr(inputs, 'keys') or 'pixel_values' not in inputs:
        raise RuntimeError('Processor não gerou pixel_values para a imagem: visão não validada.')
    inputs = {k: (v.to('cuda') if hasattr(v, 'to') else v) for k,v in inputs.items()}
    model.eval()
    with torch.inference_mode(), torch.autocast('cuda', dtype=torch.bfloat16):
        outputs=model(**inputs, use_cache=False)
        logits=outputs.logits[:, -1, :]
    if not bool(torch.isfinite(logits).all()):
        raise RuntimeError('Forward com imagem não finito.')
    print('PROBE VISUAL: forward com imagem real passou. Não avalia acerto semântico.', flush=True)
    del inputs, outputs, logits
    torch.cuda.empty_cache()


def save_adapter(model,args,step,tag,metadata):
    dest=args.out/'checkpoints'/f'{tag}-passo-{step:06d}'
    if dest.exists():raise RuntimeError(f'Checkpoint já existe, não sobrescrever: {dest}')
    if shutil.disk_usage(args.out).free < 1024**3:
        raise RuntimeError('Espaço em disco insuficiente para checkpoint (menos de 1GiB).')
    temp=dest.with_name('.tmp-'+dest.name)
    if temp.exists():raise RuntimeError('Staging de checkpoint antigo; examinar antes: '+str(temp))
    temp.mkdir(parents=True)
    model.save_pretrained(str(temp),safe_serialization=True)
    atomic_json(temp/'run_metadata.json',metadata)
    if not (temp/'adapter_config.json').exists():raise RuntimeError('Adaptador não foi escrito.')
    temp.rename(dest)
    print('CHECKPOINT',dest,flush=True)
    return dest


def main():
    raise RuntimeError('Runner histórico aposentado. Use laboratorio.treino_nf4_curto / treinos_unificados; bases e checkpoints antigos foram preservados.')


if __name__=='__main__':main()
