"""Registo técnico restrito. A UI jamais lista candidatos ausentes do SSD.

Nenhum item do catálogo equivale a aprovação na GPU ou Ollama.
"""
MODELS = (
    dict(id='qwen3-6b-sniper', name='Qwen3-6B SNIPER — preservado, fora da troca dinâmica', size='6B', kind='texto',
         repo='parmanu-lcs2/Qwen3-6B', revision='d6990725bfc555b09e1c1b76bd07cd0dcaf7aceb',
         source_files={'modeling_pruned.py':'e0cd39bd87f11283ddf03e1b0eea7737f93a3288a2a80486b935903f44d9d3d5',
                       'model.safetensors':'ec6f314ecec0f1839d3e22c2de56adddb27f5899b146f8e69f4627e1253e19c1'},
         vision=False, thinking=True, thinking_toggle='template', training='pesquisa', license='Apache-2.0',
         score='Preservado por pedido do proprietário; troca dinâmica somente 7B/9B. Ensaio NF4 não homologou; conversor atual sem suporte. Somente pesquisa, sem treino/ativação automática.',
         source='https://huggingface.co/parmanu-lcs2/Qwen3-6B'),
    dict(id='qwen3-4b', name='Qwen3-4B — retirado (histórico)', size='4B', kind='texto',
         repo='Qwen/Qwen3-4B', vision=False, thinking=True, thinking_toggle='hard',
         experimental_only=True, replacement_eligible=False, retired=True,
         training='texto_qlora',license='Apache-2.0',
         score='Retirado a pedido do proprietário; download bloqueado. Hoshino/Lilith usam 7B/9B; Alistair mantém seu modelo próprio.',
         source='https://huggingface.co/Qwen/Qwen3-4B'),
    dict(id='qwen3-8b', name='Qwen3-8B', size='8B', kind='texto',
         repo='Qwen/Qwen3-8B', vision=False, thinking=True, thinking_toggle='hard',
         training='texto_qlora',license='Apache-2.0',
         score='Qwen3 denso; alternância enable_thinking no template; +1B acima do alvo 7B.',
         source='https://huggingface.co/Qwen/Qwen3-8B'),
    dict(id='yi15-6b', name='Yi-1.5-6B-Chat', size='6B', kind='texto',
         repo='01-ai/Yi-1.5-6B-Chat', vision=False, thinking=False,
         retired=True,
         thinking_toggle='unsupported',training='texto_qlora',license='Apache-2.0',
         score='Retirado pelo proprietário em24/10 após reprovação. Registro histórico; download bloqueado.',
         source='https://huggingface.co/01-ai/Yi-1.5-6B-Chat'),
    dict(id='hunyuan-7b', name='Hunyuan-7B-Instruct', size='7B', kind='texto',
         repo='tencent/Hunyuan-7B-Instruct',vision=False,thinking=True,thinking_toggle='template',
         training='texto_qlora',license='Tencent Hunyuan Community',
         score='Thinking on/off documentado; anteriormente descartado: experimental, não candidato aprovado.',
         source='https://huggingface.co/tencent/Hunyuan-7B-Instruct'),
)
BY_ID = {x['id']:x for x in MODELS}
