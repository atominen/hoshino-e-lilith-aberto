# Consolidação do Laboratório Neural — 12/10/2026

## Ponto de partida e arquitetura

Manual mestre lido na branch `laboratorio-v11-organizacao-20261012`, referência
remota `e888400`. Checkout local em `main/37aa132`, com alterações posteriores
não commitadas, inclusive checkpoints v1.6.2. Nenhum ZIP reinstalado, rollback
ou substituição de arquivos locais por versões remotas.

Baseline real da suíte disponível localmente: **52 testes do laboratório passam**.
Os dois erros de fixtures relatados no pacote v1.6 não se reproduzem nessa suíte;
ela tampouco cobre ainda retomada, promoção ou sessão noturna. Não afirmar que
seis testes de pacote validam essas capacidades.

Decisão: expandir `treinos_unificados` / `treino_nf4_curto` e
`versionamento_lora`, reaproveitar o pipeline do professor e o Resource Manager
da aplicação. Uma interface Treinamento, um registro de jobs. Supervisor da
Central conserva a posse do ciclo de vida das entidades. Sessão noturna deve
pedir sono/restaurar somente entidades previamente ativas e exige autorização
contextual/janela explícita; nenhuma agenda antiga será reativada.

Problema de memória identificado no código instalado de PEFT: a preparação
padrão converte **todos** os parâmetros não quantizados BF16 para FP32, incluindo
embeddings/head enormes. A correção deve manter esses pesos congelados BF16,
norms em FP32 e checkpointing não reentrante. Offload textual, se necessário,
deve mover só ativações, nunca reinstalar hooks que recarreguem o embedding.
Probes físicos e orçamento amdgpu serão obrigatórios antes de homologação.

Modelos, corpora, identidades e memórias são preservados. Não há promoção
automática de adaptador, inferência externa, cloud, concorrência GPU ou exclusão.

## 1. O que foi consolidado

O v1.7 mantém os componentes existentes, sem outro cérebro, banco mental ou
scheduler. Fluxo operacional:

```text
Central → painel localhost:8788 → treinos_unificados / professor_moe
       → worker isolado → Resource Manager existente → ROCm ou Vulkan
       → checkpoint / proposta → recarga e holdout → revisão humana
       → referência estável do laboratório (não instalação em produção)
```

- Uma única seção **Treinamento**: catálogo real, plano, corpus, benchmark,
  retomada, avaliação, artefatos, revisão e rollback. O painel não carrega pesos
  ao abrir nem executa treinamento por GET.
- `probes_arquiteturas` e a CLI de Alistair encaminham ao mesmo executor NF4.
  Runners antigos `treino_texto`, `treino_qwen35_entidade`, ciclo legado e
  fechamento v1.3 não podem iniciar treinos alternativos. Código de referência,
  previews, checkpoints e relatórios antigos foram preservados.
- Aliases históricos do professor usam o pipeline único de lotes, fit,
  tokenização real e auditoria. A carga alternativa all-GPU/16K foi aposentada.
- A sessão noturna é responsabilidade do supervisor da Central: autorização
  explícita, janela, sono cooperativo, drenagem, execução serial e restauração
  somente das entidades originalmente acordadas. Não usa SIGSTOP nem horários
  antigos como prova de que o usuário foi dormir.
- A versão estável é apenas uma referência local por entidade/base. Não há
  exportação GGUF, instalação ou troca de executor de produção automática.
- Foram removidas cerca de 430 linhas de loops mortos atrás dos guards de
  aposentadoria. Entradas compatíveis, inspeção e mensagens de recusa continuam;
  os corpos antigos são recuperáveis pelo histórico Git. Imports dos runners
  aposentados não substituem mais os handlers de shutdown do processo chamador.

## 2. Bugs confirmados e correções

| Defeito | Correção / evidência |
|---|---|
| PEFT convertia embeddings/head congelados BF16 para FP32, causando OOM | Base congelada BF16, norms FP32 e checkpointing não reentrante; os cinco modelos completaram updates reais |
| 9B não cabia no perfil anterior | Embedding e parte visual congelados em CPU, restante textual e LoRA em GPU; pesos originais não são regravados |
| Recarga PEFT redispatchava base NF4 e criava estado `meta` | Carregar exclusivamente os tensores LoRA pelo get/set do PEFT, mantendo o mapa de dispositivos; chaves ausentes/inesperadas recusadas |
| Snapshot salvo trazia `inference_mode=True`, impedindo retomada | Reativar apenas os adaptadores no carregamento de treino; retomada física 2→4 idêntica ao contínuo 0→4 |
| API Transformers retornava BatchEncoding, mas teste tratava como Tensor | `input_ids` e `attention_mask` explícitos, sem perder máscara |
| Lease era liberado antes da saída completa do contexto HIP | Pai mantém lease até filho sair; telemetria amdgpu é observada antes/depois |
| Job concluído podia ser sobrescrito por cancelamento/consulta concorrente | Transições com lock no registro existente; estado terminal preservado, cancelamento persistido antes do sinal |
| Crash do iniciador antes de gravar PID deixava job eternamente ativo | Prazo de 15s para confirmação, diagnóstico durável `interrupted_unverified`, sem replay automático |
| Professor copiava perguntas/paráfrases fora da pequena amostra | Auditoria contra todo o corpus de treino autorizado; fonte/hash novamente conferidos antes de exportar |
| Lotes longos do professor desperdiçavam saída e repetiam truncamento | Lotes curtos, JSON/schema, contagem real de tokens, limite confirmado por protocolo; truncamento não é proposta completa |
| Gramática fechava strings em `maxLength` no meio de palavras, apesar de `finish_reason=stop` | Limites de campos ajustados sem aumentar contexto/saída arbitrariamente; strings próximas do limite são recusadas e recebem diagnóstico específico |
| `.env` de produção contaminava HIP com override legado gfx | Remover override somente no laboratório, depois do carregamento da configuração e antes do subprocesso |
| Falha real SDMA0 ao recarregar 9B | `HSA_ENABLE_SDMA=0` somente no runner do laboratório; não alterar driver, clocks ou ambiente das entidades |
| VRAM do driver excedia o corte apesar do cache Torch parecer menor | Monitor físico interrompe; cache inativo descartado entre amostras do perfil 9B, sem reduzir margem ou amostras |
| Utilização transitória após unload abortava o job seguinte antes de carregar | Preflight espera no máximo 10s pela mesma condição ≤10%; GPU externa persistentemente ocupada continua recusada |
| Servidor temporário do professor aceitava requisições locais sem autenticação | Chave efêmera apenas na memória/ambiente do processo owned; sem chave no argv/config/log, web UI desativada e teste real sem credencial recebeu HTTP 401 |
| Fixtures da Central divergiam dos contratos atuais | Mock da rota neural existente e raiz importável do supervisor; isolamento `HOSHINO_LAB_HOME` temporário nos testes |
| UI mantinha texto ambíguo de falha atual e mostrava log antigo como pipeline atual | Catálogo remete às medições base/corpus; log marcado histórico, sem apagar evidências; regressão de navegador |

O ajuste SDMA utiliza a opção documentada pela AMD em
[ROCm — variáveis de ambiente](https://rocm.docs.amd.com/en/docs-10.0.0/reference/environment-variables/index.html).
Não equivale a afirmar suporte completo desta GPU a todo kernel ROCm.

## 3. Máquina, recursos e preservação

RX 6650 XT/gfx1032: `8573157376` bytes reportados pelo driver (~7,98 GiB).
31 GiB de RAM e 8 GiB de swap presentes; swap chegou a ~5,5 GiB ocupados,
com ~25 GiB de RAM disponível. Swap não entra no orçamento de RAM rápida.
Disco permaneceu com ~87 GiB livres. Não houve download, reinstalação ou exclusão
de modelos nesta rodada.

Treino usa PyTorch `2.16.0a0+rocm10.2.0a20261010`, HIP `7.17.26405`, BF16 nativo.
As APIs chamadas `torch.cuda` são HIP nesse runtime, não uma dependência de CUDA
NVIDIA. Professor usa o executável Vulkan já instalado. GPU concorrente continua
desativada; lease P5 exclusivo e margem atual de 768 MiB preservados. O professor
solicita fit-target de 1 GiB e pode executar camadas restantes em CPU/RAM.
Esse parâmetro é uma estimativa, não prova de 1 GiB físico livre durante todo
o workload; no último lote o menor espaço observado foi ~0,84 GiB, ainda acima
dos 768 MiB exigidos pelo RM. Pressão externa/uso prolongado continuam pendentes.

A base 9B exige offload congelado; não se promete treino inteiramente GPU em
8 GiB. Pressão física, falta de métricas ou RAM física abaixo de 4 GiB pedem
parada conservadora, não ampliação de orçamento.

SHA256 completos das **27 shards** dos cinco modelos foram registrados em
`laboratorio-local/controle-laboratorio/treinamento-unificado/reports/consolidacao-20261012/base-integrity.json`.
O 9B original tem hash
`95117c3faed067c2a48dd3ddebf16209c4c6b60d1714ef5dd32cf784e2e053fc`,
igual ao registro anterior do manual. Os outros hashes são uma referência de
integridade local, não comparação fingida com hashes publicados pelo autor.
O professor continua identificado por header/tamanho; seu hash remoto completo
não foi homologado.

Bases, corpora, identidades e bancos mentais não foram modificados. Candidatos,
checkpoints, snapshots autorizados, logs e imagens do painel ficam em
`laboratorio-local`, ignorado pelo Git. Nenhum adaptador foi promovido.

## 4. Treinos físicos curtos na AMD

Corpus original: Alistair 51/27/16 exemplos; Hoshino 722/131/104,
respectivamente treino/validação/holdout. Seed 247, sequência até 256 tokens,
LoRA rank 4. Os valores abaixo usam **seis amostras** de validação durante o
treino; não devem ser confundidos com avaliação completa nem comparados entre
tokenizadores/modelos como ranking de qualidade.

| Base / entidade | Updates | Duração do treino + avaliação/save | Loss antes → depois | Pico alocado Torch |
|---|---:|---:|---:|---:|
| Qwen3.5 4B / Alistair | 2 | 11,34s | 3,9503 → 3,9520 | 3,151 GiB |
| Yi-1.5 6B / Hoshino | 21 | 66,13s | 3,0494 → 2,6311 | 4,021 GiB |
| Hunyuan 7B / Hoshino | 17 | 71,65s | 4,8544 → 4,7501 | 4,720 GiB |
| Qwen2.5 7B / Hoshino | 19 | 67,94s | 4,6710 → 4,2562 | 5,606 GiB |
| Qwen3.5 9B / Hoshino | 13 | 70,57s | 3,1272 → 3,0943 | 5,695 GiB |
| Qwen2.5 7B / Lilith | 19 | 67,67s | 4,5808 → 4,1535 | 5,602 GiB |

Todos salvaram LoRA, proveniência, configurações e checkpoint com estado de
otimizador, RNG e posição. O pico Torch não inclui toda a VRAM do driver. Alguns
primeiros treinos ocorreram antes da consolidação da telemetria física; os
ensaios seguintes têm séries amdgpu, RAM e utilização a cada 0,5s.

O treino separado de Lilith usa seu próprio corpus/adaptador. A primeira tentativa
foi recusada antes da carga por utilização transitória após o ensaio 9B. O retry
`consolidacao-20261012-qwen25-7b-retry`, após a espera limitada pelo mesmo critério,
concluiu com pico físico **6,841 GiB**, sem pressão; VRAM voltou a ~0,60 GiB.
Nenhum adaptador ou memória de Hoshino foi reaproveitado como dados de Lilith.

### Retomada e presets medidos

Alistair rank 4: treino contínuo 0→4 versus checkpoint 2→4 recarregado no processo
novo: **496 tensores iguais; diferença máxima absoluta 0,0**. Evidência:
`reports/consolidacao-20261012/resume-exactness.json` no registro unificado.
Primeiro ensaio da nova recarga falhou por adaptador congelado; foi preservado
em log e repetido depois da correção, não contabilizado como aprovação.

Comparação controlada 4 updates, mesma seed/base/corpus/runtime:

| Preset Alistair | Duração | Loss após | Pico Torch | Pico físico amdgpu |
|---|---:|---:|---:|---:|
| rank 4 | 17,15s | 3,9312 | 3,150 GiB | 4,774 GiB |
| rank 8 | 17,52s | 3,8828 | 3,286 GiB | 5,156 GiB |

O seletor passou a escolher rank 8 para esta base/corpus com essa evidência.
Não extrapola do 0.8B, não compara losses de quantidades distintas de updates
como se fossem pares controlados e não marca qualidade/treino longo aprovados.

### Fluxo físico pela API do painel

Job `2d402ba2aa61473e`: iniciar treino real Alistair pelo endpoint do painel,
consultar progresso, solicitar parada após `PASSO 5` e aguardar desfecho.
O update 6 em curso terminou e foi salvo; estado **cancelled_checkpointed**,
rank 8, loss final 3,8198, 22,75s, pico físico 5,256 GiB, sem pressão.
Recibo e série de métricas: `reports/consolidacao-20261012/worker-api-cancel.json`.
Não simular parada instantânea: os seis updates ocorreram de verdade.

## 5. Recarga independente e qualidade

Validação e holdout completos são executados em processo novo, com base e LoRA
recarregados. Duas perguntas simples geradas com cache de inferência e 96 tokens.
`finished` exige EOS; atingir o limite não conta como resposta completa.

| Base | Validação completa | Holdout | Duração | Pico físico | Resultado |
|---|---:|---:|---:|---:|---|
| Alistair 4B | 3,9610 / 27 | 4,4637 / 16 | 77,12s | 4,507 GiB | Recarga passa; uma resposta truncada |
| Yi 6B | 2,7168 / 131 | 2,7702 / 104 | 289,24s | 5,207 GiB | Recarga passa; duas respostas truncadas |
| Hunyuan 7B | 5,2893 / 131 | 5,8162 / 104 | 397,72s | 5,784 GiB | Recarga passa; raciocínio ocupa as duas saídas |
| Qwen2.5 7B | 4,2662 / 131 | 4,4744 / 104 | 398,41s | 6,874 GiB | Recarga passa; duas respostas terminam |
| Qwen3.5 9B | 3,0196 / 131 | 3,0395 / 104 | 390,21s | 7,007 GiB | Recarga completa e duas respostas terminadas; revisão humana pendente |

Essas perguntas avaliam o **checkpoint bruto**, sem injetar a constituição/memória
da entidade. Respostas genéricas não provam que a identidade de produção mudou,
mas tampouco homologam a qualidade do treinamento. O Hunyuan ignorou a intenção
de desligar thinking nesse protocolo: o `chat_template` instalado não possui
condicional `enable_thinking`. Enviar `False` não suprime aquele protocolo;
as duas gerações ficaram em `<think>`. Não houve alteração silenciosa do
tokenizer nem aprovação artificial pelo recorte desses fragmentos.
Nenhum resultado foi marcado `passed=True` pelo simples fato de loss ser finita.

Falhas 9B preservadas: fault SDMA0, estado NF4/meta e duas paradas conservadoras
por pressão na avaliação completa (7,280 e 7,395 GiB físicos, antes da limpeza
mais agressiva **apenas de cache inativo**). Não houve reset amdgpu detectado
no período posterior ao ajuste SDMA até a consulta registrada.

O ensaio final 9B limpou cache inativo 235 vezes; saiu com código 0, sem alerta
de pressão, VRAM ~0,66 GiB após a saída e RAM disponível mínima ~23,84 GiB.
A validação completa permaneceu numericamente igual: 3,019615070112334.
Tempo daquela mesma etapa: 199,26s no ensaio interrompido versus 201,36s no
perfil seguro (~1% de diferença neste ensaio, não benchmark estatístico).
Não houve redução de margem, mudança de labels, amostragem menor ou troca da base.

## 6. Professor 35B e curadoria

Job real `fda5d16b9a024a24`: dois casos a partir do treino autorizado de Hoshino,
snapshot/hash/source IDs preservados. Fit Vulkan, contexto 4096, thinking OFF,
416 tokens de entrada e 370 de saída. Carregamento ~15,35s, geração completa
20,61s; **22,30 tokens/s** de geração e 102,57 tokens/s no prompt. Total do job
~38,86s. O histórico anterior registrava ~4,3–5,4 tokens/s, mas não era o mesmo
workload/preset; isso não é um benchmark A/B nem ganho universal de 4–5x.

Dois pares inéditos passaram o filtro de cópia contra todo o treino. Permanecem
**PROPOSTA_NAO_APROVADA**. A primeira proposta usa estilo genérico de assistente;
o prompt foi refinado para respostas conversacionais, primeira pessoa,
tratamento de contradições e ressalvas explícitas sobre a fonte. Não foram
adicionados bordões, emoções ou identidade fictícia.

Também foi identificado um exemplo de origem com pergunta sobre deslealdade
cuja resposta começa com uma confirmação incompatível com sua justificativa.
O corpus original foi preservado; treinamento mais longo não conserta por si
só esse problema de qualidade. O professor recebeu orientação para avaliar
o significado em vez de copiar o erro. Curadoria humana continua necessária.

Segundo ensaio `f8f9bd0dce3e4231`: dez evidências, cinco lotes previstos.
**Falhou no objetivo de completar dez pares**: gerou quatro, interrompeu no
lote 3 por cópia de pergunta, estado `needs_revision`, sem exportação.
115,24s, pico físico 6,940 GiB, RAM disponível mínima 26,91 GiB.
Dois campos chegaram a 280 caracteres com cortes em palavras; a gramática
produziu JSON completo, não texto semanticamente completo. Esse defeito foi
reproduzido e ganhou regressão. Um ensaio após o novo guard
(`65b9fc27d5ce4f5f`) corretamente recusou campos `reason` no limite de 120
caracteres; limites de metadata foram ajustados antes do piloto seguinte.
O piloto `dadf81cc2b064258` concluiu **2/2 pares**: respostas de 128/140 caracteres,
sem campos próximos do limite, sem cópias detectadas. Novo ensaio autenticado
`29093a5d521342cd` também concluiu **2/2**, em 35,26s totais; 509 tokens de prompt,
445 de saída, 21,10 tokens/s de geração. Ambas as propostas continuam não aprovadas.
Isso não apaga os fracassos do lote maior.
Não houve exportação aprovada nem treinamento automático com dados gerados.

No último ensaio, `/tokenize` sem chave foi recusado com **HTTP 401** enquanto
o worker autenticado tokenizou e gerou normalmente. A chave interna é aleatória
por sessão, enviada somente no ambiente do servidor e header loopback do worker,
apagada da memória ao sair; não é credencial externa nem configuração persistida.
O servidor owned encerrou ao terminar. Nenhuma chamada externa/quota foi usada.

### Repetição final do lote de dez

Job `e8e73ed778da4000`, mesmos dez casos de treino autorizado, código final:
**5/5 lotes, 10/10 pares completos**, 165,79s totais. No último lote, a primeira
tentativa chegou ao limite de `reason` e foi recusada; a segunda terminou com
campos abaixo dos limites. Nenhum prompt/resposta copiado ou par duplicado foi
detectado. O pipeline reaproveitou prefixos em cache sem mudar a fonte ou IDs.

**Resultado de curadoria: `needs_revision`, `quality_passed=false`.** Todos os
pares receberam a categoria `personalidade`; o contrato para um conjunto dessa
dimensão exige ao menos duas. Não se enfraqueceu o filtro nem se relabelaram
exemplos para obter aprovação. Inspeção de uma resposta também mostra linguagem
genérica de função/assistente: isso não está homologado como voz de Hoshino.
Nenhum exemplo deste lote foi exportado ou treinado. Diversidade e naturalidade
continuam problemas reais de qualidade, não falhas ocultas ou meramente mocks.

Telemetria em `reports/consolidacao-20261012/professor-10-v17-final-metrics.json`:
pico **observado** 7,145 GiB, RAM disponível mínima 25,69 GiB. O sampler começou
depois do primeiro lote; não representa pico completo de carregamento.
O log registra preflight, demais lotes e descarregamento; VRAM ao sair ~0,64 GiB.
O professor encerrou, e o lease foi liberado. Não houve troca de modelo/backend.

## 7. Automação noturna e limites

Implementados e testados em ambiente isolado: consentimento contextual/janela,
recusa de preset sem medição, reserva de tempo para restauração, drenagem de
jobs/leases, manutenção que bloqueia wake automático, parada cooperativa,
restauração apenas de quem estava ativo e recuperação manual após crash.

**Não foi executada uma noite real com entidades de produção dormindo e
acordando.** O usuário não anunciou que estava indo dormir nesta rodada.
Também não se reiniciou a Central de produção para aplicar código novo sem
necessidade. Ela precisa carregar o supervisor atualizado antes do primeiro
ensaio noturno. Restauração registrada não significa health automaticamente
aprovado: `restoration_health_pending` permanece explícito.

O teste físico de start/stop/checkpoint do worker foi feito sem acordar ninguém.
Ele não substitui a homologação da noite inteira ou de sessões de horas.

## 8. Arquivos e contratos

Fontes locais anteriores ao trabalho foram versionadas junto com a consolidação;
nem todo arquivo novo no Git representa implementação nova desta rodada.
Lista completa verificável: `git show --name-status 9f527a9` e commit de fechamento.

Principais alterações/refinamentos:

- `laboratorio/treino_nf4_curto.py`: memória, reload, retomada, métricas e processo
  HIP isolado; `versionamento_lora.py`: proveniência, hashes, checkpoint completo,
  revisão, promoção/rollback; `treinos_unificados.py`: catálogo/presets, corpus
  aprovado, jobs duráveis, cancelamento, artefatos e planos noturnos.
- `laboratorio/professor_moe.py`: lotes, fit/tokenização, originalidade, métricas,
  curadoria e isolamento; aliases e estados históricos preservados.
- `laboratorio/painel.py`, `web/index.html`, `web/app.js`: controles de retomada,
  avaliação, corpus derivado aprovado, artefatos e sessão noturna no mesmo painel.
- `probes_arquiteturas.py`, `alistair.py`, `experimentos.py`,
  `treino_texto.py`, `treino_qwen35_entidade.py`, `finalizacao_10min.py`,
  `controle.py`, `personalizacao.py`: consumidores e caminhos antigos reconciliados.
- `iniciar_entidades.py`: imports/integração e manutenção no supervisor existente;
  Central nativa/web e `neural9b_modes.py`: integração anterior preservada.
- `.gitignore`, fixtures da suíte e `testes/executar_isolado.py`: estado sensível
  fora do Git e home do laboratório temporário nos testes.
- Regressões em `laboratorio/tests/test_consolidacao.py`,
  `test_noite_supervisor.py`, `test_browser.py`, `browser.cjs`; grupo existente
  `testes/test_laboratorio_ia.py` executa a suíte local atual.

APIs loopback do painel: `/api/treinos/{catalog,datasets,jobs,job,artifacts}`,
`{preview,start,stop,review,promote,rollback}`; `/api/night` e
`/api/night/{start,stop}` encaminham ao supervisor existente
`/api/control/laboratory/night{,/start,/stop}`. POST exige token efêmero e
origem/Host local. Nenhuma chave remota vai ao frontend.

## 9. Testes e evidências

Baseline: 52/52 testes do laboratório; suíte oficial inicial 73/74, com fixture
da Central divergente. Depois apareceu outro erro de import da raiz, corrigido
sem restauração da arquitetura antiga. Rodadas posteriores da suíte oficial:
**74/74**, com isolamento de arquivos/bancos e sem providers reais.
Contagem final de regressões e última execução: ver fechamento abaixo.

Além de testes unitários, houve treino e recarga reais AMD, comparação numérica
de retomada, start/stop do worker pela API e navegador real com servidor real
em modo somente leitura. Screenshot em
`laboratorio-local/controle-laboratorio/treinamento-unificado/reports/consolidacao-20261012/painel-final.png`.
O Chromium de teste usa `--disable-gpu`; isso valida DOM/HTTP, não treinamento
ou compositor de desktop. Nenhuma entidade, microfone ou serviço externo foi
iniciado por testes offline.

Painel atualizado reiniciado cooperativamente, sem reiniciar entidades.
Navegador real leu as APIs do servidor real: **PASS**, zero erros JavaScript,
sem POST de treino. Medição pontual após consultar o painel: ~25,8 MiB RSS,
0,1% CPU cumulativa do processo; antes das consultas, ~13,5 MiB RSS/0,0% CPU.
isso não é ensaio de soak nem medição do compositor. A Central de produção não
foi reiniciada; o painel já carrega o código novo, o supervisor precisa de reload.

## 10. Pendências e parecer

- Avaliação humana de naturalidade, identidade, raciocínio e dados novos; respostas
  truncadas não podem ser homologadas pela UI.
- Professor: conjunto de dez terminou tecnicamente, mas foi reprovado por uma
  única categoria; estilo genérico ainda precisa de curadoria, não de aprovação
  automática ou treino maior para mascarar o problema.
- Treinos prolongados e estudo de qualidade com holdout: minuto de treino não
  demonstra estabilidade de horas nem aprendizado conversacional sustentável.
- Primeiro ensaio noturno real: sono, fala/job em curso, restauração/health,
  pressão de aplicações externas e recovery do supervisor no desktop.
- Kernels ROCm faltantes e avisos BNB/MIOpen continuam documentados; não se
  instalaram kernels de compatibilidade desconhecida para fabricar desempenho.
- Adoção de adaptador em produção/GGUF exige etapa autorizada e validação própria;
  referência estável do laboratório não altera o executor atual.

**Parecer:** pipeline experimental consolidado, com várias operações reais
comprovadas. **Não são cinco modelos comportamentalmente homologados**, nem
uma sessão noturna prolongada certificada. Não usar testes simulados ou loss
menor para ocultar essas limitações.

## 11. Fechamento da execução

Treino e recarga dos cinco modelos: **verificados fisicamente**, nos limites dos
ensaios curtos descritos. Treino de Lilith separado, retomada numérica exata,
cancelamento com checkpoint pela API e professor autenticado também físicos.
Avaliação comportamental, promoção estável real e noite prolongada: **pendentes**.
Promoção/rollback, supervisor noturno e falhas de processo passaram em ambiente
isolado, sem escrever nos bancos mentais ou instalar pesos em produção.

Laboratório: **88/88 testes** (baseline 52, 36 adicionais), incluindo locks,
crash/replay, checkpoint/integridade, retomada, identidade/corpus, revisão,
rollback, VRAM desconhecida/pressão, CPU/embedding congelado, cache inativo,
origem dos dados, cortes de gramática, autenticação e aposentadoria dos runners.
Suíte oficial final, após o último ajuste do navegador: **74/74 grupos offline**,
exit code 0. Laboratório final: **88/88**, 2,067s. Logs integrais preservados em
`reports/consolidacao-20261012/suite-offline-final.log` e
`reports/consolidacao-20261012/laboratorio-tests-final.log` no registro unificado.

Não há worker GPU restante dos ensaios nem servidor do professor deixado aberto.
Painel do laboratório permanece em localhost:8788. Não houve reset/fault amdgpu
na consulta ao journal desde 17:49 após o ajuste; o fault SDMA anterior permanece
documentado. Modelos/corpora/bancos/identidades originais preservados.

Consulta final somente leitura: **leases vazios**, fila GPU vazia e VRAM
`643051520` bytes (~0,60 GiB), `gpu_busy_percent=0`, métricas conhecidas/estáveis.
Não ficou recurso falsamente ocupado pelos ensaios.

## 12. GitHub e entrega

Implementação e evidências textuais fechadas em
`701f733fd71d1ba81159622343e076ecdcf74449`. Esse commit foi enviado e confirmado
por `ls-remote` na branch existente `laboratorio-v11-organizacao-20261012` de
`atominen/hoshino-e-lilith`, ainda **privado**. Push normal fast-forward, sem
force e sem criar outro repositório. O merge `2721b01` conserva o histórico remoto
e o código local mais novo; o snapshot inicial de código é `9f527a9`.

O [PR existente #1](https://github.com/atominen/hoshino-e-lilith/pull/1) permanece
rascunho para revisão; não houve merge na `main`, promoção de pesos ou reload
das entidades. Este registro de entrega é uma atualização documental posterior
ao commit de implementação. Para os nomes de todos os arquivos sincronizados,
compare o histórico da branch com `e888400`; fontes locais anteriores também
foram preservadas e não devem ser atribuídas integralmente a esta rodada.

Auditoria do último conjunto enviado: 19 arquivos, 363739 bytes de fontes/docs,
nenhum segredo/artefato privado detectado. Ignore protege pesos, checkpoints,
venvs, corpora JSONL, SQLite mental, configs reais, logs e `laboratorio-local`.
Nenhum desses arquivos foi incluído no push. Evidências físicas completas
continuam no SSD; o relatório versionado contém métricas e IDs, não conversas
mentais ou conteúdos de datasets privados.
