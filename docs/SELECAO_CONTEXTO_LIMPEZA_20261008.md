# Seleção de executores, contexto e limpeza — 08–09/10/2026

## Resultado e limites desta rodada

O contexto adaptativo e o uso parcial da GPU foram refinados no Resource
Manager existente. Não foi criado outro scheduler, backend ou banco mental.
Cloud/RunPod e concorrência GPU continuam desligados; margem de 768 MiB e
limite físico de 8 GiB preservados.

**A substituição dos executores Hoshino/Lilith ainda não está aprovada.**
Os pesos escolhidos estão instalados e íntegros, mas os ensaios não demonstraram
qualidade equivalente nem a compatibilidade completa exigida. A autorização
foi substituir depois de validar, não simplesmente porque o download terminou.

| Entidade | Executor | Situação ao fechar a rodada |
| --- | --- | --- |
| Hoshino/Lilith | 9B atual Q4_K_M | Preservado; perfil GPU parcial medido |
| Hoshino/Lilith | Qwen2.5 7B atual Q4_K_M | Leve ativo preservado para continuidade/reversão |
| Hoshino/Lilith | Hunyuan 7B Q4_K_M | Instalado separadamente, ainda não ativo |
| Hoshino/Lilith | Qwen-Jan ~6B Q5_K_M | Instalado separadamente; companion desabilitado e não validado |
| Alistair | Qwen3.5 4B Q4_K_M | Configurado; inferência CPU e rota GPU oportunista verificadas |

Nenhuma entidade foi acordada para os ensaios desta seleção. Foram chamadas
inferências locais descartáveis, com identidade externa simplificada e dados
fictícios. Não houve chamadas ElevenLabs/Azure, ações reais de ferramentas nem
gravação dessas conversas nos bancos mentais.

## Origem e integridade

Foram usadas as skills HF CLI e avaliações locais. As receitas de avaliação
dependentes de CUDA/provedores externos não são aplicáveis a este ensaio AMD:
usou-se o Ollama já instalado e o lease existente, sem backend de avaliação novo.

Fontes consultadas:

- [Tencent Hunyuan 7B](https://huggingface.co/tencent/Hunyuan-7B-Instruct)
  e [GGUF Bartowski](https://huggingface.co/bartowski/tencent_Hunyuan-7B-Instruct-GGUF).
- [Qwen-Jan Brainstorm20x](https://huggingface.co/DavidAU/Qwen3-Jan-v1-256k-ctx-6B-Brainstorm20x)
  e [GGUF mradermacher](https://huggingface.co/mradermacher/Qwen3-Jan-v1-256k-ctx-6B-Brainstorm20x-GGUF).
- [Qwen3.5 4B GGUF](https://huggingface.co/unsloth/Qwen3.5-4B-GGUF).
- [Qwen3 4B Thinking 2507](https://huggingface.co/Qwen/Qwen3-4B-Thinking-2507),
  ancestral indicado no model card do Jan; não foi baixado nesta rodada.

Os arquivos foram conferidos antes da importação. O importador reescreve
metadados GGUF; portanto SHA do download e SHA do blob final são distintos.
As cinco cópias instaladas foram novamente verificadas após remover o staging.
Reutilização só aceita tamanho/hash dos pesos aprovados e SYSTEM neutro.

### Hunyuan 7B

- Revisão GGUF: `f904d96e244a51562e80925489bc393c319f231d`.
- Tamanho do peso: 4.621.992.960 bytes.
- SHA fonte: `37361ed44b126de00a551260fd7c3de3c3a7a58d6060bce99b6b8fe0c0665d63`.
- SHA importado: `1b40cd94ebddde0587cb836cd9c0d5aa2961fa3df828a9f7d8414ae6f412180c`.
- Aliases: `hoshino-hunyuan-7b:latest`, `lilith-hunyuan-7b:latest`.

### Qwen-Jan ~6B

- Revisão GGUF: `8c4b5e5b13b179aa6219a2cd4ae8f08f8a6e0b7c`.
- Tamanho do peso Q5_K_M: 4.241.176.000 bytes; backend identifica 5,9B.
- SHA fonte: `de4a21839013515909959112d67a5cda31e99a5b3e89a6b4df95376907cc7c3f`.
- SHA importado: `fd3cd77d2f1d8a55d09dcef1f85be4997b0ee16792786313b8be14dadf3564a9`.
- Aliases: `hoshino-qwenjan-6b:latest`, `lilith-qwenjan-6b:latest`.

### Alistair Qwen3.5 4B

- Revisão GGUF: `e87f176479d0855a907a41277aca2f8ee7a09523`.
- Tamanho do peso Q4_K_M: 2.740.937.888 bytes.
- SHA fonte: `00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4`.
- SHA importado: `d1f31e92476a72cbf464ae849567917b2a5fe78003906e94ae5c69b742767204`.
- Alias: `alistair-qwen3.5-4b:latest`.
- Consumidores/configuração/empacotamento PC2 atualizados para esse alias.

Identidade, personalidade, memória e autoria continuam externas aos pesos.
Os catálogos de Hoshino/Lilith possuem cópias independentes, não um checkpoint
com identidade compartilhada. Capacidades anunciadas pelo backend não equivalem
a teste real de ferramentas.

## Contexto adaptativo e contratos

- `HOSHINO_ADAPTIVE_CONTEXT` vem habilitado por padrão; desligá-lo mantém
  o teto fixo. O teto configurado não foi ampliado automaticamente.
- A mesma estimativa é usada na escolha do executor e no tamanho da janela:
  todas as mensagens, argumentos de ferramentas, schemas, autoria, saída e
  margem de template entram na conta.
- Janelas em degraus até o teto: 2K, 4K, 8K, 12K, 16K, 32K quando permitido.
- Não diminui saída nem remove mensagens silenciosamente para encaixar.
  Se a estimativa exceder o teto, falha antes do HTTP; continua necessária a
  compactação já existente. Isso não adiciona mecanismo mental novo.
- Entrada com imagem mantém a janela máxima: tokens visuais não são estimados
  por caracteres. Contexto visual prolongado não foi validado nesta rodada.
- A estimativa textual é conservadora, **não um tokenizer exato**; não prova
  que qualquer prompt arbitrário caberá no backend.
- Executor e decisão de pensamento permanecem fixos durante cada ciclo.
  O antigo Qwen2.5 não recebe `think`; candidatos com suporte nativo continuam
  recebendo o booleano da política existente.
- A Central agora recusa configuração com menos de 512 tokens restantes para
  entrada/margem. O pedido concreto ainda passa pela validação do RM. Um teste
  reproduziu o bug anterior e confirma que rejeição não altera config/backup.

## AMD/GPU: o que foi realmente medido

Hardware: RX 6650 XT 8 GiB; driver amdgpu. O Ollama 0.32.6 usado nos ensaios
reportou backend **ROCm**, não CUDA. Não se deve chamar este ensaio de validação
Vulkan só porque RADV está instalado.

A configuração HSA `10.3.0` já existia no ambiente interativo da máquina. Foi
replicada nos arquivos de ambiente das entidades para evitar que um lançamento
pela interface perca a configuração. Não foi alterada configuração global do SO.

### Principal 9B

O perfil de carga total em GPU ultrapassou a margem: pico real próximo de
7.784.628.224 bytes de VRAM e subsequente espera por pressão de memória. A sonda
`/api/ps` não contabilizou toda a alocação visual; houve diferença de cerca de
1,15 GiB. Por isso a medição amdgpu total importa mais que o número isolado do
modelo. Carga total do 9B **não foi aprovada**.

Perfil parcial medido de Hoshino e Lilith: 32 camadas GPU, teto 16K.

- Seis respostas completas por entidade, com `done` e término `stop`.
- VRAM do modelo reportada: 5.613.950.074 bytes.
- Pico real: Hoshino 6.763.094.016; Lilith 6.762.950.656 bytes.
- Orçamento de perfil: 5,5 GiB, margem preservada.
- Se 32 camadas não couberem na medição inicial mas 20 couberem, o pedido
  usa o perfil parcial de 20 antes de iniciar. Caso contrário espera/falha.
- Perfil 20: modelo ~3.834.862.631 bytes; pico real ~4.876.111.872 bytes.
- Ensaio quente 20 → 32 confirmou reload real e mudança de residência no
  backend: cargas 5,802 s / 3,819 s, respostas totais 8,16 s / 5,32 s.
  Prompts diferentes: esses números não são um A/B de desempenho.

Hoshino/Lilith não recebem fallback silencioso de modelo inteiro CPU nas rotas
LLM auditadas. Isso **não proíbe** as camadas restantes na CPU/RAM do perfil
parcial autorizado. Pressão que mude depois do preflight pode causar espera;
não se promete o máximo matemático de camadas a cada instante.

### Alistair

- Qwen3.5 4B completou seis casos em CPU e seis em GPU.
- CPU: carga/resposta fria ~8,58 s; respostas quentes ~3–5 s no PC principal.
- Rota real `Alistair.infer`: modelo antes em CPU (`size_vram=0`), depois
  oportunista GPU (`size_vram=2.988.200.427`), resposta descartável em 3,52 s.
- Lease liberado ao final e unload dos pesos do ensaio confirmado.
- Isso não demonstra desempenho no Athlon: PC2 físico continua pendente.

Nenhuma heurística geral de fairness/starvation foi recalibrada. Concorrência
agressiva permanece `concurrency_validated=false`. Não foram simulados jogos
pesados ou aplicações externas ocupando a GPU nesta rodada.

## Qualidade dos candidatos: falhas preservadas, não mascaradas

O probe local tem seis casos: apresentação, preferências de dois autores,
correção, lembrança desconhecida, companhia e despedida. Só avalia texto/contexto
descartável, não toda a mente, memória após restart ou uma sessão humana.

### Hunyuan

Seis respostas terminaram corretamente em cada catálogo, mas houve atribuição
incorreta de preferência, perda de correção e familiaridade inventada. As
respostas também trouxeram `<answer>...</answer>`. Esses wrappers fazem parte do
protocolo documentado pela Tencent, não são por si só falha de personalidade.
O adaptador ainda precisa tratar esse formato sem vazar tags para chat/TTS.

Picos reais: ~6,56 GB Hoshino / ~6,59 GB Lilith em contexto 8K. Tempos da Lilith
~1,42–7,49 s. Parte dos ensaios iniciais coincidiu com I/O pesado de importação,
portanto não há alegação de ganho/perda de velocidade por tamanho apenas.

### Qwen-Jan

Com orçamento inicial de 384 tokens houve término por limite e **resposta
visível vazia**. O ensaio registrou falha; não tratou isso como resposta válida.
Mesmo com `think=false`, o modelo produziu milhares de caracteres de raciocínio.
Os arquivos preservam apenas a contagem, não o texto desse raciocínio.

Reteste Hoshino com saída 2048, contexto 16K, 40 camadas GPU: 6/6 respostas
completas, mas ~18,94–97,05 s. Lilith com 8K/carga total GPU completou somente
dois casos, ~19,71/44,63 s; não é validação equivalente dos seis casos.

O ancestral indicado no card é Qwen3-4B-Thinking-2507, cujo card declara somente
modo pensante. Inferir que essa herança explica o comportamento é consistente
com os probes, **não prova** que nenhuma adaptação de template possa funcionar.
Não será ativado com falsa promessa de modo rápido automático.

O Qwen2.5 7B atual também inventou uma preferência própria no mesmo probe, mas
preservou a correção do usuário; completou 6/6, ~1,10–5,07 s. Não é uma baseline
perfeita, nem essa amostra curta demonstra não inferioridade dos candidatos.

## Limpeza autorizada e preservação

Pasta do projeto: aproximadamente **113 → 72 GiB**, redução líquida de ~41 GiB,
mesmo incluindo a instalação dos novos pesos. Disco ao fechar: **66 GiB livres,
92% usado**. Ainda é um disco bastante ocupado, não espaço ilimitado.

Removidos após localizar referências/consumidores e conferir alvos:

- Candidatos rejeitados Yi/Granite/Gemma/Smol e Qwen menores de ensaios anteriores.
- Aliases antigos Qwen3 4B de Alistair após validar a rota do novo Qwen3.5 4B.
- Cópias antigas de código/exportações e backups históricos autorizados.
- Imagem Flux2 Klein obsoleta sem consumidor; Qwen-Image atual preservado.
- GGUFs originais de staging Hunyuan/Jan/Alistair e blobs de upload sem referência,
  somente depois de conferir os pesos finais nos respectivos catálogos.
- Arquivo tar duplicado do pacote PC2; a pasta pronta atual ficou preservada.

Preservados: 9B e 7B atual de ambas, Hunyuan/Jan instalados, novo Alistair,
ASR/TTS/Qwen-Image atuais, ambientes necessários, fontes, testes, Git,
configs/credenciais existentes e todos os bancos mentais.

`arquivo/` agora ocupa ~112 KiB: alguns manifestos de migração ainda possuem
consumidores reais e não foram apagados. `pacotes/alistair_pc2/` ocupa ~2,7 GiB,
foi reconstruído com o novo Alistair e passou novamente em `--integridade`.
O tar pode ser regenerado pelo empacotador; não é requisito para copiar a pasta.

Os backups removidos **não foram enviados à lixeira** e não têm recuperação
local garantida. Pesos públicos descartados podem ser baixados novamente;
staging e tar podem ser recriados. Não foi executado reset do Git nem apagada
memória para obter esses números. Documentos históricos que citam backups
antigos são registros daquele momento, não confirmação de que ainda existam.

## Persistência e estado final

Mtimes dos bancos continuam anteriores aos probes. Checagem SQLite read-only
`quick_check` retornou `ok` nos três arquivos; os hashes abaixo correspondem aos
arquivos-base verificados, não substituem snapshot de WAL ativo.

- Hoshino: 417.792 bytes; SHA
  `7184fdcf709f2d2dbd7c89dc0890f19b869a92c4c39711ff0117dccf8962837b`.
- Lilith: 266.240 bytes; SHA
  `e77fceca29a43f9b3aa40190438adfd458bf0bdfdf39ad097e50980c97847488`.
- Alistair: 28.672 bytes; SHA
  `638c3b808fb99865db2216ecd6655f03f0593e7ef04298cacc5586014e640e76`.

Última consulta: Hoshino/Alistair sleeping, Lilith sem presença ativa; daemons
dedicados 11435/11436/11437 respondendo, `/api/ps` vazio nos três e nenhum lease
ativo. Não houve wake de entidade nem processo de inferência do ensaio restante.
RAM física ~31 GiB; swap real 8 GiB, ~448 MiB ocupados na última leitura;
MemAvailable ~28 GiB, apesar do cache de arquivos após verificar pesos. Swap
continua não sendo contado como RAM rápida pelo admission control existente.

A Central headless do ensaio foi encerrada pela API cooperativa existente;
o processo saiu com código 0. Foi reaberta sem `--entity`, sem acordar ninguém,
para carregar a última validação. `/api/state` confirmou `closing=false` e
zero leases. A consulta de modelos confirmou contexto adaptativo ligado,
tetos 16K/16K/4K e os executores principais esperados. Não houve teste físico
novo da interface, áudio, overlay ou Minecraft nesta seleção.

## Validação e proveniência das falhas

- Baseline anterior às mudanças: **74/74 grupos offline**.
- Primeira execução desta continuação: **70/74**. Falhas não ocultadas:
  fixture de sono com contexto=saída=4096; expectativa de janela sempre fixa;
  timeouts de causalidade/áudio durante importação pesada concorrente.
- Ajustada somente a fixture inválida de sono (saída 512) e a expectativa
  de janela do teste e2e, conservando suas verificações de autoria/lifecycle.
- Causalidade sem alterar implementação/deadlines para deixar verde:
  **37/37** sem importação concorrente.
- Áudio sem alterar implementação/deadlines para deixar verde: **41/41**
  sem importação concorrente. A pressão I/O da instalação continua um risco
  operacional; não se deve importar pesos durante uma sessão humana.
- Suíte final depois da última correção de configuração: **74/74 grupos**,
  `suite-20261009-final-config.log`.
- Executores: **77/77 testes**, `executores-20261009-entrega.log`.
- Central/configuração: **38/38 testes**, `central-config-20261009-entrega.log`.
- Execução conjunta via unittest: 167 casos, incluindo testes herdados
  repetidos. Não somar esse número às regressões únicas.
- `git diff --check` sem erro. Pacote PC2 íntegro. Cinco aliases escolhidos
  conferidos novamente, incluindo uso sem o GGUF original duplicado.

Novas regressões incluem adaptação/growth, schemas/argumentos completos,
overflow sem corte, contexto seleção=execução, catálogo/revisão/validação,
perfil 32→20 sob pressão, Hoshino/Lilith sem fallback inteiro CPU, booleano
pensante preservado para Hunyuan, hash/espaço/importação e reutilização de
alias sem confiar em peso estrangeiro, config sem espaço de entrada recusada.

Evidências locais em `compartilhado/runtime/ensaios/20261008/` (ignoradas no Git),
especialmente `selecao-*.json`, `alistair-qwen35-rota.json` e os logs nomeados
acima. Probes não gravam chain-of-thought, chaves ou headers de providers.

## Arquivos envolvidos nesta seleção

As alterações da rodada se sobrepõem a arquivos já modificados por rodadas
anteriores; o working tree inteiro não deve ser atribuído somente a esta tarefa.

- `app/config.py`, `app/main.py`, `app/alistair_runner.py`.
- `app/core/resource_manager.py`, `app/core/gpu_resource.py`,
  `app/core/central_control.py`, `app/pc2_protocol.py`.
- `scripts/preparar_executores_leves.py`, `scripts/preparar_tres_modelos.py`,
  `scripts/verificar_tres_modelos.py`, `scripts/verificar_imagem_standby.py`,
  `scripts/montar_pacote_alistair.py`.
- `entidades/alistair/entidade.json`, config/Modelfile de Alistair;
  ambientes não secretos e `config/executores.json` de Hoshino/Lilith.
- `testes/test_executores_leves.py`, `testes/test_central_control.py`,
  `testes/test_turno_e2e.py`, `testes/test_prontidao_r1_r7.py`.
- `README.md`, `pc2/LEIA-ME.md`, este relatório.
- Probe descartável `compartilhado/runtime/ensaios/20261008/probe_selecao.py`
  e pacote atual `pacotes/alistair_pc2/`.

## Pendências prioritárias, sem ampliar escopo

1. Refinar o protocolo Hunyuan no adaptador atual (frases/tags, cancelamento,
   JSON/ferramentas) e repetir autoria/correção/PT-BR antes de ativá-lo.
2. Investigar compatibilidade de pensamento/latência do Jan sem cortar
   raciocínio para apresentar uma resposta parcial como sucesso. Se não houver
   solução comprovada, manter desabilitado e informar a limitação.
3. Avaliar qualidade com contexto real de cada entidade, memória isolada e
   bateria mais extensa, sem trocar executor no meio da resposta.
4. Validar PC2 Athlon fisicamente e uso integrado/prolongado sob pressão de
   GPU/RAM. Não declarar essas etapas aprovadas com base nestes probes.

**Esta rodada não conclui a implantação dos três novos executores ativos de
cada personagem.** A infraestrutura e os pesos estão preparados; a ativação
dos dois candidatos depende dos contratos e da qualidade que ainda faltam.
