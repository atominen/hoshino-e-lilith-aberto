# Substituição dos 7B e auditoria de atualização do LLM — 13/10/2026

## Autorização e limites

O usuário autorizou remover Death Stranding, os pesos dos dois 7B atuais
(Qwen2.5 desquantizado de Q4 e Hunyuan), baixar os pesos originais Qwen2.5 7B
e examinar o mecanismo de atualização/mudança do LLM.

Preservar 9B, Alistair 4B, Yi 6B, professor, corpora, identidades, memórias,
adapters, checkpoints e evidências. Não iniciar treinamento prolongado ou
promover adaptadores automaticamente. Não habilitar cloud/concurrency.

Estado de entrada: código `ccd0133b310255d13269e8f0e91dde9fbb739ea2`, branch
`codex/laboratorio-consolidacao-20261012`; relatório da rodada anterior ainda
não commitado. Nenhuma alteração preexistente será descartada.

## Instalação do jogo identificada

- Steam App ID: **1850570**, **DEATH STRANDING DIRECTOR'S CUT**, build 13300582.
- Diretório: `/home/gustavo/.steam/debian-installation/steamapps/common/DEATH STRANDING DIRECTORS CUT`.
- Dados encontrados: **79.794.891.886 bytes** (~74,3 GiB).
- Manifest de instalação: `steamapps/appmanifest_1850570.acf`.
- `compatdata/1850570` preservado, incluindo eventuais saves/configurações Proton.
- Steam/jogo não estavam em execução e `lsof` não encontrou arquivos da instalação abertos.
- Instalação e manifest removidos; filesystem passou de ~13 para ~88 GiB
  livres antes do novo download. Recuperação do jogo exige reinstalação pela
  Steam; não foi feito backup de 80 GB. Nenhum outro jogo foi removido.

## Base original escolhida

Fonte oficial: https://huggingface.co/Qwen/Qwen2.5-7B-Instruct

Revisão fixada: `a09a35458c702b33eeacc393d103063234e8bc28`.
API pública indica **7.615.616.512 parâmetros BF16**. Baixar Safetensors,
tokenizer, configuração, template/documentação/licença, sem pesos alternativos
PyTorch nem outro modelo. Download local não é backend cloud de inferência.

Usar staging isolado e validar checksums remotos, shards/index, arquitetura e
tokenizer antes de substituir `laboratorio-local/modelos/qwen2.5-7b-hf-local`.
O download/validação são pré-requisitos, não aprovação de personalidade ou treino.

## Consumidores e compatibilidade antes da substituição

- `laboratorio/treinos_unificados.py`: catálogo único aponta para os diretórios
  dos dois 7B; presets são aceitos somente com mesma base/config/corpus/perfil.
- `laboratorio/versionamento_lora.py`: checkpoint exige mesma config, shards
  (nomes/tamanhos/mtime), entidade, corpus e preset. Candidatos antigos não
  devem ser retomados como se tivessem treinado na base oficial nova.
- `laboratorio/treino_nf4_curto.py`, scripts históricos e adapters existentes
  referenciam o caminho Qwen2.5; manter o caminho canônico, preservando a
  proveniência antiga nos relatórios e a distinção entre bases.
- Hunyuan é um candidato removido por decisão do usuário: não apagar seus
  checkpoints/relatórios, não reinstalar automaticamente.
- Os stores Ollama Hoshino/Lilith estavam vazios na auditoria anterior. Baixar
  Safetensors não cria um executor Ollama nem restaura sozinho a conversação.

## Resultados

### Exclusões e instalação efetivas

1. Death Stranding e seu manifest foram removidos como descrito acima.
2. Qwen2.5 antigo: **17 shards / 15.231.271.360 bytes** removidos após validar
   a base substituta. Hunyuan: **4 shards / 15.009.178.056 bytes** removidos.
   São ~28,16 GiB de pesos antigos retirados; não foi guardado backup binário.
   Recuperação exige novo download/reconstrução da mesma base, não restaurar
   arbitrariamente os checkpoints sobre a base nova.
3. Metadados antigos preservados em
   `laboratorio-local/controle-laboratorio/treinamento-unificado/reports/substituicao-7b-20261013/`:
   subdiretórios `qwen25-7b-desquantizado` (~11 MiB) e `hunyuan-7b` (~16 MiB).
   São proveniência/tokenizers/configs, não modelos instalados. Seus índices
   continuam descrevendo os shards antigos, intencionalmente ausentes.
4. Base oficial nova instalada no mesmo caminho canônico
   `laboratorio-local/modelos/qwen2.5-7b-hf-local`: **4 shards BF16,
   15.231.271.888 bytes**, ~14,19 GiB. Não deriva de GGUF Q4 desquantizado.
   `lab_revision.json` registra revisão, origem e SHA-256 dos quatro pesos.
5. Locks existentes `start.lock` e `trabalhador.lock` adquiridos durante a
   substituição; nenhum worker/job ativo, arquivos antigos sem uso identificado
   pelo `lsof`. Movimentos ocorreram no mesmo filesystem antes de apagar os
   21 arquivos exatos. Não usar remoção recursiva da raiz do projeto.
6. Disco após substituição: **108.661.010.432 bytes livres (~101,2 GiB)**,
   `df -h` arredondou para 102G / 87% usado. Varia com outras aplicações.

### Validações físicas de instalação (não inferência)

- `hf download` terminou com exit 0 na revisão fixada; `hf cache verify`
  verificou **14/14 arquivos remotos**, exit 0, com `--fail-on-missing-files`.
  Aviso de 31 arquivos locais extras corresponde ao diretório `.cache` de
  metadados/locks do próprio download. Depois foi acrescentado o recibo local.
- SHA-256 independente completo dos quatro Safetensors: **4/4**, iguais aos
  hashes LFS publicados na revisão. Cabeçalhos/index/offsets conferidos:
  **339 tensores BF16**, **7.615.616.512 parâmetros**, arquitetura
  `qwen2`/`Qwen2ForCausalLM`, tensor bytes 15.231.233.024.
- Tokenizer oficial carregado offline, sem código remoto: `Qwen2Tokenizer`.
  Template preservou system/user e produziu 27 tokens com attention mask.
  Nenhum peso foi carregado em CPU/GPU, nenhuma geração ou treino ocorreu.
- Dois probes preliminares não passaram: um foi tentado antes da chegada de
  `vocab/tokenizer_config`; outro assumiu lista quando Transformers 5.19.0
  retorna `BatchEncoding` por default. Repetido somente depois do download
  completo, usando `return_dict=True` e conferindo `input_ids/attention_mask`:
  **PASS**. Não eram evidência de defeito dos pesos nem exigiram patch no modelo.
- Checkpoints reais `passo-000019` de Hoshino e Lilith validavam antes da troca.
  Depois, ambos recusados: **“Base ou corpus divergente; retomada recusada”**.
  Os corpora não mudaram; o hash da config/base mudou. Presets antigos de GPU:
  `measured_preset` retorna `None` nas duas entidades, corretamente.
- Catálogo existente: Qwen7 instalado/4 shards; Hunyuan ausente, treino
  desabilitado. Qwen7 ainda mostra etiqueta OOM histórica do catálogo e fica
  sem treino homologado: **não foi provocado OOM no novo original nesta rodada**.
  Requalificação física do preset é pendência, não transferir o selo antigo.
- Painel existente respondeu HTTP 200 sem restart. Stores Ollama continuam:
  Hoshino 0 manifests/0 blobs, Lilith 0/0, Alistair 1/4. Download HF **não
  restaura os executores de produção ausentes**. Conversação Hoshino/Lilith
  permanece pendente de conversão/importação/validação próprias.
- Fingerprint de metadados de **3.899 arquivos protegidos**, 64.560.482.058
  bytes (outros modelos, adapters/checkpoints, corpora, entidades, configs e
  store Alistair): idêntico antes/imediatamente depois da troca
  `a4defaec4c95f4ba3fcd4d79937cc791068b5a06ba34b48771f96140affc1c8c`.
  Confere caminho/tamanho/mtime/inode, **não equivale a SHA integral de 64 GB**.
  A execução direta posterior de testes alterou arquivos de telemetria,
  descritos no incidente abaixo; não alegar preservação integral desse
  fingerprint até o fim sem mencionar tal diferença.

### Incidente de isolamento encontrado na conferência final

A suíte direta do laboratório passou, mas `test_noite_supervisor.py` reutilizava
uma fixture que isolava processos/bus/Resource Manager e não isolava
`diagnostics.config.RUNTIME_DIR`, `history.DB` e o destino do logger. Suas
autorizações/restaurações **simuladas** acabaram no runtime real da Hoshino.
Não houve autorização noturna real, wake, treino ou alteração da memória mental.

Foram identificados **12 eventos desta rodada**, seis por execução direta:

- PID 251603, 12:44:09 UTC: diagnostic IDs `diag-a79c5c6101c8090e`,
  `diag-0ffc53ec130704e6`, `diag-6dd343009adfac28`, `diag-99dd9c6ff4827dc8`,
  `diag-4b2dfa87b504a3bd`, `diag-d02146ebc0c42364`.
- PID 255994, 12:55:57 UTC: `diag-4331d7cb28cffb8c`,
  `diag-152f3a6b51e38e14`, `diag-da8984add95022a3`, `diag-4c94009d4cc7a153`,
  `diag-b61af08d853aa03c`, `diag-1abc50f47bf29aab`.

Eventos `laboratory.night_authorized/night_restored` no JSONL/LOG de
13/10/2026 e espelho `runtime/history.sqlite3`: **não são evidência de noites
ou entidades de produção**. Foram preservados para auditoria, não apagados
nem classificados como memória factual. A consulta SQLite posterior somente
leitura também criou sidecars WAL/SHM; não excluir arquivos SQLite abertos.

Correção restrita à fixture: runtime/histórico em pasta temporária, logger
com FileHandler temporário real, patches restaurados no cleanup. Nova regressão
`test_night_diagnostics_are_really_persisted_only_in_fixture` verifica o evento
real no JSONL, LOG e espelho SQLite com mesmo diagnostic ID. Não silencia emit
nem usa mock de persistência para fabricar aprovação. A conexão de leitura do
teste é fechada explicitamente (um ResourceWarning preliminar foi corrigido).

Após a correção, a suíte direta inteira não alterou o novo fingerprint protegido:
**3.901 arquivos / 64.560.517.139 bytes**,
`dd06d3a4f2998203ac53de5785880225dc1529d7173ad3174f934c6d13cfc0e7`
antes/depois. A diferença contra o snapshot antigo está restrita às entradas
de diagnóstico/histórico e seus sidecars; nenhum outro arquivo protegido
teve atualização observada no intervalo.

### Regressões e suítes

Arquivo alterado: `laboratorio/tests/test_consolidacao.py`, duas regressões:

- `test_replaced_7b_shards_cannot_resume_old_checkpoint_at_same_path`:
  troca 17→4 shards em fixture isolada, mesmo caminho/config/corpus;
  retomada recusada por assinatura dos pesos.
- `test_replaced_7b_does_not_inherit_previous_gpu_benchmark`:
  benchmark antes elegível deixa de valer após substituição da base; novo
  modelo não herda treino habilitado nem `measured_candidate`.

Execução anterior à substituição: **116/116 testes do laboratório**, 2,577 s,
exit 0; **74/74 grupos oficiais offline**, exit 0. As duas novas regressões
passaram também no grupo `CheckpointTests`, **5/5**. Nenhum teste simulado
foi chamado de validação física de inferência, personalidade ou treino longo.
Execução posterior à substituição, antes da correção da fixture:
**116/116**, 2,274 s, exit 0; **74/74 grupos oficiais offline**, exit 0.
Esses números não ocultam o incidente de telemetria acima.
Após a correção: **117/117 testes**, 2,203 s, exit 0; grupo noturno **6/6**.
Suíte oficial final após corrigir isolamento: **74/74 grupos**, exit 0.
Grupo noturno repetido com ResourceWarning tratado como erro: **6/6**, 0,131 s,
sem warnings. Fingerprint protegido permaneceu inalterado após as repetições.
`git diff --check`: passou.
Comandos: `PYTHONPATH=app:. compartilhado/ambientes/principal/bin/python -B
-m unittest discover -s laboratorio/tests -v` e `bash rodar_testes.sh`.
Nenhum worker GPU/job de treino ativo na conferência final; zero Safetensors
nos dois diretórios de proveniência antiga; quatro shards no caminho novo.
Espaço final: 108.658.110.464 bytes livres (~101,2 GiB).

Nenhum componente funcional, identidade, scheduler, policy GPU/RAM ou backend
foi alterado. Além das regressões da base, `laboratorio/tests/test_noite_supervisor.py`
teve seu isolamento corrigido e uma regressão acrescentada.
Arquivos novos desta rodada: este relatório, recibo de origem
junto à base e README de proveniência junto aos metadados antigos.

## Auditoria da atualização/mudança do LLM

### 1. Aprendizado contextual: existe, não reescreve o checkpoint

`app/mind/scribe.py` registra observações de comportamento; `personality.py`
atualiza traços/gostos no SQLite da entidade com evidências. `daily_summary.py`
e `night_reflection.py` consolidam acontecimentos/reflexões. Isso é estado
externo, não gradiente nos pesos. Não foi provocado aprendizado real nesta rodada.

`app/core/prompting.py` constrói a identidade/constituição e incorpora o estado
consolidado, emoção/psicologia e memórias relevantes, preservando proveniência
de registros inteiros. As experiências podem alterar respostas futuras por esse
contexto, sem exigir que a base 9B/7B seja treinada a cada mensagem.

Limite: evidências/traços algorítmicos não demonstram consciência ou sentimentos
humanos; naturalidade e coerência longitudinal continuam dependentes de avaliação.

### 2. Alternância 9B/7B: existe, não é aprendizado paramétrico

`app/core/resource_manager.py::inference_cycle` guarda a escolha no escopo do
ciclo/tarefa assíncrona. `choose_executor` reutiliza a escolha em retries e
ferramentas; só outro ciclo permite selecionar de novo. `assess_executor`
considera contexto, residência/custo, recursos e qualidade conservadora.

Não trocar executor durante a mesma resposta. Identidade, memória e relações
não são trocadas com o modelo. O cliente remove a flag thinking para Qwen2.5
7B, que não fornece o canal nativo de raciocínio dos Qwen3.5.

### 3. Mudança dos pesos por LoRA: existe no laboratório, não contínua na produção

- `laboratorio/treino_nf4_curto.py`: congela a base, otimiza LoRA, mede pressão,
  salva checkpoints com optimizer/RNG/posição/relógio e candidato final.
- `versionamento_lora.py`: exige base/config/corpus/preset compatíveis; separa
  candidato, recarga/holdout, revisão humana, registro estável e rollback.
- `iniciar_entidades.py::authorize_night/night_tick`: sessão explicitamente
  autorizada, sono/drenagem, jobs serializados e restauração apenas de quem
  estava acordado. Não há treinamento incessante em segundo plano por conversa.
- Professor propõe material; proposta/critério lexical não são autorização de
  treino. Os problemas semânticos descritos no v1.8 continuam pendentes.

**A promoção estável altera somente referências do laboratório.** As funções
`promote` e `rollback` retornam `production_changed=false`; não publicam um
novo GGUF/Ollama nem atualizam automaticamente o executor de uma entidade.
Nenhum `stable/*/current.json` foi encontrado no laboratório nesta auditoria.

### 4. Aplicação em produção: há seletor, mas o ciclo completo não está fechado

`app/core/neural9b_modes.py` possui Original/Neural 9B por entidade.
`central_control.py::save_neural9b_mode` exige entidade dormindo, ausência de
job/lease e revisão de config; aplica na próxima inicialização. No estado atual
não há arquivo de seleção, portanto o default é Original.

O seletor exige um alias neural instalado, mas seu `model_ready` confere
manifest, formato de digest, existência/tamanho dos blobs e um peso grande.
**Isso não vincula o alias à avaliação aprovada, autoria do adaptador,
revisão estável ou hash integral efetivamente conferido.** O registro estável
do laboratório e esse alias não estão ligados automaticamente.

Por isso, não afirmar que “aprendeu hoje e amanhã já executará o LLM atualizado”.
Exportação/importação de uma versão estável, verificação, ativação durante sono
e rollback efetivo do executor ainda precisam de homologação conjunta. O seletor
Neural 9B também não representa um mecanismo de atualização do executor 7B.
Nenhuma dessas lacunas foi mascarada habilitando um adaptador nesta rodada.

### Riscos / próximos refinamentos (não implementados por uma auditoria)

1. Ligar exportação/importação à mesma base, entidade, adapter SHA e avaliação
   aprovada usando os registros existentes; não criar outro scheduler/registro.
2. Verificar o artefato implantado e correlacionar a versão ao turno, permitindo
   reverter a versão executada, não só a referência estável do laboratório.
3. `base_signature` hoje usa nomes/tamanhos/mtime dos Safetensors (mais hash da
   config), não hash integral de cada peso. Troca desta rodada muda config e
   shards, sendo detectável; mutação com tamanho/mtime preservados é risco residual.
   Utilizar o recibo/hash de origem sem reler 15 GB em toda inferência.
4. Manter aprendizado de fatos/experiências no estado externo. LoRA deve consolidar
   comportamento com dados curados e retenção/testes de identidade; não converter
   respostas inventadas, diários privados ou toda mensagem em treino automático.
5. Requalificar o Qwen7 oficial em GPU antes de reutilizar presets. A etiqueta
   OOM conservadora do catálogo é histórica, da base anterior, não um benchmark
   realizado no novo BF16. Nenhum novo preset/benchmark foi aprovado por download.
6. `treinos_unificados.start` calcula o plano antes de adquirir `start.lock`.
   Um plano pode ficar obsoleto se a base for substituída enquanto a chamada
   aguarda o lock. A substituição desta rodada ocorrerá sem jobs ativos e com os
   locks atuais de início e worker adquiridos; isso não elimina a janela TOCTOU
   geral. Antes de automatizar futuras trocas, revalidar a assinatura sob o lock
   e no worker, usando o contrato de proveniência existente.

**Parecer:** atualização contextual e treino LoRA isolado existem. Atualização
paramétrica automática e fechada na produção **não está comprovada/implementada
de ponta a ponta**; não iniciar tal automação nesta rodada nem declarar prontidão.

## Encerramento e próximos passos mínimos

- **Concluído fisicamente:** exclusão autorizada do jogo/das duas bases antigas,
  download e integridade da base original, preservação dos outros dados,
  recusa de checkpoints antigos incompatíveis e leitura do painel.
- **Concluído offline:** duas regressões permanentes e suítes completas verdes
  antes/depois. Não substituem inferência ou homologação comportamental.
- **Pendente:** requalificar o preset do original Qwen7 e restaurar/conferir
  os aliases Ollama Hoshino/Lilith, ausentes antes desta substituição. Os
  originais BF16 de ~14,19 GiB não cabem integralmente nos 8 GiB de VRAM;
  a versão de execução deve ser derivada/validada, preservando a base original.
- **Pendente na atualização dos pesos:** fechar implantação/ativação/rollback
  por entidade a partir de um candidato aprovado. Recomenda-se aprendizado
  contextual contínuo, treino em lotes curados e implantação somente entre
  sessões; não alterar pesos após cada fala nem substituir identidade por LoRA.

Mudança de compatibilidade intencional: os adaptadores/checkpoints antigos
Qwen7 continuam arquivados, mas não podem ser retomados automaticamente sobre
o original novo. Não houve promoção estável, treino de 12 horas, reset de
memória, mudança de identidade ou relaxamento de concorrência/margem GPU.
