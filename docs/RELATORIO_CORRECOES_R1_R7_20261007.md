# Rodada mínima R1–R7 — 7 de outubro de 2026

## Parecer

**PODEMOS INICIAR O TESTE MANUAL INTEGRADO? SIM.**

Os defeitos determinísticos reproduzidos da auditoria foram corrigidos e ganharam regressões permanentes. Isso autoriza começar uma sessão controlada; **não** equivale a validar Minecraft real, microfone físico, qualidade de voz/persona, Athlon/PC2 ou uso prolongado. Nenhuma dessas validações foi fingida com mocks.

Baseline antes das mudanças: **67/67 grupos offline**. Resultado da última execução integral após as correções: **70/70 grupos offline**, código de saída 0. Sem regressão remanescente encontrada nessa suíte.

Escopo preservado: modelos 9B/7B/4B e dados existentes; nenhum banco, scheduler, modelo, integração de execução ou sistema mental novo. Resource Manager e sua configuração não foram recalibrados. `concurrency_validated=false`, limite de 8 GiB, margem de 768 MiB, roteamento conservador e fallbacks foram mantidos. Destinos cloud continuam desativados em `compartilhado/config/capacidades.json`. A instrumentação de reprodução usa o endpoint/diário de áudio existentes, não outro coletor.

## Correções e contratos

### R1 — autoria, memória e episódios

As entradas agora carregam autoria do transporte, sujeito declarado, entidade ouvinte, IDs de mensagem/history/source/submission, canal e timestamp. A evidência acrescenta o turno de origem/aprendizado quando disponível. Isso percorre fila, pós-turno, regras, extração e compactação.

- `usuario` dizendo “Meu nome é Gustavo” continua sendo informação **declarada pelo humano**, com confiança na declaração, não comprovação civil externa.
- Autodeclarações de Alistair/Hoshino/Lilith têm sujeito próprio e chaves escopadas por participante. Não renomeiam o usuário nem disputam sua chave.
- Mesmo nome declarado por sujeitos diferentes e propriedades iguais não se supersedem por essa coincidência.
- O texto de uma declaração não pode falsificar o nome do autor identificado pelo transporte: Alistair dizendo “Eu sou Gustavo” continua tendo **autor Alistair**.
- Perguntas, citações, roleplay, hipóteses e marcadores de reflexão não viram autodeclarações pelas regras. Uma apresentação seguida de “e você?” ainda pode ser reconhecida.
- Extrações do LLM que se autodenominam `fato` tornam-se `interpretacao`. Hipótese e reflexão continuam categorias próprias. Extração não inventa sujeito confirmado; conserva fonte e participantes mencionados.
- Ferramentas de memória herdam a referência à entrada, mas não presumem que o objeto memorizado seja o autor dela. Confiança 0 permanece 0; defaults para ausência continuam os existentes.
- Episódios usam o nome real da entidade e do participante. O contexto existente conserva a autoria estruturada; episódios de Lilith não escrevem “Hoshino” como respondente.
- A compactação transmite a autoria no texto a resumir. Registros legados sem autoria não são convertidos automaticamente em novas autodeclarações.

**Compatibilidade:** nenhum dado antigo foi reclassificado/migrado em lote. Registros novos atribuídos não supersedem cegamente registros legados cujo sujeito é desconhecido. Esses dados antigos continuam legíveis, mas eventuais erros históricos não foram “curados” por adivinhação. Memórias usam `links` existentes; propriedades atribuídas usam um envelope `memory_provenance` no campo `source` já existente, reconhecido pelo leitor, que continua aceitando fontes antigas simples. Leitores externos de SQLite precisam considerar esse envelope nos registros novos.

Consumidores conferidos: pós-turno e publicador em `main`, escriba determinístico/extrator, compactação, reflexão/reflexão noturna, leitores do knowledge store, ferramentas de memória e seus testes.

### R2 — descoberta Minecraft Java LAN

O discovery existente reconhece o pacote padrão `[MOTD]...[/MOTD][AD]PORTA[/AD]`, decodifica UTF-8 estritamente e aceita somente portas 1–65535. Conserva deduplicação host/porta, múltiplos mundos, timeout e conexão manual. Não foi criado outro discovery.

### R3 — stream incompleto

EOF não confirma resposta: exige `done=true`. Erro do backend, frame inválido, prazo excedido, ausência de término ou argumentos de ferramenta incompletos fazem a chamada falhar. Término por limite de geração (`done_reason=length`) também não é tratado como resposta concluída.

O adaptador de respostas sem `iter_lines` segue a mesma exigência. A fala correspondente é invalidada em falha; ferramenta parcial não chega ao dispatcher. Não foi adicionado retry mutável automático.

**Limite honesto:** o prazo é conferido durante a leitura, além do timeout HTTP existente; não é preempção imediata de uma leitura de rede bloqueada. Uma sentença estável já ouvida antes da falha não pode ser desfeita; cancelamento impede continuação/reprodução pendente, não “desfala”.

### R4 — Alistair durável

Usa o `processing_outcome` existente antes da inferência e registra `answered` ou `uncertain`. Falhas não dependem mais de cooldown somente em RAM. Mensagens retidas continuam diagnosticáveis e não recebem replay automático após restart; não escondem entradas posteriores.

Contexto apresenta sender/destinatário/ID/time/canal reais. A recuperação usa apenas `alistair_turns`: mantém quatro turnos recentes e acrescenta primeiras informações e correspondências lexicais antigas, com IDs/timestamps, em volume limitado. São citações históricas, não nova memória mental nem fatos verificados.

Uma regressão revelou que `ActionWindow` convertia efeito incerto em erro comum. Alistair agora preserva essa incerteza, encerra a rodada e não oferece ao modelo outra tentativa mutável. Marcadores/recibos duráveis existentes continuam sendo usados. Eventos de executor, inferência e ferramentas conservam os IDs sem acrescentar texto de conversas aos novos eventos de Alistair.

### R5 — sono/shutdown

O pedido de sono pela central e o supervisor cancelam apenas TTS pendente da entidade-alvo. A UI para apenas seu player; sono de Hoshino não para Lilith. ASR não relacionado permanece intacto. A submissão tardia de fala é recusada depois do pedido de sono.

No encerramento, a ponte Minecraft é fechada somente pelo `Popen` criado naquela entidade. O script usa `exec node`, portanto o handle corresponde ao processo da ponte; não se busca/mata por porta/nome. Pontes externas não são sinalizadas. Drenagem de trabalhos/leases e tratamento de resultado incerto continuam nos contratos existentes.

Presence/diagnóstico distinguem **processo encerrado** de **unload confirmado**. Falha/retorno falso do unload produz `unload=unconfirmed`, inclusive em Alistair. Modelo remoto sob idle timeout não é declarado descarregado pelo PC principal. O supervisor não apaga essa distinção ao observar a saída do filho.

### R6 — bridge e sessões

Setup de plugins/Movements que falha não vira `ready`. Spawn tardio após erro, kick ou timeout também não confirma conexão.

Callbacks ficam vinculados ao bot/sessão que os criou. Eventos antigos são ignorados; a conclusão tardia de navegação/mineração/coleta e outras ações assíncronas não modifica a sessão nova. Uma operação cuja sessão foi substituída não recebe sucesso confirmado.

O RPC preserva request ID e correlaciona parent/tool, turn, entity e session. Metadados extras são compatíveis com o protocolo existente; quando presentes, recibos estrangeiros são recusados. Timeout/recibo inválido de ação mutável continua `RESULTADO_INCERTO`. STOP solicita parada cooperativa, sem afirmar parada instantânea; `path_stop` fornece confirmação do pathfinder.

### R7 — rastreabilidade

`diagnostics/history/links` existentes agora ligam input/submission/history → turno/autoria/entidade → executor/request/compute lease → ferramenta/parent → RPC/session/receipt → memória → stream/job de áudio/provider → cancelamento/desfecho.

A central registra relatos de início/fim de reprodução, autoplay negado, erro e cancelamento no diário existente, com validação de entidade/job/chunk. Não muda o contrato público de consulta de jobs. **Síntese concluída não significa áudio ouvido**: playout é marcado como relato do browser, não prova de audição humana. Perda de conexão do browser pode deixar confirmação de reprodução ausente.

Não foram solicitadas/lidas/gravadas chaves reais. Os novos eventos de memória e playout usam referências e metadados, não conteúdo da memória, headers remotos ou credenciais.

## Testes permanentes e resultados

Foram acrescentados **35 casos Python**, distribuídos em três grupos novos e grupos existentes, além de **11 cenários internos da bridge com bot fake** (executados por um dos casos Python; não somar como 11 grupos oficiais).

| Grupo executado | Resultado | Evidência principal |
|---|---:|---|
| `test_autoria_memoria` | 10/10 | Quatro participantes; mesmo nome/propriedade; três bancos temporários/reabertura; evidência/0.0; legado; categorias; compactação; episódios H/L |
| `test_prontidao_r1_r7` | 19/19 | LAN/timeout/manual; EOF/erro/length/ferramenta parcial; invalidação de fala; Alistair crash/restart/backlog/efeito incerto; sleep/unload/ownership; turno completo rastreável |
| `test_minecraft_bridge` | 1/1, com 11/11 cenários Node | Sessões/callbacks antigos, reconexão em curso, setup failure, timeout/spawn tardio, erro/kick, IDs, recibo estrangeiro, STOP e ação antiga terminando após ação nova |
| `test_mensagens_causalidade` | 34/34 | Inclui as duas simulações simultâneas; FIFO/correções/interrupções existentes mantidas |
| `test_audio_service` | 37/37 | Origem no job; validação HTTP do relato de playout; isolamento/cancelamento e transporte existentes |
| `test_voz_streaming` | 19/19 | Ordem/chunks/autoplay; H dorme enquanto L fala; cancelamento do player-alvo; áudio nativo simulado |
| Suíte oficial integral | **70/70 grupos** | Última execução após alterações, exit 0 |

As regressões existentes de shutdown normal/lento/travado/mutável incerto, recuperação de lock após crash, integridade de memória, reflexão, executores leves, GPU, Azure e ElevenLabs também foram executadas na suíte integral.

Validação adicional: sintaxe Python de **103 arquivos** OK; `node --check` da bridge OK; compilação sintática do JavaScript da central OK.

Execução reproduzível: `bash rodar_testes.sh`. Casos específicos passam por `compartilhado/ambientes/principal/bin/python -B testes/executar_isolado.py testes/NOME.py`. Guardas offline recusam escrita em bancos/pastas reais, serviços reais, rede externa, modelos e microfone. A fixture Node substitui fs/http/Mineflayer, sem abrir socket ou escrever logs reais.

As duas simulações são processamento real das filas/publicador com modelo e partes mentais mockados. A integridade R1 é validada separadamente com regras/gravações reais em SQLite temporário. O teste de rastreabilidade executa fila, roteamento, dispatcher, memória e serviço de áudio reais, substituindo inferência, transporte Minecraft e síntese. Isso **não** prova comportamento de um LLM/servidor/motor de voz real.

## Falhas encontradas durante a implementação

Não foram mascaradas:

- Instrumentação nova atravessava o `signature.bind` do Resource Manager antes de ser consumida e impedia iniciar turnos. Corrigida a ordem dos decoradores, preservando o mesmo RM e a escolha de executor.
- Metadados do histórico central chegavam como JSON textual; TTS esperava objeto. Corrigida a leitura compatível, sem mudança do formato do barramento.
- `ActionWindow` engolia a sinalização de ação incerta de Alistair. Corrigida a propagação sem retry.
- Fixtures HTTP antigas omitiam `done`; agora confirmam término como o backend real. Não se flexibilizou o contrato de produção para aceitá-las.
- Fixture de compactação não carregava autoria e esperava resgate factual de histórico anônimo. Passou a usar origem da pessoa real da fixture e consultar suas propriedades. Há teste separado garantindo que o legado anônimo **não** seja convertido cegamente.
- Player fake não implementava eventos DOM nem diferenciava publicação de diagnóstico de polling de jobs. Fixture corrigida e ampliada para testar autoplay e isolamento no sono.

Execuções intermediárias tiveram falhas (62/67 e depois 69/70); o resultado válido de entrega é a última execução **70/70**, não esses runs parciais.

## ElevenLabs

Voice IDs registrados na configuração não secreta:

- Hoshino: `jotBQRDYDizrWQAbv9VO`
- Lilith: `m151rjrbWXbBqyq56tly`

**Deixado `elevenlabs.enabled=false`; `preferred_provider` continua `azure`.** Para o primeiro uso real, habilitar manualmente `elevenlabs.enabled=true` e `preferred_provider="elevenlabs"` em `compartilhado/config/audio.json`, com a chave somente em `ELEVENLABS_API_KEY` do ambiente. Não inserir chave no JSON, código ou relatório.

Nenhuma chamada real/quota foi consumida. Azure/Qwen3-TTS/Kokoro e seus fallbacks permanecem. Validação real de ElevenLabs continua pendente.

## Arquivos modificados/criados

Todos os caminhos abaixo são relativos à raiz **`/home/gustavo/hoshino e lilith`**.

Produção/configuração (16):

- `app/main.py`
- `app/mind/scribe.py`
- `app/memory/knowledge_store.py`
- `app/core/compaction.py`
- `app/core/diagnostics.py`
- `app/core/dispatch.py`
- `app/core/speech_stream.py`
- `app/core/audio_service.py`
- `app/alistair_runner.py`
- `app/entity_runner.py`
- `app/tools/minecraft.py`
- `app/tools/minecraft_launcher.py`
- `app/ui/central.html`
- `iniciar_entidades.py`
- `compartilhado/servicos/minecraft/bridge.js`
- `compartilhado/config/audio.json`

Testes existentes ajustados/ampliados (6):

- `testes/catalogo.py`
- `testes/test_mensagens_causalidade.py`
- `testes/test_audio_service.py`
- `testes/test_voz_streaming.py`
- `testes/test_turno_e2e.py`
- `testes/test_integracao.py`

Testes novos (4 arquivos):

- `testes/test_autoria_memoria.py`
- `testes/test_prontidao_r1_r7.py`
- `testes/test_minecraft_bridge.py`
- `testes/fixture_minecraft_bridge.js`

Documento novo: `docs/RELATORIO_CORRECOES_R1_R7_20261007.md`.

Backup de fontes pré-rodada: `arquivo/refinamento_20261006_r1_r7/fontes_antes.tar.gz`. Não contém modelos/bancos; não restaurar em bloco se houver mudanças posteriores. Nenhum modelo/dado foi apagado.

Os hashes dos três bancos mentais principais permaneceram idênticos entre as conferências antes/depois dos últimos testes. Isso é uma conferência adicional desse intervalo, não substitui as guardas de isolamento nem é alegação de backup dos dados reais.

## Mudanças de comportamento e riscos restantes

Mudanças intencionais: stream truncado falha em vez de publicar fragmento; extração LLM deixa de promover conclusão a fato; autoria/sujeitos delimitam conflitos; compactação deixa de aprender factualidade de histórico sem autoria; Alistair retém falhas duráveis e recusa efeito incerto; sono cancela só voz-alvo; unload não confirmado fica explícito.

Não há bloqueador determinístico reproduzível remanescente nos probes desta rodada. Ainda observar no teste:

1. Minecraft 1.16.5 real, LAN da máquina, permissões/reconexão/eventos e stop sob condições reais. Mocks não comprovam servidor real.
2. Microfone físico/ASR, reprodução, timbre, latência e interrupção real de TTS. ElevenLabs permanece desligado.
3. Naturalidade e consistência 7B/9B, recordação após o restart completo e aprendizado relevante da sessão humana.
4. GPU/RAM sob pressão, starvation, staging agregado, swap, daemon que ainda computa após crash e backlog: limitações conhecidas do RM, não recalibradas nesta rodada.
5. Athlon/PC2 e uso prolongado: não validados fisicamente aqui. Não colocar PC2 como requisito para iniciar no PC principal com os fallbacks existentes.
6. Memórias históricas já incorretas podem continuar visíveis. Foram preservadas, não reatribuídas automaticamente. Corrigi-las exige evidência e seleção específica.
7. Playout é best-effort e áudio já ouvido não possui rollback. Não afirmar “ouvido” porque WAV ficou pronto.

Próximo passo prioritário dentro do escopo congelado: executar o roteiro humano progressivamente (apresentações/sono primeiro, Minecraft depois), guardar IDs/horários de falhas e verificar memórias importantes após restart. Em seguida calibrar o RM e latência com os dados reais coletados, sem ampliar capacidades.
