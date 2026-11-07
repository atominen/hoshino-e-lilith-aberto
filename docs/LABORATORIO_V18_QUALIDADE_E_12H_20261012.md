# Laboratório Neural v1.8 — professor e preparação de 12 horas

## Escopo e proveniência

Continuação do v1.7, não reinstalação. Entrada local limpa na branch
`codex/laboratorio-consolidacao-20261012`, commit
`d6bf47f2b97191881e87272026c9cee0e9b3c403`. Manual/consolidação existentes lidos;
relatos anteriores preservados. PR existente #1, branch remota
`laboratorio-v11-organizacao-20261012`, privado, rascunho, sem merge automático.

Arquitetura mantida: Central → painel local → registro de jobs existente →
runner NF4/ROCm ou professor GGUF/Vulkan → Resource Manager existente →
checkpoint/proposta → avaliação → curadoria humana. Sem outro scheduler,
banco mental, backend cloud ou carga GPU concorrente.

**12 horas não foram iniciadas.** Nenhuma entidade de produção foi acordada,
nenhum adaptador promovido e nenhum dado sintético desta rodada foi exportado
ou usado em treinamento. Bases, datasets, identidades e bancos preservados.

## Professor — alterações verificáveis

- Amostra distribuída pelo corpus de treino inteiro, com deduplicação antes da
  seleção. Não usa validação/holdout ou diários privados como matéria-prima.
- Seis categorias e dez intenções distintas: conversa casual, discordância,
  memória/autoria, decisão condicional, correção, recibo parcial, silêncio,
  conflito de interesses, investigação e regra/exceção.
- Diálogos de quatro mensagens. Aliases user/assistant são derivados do último
  par; gerar a mesma string duas vezes era uma fonte de falha real. Divergências
  explícitas continuam recusadas, não corrigidas silenciosamente.
- Perfil de personalidade lido somente da adaptação local da seção da entidade no corpus autorizado;
  temas/tendências não são transformados em autobiografia da obra.
- Verificação de todos os turnos contra todo o treino autorizado, cópia lexical,
  paráfrase superficial, resposta genérica, autoria estrangeira, repetição dentro
  do diálogo e padrões conhecidos de falsa memória/recibo incerto.
- Contexto/tokenização reais; batches curtos; reasoning de curadoria até 256 tokens.
  Contagem de reasoning observada confirma comportamento do backend; não se
  registra cadeia de pensamento privada. Saída truncada não vira proposta válida.
- Métricas de tokens, cache, latência, tentativas e custo por aceitação técnica.
  Custo por aprovação humana permanece indefinido enquanto não houver curadoria.
- Raw de tentativas recusadas preservado para diagnóstico. Nenhuma credencial,
  header sensível ou chave do servidor é persistida.
- Crítica semântica curta pelo **mesmo servidor 35B**, sem outro modelo/processo:
  tenta detectar fatos sem suporte, contradições, intenção perdida e retry inseguro.
  Tem thinking limitado a 256 tokens. Criar e revisar material consistente é trabalho
  de curadoria; a política de thinking das entidades não foi alterada.
  Flags fazem o lote ser refeito no máximo uma vez; persistência da falha interrompe
  a geração e bloqueia sua aceitação. A crítica não é independente e também erra.

Filtro técnico **não prova** profundidade, persona ou coerência semântica.
Contradições e adequação ao tema ainda exigem leitura humana. Não trocar uma
avaliação semântica por aprovação automática baseada em rótulos.

A revisão manual detectou falsa lembrança, duração trocada, caminho inventado,
certeza indevida em HTTP 503 e falas excessivamente explicativas em lotes que
haviam passado no filtro lexical. Lotes antigos não foram apagados nem reescritos
para mudar sua aprovação histórica. O custo por exemplo **humano aprovado** é
indefinido: nenhum exemplo novo recebeu tal aprovação nesta rodada.

## Corpus original — medido, não alterado

Tokenização CPU pelo tokenizer original 9B. Hoshino e Lilith têm cada uma
722 exemplos de treino, 131 de validação e 104 de holdout. Nenhuma interseção
exata tokenizada entre os splits da mesma entidade; isso não descarta vazamento
por paráfrases. Censo/hash local em
`laboratorio-local/controle-laboratorio/treinamento-unificado/reports/v18-20261012/corpus-census.json`.

| Treino | Tokens de entrada | Tokens supervisionados | Respostas únicas | Multiturno | Maior sequência |
|---|---:|---:|---:|---:|---:|
| Hoshino | 45.578 | 19.197 | 530 | 33 | 124 |
| Lilith | 45.149 | 18.775 | 530 | 33 | 121 |

Há **399 conversas exatas compartilhadas** entre os corpora originais (55,26%)
e 213 respostas exatas coincidentes. Muitos são contratos operacionais comuns;
é um risco de pouca diversidade/discriminação, não mistura feita pelo runner.
Não modificar o corpus para esconder isso. Propostas novas são revisáveis.

## Treinamento — mudanças no mecanismo existente

- Relógio cumulativo de otimização: forward, backward, optimizer e sincronização.
  Carga, avaliação, gravação e espera não consomem as seis horas prometidas.
- Checkpoints conservam relógio, tokens, posição, RNG, optimizer, histórico de
  validação, base/corpus/preset e hashes. Snapshot antigo sem relógio não recebe
  duração inventada. Validações 6/16 são populações distintas, não comparáveis.
- Cada epoch é embaralhada deterministicamente; nada de treinar repetidamente
  apenas os primeiros exemplos. Todos os exemplos devem caber no contrato de
  256 tokens: exemplos longos são erro explícito, não descarte silencioso.
- Monitoramento intermediário de 16 exemplos de validação, sem usar holdout para
  escolher hiperparâmetros. Early stop após três checagens >2% acima da melhor
  loss. Isso reduz risco, não prova ausência de sobreajuste.
- Memória AMD física, RAM disponível, swap/page faults, potência, fans e sensores
  edge/junction separados. Temperaturas usam teto conservador inferior ao crítico
  reportado pelo driver; não houve alteração de clocks, potência ou fans.
- O perfil GPU do v1.7 voltou a exceder a margem em sequências mais longas.
  Rank8 GPU-head foi interrompido por pressão. Essas falhas não foram homologadas.
- Novo offload opcional **head congelado CPU FP32**; camadas textuais e LoRA
  permanecem GPU. BF16 CPU emulado ficou preso numa operação longa: parada
  cooperativa não terminou; somente o filho isolado foi encerrado, pais liberaram
  o lease e registraram falha. FP32 corrigiu a limitação nesse caminho.
- Cancelamento pede checkpoint; escalada, se necessária, só alcança processo
  criado pelo runner, nunca terceiros. Lease só é liberado após saída HIP.

## Plano longo preparado — não autorizado

Hoshino 9B original + Hoshino train/validation → candidato/checkpoints →
recarga/validação/holdout Hoshino → liberação GPU → Lilith 9B original +
Lilith train/validation → candidato/checkpoints → recarga/validação/holdout Lilith.

Objetivo: 21.600 segundos de otimização **por entidade**. Tempo de parede maior
que 12h, calculado separadamente com carga, checks e avaliação. Checkpoints
projetados para cerca de 20 minutos efetivos; frequência baseada em throughput
medido, nunca em benchmark 0.8B ou outra entidade. Disco exige previsão de
checkpoints mais 5 GiB livres. O disco atual está perto do limite; não apagar nada
para fabricar viabilidade.

A avaliação aponta para o predecessor durável exato da mesma entidade/base/corpus,
não o último candidato global. Retomada prepara etapas restantes; só uma nova
autorização explícita de sono/janela inicia trabalho. Resultado incerto não é replay.
Originais, candidatos e estáveis continuam separados. Stable exige avaliação e
aprovação humana, sem instalar na produção.

## Interface

Atalho no dashboard principal da Central, usando `open_laboratory` existente.
No painel: **Preparar plano 12h · NÃO inicia**, **Preparar retomada interrompida**
e autorização separada. Curadoria mostra os quatro turnos, sem HTML vindo do LLM.
O painel do laboratório foi reiniciado normalmente; entidades/Central não foram
reiniciadas para instalar mudanças de produção.

## Medidas físicas — professor

Referência v1.7 `e8e73ed778da4000`: dez pares, uma categoria (personalidade),
165,79 s. Respostas formalizadas sobre lealdade, segurança e proatividade;
o lote já estava `needs_revision`. Não era dataset aprovado.

| Job local | Entidade | Exemplos / turnos assistant / categorias | Parecer |
|---|---|---|---|
| `53480b5ef6c34a79` | Hoshino | 10 / 20 / 6 | 221,88 s; revisão achou falsa biografia; filtro atual recusa 3 exemplos |
| `0b615af2abd64ca8` | Hoshino | 10 / 20 / 6 | 248,62 s; filtro atual recusa grounding; revisão achou recibo incerto mal interpretado |
| `9822a13c15354b7f` | Hoshino | 10 / 20 / 6 | 244,71 s; mesmas dez fontes/hash do v1.7; filtro lexical passa, revisão encontrou fatos/duração inventados |
| `91aad1a9f8854bcc` | Lilith | 10 / 20 / 6 | 297,38 s; corpus próprio; crítico sem thinking deixou passar caminho inventado e certeza em HTTP 503 |
| `c2ad2ac064604e42` | Alistair | 10 / 20 / 6 | 251,46 s; seed próprio; crítico sem thinking não detectou vários erros de condições/recibo |
| `412ea12d38454f38` | Hoshino | 6 / 12 / 6 | 273,78 s; incompleto, `needs_revision`; crítica bloqueou batch 4, exportação impedida |
| `f9aaba7cf7014951` | Hoshino | nenhum lote aceito | ~145 s de ocupação; crítica com thinking observado bloqueou corpo físico inventado, mas também teve falso positivo |
| `4eb66fabe47648da` | Hoshino | 10 / 20 / 6 | 339,73 s; mesmas fontes do baseline, contexto 6.144; writer/crítico com thinking limitado, curadoria humana pendente |

Correção do falso positivo: a crítica recebeu explicitamente que discordância
e revisão motivada de preferência não significam erro. Isso não garante que
o crítico nunca se engane. Revisão não exige submissão ao usuário nem persona
imutável. O contexto do professor foi reduzido à adaptação funcional do perfil;
a biografia da obra não é histórico vivido da instalação local.

Comparação de cobertura: **1 → 6 categorias; 0 → 10 diálogos de dois turnos**.
No A/B com as mesmas fontes, a duração cresceu 47,6%, mas as falas assistant
dobraram: 16,58 → 12,24 s por fala, antes da crítica semântica extra. Não é ganho
de custo por exemplo humano aprovado; ainda há **zero** aprovações humanas.
Tamanho/complexidade/contexto mudaram, portanto não é benchmark de velocidade
do modelo isolado nem demonstração estatística de superioridade de personalidade.

Último lote: 13.844 tokens de prompt, 6.492 de geração (incluem reasoning), 5.652
tokens de prompt em cache; 33,97 s por exemplo tecnicamente aceito, 16,99 s por
fala assistant. Dois turnos, aliases e encerramento completos. Não foi encontrada
alegação literal de corpo humano nesse lote. Persistem falsas lembranças/estados
e raciocínio técnico fraco: exemplo 2 inventa que jogou ontem; 7 afirma que checa
logs/nada travou; 10 assume que HTTP 404 decorre da senha e que alterá-la resolve.
Também há adição de backup/montagem não solicitada e inferência social sem prova.
**A crítica semântica deixou passar esses casos.** O lote não é aprovação de
qualidade nem material autorizado. Inspeção técnica em `final-teacher-review.json`
ao lado do resumo; não foi reescrito nem usado como treino. Qualidade melhorou em
cobertura/alguns defeitos conhecidos, mas a curadoria semântica não foi homologada
como filtro autossuficiente. Não resolver inventando um placar de personalidade.

Todos os lotes permanecem propostas, nunca treino. O resumo computado está em
`laboratorio-local/controle-laboratorio/treinamento-unificado/reports/v18-20261012/teacher-comparison.json`.
Raw recusado, parciais e métricas estão em `laboratorio-local/professor-moe-35b`.

## Medidas físicas — 9B

| Job | Perfil / resultado | Otimização e validação |
|---|---|---|
| `888476f7fa4342ca` | GPU-head rank4, parado | 6 updates; limite térmico inicial genérico 95°C corrigido para sensores/crit separados |
| `8dbf79eea76c4c72` | GPU-head rank4, 16 updates | 771,59 updates/h; pico físico 7,17 GiB; janela curta não homologa carga longa |
| `df122d2c0886429f` | GPU-head rank8, parado | 2 updates; VRAM excedeu margem |
| `d53429e091094676` | GPU-head rank4, retomada parada | 5 updates novos; pressão em 7,24 GiB; perfil excluído do plano longo |
| `970cd6ecb87c41b6` | CPU-head BF16, falhou | CPU AVX2 sem BF16 nativo; operação longa não terminou com SIGTERM; filho owned encerrado, pais liberaram lease |
| `dc2db7b4138b4740` | CPU-head FP32 rank4, 16 updates | 87,17 s efetivos; 660,77 updates/h; validação 16 exemplos 2,9917 → 2,9473 |
| `ba9a1f51905f4c32` | CPU-head FP32, retomada até 56 | 214,84 s novos; 670,26 updates/h; validação 2,9473 → 2,6207 |
| `2ef1f246f03545f1` | CPU-head FP32, parada cooperativa até 111 | checkpoint/reload/RNG/clock confirmados; 602,68 s acumulados; sem escalada |
| `cabf3489b4fb4a30` | CPU-head FP32, retomada até 335 | 1.199,42 s novos; 1.802,10 s acumulados; 672,33 updates/h; validação 2,2239 → 1,9155 |
| `7e8b4d2c29834a2d` | Lilith CPU-head FP32, original/corpus próprio | 170 updates; 900,53 s efetivos; 679,60 updates/h; validação 2,8781 → 1,8251 |

Último trecho Hoshino: 42.947,85 tokens de sequência/h e 18.287,88 tokens
supervisionados/h; **entrada já inclui saída**, não somar as duas métricas.
335 updates correspondem a 0,464 epoch, não vários ciclos completos do corpus.
Janelas de 6 e 16 validações não foram comparadas como população igual. Throughput
dos perfis usa amostragem/workload diferentes: é medida operacional, não A/B puro.
Os primeiros 16 updates dos perfis usam a mesma ordem determinística; a comparação
de throughput nesse trecho é possível, mas os monitores de loss são 6 versus 16.
Rank8 com head CPU não foi varrido: rank4 é o perfil de maior evidência estável,
não uma alegação de ótimo global de hiperparâmetros.

No trecho `cabf`: pico físico **5,53 GiB** (Torch allocator 3,83 GiB), RAM disponível
mínima **20,37 GiB**, mem/edge/junction máximos **60/61/85°C**, pressão `[]`,
filho exit 0, lease liberado. Otimização nova ~20 min contínuos; carga/validação/save
separados; cerca de 30 min acumulados após retomadas. **Não comprova seis horas.**

Swap atingiu **5,89 GiB** transitoriamente durante carga; contadores globais de
page-out ficaram estáveis na maior parte posterior e swap recuou. Não esconder
esse custo: medição é do host, pode incluir processos externos. Sem evidência de
thrashing sustentado nesta janela, mas carga/alternância com professor exigem
RAM/swap monitorados. Swap não entra como RAM disponível no gate.

Checkpoint rank4 com optimizer ~130,35 MB; adaptador final ~43,35 MB. Candidato
continua sem promoção. O job BF16 forçado não ganhou confirmação fictícia de
checkpoint; falha, diretório parcial e evidência foram preservados.

Lilith: 42.003,18 tokens de sequência/h e 17.469,68 supervisionados/h; pico físico
**5,51 GiB**, RAM disponível mínima **18,52 GiB**, swap máxima **1,65 GiB**,
mem/edge/junction **60/61/84°C**, pressão `[]`, exit 0. Carga 27,40 s,
validações baseline/intermediária/final 32,18/30,97/30,85 s, quatro checkpoints
1,61 s somados; parede do filho 1.026,32 s (~17,1 min) para 15 min efetivos.
Um ponto CPU Tctl observado durante updates foi 48,75°C; não é série de máximos CPU.

Após esses ensaios, a revisão encontrou a parada por pressão fora do relógio de
cancelamento manual. Ambos agora usam o mesmo prazo de 60 s no pai do filho owned;
o monitor só inicia após PID/handlers existirem. Teste com processo simulado cobre
saída normal, saída lenta, travamento e filho já encerrado; não se provocou calor
ou OOM para testar o sensor fisicamente. Também se recusam opções `[]`, `false`,
`0` e string vazia, anteriormente confundidas com objeto ausente. O SHA do runtime
agora é capturado na entrada, não ao fim. Cópia do runner usado nos benchmarks
`a8708b31…` preservada no diretório de evidências, sem virar executor paralelo.

## Previsão do plano longo

| Entidade | Updates/6h projetados | Epochs | Checkpoint | Parede treino projetada |
|---|---:|---:|---|---:|
| Hoshino | 4.034 | 5,59 | 224 updates (~20 min efetivos) | 383,1 min |
| Lilith | 4.078 | 5,65 | 227 updates (~20 min efetivos) | 382,7 min |

12h efetivas + carga/validação/checkpoint + orçamento de 15 min para recarga/holdout
por entidade + 10 min para restauração: **805,8 min (~13h26)** projetados.
Janela autorizável de 18h é teto de segurança, não duração comprovada ou autorização.
O custo de validação (~31 s por 16 exemplos) é separado do throughput de updates.
As recargas completas finais ainda são ensaios separados; não estimar um treino
contando toda a validação curta repetidamente por update.

Plano persistido em `controle-laboratorio/treinamento-unificado/plans/12h-prepared.json`,
`execution_started=false`, `confirm=null`, **allowed=false** por espaço.
Checkpoints novos estimados: **5.878.914.701 bytes (~5,48 GiB)**, além de 5 GiB de
reserva. Após benchmarks, ~9,08 GiB livres versus ~10,48 GiB necessários: déficit
~1,40 GiB. Recomenda-se liberar ao menos **3 GiB adicionais** antes de preparar de
novo; o gate mede de novo na autorização. Nenhum modelo/backup/dado foi apagado.

Parecer: **viável como experimento sequencial condicionado**, não homologado para
seis horas sem interrupção nem garantido como aprendizado melhor. O corpus tem
poucos multitur­nos e muita sobreposição operacional. Alternativa recomendada:
considerar 6h um teto, fazer primeiro ~1 epoch (~65 min efetivos) e só prolongar
se validação/checkpoints e leitura humana demonstrarem ganho. Não iniciar essa
alternativa automaticamente, nem usar sintéticos não aprovados para aumentar volume.

## Limites de homologação

Estabilidade de seis horas, generalização após cinco/seis epochs, evolução natural
das personas, recuperação elétrica e restauração de entidades de produção após
noite inteira continuam pendentes de autorização/ensaio prolongado. Os gates e
simulações do supervisor não substituem esse ensaio físico.

## Recarga e avaliação independente

Hoshino, job `7b7250389d0445f6`, candidato `cabf3489b4fb4a30`: carregado de novo
em outro processo, SHA do adaptador `9d56705b…`. **131 validações completas**
(loss 1,989717, 256,21 s) + **104 holdout** (loss 1,916243, 202,62 s), sem
interseção exata com treino/validação. Carga 18,66 s; parede do filho 494,09 s
(~8,2 min); pico físico 4,83 GiB, pressão `[]`. Duas saídas com EOS confirmado:
12 tokens / 6,89 s e 15 tokens / 7,86 s. Sem resposta parcial tratada como sucesso.

Probe neutro, sem constituição/persona/contexto mental:
`Oi! Como você se apresenta?` → `Eu sou o Qwen3.5.`.
Isso **não aprova identidade, naturalidade ou companheirismo**. É um controle de
geração nua do executor; a arquitetura conserva identidade externa. Não inserir
um nome em system prompt depois e fingir que corrigiu a qualidade do adaptador.
O segundo probe respondeu que consultaria fontes e admitiria o limite. Candidato
mantém `passed=false`, `human_review_required=true`, sem referência estável nova.

Lilith, job `8bb5ccc4b4e54b61`, candidato `7e8b4d2c29834a2d`: SHA
`f14b8d3b…`; **131 validações** (1,933004, 254,18 s) e **104 holdout**
(1,990634, 197,82 s). Carga 19,24 s; parede 492,91 s (~8,2 min), pico físico
4,83 GiB, pressão `[]`, duas saídas encerradas com EOS (22/17 tokens).
No probe neutro ela se apresentou como IA/assistente; personalidade não foi
homologada. Ambos os ensaios foram processos independentes, sem corpus misturado.

Os dois orçamentos conservadores de avaliação (15 min cada) excedem os ~8,2 min
realmente medidos. Usando a medida, a projeção seria ~13h12; o plano mantém
~13h26 com folga. Isso continua sendo projeção baseada em minutos e host ocioso,
não prova de velocidade constante durante seis horas. Avaliações em
`reports/hoshino/7b7250389d0445f6-qwen35-9b.json` e
`reports/lilith/8bb5ccc4b4e54b61-qwen35-9b.json`, dentro do registro unificado.

Loss completa e monitor de 16 exemplos são populações diferentes; não comparar
1,9897 versus 1,9155 como piora temporal. Não houve baseline completo FP32 dos
131/104 nesta rodada; portanto não se promete um ganho percentual de holdout.

## Arquivos e contratos alterados

- `laboratorio/professor_moe.py`, `professor_schema.py`: amostragem, multitur­nos,
  contexto próprio, filtros, crítica bounded e métricas/proveniência.
- `laboratorio/treino_nf4_curto.py`, `versionamento_lora.py`: head CPU FP32,
  relógio, checkpoint/retomada, early stop, telemetria e encerramento bounded.
- `laboratorio/treinos_unificados.py`, `iniciar_entidades.py`: preset medido,
  preparação longa, predecessor exato, recuperação e gate de disco/autorização.
- `laboratorio/painel.py`, `web/index.html`, `web/app.js`: APIs existentes refinadas,
  preview e retomada sem execução, curadoria mostrando diálogo completo.
- `app/ui/central_native.py`: atalho do dashboard, callback existente.
- `laboratorio/tests/test_consolidacao.py`, `test_noite_supervisor.py`,
  `browser.cjs`: regressões e navegador; nenhum hardware simulado é chamado real.
- README raiz, README laboratório e manual mestre apontam ao fechamento v1.8.
  Novos documentos: este relatório e `LABORATORIO_V18_PLANO_20261012.md`.

APIs novas: POST `/api/treinos/prepare-12h` (somente plano/diagnóstico) e
`/api/night/resume-preview` (somente etapas pendentes). Preview/start existentes
recebem opções validadas; autorização continua no supervisor existente.
Mudanças de contrato: corpus inválido não é descartado silenciosamente; clock
ausente não é inventado; rank/offload mudado na retomada é recusado; revisão
semântica/truncamento pode bloquear um lote antes considerado formalmente válido.

## Testes e evidência

Baseline offline **74/74 grupos**; laboratório **88/88 testes**. Última rodada:
**74/74** (`/tmp/suite-v18-final3.log`) e **114/114**
(`/tmp/lab-v18-final4.log`). +26 testes; exemplos/modelos/bancos temporários nos
testes. Opções inválidas foram reproduzidas antes da correção; testes vermelhos
e resultados intermediários permanecem no histórico da execução, não omitidos.

Navegador: transporte simulado PASS; painel localhost real, somente leitura PASS,
zero erros JS. Screenshot `/tmp/laboratorio-v18-painel.png`. Não prova compositor,
sono de entidade real, qualidade de áudio ou treinamento. Atalho nativo verificado
pelo contrato offline; será visível ao reabrir a Central com o código novo.
Compilação Python, sintaxe JS e `git diff --check` passaram.

Preparação via API localhost real PASS: ordem H-treino/H-avaliação/L-treino/
L-avaliação, **zero jobs novos**, estado noturno inalterado, execução false e
bloqueio de disco visível. O painel foi encerrado normalmente e reiniciado com
as correções; não foi necessário reiniciar entidades ou Central de produção.

Treinos, retomadas, checkpoint, cancelamento seguro e recarga acima são físicos na
RX 6650 XT. Filtros/seletores/supervisor/cancelamento por sensor possuem testes
isolados adicionais, não homologação de uma noite com entidades de produção.

## Fechamento e próximos gates

Rodada física encerrada em 13/10/2026. Nenhum worker de treino/professor permaneceu
ativo; os leases dos ensaios foram liberados. Painel localhost continua disponível.
Log de kernel acessível desde 12/10 18h: nenhuma ocorrência correspondente a
reset/fault/timeout amdgpu, sem aviso de permissão nessa consulta. Não é garantia
de ausência de falhas futuras. Base original comparada pelo SHA completo com a
referência v1.7; datasets/corpora não foram editados.

Próximos gates: liberar espaço; revisar propostas e preferências de persona
humanamente; autorizar separadamente a janela longa; observar checkpoints e
validação durante mais de um epoch; testar entidades completas com seus contextos
de identidade e relações; só então considerar versões estáveis. Sobreajuste após
5–6 epochs, evolução de personalidade e restauração física de produção permanecem
pendentes. MoE 35B não pode ser considerado curador infalível pelo resultado atual.

**Parecer final:** v1.8 implementado e ensaiado; plano longo preparado, bloqueado
por disco e NÃO autorizado. Treino/recarga/checkpoint demonstrados na AMD com
perfil mais seguro. Professor ganhou cobertura e proteção, mas qualidade
semântica/personalidade ainda requerem curadoria; não há aprovação completa.
