# Armazenamento, proveniência e restauração dos executores — 13/10/2026

## Escopo e estado encontrado

Rodada autorizada após a auditoria de organização: limpar resíduos de baixo
risco e verificar a restauração local dos executores. Não instalar novos
candidatos, alterar identidades, apagar memórias/checkpoints ou iniciar treino.

Código inicial: branch `codex/laboratorio-consolidacao-20261012`, commit
`ccd0133b310255d13269e8f0e91dde9fbb739ea2`; working tree limpo antes deste relatório.

A separação atual foi preservada: `app`/`laboratorio` para código,
`entidades` para dados/configurações individuais, `compartilhado` para serviços
e artefatos de execução, `laboratorio-local` para bases HF, corpora e candidatos.
Os links `~/hoshino` e `~/laboratorio-lora` são compatibilidade, não novas cópias.

### Problema de produção confirmado

Contagem de arquivos nos stores configurados, sem iniciar inferência:

| Store | Manifests | Blobs | Resultado |
|---|---:|---:|---|
| `compartilhado/modelos/ollama` | 0 | 0 | Executores de Hoshino ausentes |
| `compartilhado/modelos/ollama-lilith` | 0 | 0 | Executores de Lilith ausentes |
| `compartilhado/modelos/ollama-alistair` | 1 | 4 | Alias/pesos presentes; não é novo teste físico |

As bases HF de treinamento **não equivalem** a executores registrados no
Ollama. A Central não deve ser considerada pronta para conversar com
Hoshino/Lilith só porque essas bases existem. Esta rodada não descobriu quem
ou qual operação removeu os stores; não atribuir causa sem evidência.

## Limpeza executada e preservação

1. Cache de pacotes em `/home/gustavo/.cache/pip`: limpeza pela ferramenta
   oficial, 1.064 arquivos/41 diretórios, 2.407,3 MB reportados. Inclui cache
   HTTP e dez wheels; nenhum pacote instalado foi desinstalado. Conteúdo
   recuperável por novos downloads, não por um backup criado nesta rodada.
2. Parcial redundante do Yi removido: 272.629.760 bytes (260 MiB), arquivo
   `modelos-extras/yi15-6b/hf/.cache/huggingface/download/`
   `D5-QTaCbl9VUFv9Wr0C28eFewRc=.3c6d2c5eb6283ee9ce45bbd3f28a7a235a3465f7c4d499d75aa0eeec1cdba8cb.65bc9a9c.incomplete`.
   Antes da exclusão, o shard completo `model-00002-of-00003.safetensors`
   passou em SHA-256: `3c6d2c5eb6283ee9ce45bbd3f28a7a235a3465f7c4d499d75aa0eeec1cdba8cb`.
   Não havia downloader identificado nem arquivo parcial aberto no `lsof`.
   O shard completo de 4.976.802.816 bytes foi preservado.
3. Ambiente antigo `laboratorio-local/.venv`: removido após guardar o manifesto
   de dependências abaixo; sem consumidores encontrados nos scripts, serviços e autostart
   examinados, nem processo Python com esse ambiente mapeado. Manifesto abaixo.
   O ambiente atual `.venv-rocm` é separado e permanece intacto.
   Aproximadamente 1,38 GiB adicionais liberados; reconstrução exige reinstalar
   os pacotes, não há backup binário desse ambiente descartável.

Espaço livre inicial: 9.712.955.392 bytes (9,05 GiB). Depois dos itens 1–2:
12.395.069.440 bytes (11,54 GiB). Diferenças de espaço livre incluem atividade
normal do sistema; não são uma medida exata dos bytes apagados.
Depois dos três itens: 13.880.360.960 bytes (12,93 GiB), aproximadamente
3,88 GiB a mais do que no início. Ainda faltam cerca de 37 GiB para atingir
a folga estimada de preparação de 50 GiB.

Preservados: todas as bases completas, professor 35B, Yi/Hunyuan/Alistair HF,
Qwen-Image/visão/TTS, ambiente ROCm atual, datasets, adaptadores, checkpoints,
históricos, bancos mentais, identidades, relatórios e pacote PC2.
Não purgar a pasta `.cache` inteira: contém runtimes e outros consumidores.

## Conversão: ressalvas importantes

| Artefato local | Proveniência / precisão | Consequência |
|---|---|---|
| Qwen3.5 9B HF | `ccharnkij/Qwen3.5-9B-Uncensored`, checkpoint completo F16, ~17,53 GiB | Pode ser convertido/quantizado localmente, sujeito a espaço e validação; não é a variante oficial intocada da Qwen |
| Qwen2.5 7B HF | GGUF Q4_K_M desquantizado para 17 shards F16, ~14,19 GiB | F16 descreve o armazenamento, não precisão original recuperada; nova quantização não deve ser chamada de conversão sem perda |
| Professor 35B | Apenas GGUF Q3_K_M, ~15,23 GiB | Não produz uma base original BF16 ou Q4 de qualidade superior por reconversão |
| Yi-1.5 6B Chat | Base HF completa, candidato experimental | Sem obrigação de thinking; não promovido como executor de produção |

Evidência do 7B: `laboratorio-local/converter_qwen2_gguf.py` lê
`modelos/qwen2.5-7b-local/modelo.gguf`, desquantiza tensor a tensor e grava F16.
`laboratorio-local/pacote_neural_v3/DECISOES_MODELOS.md` documenta a origem Q4
e a perda prévia. O GGUF de origem desse conversor está atualmente ausente.
Não mesclar adaptadores experimentais Aster/Hoshino/Lilith para fabricar uma
base. Não chamar a base desquantizada de pesos originais oficiais.

### Espaço impede a restauração nesta rodada

O gate existente de `laboratorio/trabalhador.py` requer pesos × 1,40 + 12 GiB
livres antes de criar GGUF F16 e Q4_K_M:

- 9B: **36,54 GiB livres** apenas para a conversão inicial.
- 7B: **31,86 GiB livres** para a conversão, além dos executores 9B já instalados.

`/tmp` fica no mesmo filesystem, portanto não resolve a falta de espaço.
Não usar RAM/swap como disco temporário para contornar a reserva; não reduzir
margens nem iniciar uma exportação que possa encher o disco.

Planejar **ao menos 50 GiB livres** antes de retomar conversão sequencial e
instalação independente para as duas entidades. Essa é uma estimativa
conservadora de preparação, não tamanho final medido. Será recalculada com o
plano exato de staging/importação antes de qualquer carga.

O instalador atual exige cópias físicas independentes por entidade em
`scripts/preparar_executores_leves.py`; não trocar por hardlinks/store compartilhado
sem uma decisão explícita. A identidade continuar externa aos pesos não revoga
esse contrato de instalação.

Um GGUF recém-convertido/importado terá novo hash/manifest. Os perfis 9B
validados em `app/core/resource_manager.py` são presos aos manifests anteriores.
Não reaplicar automaticamente o selo de validação GPU antigo: verificar a nova
importação e executar um probe real conservador antes de registrar o perfil.

## Comparação dos 7B / 6B

Recomendação provisória continua Qwen2.5 7B, pelo protocolo atual: os probes
registrados no relatório v1.7 terminaram respostas Qwen, enquanto os Hunyuan
esgotaram o orçamento em thinking e seu template não respeitou a flag OFF.
Isso **não** é aprovação humana de personalidade ou A/B completo. Não usar
loss de tokenizadores diferentes como ranking direto de qualidade.

O Yi 6B é candidato do laboratório e não precisa de modo de raciocínio.
Não foi instalado um novo executor 6B nesta rodada.

## Validações desta rodada

- SHA-256 completo do shard Yi: passou antes da exclusão do parcial.
- Cache pip após limpeza: zero arquivos HTTP/wheels; pacotes do ambiente atual intactos.
- `.venv-rocm/bin/python` importou o módulo GGUF instalado localmente.
- Painel existente `http://127.0.0.1:8788/`: HTTP 200 após a limpeza, sem restart.
- Ollama sistêmico em 11434: GET `/api/tags` retornou `{"models":[]}`;
  não existe um executor de Hoshino/Lilith escondido nessa instância.
- Stores das três entidades: contagem acima; não houve pull/create/generate.
- Nenhuma entidade acordada, nenhum job de treino iniciado, nenhuma quota/cloud.
- Laboratório: **114/114 testes**, 2,729 s, exit 0 após a limpeza;
  `PYTHONPATH=app:. compartilhado/ambientes/principal/bin/python -B -m unittest discover -s laboratorio/tests -v`.
- Suíte oficial: **74/74 grupos offline**, `bash rodar_testes.sh`, exit 0
  após a limpeza. As duas suítes não fizeram chamadas de inferência real.
- Nenhum código funcional alterado. Nenhuma inferência ou homologação física
  de modelo nesta rodada. Apenas este relatório foi criado no checkout.

## Dependências do ambiente antigo (para eventual reconstrução)

Python 3.12.3, sem pacotes do sistema. Esta lista preserva versões, não garante
que os artefatos continuarão disponíveis no índice nem substitui um backup binário.

```text
accelerate==1.15.0
aiohappyeyeballs==2.7.1
aiohttp==3.14.4
aiosignal==1.4.0
annotated-doc==0.0.5
anyio==4.15.1
attrs==26.1.0
click==8.5.0
datasets==5.1.0
dill==0.4.1
filelock==3.32.3
frozenlist==1.8.0
fsspec==2026.7.0
h11==0.16.0
hf-xet==1.7.0
httpcore2==2.13.1
httpx2==2.13.1
huggingface_hub==2.2.0
idna==3.20
Jinja2==3.1.6
markdown-it-py==4.2.0
MarkupSafe==3.0.3
mdurl==0.1.2
mpmath==1.3.0
multidict==6.9.1
multiprocess==0.70.19
networkx==3.6.1
numpy==2.5.4
packaging==26.3
pandas==3.0.6
peft==0.21.2
pip==26.2.1
propcache==0.5.4
psutil==7.2.2
pyarrow==26.0.0
Pygments==2.21.0
python-dateutil==2.9.0.post0
PyYAML==6.0.3
regex==2026.9.29
rich==15.0.0
safetensors==0.8.0
sentencepiece==0.2.2
setuptools==84.0.0
shellingham==1.5.4
six==1.17.0
sympy==1.14.0
tokenizers==0.23.3
torch==2.14.1+cpu
tqdm==4.70.1
transformers==5.19.0
truststore==0.10.4
typer==0.27.3
typing_extensions==4.16.0
wheel==0.48.0
xxhash==4.0.1
yarl==1.25.1
```

## Próximos passos sujeitos ao espaço e à proveniência

1. Disponibilizar espaço seguro ou outro disco explicitamente autorizado.
2. Decidir a restauração do 7B: não apresentar a base desquantizada como original;
   recuperar o GGUF original verificado, caso o operador autorize esse download.
3. Converter/importar só os executores aprovados, com staging, hashes, tokenizer,
   template, término confirmado, testes físicos e validação de perfil GPU.
4. Só então registrar/restaurar os aliases na Central, preservando os dados mentais.

**Estado: limpeza parcial concluída; restauração de Hoshino/Lilith pendente.
Não declarar o sistema pronto para conversação real com elas.**
