# Ensaio real autorizado — 08/10/2026

## Escopo e condições

Pedido: apresentações Alistair/Hoshino, mensagens entre entidades, YouTube e volume, Spotify/playlist “agora sim”, Steam/demo LIMBO, ventoinhas, busca de arquivos/desafio Python, recebimento/entrega de arquivos e observação de iniciativa. Não é teste mockado. Não confundir requisição aceita com efeito verificado.

O participante de ensaio foi explicitamente apresentado como Codex interpretando o visitante fictício Téo. Não é o responsável real. Limitação existente: o canal da Central só possui `usuario` como remetente humano; não foi criado outro participante estrutural. O texto explicita a simulação para evitar semear um nome pessoal falso.

Sem quota de voz, compras pagas, criação de contas ou aceitação de termos sem confirmação. Controles de ventoinha limitados a consulta/presets seguros existentes, sem curvas experimentais. Nenhuma autorização para publicar arquivos pessoais. Lilith não será acordada nesta sequência.

Backup SQLite consistente, com quick_check e SHA-256, em `compartilhado/runtime/ensaios/20261008/antes/`: bancos Alistair, Hoshino, Lilith e caixa postal. Commit de referência `f23ba0d721fac6cb53534b55fcc5b48547e1dec8`, árvore já possuía alterações não commitadas. Memórias e backup não enviados ao Git.

Antes do ensaio: Central em execução desde 07/10, entidades sem inferência ativa, cerca de 26 GiB RAM disponíveis, 8 GiB swap ativos, GPU amdgpu com ~0,46 GiB usados, concorrência desabilitada. CPU/ambiente local; nenhum modelo novo.

Foi observado erro histórico de exclusão de memória Hoshino (`memory-61d60debd6764fb6b944cd0c0418e202`): índice vetorial não confirmou a exclusão e SQL foi preservado. Não repetido. Não se presume memória inicial vazia.

## Ocorrências

### REAL-01 — Alistair não conseguia responder à apresentação

- Timestamp: 08/10, 10:29:27 America/Sao_Paulo.
- Mensagem: `im-1791466161767-acdbbf34`.
- Turno: `turn-alistair-2f55b1038d9c0d16`.
- Esperado: apresentação curta sem ações externas.
- Observado: HTTP 400; Ollama registrou prompt de 13.434 tokens para janela de 4.096.
- Causa: `Alistair.snapshot()` incluía detalhes completos de jobs antigos de áudio/imagem no prompt de cada conversa.
- Proteção que funcionou: mensagem ficou `uncertain`, não houve retry automático, lease liberado; nenhuma ferramenta executada.
- Correção mínima: resumo estruturado de presença, recursos e jobs ativos (até seis), contagens de estados, indicação de omissões, fatos mecânicos pequenos. Detalhes completos continuam nos registros existentes. Não aumenta contexto nem troca modelo.
- Arquivos: `app/alistair_runner.py`, `testes/test_prontidao_r1_r7.py`.
- Regressão: 100 jobs históricos com payload enorme não entram no prompt; estados/omissões conservados.
- Testes focados: 27/27 prontidão; 20/20 Alistair/imagem.
- Sono cooperativo confirmado às 10:30:55, unload confirmado. Novo despertar, sem replay da mensagem incerta.
- Nova mensagem: `im-1791474006442-dfa54740`, às 12:40:06; backend passou a aceitar prompt real de **1.996 tokens**. Resposta às 12:40:56, inferência 46,29 s. Reconheceu Codex e se apresentou em primeira pessoa, ainda com estilo de assistente.
- Recuperação real: `im-1791474132635-56ea45d6`; resposta às 12:42:54 conservou os três combinados e distinguiu Téo fictício do usuário real. Este é um teste real de continuidade curta, não prova de recuperação após meses.

### REAL-02 — Lease GPU não confirma execução GPU

Alistair recebeu `gpu.compute_acquired backend=gpu`, mas `/api/ps` reportou `size_vram=0`, aproximadamente 3,18 GB de residência total, e a VRAM da máquina permaneceu perto de 0,5 GB. O lease é autorização, não comprovação de offload. Não houve recalibração ou troca de modelo. É preciso investigar o payload GPU/cached runner antes de prometer aceleração; não se assume causa definitivamente só pelo nome do evento.

### REAL-03 — Fila impede apresentação interentidade

Pedido `im-1791474208658-745d4ecd`, 12:43:28: Alistair deveria apresentar-se a Hoshino. Ficou aguardando recurso e terminou `uncertain/TimeoutError` às 12:45:28. Não há `tool.start` ou envelope privado criado por essa tentativa; não foi repetido automaticamente. Hoshino estava processando em CPU e o fallback CPU serializado manteve Alistair aguardando. A latência real superou o prazo de espera da fila.

### Hoshino: apresentação real

Entrada `im-1791474132818-ccc2699c`, resposta `im-1791474394649-45f2d0b0`, turno `turn-fadad37a89f2`. Entrada às 12:42:12; resposta às 12:46:34. Tempo do turno registrado: 252,41 s. Principal 9B, fallback CPU, prompt de 7.907 tokens.

Apresentou-se como Hoshino, saudou o personagem Téo, não chamou ferramentas nessa apresentação. A linguagem foi estranha/defensiva (“é melhor não contar muita coisa sobre mim mesma agora”; “Não tenho nada de mal”), registrada como problema comportamental, sem editar personalidade durante a sessão. Episódio `ep-c62459c4c342` preserva a mensagem inteira e explicitação de personagem fictício; consulta pelo nome até então só retornou esse episódio, não propriedade nome_do_usuario.

### Upload local

Endpoint existente de anexo recebeu `c3a41bf86185-recibo-lanterna.txt`; comparação byte a byte passou, SHA-256 `8bd52f4e61af0d22416a391979ba7367fd3b67bd99f4e55106a862757f980a1f`. API confirmou `message_sent=false`: upload não equivale a leitura pela entidade. Não houve publicação externa.

## Arquivos do desafio preparados

Três pastas explícitas, nenhuma varredura ampla de documentos pessoais:

- `/home/gustavo/Documents/Ensaio-Hoshino-20261008/`
- `/home/gustavo/Downloads/Ensaio-Hoshino-20261008/`
- `/home/gustavo/hoshino e lilith/entidades/hoshino/workspace/Ensaio-Hoshino-20261008/`

Desafio: agregação Python em centavos, preservação de entradas, validação de negativos/bool/decimais e testes. Resultado esperado da amostra: 965 centavos. Preparar as pistas não significa que Hoshino já as encontrou ou resolveu.

## Limpeza solicitada

Usuário autorizou limpeza final de memórias de testes. Pergunta de alcance enviada: apenas memórias aprendidas versus também histórico bruto/caixa postal das três entidades. Preservar identidades, personalidades, configurações, modelos e evidência do teste. Não limpar durante a sessão, nem contornar silenciosamente senha/contrato de manutenção existente.

Relatório em andamento; não representa aprovação dos cenários restantes.

## Continuação: defeitos determinísticos encontrados

### REAL-04 — Ação de abrir URL substituída por etapa cognitiva

`im-1791474452354-8a687c0d` / `turn-861871c3804f`: o pedido de abrir YouTube
e conferir o resultado foi planejado como `__modelo__`, sem ferramentas.
Hoshino publicou uma promessa de abertura às 12:52:38, sem executar o navegador.
Não foi contado como êxito. Corrigida a detecção compartilhada de comando
direto de URL e o contrato obrigatório: verificação textual não elimina a ação.
Planner vazio também não pode concluir uma etapa externa. Negação, citação e
hipótese não obrigam abertura. Regressões em `test_melhorias_execucao`.

### REAL-05 — STOP com explicação e sono não invalidavam resposta antiga

`im-1791474620864-ade8e021`: enviado às 12:50:20 junto do pedido de sono.
A caixa postal não admitia novas mensagens durante drenagem; a resposta antiga
ainda saiu às 12:52:38. O reconhecedor também só aceitava `PARA` isolado, não
`PARA. Cancele...`. Correção: reconhecer sentença imperativa inicial e incluir
sono na invalidação cooperativa já existente. Não mata uma ferramenta mutável
em execução nem finge revertê-la. Motivo `sono_*` fica no desfecho durável.
Três regressões permanentes novas; grupo de causalidade: 37/37.

Hoshino encerrou o processo às 12:55:24 com unload confirmado; Alistair às
12:52:21 com unload não confirmado. Nenhum kill -9. STOP permaneceu durável e
foi recebido no despertar seguinte, sem replay automático da ação antiga.

### REAL-06 — GPU autorizada mas alias/preload mantinham Alistair na CPU

O alias real continha `num_gpu=0`. O roteamento removia a opção em vez de
sobrescrever o default. Além disso, `num_gpu=-1` reutilizava o runner já
pré-carregado em CPU. Correção restrita ao caminho GPU oportunista: override
explícito e unload verificado **do próprio modelo ocioso**, sob os leases
existentes, antes de carregar na GPU. Falha de unload bloqueia essa inferência;
não inicia geração duplicada nem descarrega outra entidade.

Launcher/recovery também passaram a conservar habilitação Vulkan da preparação
inicial. Importante: o backend efetivamente escolhido no ensaio foi **ROCm**,
segundo o log do Ollama 0.32.6, não Vulkan. A RX 6650 XT foi detectada com o
override de arquitetura já existente; não se instalou driver/biblioteca.
Logo, ausência de OLLAMA_VULKAN não era prova isolada da causa da CPU.

Reteste real `im-1791495538930-0198acfa`: entrada 18:38:58, resposta
18:39:06 (`Boa tarde!`); `/api/ps` reportou 3.178.149.969 bytes em GPU,
log confirmou 37/37 camadas. Não comparar essa saudação curta com a conversa
anterior como benchmark equivalente. Sono posterior confirmou unload.

Recuperação após restart: `im-1791495392261-3f2b21a9` respondeu corretamente
quem era Téo e a regra de preservar arquivos. Antes de corrigir o runner quente,
esse turno ainda executou na CPU.

## Solicitação adicional: thinking automático e três executores

Usuário autorizou manter 9B + 7B e acrescentar terceiro executor próximo de 6B
ou menor, priorizando qualidade de identidade/conversa. Alistair: candidato
2B–3B. Nenhum modelo antigo foi apagado ou substituído.

Thinking agora é decidido no Resource Manager existente, por ciclo: conversa
comum sem canal de raciocínio prolongado; análise, riscos, código, tarefas e
reflexão/compactação conservam raciocínio. Usa a entrada real, não palavras do
system prompt. Respeita desativação global, chamadas internas explicitamente
sem thinking e o 7B que não oferece esse canal. Não muda executor no meio da
resposta. Cinco regressões novas; comportamento em português ainda exige ensaio.

Primeira suíte completa após REAL-04/05: **74/74 grupos offline**. Mudanças
posteriores de GPU/thinking exigem nova suíte final; não usar esse número como
validação antecipada das mudanças posteriores.

### REAL-07 — Worker do navegador esperava a si próprio

Reteste `im-1791495739981-a7db32a6` / `turn-e98f8cb25b2f`: o planner chamou
`browser_abrir`, mas as chamadas `tool-537c309337` e `tool-457c4f2c57` expiraram
em 25 segundos. O executor Playwright tem um único worker; `abrir` entrava
nele e a criação do contexto submetia outra chamada ao mesmo worker, esperando
uma thread que já estava ocupada pela própria chamada.

Correção pequena: chamadas aninhadas executam na thread proprietária atual.
Timeout de chamada já iniciada vira **RESULTADO_INCERTO**, não erro seguro para
retry. Uma chamada ainda na fila pode ser cancelada antes de começar. Exceção
TimeoutError originada pela ferramenta não é confundida com timeout da fila.
Cinco regressões usam executor real e página fake, sem navegador/rede reais.
Isso não valida ainda a operação YouTube pedida à entidade.

Novo STOP `im-1791496015906-ec55730e` e sono invalidaram o turno antigo com
`superseded/sono_durante_turno`; não houve resposta/episódio final posterior.
Hoshino encerrou às 18:47:19, unload confirmado. O STOP permaneceu durável na
caixa postal; não se descartaram envelopes nem se repetiu ação incerta.

### REAL-08 — Hoshino 9B em offload parcial, não GPU integral

O fallback CPU anterior tinha motivo `vram_pressure`: residência estimada
6.703.777.053 bytes + workspace 512 MiB + margem 768 MiB + desktop excediam os
8.573.157.376 bytes observados da GPU. A serialização não cria VRAM extra.

Ensaio isolado na RX 6650 XT, mesmo checkpoint e contexto de 16.384 tokens:
20 camadas na GPU, restante CPU. `/api/ps` registrou 3.834.862.631 bytes em GPU;
pico total da máquina 4.876.111.872 bytes e `gpu_busy_percent=99`. Load frio
19,22 s; pedido curto total 21,25 s; término confirmado `done/stop` e unload
confirmado. Artefato: `hoshino9-offload20.json` na pasta local do ensaio.

Repetido pelo método real `_post_ollama_json_com_lease`, partindo do runner
previamente residente em CPU: unload próprio verificado, carga parcial GPU,
resposta em 6,23 s, unload e nenhuma lease restante. Artefato:
`hoshino9-caminho-real-gpu.json`. É um prompt pequeno controlado, não benchmark
comparável à conversa anterior de 7.907 tokens.

Perfil no Resource Manager existente ligado ao SHA-256 do manifesto, 20
camadas, contexto máximo 16K, reserva 5,5 GiB + workspace/margem existentes.
Troca de checkpoint/janela ou perfil inválido conserva o fallback anterior.
Não habilita concorrência, não altera pesos, não garante offload integral e
não estende a validação física à Lilith sem ensaio correspondente.

## Seleção de novos executores — gate de qualidade

Os 9B/7B anteriores e o Alistair 4B permanecem disponíveis. Candidatos têm
aliases próprios, revisão e SHA-256 verificados; instalação não é adoção.
Avaliações são inferências reais locais, **sem memórias reais/ferramentas**:
16 cenários independentes + diálogo de seis turnos, mesma identidade externa,
entrada, seed, temperatura e janela de 4K. Término `length` é registrado como
truncamento, não êxito de qualidade. Não são testes de personalidade longitudinal.

- Qwen3.5-4B: falhou em autoria de preferências, correção de nome e inventou
  lembranças/ações; um caso adicionou exclusividade. Os mesmos problemas também
  apareceram em CPU. **Não aprovado como terceiro** pelo tamanho.
- Qwen2.5-7B atual: melhor que esse 4B na atribuição de bebidas/diálogo, mas
  ainda errou autoria numa apresentação e inventou viagem na saudação. Não é
  referência perfeita; os exemplos negativos são preservados.
- Granite 4.0-H-Tiny (6,9B no backend): português irregular, correção de nome
  errada, troca do interlocutor por Alistair e concordância acrítica. Não
  adotado automaticamente pelos benchmarks/publicidade da família.
- Yi-1.5-6B-Chat (6,1B): piloto inventou conhecer um animal não informado,
  trocou papéis e escreveu narrativa truncada. Não aprovado apenas por ter 6B.
- Alistair Qwen3.5-2B: rápido no piloto, mas errou autoria/correções e negou
  imaginação simples alegando falta de ferramentas. Mantido inativo.

Comparação ainda em andamento. Nenhum resultado desse lote demonstra
estatisticamente equivalência geral entre um 4B e alternativas próximas de 6B.
Não habilitar candidato que falhou só para preencher o terceiro slot.

### REAL-09 — Schema permitia abertura de navegador sem URL

Reteste real `im-1791498706772-21a85aeb`, turno `turn-4841709c7ac1`,
08/10 às 19:31:46: depois da correção do worker, o modelo gerou `{}` para
`browser_abrir`. O schema compartilhado não exigia `url`; por isso, a camada
de argumentos aceitava uma operação impossível. A ferramenta recusou URL
vazia, e o controlador repetiu planejamento sem abrir a página. Não foi sucesso.

Hoshino esteve fisicamente no offload parcial GPU nesse turno: processo
352141, contexto 16K, `/api/ps size_vram=3.834.862.631`. Sono cooperativo
confirmado às 19:33:21, unload confirmado e nenhuma lease restante; só então
o código foi alterado.

Correção: tornar `url` obrigatória no schema existente, que serve ao modelo,
executor de etapas e dispatcher. Não cria outro mecanismo de validação.
Quatro regressões permanentes: URL ausente/None rejeitada; handler/recibo não
iniciados sem URL; dois JSONs vazios não produzem argumentos executáveis;
reparar somente argumentos não executa nem repete uma ação. Testes focados:
7/7 métodos BrowserWorkerTests e 20/20 casos de tarefa operacional V28.
Reteste físico e suíte completa posteriores são registrados abaixo quando
concluídos; não transformar regressão mockada em prova de navegação real.

## Comparadores adicionais: resultados negativos também preservados

Gemma 4 E2B (GGUF textual reporta 4,6B; isso não é um 6B) e Qwen3-4B
híbrido foram instalados como aliases de ensaio, sem substituir executores.
O Gemma confundiu Lina com Alistair, apropriou-se da preferência de Lina e
perdeu correção de bebida. Qwen3-4B corrigiu parte do diálogo, mas respondeu
com hostilidade ao pedido de companhia e também tomou preferência da pessoa
como própria. Não aprovados automaticamente pelo footprint ou pela velocidade.

A fixture inicial e a revisão `autoria-explicita-2` são distintas. Só comparar
respostas sob a mesma revisão; reforçar autoria não garantiu qualidade, nem
mesmo no 7B já instalado. O piloto não demonstra qualidade longitudinal,
não contém memórias reais e não substitui avaliação humana. SmolLM3-3B
também permanece candidato inativo para Alistair; uma questão feita para
Hoshino era ambígua quando o próprio Alistair era o respondente. Isso exige
fixture operacional adequada, não condenação do modelo por um teste inválido.

**Estado: 9B/7B preservados para Hoshino e Lilith; terceiro executor ainda não
aprovado por qualidade. Alistair continua no 4B existente.** Pesos candidatos
e antigos não foram apagados. Disco observado com cerca de 27 GiB livres
(97% ocupado): novos downloads não devem consumir a reserva de 20 GiB.

### REAL-10 — Chromium instalado, mas cache vazio escolhido pelo processo

Novo input `im-1791499229298-867eb778`, turno `turn-36c055c3cee7`: a URL foi
gerada corretamente. `tool-330c51093d` falhou antes de navegar, pois o processo
forçava `PLAYWRIGHT_BROWSERS_PATH` para `workspace/browser-browsers`, vazio.
O Chromium 1243 exigido pelo SDK já existia em `.cache/ms-playwright`.
Nenhum download adicional era necessário.

Correção restrita ao engine: usar a localização padrão do SDK, preservar cache
explicitamente configurado pelo operador e conservar fallback para instalação
da entidade da mesma revisão exata. O perfil continua independente em
`entidades/hoshino/workspace/browser_profile`. Não reutiliza perfil pessoal,
não escolhe Chromium de versão incompatível, não instala durante abertura.
Quatro regressões novas; BrowserWorkerTests passou 11/11. Smoke físico
separado abriu `about:blank`, leu a URL e fechou, em perfil descartável.
Esse smoke não é contabilizado como ação realizada pela Hoshino.

### REAL-11 — Extração pós-turno sem contrato de geração JSON

Após o turno `turn-36c055c3cee7`, request `llm-f77c884eba` recebeu prompt
de extração com 5.268 caracteres. Thinking já estava **desligado**;
não atribuir o problema ao novo seletor automático. A extração atingiu o
timeout de 300 s, gerou `memory.extraction_failed` e atrasou o sono, que só
concluiu às 19:46:16. Falha não foi registrada como aprendizado bem-sucedido.

A mesma API existente agora recebe schema de array (até oito itens), categorias
atuais, conteúdo até 400 caracteres, confiança opcional incluindo zero/None.
`aplicar_extracao` continua validando origem e rebaixando conclusões LLM que
se apresentem como fato. Não migra banco nem muda o pipeline de memória.
Extração explicitamente sem thinking; reflexão/compactação não foram alteradas.
Três regressões novas: solicitação estruturada/prioridade, timeout sem commit,
categorias e confiança preservadas. Grupo prontidão: 30/30; integridade: 9/9.

Probe físico sem gravar memória mental: dois pedidos ao 9B, GPU parcial,
`done/stop`, arrays válidos, 4,71 s e 7,62 s; unload confirmado. Artefato
`extracao-json-probe.json`. Workloads distintos da falha: não declarar ganho
de 300 s para 7 s como benchmark equivalente. A saída ainda incluiu entidades
desnecessárias como “bebida quente (implied)”; JSON válido não valida qualidade.

## Reteste de navegação pela entidade, não pelo Codex

- Cancelamento da tarefa antiga: `im-1791499977558-a36b5667`, turno
  `turn-59df8d59e9a9`; resposta confirmou cancelamento, sem ação externa.
- Novo pedido: `im-1791500038539-be16614d`, turno `turn-febdaa03bd81`.
- Resposta: `im-1791500061184-0ecf5233`, às 19:54:21.
- `browser_abrir` chegou ao YouTube; `browser_info`, recibo
  `tool-8989bc548d`, confirmou título YouTube e URL `https://www.youtube.com/`.
- Turno: 20.914 ms; extração pós-turno estruturada: 13.037 ms, sem timeout.
- Nenhum vídeo iniciado, nenhuma conta acessada e nenhuma quota de voz usada.

**Funcionamento não significa naturalidade aprovada.** O executor primeiro
inventou uma aba `default` e recebeu erro correto; fez três navegações
bem-sucedidas antes da leitura, desnecessárias para esse pedido. Não foram
efeitos incertos repetidos, mas redundância operacional merece correção após
consolidar a evidência. A fala final começou com “Tarefa concluída; fim da
execução” e copiou texto bruto da ferramenta: problema comportamental/UX
registrado, sem mudar a persona durante a conversa.

## GPU continua condicional: pressão com navegador real

Às 19:54:59, outro pedido do 9B (`llm-261967a513`, sem turn ID correlacionado)
voltou ao fallback CPU por `vram_pressure`. Métrica real: 5.199.683.584 bytes
usados; residência própria GPU 3.834.862.631; orçamento 5.905.580.032 + workspace
536.870.912; adicional previsto 2.607.588.313. Somando a margem 768 MiB,
a estimativa excedia o total 8.573.157.376 em aproximadamente 39,4 MB.

Logo, a correção não significa “GPU para sempre”. Esse fallback é coerente
com o orçamento conservador, embora tenha custo alto de reload/latência.
Não reduzir a margem, habilitar concorrência ou recalibrar agressivamente
com base só neste episódio. A ausência de turn ID nessa chamada interna e
o encerramento lento correspondente continuam riscos de rastreabilidade/latência.

### REAL-12 — Ciclo autônomo continuava novas etapas durante drenagem

Pedido de sono após o reteste YouTube: a entidade já estava `stopping`, mas
um tick iniciado antes disso continuou novas inferências após a primeira.
Exemplos: `llm-10cebc554b` às 19:59:49 e `llm-37c0db2902` às 20:00:47.
O ciclo só parou por `max_tool_steps` às 20:03:29, com unload confirmado.
Nenhum kill -9, nenhum processo terceiro encerrado. Isso não é sono rápido.

Causa: o timer recusava ticks novos, mas a continuação de um tick ativo não
combinava `_draining` com seu callback de cancelamento. Correção no mecanismo
atual: recusar inferência antes da seleção, depois de esperar a trava de modelo
e antes de recovery/retry; combinar sono ao cancelamento já usado pelo ciclo
e execução de etapas. Usa `TurnoCancelado` existente. Não interrompe a thread
de uma mutação já iniciada nem libera lease enquanto o HTTP ainda executa.

Quatro regressões novas: sono antes da seleção; sono durante espera da trava;
falha de conexão seguida de sono sem recovery/retry; ferramenta nova recusada
mesmo sem callback explícito do turno. Grupo prontidão passou **34/34**;
causalidade/simulações simultâneas são reexecutadas abaixo. O processo antigo
encerrou com o código que já estava carregado; a correção passa a valer no
próximo despertar. Não alegar reteste físico desse guard apenas pelos mocks.

## Arquivos desta rodada e limites da evidência

Correções de runtime: `app/alistair_runner.py`, `app/main.py`,
`app/core/conversation.py`, `app/core/task_state.py`, `app/core/resource_manager.py`,
`app/core/gpu_resource.py`, `app/core/ollama_lifecycle.py`,
`app/core/memory_maintenance.py`, `app/mind/scribe.py`, `app/core/dispatch.py`,
`app/tools/browser.py`. Seleção/configuração: comentário em `app/config.py`,
catálogo na central em `app/core/central_control.py`, perfil não secreto em
`entidades/hoshino/config/executores.json` e ambiente do launcher
`iniciar_hoshino.sh`. Alterações anteriores não relacionadas da árvore suja
foram preservadas; não houve commit geral ou staging indiscriminado.

Regressões acrescentadas aos grupos existentes: capacidade operacional,
tarefa operacional V28, prontidão R1–R7, causalidade, melhorias de execução,
executores leves, GPU cooperativo, lifecycle e refinamento da central.
Harnesses/probes e dados brutos ficam em `compartilhado/runtime/ensaios/20261008`,
fora do Git; não criam um backend ou banco mental paralelo.

Uma passagem da suíte durante carga de avaliação/importação retornou 73/74,
com timeout na fixture de causalidade; o grupo isolado passou 37/37 e a
passagem completa posterior passou 74/74. O prazo do teste não foi aumentado
para escondê-lo. Os logs das passagens são preservados. Suíte após JSON/browser
passou 74/74; a passagem final após REAL-12 é registrada quando concluída.

Pendências honestas: terceiro executor de Hoshino/Lilith ainda não aprovado;
Alistair 2B/3B ainda inativo; qualidade das conversas e naturalidade de tarefas;
redundância de navegação; calibração de orçamento/reloads sob navegador;
identificação dos ticks internos sem turn ID; sono físico com o novo guard.
YouTube play/pause/volumes, Spotify, Steam/demo, ventoinhas e o desafio de
arquivos **ainda não foram aprovados**. Upload verificado não equivale a arquivo
lido/produzido pela entidade. Nenhuma limpeza de memórias de testes foi feita.

## Validação final desta continuação

| Grupo executado | Resultado |
|---|---|
| Suíte oficial offline após REAL-12 | **74/74 grupos**, código de saída 0 |
| Prontidão / R1–R7 / guards de sono e extração | **34/34 testes** |
| Causalidade, incluindo duas simulações simultâneas | **37/37 testes** |
| GPU cooperativo | **30/30 testes** |
| Executores, oportunidade Alistair e instalação | **60/60 testes** |
| Ollama lifecycle / unload | **13/13 testes** |
| BrowserWorkerTests / contrato URL / caches | **11/11 métodos**, checks antigos preservados |
| Tarefa operacional V28 | **20/20 casos** |
| Integridade de memória | **9/9 testes** |

Nesta continuação foram acrescentadas **15 regressões** aos grupos existentes
(REAL-09: 4; REAL-10: 4; REAL-11: 3; REAL-12: 4); não são 15 grupos novos.
Log final: `compartilhado/runtime/ensaios/20261008/suite-final-sono.log`.
`git diff --check` dos arquivos corrigidos passou. Houve um ResourceWarning
de conexão SQLite não fechada numa execução isolada de integridade: testes
passaram, mas o aviso permanece dívida de fixture, não foi suprimido.

Ao final, Hoshino e Alistair dormindo com unload confirmado; Lilith não foi
acordada nesse ensaio. Nenhuma lease ativa; os três daemons dedicados não
reportaram modelos residentes. Processo da Hoshino e seus processos de
navegador também saíram. Central foi preservada. RAM disponível na amostra
final anterior: 23 GiB; swap 8 GiB total, 3,5 GiB usado. Uma amostra de vmstat
não valida pressão longitudinal. Disco cerca de 26 GiB livres, 97% ocupado.

**Parecer:** GPU comprovadamente funcional nas rotas testadas; navegação básica
real comprovada, mas primeiro teste integrado completo **não aprovado ainda**.
Terceiro modelo não será ativado abaixo do critério de qualidade solicitado.
Não houve nova capacidade, backend cloud, concorrência GPU habilitada,
provider real de voz consumido, migração cega ou exclusão de modelos/memórias.
