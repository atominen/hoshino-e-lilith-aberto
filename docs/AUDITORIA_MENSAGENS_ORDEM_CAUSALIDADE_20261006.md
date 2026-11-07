# Auditoria de múltiplas mensagens, ordem e causalidade

Data: 06/10/2026. Projeto: `/home/gustavo/hoshino e lilith`.

## 1. Conclusão

O projeto tem caixas postais persistentes, filas por conversa, locks de modelo/ação, revisões de conversa, recibos operacionais e cancelamento de áudio. **Não tem uma ordenação causal unificada entre essas peças.** Existem falhas reais na composição do fluxo, não somente recursos ausentes.

Os achados principais foram reproduzidos sem modelos, hardware ou serviços reais:

1. Na rota normal da central, A começa a gerar; B e C chegam; A pode ser publicada; B é retirada da fila e seu turno é descartado; C é processada com B no contexto. B permanece não lida e presa em `_interentity_inflight`.
2. Uma correção reconhecida descarta a resposta textual anterior, mas não finaliza o processamento da mensagem original na caixa postal. Um timeout de LLM tem o mesmo problema de mensagem presa.
3. `não, direita` e `PARA` **não** são reconhecidos por `parece_correcao`. `pare` e `espera, direita` são. O cancelamento de tarefa reconhece `PARA`, mas só quando seu turno chega ao worker; é outro mecanismo.
4. Uma ação aguardando `trava_acao` pode começar **depois** de a condição de cancelamento ter ficado verdadeira. Não há uma segunda checagem imediatamente após obter esse lock.
5. Timeout de RPC Minecraft mutável vira `error`, sem `outcome_uncertain`. Uma nova invocação idêntica é aceita pelo diário, embora a primeira possa continuar no servidor.
6. Dois envios iguais do usuário, sem chave de idempotência, viram duas mensagens independentes. A proteção de respostas/notificações não cobre o envio da UI.
7. Eventos Minecraft ficam em estado/log da ponte; não são automaticamente encaminhados como mensagens ordenadas ao LLM. Não há reconstrução causal automática entre dano, fala, recado e resultado de ferramenta.

**Nada foi implementado.** Somente este relatório foi acrescentado. Nenhum código, teste, modelo, banco real, configuração cloud ou scheduler foi alterado. Não foram reiniciadas entidades.

## 2. Método e limites da evidência

Foi seguido o caminho de consumidores em `app/main.py`, central HTTP/UI, caixa postal, Alistair, canais Discord, captura/transcrição, serviço de áudio, ponte Minecraft, dispatcher, tarefas, histórico, jobs e Resource Manager.

As evidências abaixo são separadas em:

- **Código:** fluxo e contratos efetivamente chamados, com referências ao final.
- **Probe isolado:** execução dos métodos reais de fila/turno/barramento com transporte, LLM, efeitos externos e interface substituídos explicitamente. Bancos e arquivos somente temporários, sob as guardas de `testes/executar_isolado.py`. Nenhuma simulação foi apresentada como ação real executada.
- **Teste existente:** oito grupos offline executados, todos com saída 0.

Não foi validada uma sessão real Minecraft 1.16.5, microfone, Discord, Azure, GPU, PC2 ou uso prolongado nesta auditoria. O comportamento do modelo ao interpretar linguagem natural não é garantido pelos probes. A descrição de correção e dependência refere-se ao controlador, não a uma suposição sobre o LLM.

## 3. Estrutura comum encontrada

### 3.1 Conversas de Hoshino e Lilith

As duas usam `InterfaceHoshino`, com configuração e dados próprios da entidade. O executor 7B/9B não é o dono da fila, memória ou identidade.

O caminho real é:

`receber_de_pessoa → persistir histórico bruto → anexar user ao histórico em RAM → enfileirar → worker da chave → snapshot → responder → LLM/ferramentas → publicar`.

A chave de conversa é a tupla **`(canal, destino ou "local", pessoa.id ou "")`**, não apenas o canal. Não existe um UUID de conversa propagado por toda a cadeia.

- `_fila_chaves[chave]`: deque FIFO e um worker por chave.
- `_fila_conversa`: deque agregado de pendências, usado para controle/observação; **não** é um executor global linear de todas as entradas.
- `_travas_conversa[chave]`: serializa o turno do mesmo fio.
- `trava_modelo`: serializa as chamadas HTTP do modelo no fluxo normal de uma mesma instância.
- `trava_acao`: serializa ferramentas mutáveis dentro da instância; consultas autorizadas como somente leitura podem correr em paralelo.
- Hoshino e Lilith possuem locks de ação/modelo de processos distintos. O Resource Manager compartilha a arbitragem de recursos, não transforma esses locks em uma fila global de intenções.

`ConversationState` tem fila, revisão e métodos próprios, mas a busca de consumidores mostrou que essa classe é utilizada pelo teste `test_conversa_continua`, **não** pelo caminho operacional de `app/main.py`. Seu comportamento não pode ser usado como prova do comportamento da central.

### 3.2 Persistência não é execução

Há registros distintos: caixa postal `interentidades.sqlite3`, histórico bruto por entidade, tarefa persistente por entidade, diário compartilhado de jobs/recibos, arquivos de canais e logs. Não existe uma transação única envolvendo entrada, execução externa, resposta, leitura e aprendizado.

Em `publicar`, a resposta local é guardada na caixa postal e a entrada é marcada lida **antes** de salvar episódio e executar o escriba. “Lida” não prova que a UI exibiu a resposta, que o áudio foi ouvido ou que todo o aprendizado terminou.

## 4. Mapa das fontes

As referências S1–S15 apontam para os consumidores e contratos reais, listados na seção 13. “F/M/A” nesta seção significa lock de fio/modelo/ação da instância, respectivamente; não um lock único entre entidades.

### 4.1 Identificação, tempo e destino

| Fonte | Entrada efetiva | Identificador e timestamp | Entidade / conversa / canal |
|---|---|---|---|
| Texto da central | `central.html` submit → POST `/api/send` → `interentity.send` → `ler_interentidades` → `receber_de_pessoa` (S1/S2/S3) | `im-epoch_ms-uuid8`; `created_at` UTC com microssegundos. O histórico cria outro `msg-uuid`; não mantém automaticamente o `im-*` como correlação. A UI não fornece ID estável de submissão. | Destinatário selecionado; sender `usuario`; canal `localhub`; destino `usuario`; pessoa identificada para esse remetente. |
| Microfone da central | WAV → POST `/api/audio/transcribe` → `AudioService` → rascunho revisável → envio explícito `/api/send` (S1/S2/S8) | Job `audio-uuid20`, request UUID do worker, `created_at/updated_at` epoch do job; depois `im-*`. Origem e `audio_job_id` ficam no metadata da caixa postal. | Entidade escolhida na gravação; depois mesmo fio `localhub` do texto. O reader não encaminha o metadata como modalidade de fala: `receber_de_pessoa` recebe os defaults `texto` e speaker vazio. |
| Microfone local PTT | `GlobalPTT` → transcritor → callback `_resultado_ptt` → `receber_de_pessoa` (S4) | Resultado com texto/duração; sem ID de mensagem e sem timestamp de captura no resultado PTT. Ganha `msg-*` ao entrar no histórico. | Processo da entidade; canal `voz`; destino local; pessoa não passada explicitamente; speaker normalmente vazio nesta rota. |
| Microfone contínuo local | captura/VAD → grupo de fala → ASR/diarização → `Transcritor.fila` → `ler_microfone` (S4) | Trecho tem `origem`, `quando=datetime.now()` ao produzir transcrição, duração e `speaker_id`; sem ID estável. `ler_microfone` encaminha texto/speaker, não o timestamp/origem completos. | Canal `voz`, modalidade fala. Speaker é rótulo de diarização, não autenticação ou identificação da pessoa. |
| Hoshino → Lilith / Lilith → Hoshino | ferramentas de entidades ou resposta → `interentity.send` → inbox da outra → `ler_interentidades` (S3/S6) | `im-*`, UTC, sender/recipient; resposta automática pode ter `reply_to` e `hops`. | Canal `interentidades`; destino é o remetente; fios separados por remetente. |
| Alistair → Hoshino / Lilith, chat | `Alistair.call_tool` ou resposta de `run` → mesmo barramento (S6/S7) | Mesmos IDs/timestamps; ações do Alistair possuem identificadores duráveis derivados da entrada/rodada/índice. | Autoria `alistair`, destinatário explícito, canal `interentidades` na entidade receptora. |
| Avisos de standby Alistair | `standby` observa jobs → envia notification para `usuario` (S7) | `im-*`, `dedupe_key` por job/status; metadata `job_id`, `entity_context` ou `pending_message`. | Na implementação atual esses avisos mecânicos vão ao **usuário**, não ao LLM da entidade que faz a imagem. |
| Eventos espontâneos Minecraft | callbacks `health`, `death`, `chat`, etc. na ponte (S9) | Log com UTC, PID, `seq` crescente do processo e `sessionId`; `lastEvent` tem type/detail/at, mas não uma fila de todos os eventos. | Bot/sessão da ponte. Não há `conversation_id` nem encaminhamento automático ao fio de texto/voz. |
| Resultado de ação/consulta Minecraft | ferramenta → `_rpc` HTTP → bridge `dispatch` → retorno → dispatcher → ciclo (S5/S9/S10) | RPC `mc-epoch_ms` (sem UUID, pode colidir no mesmo milissegundo), eco no HTTP; recibo mutável `tool-uuid10`; operação de tarefa pode ter `operation_id`. O adaptador não verifica igualdade do ID retornado e devolve só `resultado`/texto. | Fio que chamou a ferramenta; request não leva a chave da conversa nem parent de entrada até a ponte. |
| Outros resultados de ferramentas | `_executar_chamadas_da_etapa` → `dispatch.executar_resultado` → `role=tool` (S5/S10) | Recibo para mutáveis, IDs de tarefa/operação quando aplicáveis, request de diagnóstico. O dicionário de retorno não tem um ID causal universal de recibo. | Pertencem ao turno/fio; `_saidas_por_conversa` guarda três saídas recentes em forma de nome/texto. |
| Resultados de jobs | job de imagem/áudio no `job_bus`; comando longo em metadados de arquivo; `jobs_recem_terminados` no batimento (S7/S11) | `job_id`, entity, status, PID/process stamp, created/updated; arquivos de terminal têm ID e horários próprios. Parent de mensagem não é obrigatório para todos os jobs. | UI e consulta de estado; gatilhos internos de terminal; avisos Alistair por imagem; resultado só entra no fio quando consultado ou selecionado para iniciativa. |
| Discord textual existente | `on_message` → `channels.publicar_entrada` → arquivos → `ler_canais` (S12) | `in-epoch_ms-uuid6`, timestamp local em segundos, autor/autor_id/destino. O ID original da mensagem Discord **não** é transportado. O reader não encaminha o ID do arquivo para a fila de conversa. | Canal `discord`, destino channel ID, pessoa por autor ID. Duas pessoas do mesmo canal constituem chaves distintas. |
| Eventos internos / áudio ambiente | sensores/world snapshot → situação/kernel; `escuta.coletar` → `percebido_recente`; lembretes e batimento (S13) | World events têm inteiro autoincremental/observed_at; log interno tem timestamp e tipo; áudio ambiente guarda origem/horário, sem ID universal. | Situação global da entidade ou contexto ambiental; não são todos turnos dirigidos. |

### 4.2 Fila, lock, persistência, prioridade e entrega ao LLM

| Fonte | Fila e locks | Persistência e prioridade | Momento de entrega ao LLM |
|---|---|---|---|
| Texto central | Inbox SQLite → deques por chave → F/M/A; transações SQLite serializam escritas, mas inbox não faz claim exclusivo. | Mensagem durável até lida; deques/inflight/histórico de trabalho voláteis. Sem prioridade por mensagem; resposta usa compute P1. | Poll local a cada 1 s, debounce, turno do fio, disponibilidade do modelo. Pode sofrer descarte descrito abaixo. |
| Mic central | `WorkQueue(maxsize=4)` ASR critical/TTS normal, lock de serviço/worker e lease CPU de áudio; após envio, mesma fila do texto central. | Job persistente; fila/Events de cancelamento em RAM; WAV temporário. ASR pode ultrapassar TTS pendente; não interrompe automaticamente o job ativo. | Transcrição **não** dispara conversa: requer enviar o rascunho. Depois segue a fila `localhub`. |
| PTT / contínuo local | Buffers de captura; `queue.Queue`; diarização tem fila de trabalho de tamanho 3; depois deque `voz` e F/M/A. | Áudio/trechos pendentes não têm replay durável. Fila de diarização cheia descarta a janela mais antiga. Histórico bruto após entrada é persistente. | PTT ao callback; contínuo no batimento (default 8 s), mais janela/ASR/debounce/espera do modelo. Sem via urgente garantida. |
| H/L e chat Alistair recebido por H/L | Mesma inbox SQLite/deque por remetente; F/M/A; `_interentity_inflight` local. | Durável, leitura depois de publicar; sem prioridade de mensagem. Compute da resposta P1. | Poll de 1 s e lote unitário. Notifications e mensagens com hops ≥ 6 são marcadas lidas e não chegam ao LLM por esse reader. |
| Mensagens recebidas por Alistair | `run` lê até 10, processa sequencialmente com `await to_thread(chat)`; heartbeat separado. | Turnos cacheados por `source_id` e ações duráveis no banco próprio; backoff local de 60 s por falha. CPU fallback/GPU oportunista P5; não há debounce textual. | Uma a uma no loop, com até quatro pares anteriores do mesmo sender. Falha de uma pode ser ultrapassada por outras durante seu backoff. |
| Avisos standby | Consulta jobs + caixa postal `usuario`; não entram na fila de H/L. | Persistência/dedup por notification key. Sem LLM para produzir o aviso. | Exibidos pela central; não entregues automaticamente ao LLM de H/L. |
| Eventos Minecraft | Callbacks Node e `lastEvent`; log append síncrono; **sem fila de ingestão cognitiva**. | Log durável; estado vivo e último evento em RAM. Sem prioridade de dano/urgência na conversa. | Somente estado solicitado por ferramenta e resultados correlatos; dano/chat não são entregues automaticamente como mensagens. |
| Resultados Minecraft / ferramentas | Retorno aguardado no turno; A para mutáveis, consultas paralelas via gather que devolve na ordem de submissão. | Recibos mutáveis em job bus e estado de tarefa quando o retorno chega ao controlador; saídas curtas do fio em RAM. | `role=tool` no próximo passo do próprio ciclo. Não se injeta em inferência que já está sendo calculada. |
| Jobs | Backend de trabalho próprio; diário de estados; consultas/polling; terminal via batimento. | Estados persistentes; consulta por `updated_at DESC`, não ordem causal de mensagens. Cancelamento depende do backend. | Consulta explícita por ferramenta, contexto factual selecionado ou iniciativa; não há fusão universal com texto/voz. |
| Discord | Arquivos entrada/saída ordenados pelo nome, depois deques F/M/A. | Arquivo de entrada é removido **antes** de o turno terminar; saída só removida após envio Discord. Sem prioridade/dedup do Discord message ID. | No batimento, resolução de anexos, debounce/lote unitário e espera do modelo. |
| Internos / ambiente | Situação, kernel por saliência; áudio ambiente deque de 12 na interface e janela de 400 na escuta; turno autônomo usa `trava`, M/A. | Agenda/tarefas/estado/fatos/log persistem conforme componente; filas perceptivas em RAM. Compute autônomo P2, reflexão/batch P5. | Contexto seguinte ou deliberação selecionada; ambiente é contexto, não pergunta. `_bloco_percebido` consome todos os itens ao montar o próximo contexto, não segundo um parent causal. |

Os intervalos citados são os defaults do código. Não foram encontrados overrides desses parâmetros nos diretórios de configuração H/L consultados; o ambiente de um processo pode alterá-los. Não foi presumida a cadência exata de uma sessão real.

## 5. Cenário A → B → C durante geração

### Rota normal da central, reproduzida

1. A é persistida, importada, adicionada ao histórico e retirada da deque para seu turno. O snapshot enviado ao modelo contém A.
2. B e C chegam enquanto esse modelo ainda responde. Ficam persistidas na caixa postal, em `_interentity_inflight`, na deque da mesma chave e no histórico em RAM, nessa ordem de importação.
3. Se não forem correções reconhecidas, não incrementam a revisão. A geração HTTP de A não é abortada nem recebe B/C retroativamente.
4. Se A devolver apenas resposta textual, o checkpoint pós-LLM verifica **revisão**, não qualquer pendência do fio. A pode ser publicada mesmo com B/C esperando.
5. O worker tira B, captura histórico contendo A/B/C e chama `responder`. O ciclo normal vê C ainda na fila e levanta `TurnoCancelado` antes da inferência de B.
6. B já foi retirada, não é devolvida, não é marcada lida e continua no set inflight. O poll seguinte a ignora.
7. O worker tira C. Agora não há pendência. O LLM vê também B no histórico, mas a resposta é correlacionada somente a C.

O probe registrou duas inferências (`[A]` e `[A,B,C]`), duas respostas (para A e C), B não lida, inflight=1 e **zero novas inferências após repoll**. A tabela registra apenas users: no fluxo real o histórico também insere a resposta de A antes de B/C.

### Respostas diretas às perguntas

| Pergunta | Resultado |
|---|---|
| B/C ficam armazenadas? | Sim na central/barramento, além das filas em RAM. Armazenamento não garante processamento separado ou conclusão. |
| Em qual ordem? | Inbox por `created_at,id`; deque por ordem de importação. B precedeu C no probe. Exibição é por rowid; não há sequência global única. |
| Podem ser perdidas? | Texto central não é apagado nesse descarte, mas seu **turno fica perdido/preso** até reiniciar ou intervir. TUI/voz não têm caixa postal durável. Discord é removido do spool antes do turno. Exceção fora do try interno de `responder` pode remover a deque restante no finally do worker e deixar itens agregados órfãos. |
| Inferência paralela? | Não no fluxo normal do mesmo fio/instância: worker+M serializam. Fios/processos diferentes avançam independentemente; compute depende do RM. Cancelar task que aguarda `to_thread` não encerra a thread HTTP, portanto não é uma garantia absoluta para resets/cancelamentos fortes. |
| Mesmo contexto? | Não entram na inferência de A já iniciada. Entram juntas no snapshot de turnos seguintes, mesmo quando o lote tem uma só mensagem. |
| Só entram após resposta de A? | No snapshot seguinte, normalmente sim. Mas A pode ser descartada sem publicar; e mensagens já recebidas **antes** de capturar seu snapshot aparecem nele mesmo se ainda pertencem a lotes futuros. |
| A resposta atual é cancelada? | Correção reconhecida no mesmo fio: invalidação lógica em checkpoints. Mensagem comum: pode impedir próximo passo operacional, mas não necessariamente a resposta textual atual. Não aborta HTTP iniciado. |
| Áudio pendente é cancelado? | Submit da UI para áudio/reprodução desta aba; streaming invalidado por revisão/checkpoint; não existe cancelamento único de todos os áudios/LLMs/ações. Voz local legada não é parada automaticamente pelo simples recebimento de toda nova mensagem. |
| A pode sair após ser corrigida? | Sim se o marcador não for reconhecido (`não, direita`) ou a correção vier por outro fio (`voz` versus `localhub`). Correção reconhecida no mesmo fio foi barrada antes de publicar no probe. Áudio já reproduzido/efeito executado não pode ser desfeito por descartar a resposta. |
| B/C fora de ordem? | A deque preserva ordem, mas B pode não ter turno processado; snapshot de B já contém C. Entre fios, autores, canais e resultados não há ordem global. |

Com A/B/C já acumuladas **antes** de começar, o probe da rota normal descartou A e B nos checkpoints de fila e gerou só para C, usando A/B/C como contexto. Isso **não** é coalescing semântico explícito: A/B ficaram não lidas. Caminhos de resposta imediata de segurança, anteriores ao ciclo LLM, podem publicar sem passar pelo mesmo checkpoint; o descarte não é uma regra uniforme para toda entrada.

## 6. Ordem temporal, semântica e agrupamento

### 6.1 Os casos solicitados

| Caso | O que existe hoje | O que não está garantido |
|---|---|---|
| A: esquerda → `não, direita` | Histórico contém os dois textos; LLM pode interpretá-los. Há revisão para alguns outros marcadores e atualização heurística de descrição de tarefa compatível. | Esse marcador exato não incrementa revisão. Não existe uma relação persistente `supersedes=A` nem substituição segura universal de intenção anterior. Uma nova mensagem comum pode parar um próximo passo, mas isso não prova que a intenção foi substituída corretamente. |
| B: madeira → `depois faça uma bancada` | `task_state` reconhece `depois`, decompõe etapas e pode acrescentar à mesma tarefa/reabrir recente; operações pendentes são sequenciadas e resultado incerto/pending impede dependentes. | É condicionado à tarefa reconhecida e ao mesmo fio. Não há `depends_on` entre IDs dessas mensagens. Se A for descartada antes da execução, B pode existir com madeira não adquirida; o controlador não prova inventário por causalidade textual. |
| C: caverna → `leva comida também` | TUI/voz podem agrupar; histórico e instrução de continuidade permitem contexto; task state reconhece `também` **no início** de alguns comandos. | `leva comida também` não casa com esse marcador inicial. Não há classificação determinística de complemento nem fusão de parâmetros. Pode ser interpretação do LLM ou tarefa separada, não contrato demonstrado. |
| D: andar → `PARA` | Cancelamento lógico de tarefa reconhece `para`; ponte tem ação `stop` para pathfinder; há checkpoints de turno/ferramenta. | `parece_correcao('PARA')` é falso. Não há despacho imediato, bypass seguro de navegação ativa, prioridade textual urgente ou prazo curto garantido. Cancelar tarefa não envia automaticamente `minecraft_parar`. |
| E: mic + dano + recado + texto | Origens têm identificadores locais e rotas distintas. Autor/remetente textual fica nos registros. Locks e prioridades protegem parcialmente os recursos. | Não há ordem causal comum. Dano não entra automaticamente; recado tem fio próprio; mic local e texto central têm fios distintos. Metadados completos não chegam a todas as representações para o LLM. |

`task_state.iniciar_ou_continuar` pode continuar, atualizar etapa compatível, pausar tarefa diferente e cancelar tarefa. Isso constitui **organização semântica parcial de tarefas**, não uma organização semântica completa de todas as mensagens. Não é correto dizer que o projeto é somente FIFO; também não é correto atribuir-lhe substituição/dependência geral já implementada.

### 6.2 Janela real

Default: `DEBOUNCE_CONVERSA_MS=900`, `MAX_MENSAGENS_LOTE=8`.

O worker anota o tamanho da deque, dorme 900 ms e repete se o tamanho mudou. Portanto é uma verificação periódica por tamanho, **não** um timer com deadline exato de 900 ms contado da última mensagem. Não tem limite global de espera sob fluxo contínuo.

- TUI e `voz`: até oito mensagens da mesma chave formam um lote, textos unidos com newline; as mensagens continuam separadas no histórico.
- Central (`localhub`), Discord e interentidades: lote de **uma** mensagem, mesmo após debounce.
- Não agrupa autores diferentes, destino diferente ou texto central com mic local.
- Browser mic enviado como rascunho usa o mesmo fio de texto central, mas continua em lote unitário.
- ASR contínuo faz agrupamento anterior à conversa: janela default 8 s ou flush após 1,2 s de silêncio, sujeito a VAD/processamento. Isso não é batching de mensagens já persistidas.
- Não há edição de mensagem já enfileirada por ID, ingestão de `on_message_edit` Discord, supersession por parent ou vínculo semântico explícito entre lotes.

No exemplo 0/350/700 ms, tomando tempos de **entrada na deque TUI/voz**, o worker iniciado em t≈0 detecta mudança em t≈900 e pode iniciar o lote em t≈1800, juntando os três trechos. Não precisam ser três turnos. Na central o poll e o lote unitário mudam o resultado; pode ocorrer descarte de turnos em vez de agrupamento correto. Não se deve prometer três respostas independentes nem um único turno semanticamente consolidado nessa rota.

## 7. Cinco cancelamentos distintos

| Mecanismo | Implementação atual | Limitação |
|---|---|---|
| Áudio | UI `speechSerial`/`stopSpeech`, cancel de job áudio, Events/removal de pendentes, invalidação `llm_speech`, worker com request ID, `voice.parar` local. | Cancela áudio pertencente ao mecanismo/aba/processo. Não cancela automaticamente todas as inferências/intencões; áudio já ouvido não é revertido. Um novo submit cancela reprodução mesmo se o envio posteriormente falhar. |
| LLM | Revisão passada a GPU lease e checkpoints; `TurnoCancelado`; cancelamento de asyncio task em limpeza/reset. | Lease pode ser cancelado enquanto espera. `_post_ollama_stream` não testa cancelamento dentro de `iter_lines`; geração HTTP iniciada continua até finalizar/falhar/timeout. `task.cancel` não mata a thread de `to_thread`. |
| Ação | Checkpoints antes de lote/execução; A serializa mutáveis; correção/qualquer pendência do mesmo fio pode impedir continuação. | Não reverte efeito em curso. Checagem ocorre **antes de aguardar A**, não depois de obter A: probe executou o handler simulado após flag true. |
| Job | Áudio pendente removível; áudio ativo cooperativo/worker próprio encerrável; terminal possui validação de posse para encerrar; imagem/backend tem política própria. | Não é um cancel genérico por nova mensagem. Matar processo não prova nem desfaz efeito; imagem não pode ser suposta pausável. |
| Invalidação lógica | `_revisoes_conversa` por fio, checks pós-LLM/antes de publicar, stream invalidated, revisão de memória para extração após reset; task state pode cancelar/pausar. | Não é um parent/sequence universal para texto, ações, jobs e memória. Descartar turno de caixa postal não resolve automaticamente sua leitura/inflight. |

**Resultados executados antes de cancelar:** numa etapa com várias ferramentas, o executor acumula resultados e os devolve ao controlador só ao final. Se uma ferramenta terminar e nova entrada acionar o checkpoint antes da ferramenta seguinte, pode levantar `TurnoCancelado` sem devolver os resultados já acumulados. O recibo mutável do dispatcher permanece durável, mas a atualização de task state e `_saidas_por_conversa` situada depois do retorno pode não ocorrer. Essa é evidência de código, não um ensaio com efeitos reais.

**Resultado atrasado Minecraft:** a ponte não cancela dispatch porque o cliente HTTP perdeu o prazo. O retorno tardio fica na própria chamada/log; não há caminho de reenfileiramento que o associe à correção posterior. O registro local de timeout como erro confirmado agrava essa lacuna.

## 8. Mensagens entre entidades e sono

H→L, L→H, Al→H e Al→L usam o mesmo `interentity.send`, preservando sender/recipient. O transporte é comum; o consumidor H/L e o consumidor Alistair **não são iguais**.

- Escritas simultâneas são transacionais (`BEGIN IMMEDIATE`) e têm IDs únicos. O teste existente confirmou persistência de 15 envios concorrentes; não prova ordem causal entre eles.
- Inbox ordena por `created_at,id`; histórico/UI ordena por rowid. O timestamp é calculado antes de adquirir a transação. Probe forçou a primeira solicitação a esperar e a segunda a gravar: inbox `[primeira,segunda]`, exibição `[segunda,primeira]`. Não há sequence explícito comum entre as duas ordens.
- Dois remetentes para H/L produzem workers/chaves diferentes. O modelo serializa no processo, mas respostas podem completar em ordem diferente da chegada, especialmente com ferramentas no meio.
- `delivered_at` é carimbo de consulta da caixa; não claim exclusivo. `read_at` confirma o leitor correto, mas H/L só o registra ao publicar (ou descartar notification/hops limite). Não existe ACK do cliente final.
- `_interentity_inflight` evita reimportar durante o mesmo processo, mas vira bloqueio permanente nos caminhos de turno cancelado/erro/vazio sem publicação. Vinte mensagens não lidas presas podem ocupar toda a página de inbox do reader H/L e impedir importar mensagens mais novas.
- Respostas têm dedup durável por `(parent_id,sender,recipient)` e `reply_to`. Isso permite **uma** resposta por parent/par de participantes: dois textos legítimos enviados para o mesmo destinatário durante esse processamento também podem ser colapsados. Não é dedup por conteúdo nem por nova intenção humana.
- Loop automático é limitado a seis hops. O reader H/L marca a mensagem de limite lida sem entregar ao LLM; notification também é registrada no histórico e marcada lida, sem chegar ao contexto imediato.
- Alistair processa sequencialmente, cacheia resposta concluída por `source_id`, conserva recibos de ação, tenta mensagens falhas após 60 s e pode processar posteriores no intervalo. Não mistura os quatro pares de histórico de um sender com outro.
- Entidade dormindo: mensagem fica no banco; `wake=True` pode produzir pedido de despertar. A central só consome esse pedido quando confirma presença awake, não apenas por ter iniciado processo.
- Sono cooperativo H/L deixa de importar novas entradas e espera trabalhos já ativos. Mensagens novas permanecem para o próximo despertar. Pedidos antigos de wake anteriores a um sleep são filtrados; wake novo é preservado.
- Reinício: caixa postal não lida pode ser reimportada; deques/inflight/histórico de trabalho recomeçam vazios. Isso desbloqueia mensagens presas, **mas pode reprocessar pedido que já teve efeito**. Histórico bruto não é automaticamente restaurado inteiro como conversa; memória/episódios continuam disponíveis por recuperação seletiva. Alistair tem cache de turnos mais forte por source ID.

O projeto não tem semântica end-to-end de exactly-once. Tem persistência, dedup parcial e recibos; os limites entre estes precisam ser reconciliados.

## 9. Minecraft + conversa e prioridade

### 9.1 Não existe uma única linha de eventos

Há ao menos: inbox/deque `localhub`, deque `voz`, fio privado por remetente, spool Discord, ciclo de ferramentas de cada turno, jobs compartilhados, callbacks/log/estado Node e percepção interna. `world_state.KEYS` não inclui estado/dano Minecraft. Seus eventos inteiros e TTL não conectam o jogo automaticamente à conversa.

No caso pedido → confirmação Minecraft → correção → nova mensagem:

1. O pedido entra no histórico do fio; a ferramenta Minecraft é aguardada nesse ciclo.
2. Se a chamada responder, o ciclo recebe o resultado como `tool` e pode verificá-lo com `minecraft_estado`. O request ID RPC é logado, mas não é um elo obrigatório ao `im-*` de entrada.
3. Correção/nova mensagem entram na deque e histórico. Não modificam o payload já em inferência. Se forem reconhecidas no mesmo fio, invalidam continuação/publicação anterior; outro fio não invalida.
4. Se o ciclo for cancelado após efeito, o recibo pode estar no job bus, sem resultado anexado ao histórico do próximo turno. O histórico permanente de conversa guarda texto do usuário/assistente, **não toda a trajetória `assistant(tool_calls) → tool`** da lista de trabalho.
5. O LLM seguinte recebe o histórico de mensagens, memória recuperada, contexto de situação, saídas recentes do fio e tarefa se anexada. Não recebe automaticamente uma sequência normalizada `pedidoID → efeitoID → correçãoID → novaID`.
6. Eventos como dano, entre esses passos, podem apenas sobrescrever `lastEvent`. Log mantém a trilha para diagnóstico, mas o LLM não consome esse log como fila causal.

Logo, a ordem causal **não é reconstruída sistematicamente**. Pode ser inferida do texto, resultado ainda presente no ciclo ou consulta do estado atual; isso é diferente de uma garantia de causalidade.

### 9.2 Prioridade de recursos não é prioridade causal

Resource Manager usa P0 áudio, P1 resposta, P2 espontânea, P3 visão/interativo, P4 imagem, P5 batch. Seleção de pedidos GPU é por prioridade/tempo/token; não há parent/depends_on nessa seleção. O áudio usa sua WorkQueue com prioridade/envelhecimento/FIFO no empate. O kernel ordena candidatos por saliência.

**Proteções locais existentes:** mesmo fio serializado; operações de tarefa em ordem; consultas gather retornam na ordem de submissão; mutação com outcome incerto/pending impede operações dependentes; stream de voz mantém índices e rejeita desordem; worker de áudio valida request ID; world_state recusa observação mais velha substituindo nova da mesma origem/chave.

**Proteção ausente:** um requisito global de que uma entrada/efeito causal anterior seja visto antes de seu dependente em outro fio, fila ou origem. O RM não conhece essa relação. Portanto não foi demonstrado um bug de “prioridade invertendo o mesmo par de tarefa” no ensaio, mas **não existe proteção geral** contra a entrega/apresentação de efeito sem seu contexto causal. Um job concluído/recado prioritário pode ser observado antes do pedido original ser processado por seu destinatário.

## 10. IDs e deduplicação

| Objeto | IDs atuais | Parent / sequência / dedup real |
|---|---|---|
| Mensagem central/interentidades | `id=im-*`, sender, recipient, timestamps | `reply_to/hops` quando gerada em processamento; sem conversation UUID/sequence dedicado; rowid implícito é ordem de gravação, mas inbox não o utiliza como ordem. Dedup opcional por notification key e parent/par. |
| Submissão UI | Campos entity/text/wake, opcional áudio origem | Sem request ID/idempotency key reaproveitável no retry. Botão desabilitado reduz cliques, não fornece idempotência. Probe: dois envios iguais → dois IDs/duas entradas. |
| Histórico bruto | `msg-*`, `evt-*`, session_id, turn_id opcional | Input ignora retorno de `history.message`; IDs de transporte não são copiados por padrão. Output gera seu próprio `turn-*`; não constitui um parent universal de toda execução. |
| Item de deque | Chave tupla, texto, pessoa, canal, modalidade, speaker, mensagem_local | `mensagem_local` conserva objeto de transporte para localhub/interentidades; sem item ID/timestamp/sequence obrigatório no envelope comum. História para LLM usa role/content, não todos esses metadados. |
| Inferência | `llm-uuid10`; passo usa também `turn-uuid10` de diagnóstico | ID útil para logs; não liga obrigatoriamente origem, ferramenta, job e publicação. Executor fica fixo no ciclo por ContextVar do RM. |
| Tarefa / operação | Task `ct-*`, chave textual, step IDs e ordem, operation IDs | Sequência operacional própria; atualização/compatibilidade de etapa e assinaturas. Não é grafo de dependências entre todas as mensagens. |
| Ferramenta mutável | Recibo/job `tool-uuid10`, assinatura SHA-256 de nome/argumentos e entidade | Reserva atômica bloqueia assinatura enquanto running/interrupted não resolvido. Ação concluída/error pode ser invocada de novo. Não deduplica duas intenções oriundas de retry da UI. |
| Job compartilhado | ID, entity, kind, PID/process_stamp, created/updated, details | Details podem ter request/message/stream ID; não são obrigatórios universais. Estado terminal não reabre; isso não define ordem causal com texto. |
| Alistair | source ID cacheado; identificador de inferência por source/rodada; action ID source/rodada/índice | Recibo durável com digest; marcador incerto não é repetido; resposta cacheada e dedup parent/par protegem retorno após queda. Novo source ID de UI retry não é o mesmo turno. |
| Discord | Snowflake de autor/canal; ID novo de spool entrada/saída | Snowflake da mensagem original não passa; sem dedup de reentrega/edit. Entrega de saída parcial seguida de erro pode repetir trechos no próximo loop. |
| Minecraft RPC/evento | `mc-epoch_ms`, sessionId, seq de log por processo | ID não é idempotency key; bridge executa cada POST, sem cache/dedup; seq reseta com processo e não entra no histórico conversacional. Action.start/end usam ação/session, não o request ID em todos os registros. |
| Áudio | Job `audio-*`, worker UUID por request, stream `speech-*`, índices de chunks | ID de resposta do worker tem validação estrita; mismatch encerra worker para não contaminar próximo pedido. UI evita repetir chunk e usa serial para resultado tardio. Não equivale a dedup de envio textual. |
| World events | Inteiro autoincremental, fonte/chave/observed_at, cursor/gap | Ordem/cursor somente desse armazenamento; TTL/antirretrocesso de fatos. Não é sequência de mensagens/jogo/tool results combinados. |

## 11. Verificação executada

### 11.1 Grupos existentes, offline

| Grupo | Resultado desta rodada |
|---|---|
| `test_conversa_continua` | Exit 0; 9 chamadas de verificação efetivas passaram. O rodapé do próprio teste imprime 11; sua contagem textual é incorreta e não foi editada. Testa a classe ConversationState, não a fila de produção completa. |
| `test_turno_e2e` | 26 verificações, 0 falhas. |
| `test_central_entidades` | 17 testes, OK. |
| `test_audio_service` | 34 testes, OK. |
| `test_voz_streaming` | 17 testes, OK. |
| `test_minecraft` | 10 testes, OK. |
| `test_discord` | 18 verificações passaram. |
| `test_alistair_imagem` | 20 testes, OK. |

**8/8 grupos executados passaram.** A suíte completa de 65 grupos não foi reexecutada nesta rodada de auditoria sem alterações de código. Esses resultados não significam que os fluxos múltiplos estejam corretos: os probes abaixo expuseram lacunas que os testes atuais não cobrem.

### 11.2 Dez cenários/checagens adicionais, sem arquivos de teste novos

| Probe | Observação real do código sob simulação |
|---|---|
| Match de correção | `não, direita=false`; `PARA=false`; `pare=true`; `espera, direita=true`. |
| B/C durante inferência A | Inferências para A e C; B no contexto de C, não lida, inflight=1; repoll não inicia inferência nova. |
| A/B/C acumuladas | Uma inferência contendo A/B/C; só resposta correlacionada a C; A/B não lidas, inflight=2. |
| Correção não reconhecida | Resposta antiga publicada, depois resposta para `não, direita`; nenhuma invalidação por revisão. |
| Correção reconhecida | Resposta antiga descartada; original permanece não lida/inflight; só nova resposta publicada. |
| Timeout de LLM | Sem resposta; entrada não lida e inflight; repoll não tenta de novo. |
| Cancelamento aguardando action lock | Flag tornou-se verdadeira antes de liberar lock; handler simulado foi chamado depois disso. Nenhuma ação externa foi feita. |
| Reenvio textual sem chave | Dois IDs e duas entradas independentes para `vá para casa`. |
| Timestamp versus gravação concorrente | Inbox `[primeira,segunda]`; histórico exibido `[segunda,primeira]`; zero erros de escrita. |
| Timeout Minecraft mutável | Duas invocações idênticas do dispatcher → duas tentativas HTTP mockadas; ambos contratos/recibos `error`, ambos `outcome_uncertain=false`; zero ações reais. Não prova retry automático, prova que uma nova chamada não é barrada como efeito incerto. |

## 12. Tabela de capacidades e riscos

### 12.1 Estado atual

“Parcial” significa que há mecanismo utilizável, mas ele não entrega a garantia completa pedida. Não significa apenas que o nome de uma função sugere suporte.

| CAPACIDADE | EXISTE | PARCIAL | NÃO EXISTE | COMO FUNCIONA |
|---|:---:|:---:|:---:|---|
| FIFO por conversa, de ponta a ponta | — | ✓ | — | Deque FIFO/worker por chave; descarte de turnos, snapshots mais amplos e inbox/UI com ordens distintas quebram a garantia completa. |
| Mensagens durante geração | — | ✓ | — | Armazenadas; não entram no HTTP atual; B pode ficar presa enquanto C inclui seu texto. |
| Mensagens simultâneas | — | ✓ | — | Escrita transacional e workers independentes; sem ordem global nem processamento garantido de cada item. |
| Agrupamento de mensagens próximas | — | ✓ | — | Debounce por tamanho; lote ≤8 TUI/voz, lote 1 central/Discord/entidades; sem fusão semântica universal. |
| Supersession/correção | — | ✓ | — | Alguns marcadores incrementam revisão e task state atualiza/pausa; sem vínculo supersedes e com lacunas de marcador/ack/lock. |
| Interrupção urgente garantida | — | — | ✓ | Checkpoints e stop existem, mas `PARA` não tem via imediata/prioritária até ação em curso. |
| Dependências causais | — | ✓ | — | Etapas de tarefa, parent de resposta, pares tool e índices de voz; sem causalidade entre todas as fontes. |
| Prioridade | — | ✓ | — | RM, áudio e saliência; não prioridade causal universal de mensagens. |
| Deduplicação | — | ✓ | — | Resposta/notification/ação incerta/Al cache; não submissão UI, Discord ou RPC Minecraft. |
| Autoria/origem completas até o LLM | — | ✓ | — | Sender/autor persistidos; envelope perde IDs/origem/modalidade em rotas e usa role/content no histórico. |
| Mensagens entre entidades | — | ✓ | — | Transporte persistente, destinatário, wake e limites; consumidor H/L pode prender mensagem; Al é mais robusto por source ID. |
| Texto + voz | — | ✓ | — | Browser draft integra-se ao texto central; mic local em fio separado; sem timeline causal comum; modalidade browser não propagada. |
| Minecraft + conversa | — | ✓ | — | Ferramentas/estado entram no turno; eventos espontâneos não chegam automaticamente em ordem ao LLM. |
| Resultados atrasados | — | ✓ | — | Worker áudio/stream têm ID e invalidação; texto/ferramentas/jobs não têm barreira universal; timeout MC não conserva incerteza. |
| Entidade dormindo | ✓ | — | — | Caixa postal persiste, wake opcional e confirmação de presença; sem promessa de qualidade/perfeição do processamento ao acordar. |
| Recuperação após restart | — | ✓ | — | Unread e tarefas/recibos persistem; deques/histórico de trabalho não; reimportação pode repetir intenção de efeito já executado. |

### 12.2 Classificação

**CRÍTICO — integridade operacional**

- **C1:** cancelamento válido durante espera de `trava_acao` não impede início posterior da mutação. Probe reproduziu a janela com handler sem efeito. Pode atingir outras ferramentas mutáveis além do Minecraft, inclusive escrita.
- **C2:** timeout após enviar comando Minecraft é tratado como erro conhecido, não resultado incerto. Backend pode continuar; nova invocação idêntica é aceita. Não foi encontrado retry automático em `_rpc`, mas a proteção durável contra repetição de efeito incerto não se aplica nesse caminho.

**ALTO**

- **A1:** turnos centrais/privados descartados, falhos ou vazios deixam entrada unread+inflight. Podem bloquear a página de 20 itens e perder processamento de novas mensagens.
- **A2:** pendência comum é usada como interrupção indiscriminada da sequência operacional. Dependência/complemento podem perder turno em vez de serem tratados corretamente.
- **A3:** correção natural não reconhecida ou feita no outro canal não invalida A; `PARA` não tem deadline/bypass até navegação em curso. Não é garantido parar antes de outro efeito.
- **A4:** retry de UI/Discord/RPC não tem identidade end-to-end. Sucesso anterior não é bloqueado como duplicate pela assinatura de ação, logo nova intenção duplicada pode produzir outro efeito.
- **A5:** cancelamento entre ferramentas pode esconder do task state resultados já executados, embora seu recibo ainda exista no job bus; reinício de pedido unread pode encontrar uma visão incompleta.
- **A6:** spool Discord consumido antes de processamento não fornece recuperação confiável do turno após crash/cancelamento; entrega parcial pode repetir trechos de saída.

**MÉDIO**

- **M1:** snapshot inclui pendências fora do lote; objetivo/entrada do turno pode discordar do último user visto pelo modelo.
- **M2:** inbox e UI usam ordens diferentes; timestamps de origens/processos e seq locais não são sequência causal global.
- **M3:** ausência de ingestão automática de eventos do jogo e vínculo causal comum; dano pode não ser considerado até consulta. Importante para o teste real, mas não houve perda real de HP medida nesta auditoria.
- **M4:** metadados de browser ASR persistem, mas modalidade/origem não seguem até contexto LLM; speaker local não identifica necessariamente autor.
- **M5:** cancelar playback não invalida toda resposta/stream antiga ainda produzida; nova fala local não faz barge-in universal. Mensagem velha ainda não falada pode ser selecionada pela UI conforme os filtros existentes.
- **M6:** fluxo contínuo pode adiar debounce indefinidamente; diarização cheia descarta janela mais antiga; áudio ambiente limitado é consumido pelo próximo contexto, não pelo fio causal apropriado.
- **M7:** leitura, resposta e aprendizado não são atômicos. H/L não restauram automaticamente o histórico de trabalho lido ao reiniciar; recuperação seletiva de memória não equivale a replay causal.

**BAIXO**

- **B1:** teste ConversationState verde não valida o consumidor real de produção; seu rodapé também superconta as verificações (11 versus 9 chamadas).
- **B2:** request ID Minecraft apenas em milissegundos pode colidir; é problema de diagnóstico/correlação, não uma proteção de dedup que já estivesse funcionando.

## 13. Referências verificadas no código

As linhas identificam pontos de entrada; consultar o corpo das funções para todo o contrato. Os links se referem ao projeto atual desta auditoria.

- **S1 — UI:** [submit e cancelamento na central](</home/gustavo/hoshino e lilith/app/ui/central.html:166>), [serial/playback de voz](</home/gustavo/hoshino e lilith/app/ui/central.html:51>), [rascunho ASR](</home/gustavo/hoshino e lilith/app/ui/central.html:126>).
- **S2 — HTTP central:** [envio de mensagem](</home/gustavo/hoshino e lilith/iniciar_entidades.py:341>), [origem de áudio revisado](</home/gustavo/hoshino e lilith/iniciar_entidades.py:204>), [wake/supervisão](</home/gustavo/hoshino e lilith/iniciar_entidades.py:111>).
- **S3 — fila H/L:** [recebimento](</home/gustavo/hoshino e lilith/app/main.py:537>), [worker/lote/snapshot](</home/gustavo/hoshino e lilith/app/main.py:630>), [inbox reader](</home/gustavo/hoshino e lilith/app/main.py:1417>), [histórico inicial/fios](</home/gustavo/hoshino e lilith/app/main.py:503>).
- **S4 — microfone:** [callback PTT](</home/gustavo/hoshino e lilith/app/main.py:740>), [leitura contínua](</home/gustavo/hoshino e lilith/app/main.py:1445>), [fila limitada de diarização](</home/gustavo/hoshino e lilith/app/tools/transcricao.py:597>), [agrupamento contínuo](</home/gustavo/hoshino e lilith/app/tools/transcricao.py:871>), [resultado PTT](</home/gustavo/hoshino e lilith/app/tools/transcricao.py:809>).
- **S5 — execução/cancelamento:** [trava de modelo](</home/gustavo/hoshino e lilith/app/main.py:1721>), [HTTP stream](</home/gustavo/hoshino e lilith/app/main.py:1560>), [cancel antes do action lock](</home/gustavo/hoshino e lilith/app/main.py:1926>), [checkpoint entre ferramentas](</home/gustavo/hoshino e lilith/app/main.py:2006>), [pendência interrompe ciclo](</home/gustavo/hoshino e lilith/app/main.py:2729>), [checkpoint pós-LLM](</home/gustavo/hoshino e lilith/app/main.py:2957>), [publicação/leitura](</home/gustavo/hoshino e lilith/app/main.py:3423>).
- **S6 — caixa postal:** [schema](</home/gustavo/hoshino e lilith/app/core/interentity.py:54>), [send/dedup](</home/gustavo/hoshino e lilith/app/core/interentity.py:174>), [inbox e leitura](</home/gustavo/hoshino e lilith/app/core/interentity.py:229>), [histórico UI](</home/gustavo/hoshino e lilith/app/core/interentity.py:290>).
- **S7 — Alistair:** [recibo de ação](</home/gustavo/hoshino e lilith/app/alistair_runner.py:125>), [cache/histórico por sender](</home/gustavo/hoshino e lilith/app/alistair_runner.py:181>), [standby/dedup](</home/gustavo/hoshino e lilith/app/alistair_runner.py:246>), [consumo e retry](</home/gustavo/hoshino e lilith/app/alistair_runner.py:297>).
- **S8 — áudio:** [fila de áudio](</home/gustavo/hoshino e lilith/app/core/audio_service.py:169>), [submit e prioridade](</home/gustavo/hoshino e lilith/app/core/audio_service.py:319>), [validação request ID](</home/gustavo/hoshino e lilith/app/core/audio_service.py:120>), [consumo/invalidação de sentenças](</home/gustavo/hoshino e lilith/app/core/audio_service.py:286>), [SpeechStream](</home/gustavo/hoshino e lilith/app/core/speech_stream.py:12>), [fila com sequência local](</home/gustavo/hoshino e lilith/app/core/work_queue.py:15>), [voz legada/cancel](</home/gustavo/hoshino e lilith/app/tools/voice.py:231>).
- **S9 — Minecraft:** [RPC Python e timeout](</home/gustavo/hoshino e lilith/app/tools/minecraft.py:50>), [goto 60 s](</home/gustavo/hoshino e lilith/app/tools/minecraft.py:297>), [eventos/log](</home/gustavo/hoshino e lilith/compartilhado/servicos/minecraft/bridge.js:39>), [callbacks](</home/gustavo/hoshino e lilith/compartilhado/servicos/minecraft/bridge.js:186>), [goto/stop](</home/gustavo/hoshino e lilith/compartilhado/servicos/minecraft/bridge.js:261>), [cada POST executa dispatch](</home/gustavo/hoshino e lilith/compartilhado/servicos/minecraft/bridge.js:468>).
- **S10 — recibos/contratos:** [reserva antes do efeito](</home/gustavo/hoshino e lilith/app/core/dispatch.py:1754>), [classificação erro/incerto](</home/gustavo/hoshino e lilith/app/core/dispatch.py:1798>), [retorno estruturado](</home/gustavo/hoshino e lilith/app/core/dispatch.py:1862>), [reserva atômica por assinatura](</home/gustavo/hoshino e lilith/app/core/job_bus.py:118>), [registro de resultado no task state](</home/gustavo/hoshino e lilith/app/main.py:3159>).
- **S11 — jobs:** [diário e estados terminais](</home/gustavo/hoshino e lilith/app/core/job_bus.py:41>), [ordem de consulta](</home/gustavo/hoshino e lilith/app/core/job_bus.py:67>), [terminal recém-terminados](</home/gustavo/hoshino e lilith/app/tools/terminal.py:262>), [encerramento validando posse](</home/gustavo/hoshino e lilith/app/tools/terminal.py:282>).
- **S12 — Discord:** [entrada bot](</home/gustavo/hoshino e lilith/app/integracoes/discord_bot.py:144>), [spool e consumo](</home/gustavo/hoshino e lilith/app/social/channels.py:54>), [entrega de saída](</home/gustavo/hoshino e lilith/app/integracoes/discord_bot.py:171>), [reader principal](</home/gustavo/hoshino e lilith/app/main.py:1375>).
- **S13 — internos:** [batimento/fontes](</home/gustavo/hoshino e lilith/app/main.py:1022>), [contexto/consumo de percebido](</home/gustavo/hoshino e lilith/app/main.py:471>), [escuta por origem](</home/gustavo/hoshino e lilith/app/social/escuta.py:220>), [world keys/eventos](</home/gustavo/hoshino e lilith/app/core/world_state.py:21>), [saliência](</home/gustavo/hoshino e lilith/app/core/kernel.py:44>).
- **S14 — semântica:** [match correção](</home/gustavo/hoshino e lilith/app/core/conversation.py:17>), [continuação/cancelamento](</home/gustavo/hoshino e lilith/app/core/task_state.py:22>), [atualização/pausa da tarefa](</home/gustavo/hoshino e lilith/app/core/task_state.py:892>), [defaults debounce](</home/gustavo/hoshino e lilith/app/config.py:151>).
- **S15 — recursos/histórico:** [prioridades RM](</home/gustavo/hoshino e lilith/app/core/resource_manager.py:420>), [ordem de GPU](</home/gustavo/hoshino e lilith/app/core/resource_manager.py:658>), [executor fixo no ciclo](</home/gustavo/hoshino e lilith/app/core/resource_manager.py:139>), [IDs do histórico](</home/gustavo/hoshino e lilith/app/core/history.py:61>), [guardas offline](</home/gustavo/hoshino e lilith/testes/executar_isolado.py:18>).

## 14. Menor alteração futura proposta — não implementada

Não é necessário um novo message manager, scheduler, banco ou sistema mental. A base utilizável já existe: `receber_de_pessoa`, deques/worker por fio, `interentity`, `task_state`, `job_bus`, revisões e contratos.

**Menor primeira rodada:** corrigir a composição do consumidor atual, com testes do caminho `inbox → worker → responder → publicar` (não somente ConversationState):

1. Não usar “há qualquer item seguinte no fio” como descarte indiscriminado de um turno. Preservar mensagens comuns/dependentes/complementares; reservar supersession para correção reconhecida. Pausar uma tarefa e consumir uma nova mensagem são decisões distintas.
2. Dar destino explícito a cada mensagem retirada: respondida, supersedida intencionalmente, falha recuperável ou efeito incerto. Reconciliar inflight/ACK em todos os caminhos, usando metadados e recibos **existentes**. Não marcar como sucesso nem reenfileirar automaticamente uma mutação de resultado incerto. Só limpar inflight e tentar tudo de novo seria inseguro.
3. Snapshot deve corresponder ao lote realmente selecionado, com watermark/IDs dos itens existentes; não incluir C como última entrada no turno nominal de B. Manter origem/modalidade/transporte no envelope atual e na correlação de histórico.
4. Rechecar cancelamento após adquirir action lock e antes de iniciar efeito. Conservar/registrar resultados de efeitos anteriores mesmo que o próximo checkpoint interrompa a etapa.
5. Preservar outcome incerto no contrato atual para timeout pós-envio de Minecraft, associando-o ao recibo existente; consultar estado antes de permitir nova mutação equivalente.

Essa rodada resolve as falhas centrais demonstradas sem prometer causalidade global completa.

**Passos seguintes, ainda mínimos e no escopo:** fazer `/api/send` aceitar uma chave de submissão estável reutilizando a deduplicação durável já existente (validando mesmo conteúdo/entidade em reutilização); propagar IDs de origem aos resultados/jobs atuais; aproximar a ordem de inbox e histórico; ajustar marcadores conservadores (`não, direita`, `PARA`) e encaminhar a interrupção segura pelo controle Minecraft já existente. A integração de eventos do jogo deve aproveitar eventos/estado/filas existentes, com sequência local e parent quando disponível, sem criar uma segunda infraestrutura.

Não há ajuste isolado de debounce ou prioridade que resolva tudo. O primeiro conserto deve ser **não perder turnos nem a incerteza de efeitos**, depois idempotência e correlação. Qualquer implementação futura precisa de autorização em uma nova etapa; esta rodada termina na auditoria.
