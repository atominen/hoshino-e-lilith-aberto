# Sessões diárias — decisão de implementação

Incremento da fase 2. Baseline antes: 74/74 grupos offline, em
`/tmp/hoshino-sessoes-diarias-antes-20261009.log`.

## Fonte de verdade e consumidores

Central nativa e Central web → `/api/state` e `/api/send` → Supervisor →
`core.interentity` → `entity_messages.metadata`, no SQLite compartilhado existente.
Hoshino/Lilith → `main.receber_de_pessoa`/`publicar`; Alistair → runner e histórico
próprios. Áudio consulta envelopes e jobs existentes; o overlay continua usando a
consulta legada. O histórico mental não é a caixa postal da Central.

Não criar banco, tabela de sessões, scheduler ou nova fila. Sessões são metadados
de organização da conversa principal do participante local `usuario`; Discord,
Minecraft e mensagens privadas conservam canais, autoria e filas atuais.

## Contrato

- Uma identificação determinística por entidade, data local e fuso. Atribuída
  pelo backend no aceite, nunca pelo LLM ou pelo relógio da interface.
- Envio com sessão arquivada recusado. Dedupe ocorre antes dessa validação:
  repetir o mesmo submission já aceito antes da meia-noite confirma o mesmo
  envelope, sem criar outra mensagem nem novo wake.
- Resposta herda a sessão do envelope humano que está sendo processado, mesmo
  após meia-noite. A sessão antiga continua somente leitura para novos envios.
- Dia novo é uma vista vazia quando não há mensagens; não reinicia identidade,
  contexto mental, objetivos, promessas, tarefas, inbox ou processamento.
- Legado interpretado em leitura, com origem derivada explícita; nunca reescrever
  o histórico em massa. Datas sem fuso continuam marcadas como não confirmadas.
- Consulta atual opt-in (`daily=1`), preservando a API all-time de outros
  consumidores. Páginas com teto de rowid e cursor, sem alegar ordem causal global.
- Resumos serão contagens verificáveis de registros, não narrativas inventadas
  ou novas inferências. Resumo semântico permanece indisponível nesta rodada.
- Interface observa a sessão retornada: bloqueia composer/captura de conversa
  arquivada; testes isolados de áudio permanecem disponíveis. Leitura histórica
  não dispara TTS automático. Rascunhos e respostas HTTP atrasadas não se apagam
  mutuamente. Streams conservam a referência à sessão de origem.

## Preservação e validação

Código prévio e snapshots SQLite consistentes estão em
`compartilhado/runtime/ensaios/20261009/sessoes-diarias/pre-incremento/` (privado,
fora do Git). Nenhuma migração mental, inferência real, quota TTS, alteração de
modelo, wake automático ou concorrência GPU autorizada neste incremento.

Regressões nos grupos existentes: data/fuso, restart, herança de respostas,
dedupe em virada de dia, legado, isolamento, paginação, HTTP, Qt e navegador com
transporte simulado. Testes de UI não comprovam hardware, áudio ouvido ou uso
prolongado. Custo da leitura de legado deve ser medido e documentado.

## Resultado do incremento

Implementado na Central nativa e no cliente web preservado:

- Seletor de dias, Hoje, busca por data/assunto e páginas de 100 envelopes.
  Catálogo de 60 sessões recentes; datas anteriores consultáveis pelo campo de
  data. Não renderizar todo o histórico de uma vez.
- Metadado `conversation_session` no envelope novo, separado do `session_id`
  diagnóstico. IDs incluem entidade, dia e digest do participante/fuso.
- Backend recusa sessão arquivada/estrangeira para novos envios. Submission
  já aceito continua idempotente depois da meia-noite. API all-time preservada.
- Resposta herda a sessão da entrada humana persistida, verificando autoria e
  destinatário; resposta tardia não reabre o arquivo para novos envios.
- Legado derivado sem alterar linhas; `session_origin` e `time` distinguem dados
  registrados/derivados e fuso original desconhecido. Datas inválidas são
  contabilizadas e continuam acessíveis pela API all-time, sem data fictícia.
- Paginação com teto de rowid/cursor e transação de leitura. Não é snapshot
  permanente dos estados de processamento nem ordem causal global.
- Rascunhos preservados ao mudar dia/entidade. HTTP atrasado não limpa rascunho
  novo nem substitui a vista selecionada. Anexo atrasado conserva o destino.
- Composer/anexos/captura de conversa bloqueados no arquivo; teste descartável
  de mic permanece disponível, sem envio automático à entidade.
- Arquivo, busca e páginas antigas não disparam TTS automático. Streams levam
  a sessão de origem, evitando começar fala de ontem na vista de hoje. A virada
  do relógio não cancela o turno nem uma reprodução que já começou.
- Histórico de entrada/saída, origem do escriba, jobs/eventos de áudio conservam
  a referência diária. Memória mental, relações, tarefas, filas e chaves de
  conversa não são particionadas/resetadas pelo dia.
- Bug Qt adicional reproduzido: conversa privada filtra pela entidade
  selecionada, não pela variável da última entidade do dashboard.

### Arquivos desta rodada

| Área | Arquivos alterados |
|---|---|
| Sessões/API | `app/core/interentity.py`, `iniciar_entidades.py` |
| Central | `app/ui/central_native.py`, `app/ui/central.html`, `app/ui/control.js` |
| Rastreabilidade | `app/main.py`, `app/mind/scribe.py`, `app/core/speech_stream.py`, `app/core/audio_service.py`, `app/core/diagnostics.py` |
| Testes | `testes/test_central_entidades.py`, `testes/native_central_contracts.py`, `testes/test_central_refinamento.py`, `testes/central_browser.cjs`, `testes/test_mensagens_causalidade.py`, `testes/test_prontidao_r1_r7.py` |

Este documento foi criado. O diff total do Git inclui alterações anteriores
muito maiores: não atribuir tudo a esta rodada. Elas foram preservadas.

### Testes/evidências

16 novos métodos permanentes: 9 Central/caixa postal, 6 Qt, 1 turnos/causalidade.
Fortalecidas as duas simulações simultâneas existentes, o turno completo R7 e
assertivas do navegador.

| Execução | Resultado |
|---|---|
| Baseline oficial | 74/74 grupos offline |
| Central/caixa postal, processo novo e HTTP efêmero autenticado | 28/28 |
| Turnos/causalidade, duas simulações simultâneas e meia-noite durante resposta | 40/40 |
| R1–R7, mensagem → memória → TTS → playback correlacionados | 111/111 |
| Refinamento Central | 34/34, incluindo subprocesso Qt com 42/42 contratos |
| Chromium headless, APIs simuladas, arquivo/read-only/Hoje | 1/1 teste de navegador |
| Suíte oficial final | **74/74 grupos offline** |
| `git diff --check` | sem erros |

Integração isolada: SQLite temporário real, processo novo lendo o mesmo arquivo,
HTTP local em porta efêmera, Qt offscreen e Chromium headless. LLM, Minecraft
RPC, áudio e transporte da UI são simulados; isso não comprova personalidade,
voz ou hardware real.

Medição: 2.000 envelopes temporários com metadados registrados; 100 retornos em
**0,024407 s**. Catálogo/compatibilidade examina metadados do histórico: custo
cresce com o número de envelopes. Não afirmar calibração para milhões de mensagens.

Smoke Qt offscreen, ~2 s de **inicialização e polling**: RSS máximo 92.924 KiB
(~90,7 MiB), CPU 0,417 s (~20,76% de um núcleo nesse intervalo). Não é medição de
idle, desktop real, ganho de desempenho ou soak. Nenhum shutdown do backend enviado.

### Falhas da validação, sem ocultação

1. Cinco testes de sessão falharam antes da implementação por ausência dos
   contratos novos; reprodução preservada.
2. Import local introduzido em `publicar` sombreou `interentity` e bloqueou
   respostas locais/privadas. A suíte expôs a regressão; removido o import
   redundante, sem relaxar fixtures para aceitar ausência de resposta.
3. Fixture nova de stream não fornecia sentença seguinte/terminação confirmada.
   Corrigida para sentença estável e finalização explícita; gate do produto mantido.
4. Assertiva nova de áudio buscava `details` na API pública reduzida. Corrigida
   para job persistido existente, também exigindo ID diário no evento playback.
   Whitelist de diagnóstico ampliada para esse ID, não para texto/segredos.
5. Teste de navegador esperava bloqueio provisório de carregamento, não arquivo
   confirmado. Agora espera a data retornada, read-only, ausência de envio e Hoje.
6. Pai dos testes Qt exigia literalmente 36 métodos; atualizado para 42 devido
   aos seis novos, preservando exigência de saída zero.

Primeira suíte pós-alteração: **69/74**, não aprovação. Falhas e resultados finais
conservados nos logs privados.

### Preservação

Dumps lógicos dos três históricos reais coincidem com seus snapshots. Caixa
postal também permaneceu igual, SHA-256 lógico
`220480b9108e283db450be54d3dd7d6e00a2635a55f667c3ed8e10011c683cb6`.
Isso não é hash de todos os bancos/modelos. Testes com o isolador existente;
nenhum banco mental real disponibilizado para escrita. Sem migração, delete,
wake, restart real, download, quota ou inferência real.

Evidências privadas em `compartilhado/runtime/ensaios/20261009/sessoes-diarias/`:
baseline, reprodução inicial, primeira suíte vermelha, suíte final e testes
específicos. Não versionar logs/snapshots/conversas no Git. Reversão retira somente
o incremento; não restaurar banco antigo por cima de novas conversas.

## Pendências/próximo passo

- Central já aberta precisa de restart cooperativo do backend/cliente para usar
  o código novo. **Não feito**; não interromper sessão humana em andamento.
- Teste manual no desktop, virada real de dia, áudio, uso prolongado e arquivos
  grandes pendentes. Somente os mecanismos foram validados em isolamento.
- Resumo narrativo do dia anterior não produzido. Contagens não cumprem esse
  requisito semântico. Continuidade de objetivos/promessas não foi resetada,
  mas ainda exige ensaio prolongado.
- Esta UI diária é da conversa principal do participante local `usuario`;
  pessoas/canais externos continuam separados. Não prova identificação biométrica.
- Fase 2 ainda exige auditoria dos consumidores mentais de tempo/duração.
  Diários privados, aprendizagem, oficina visual e experimentos de cache/modelos
  das fases seguintes **não foram implementados aqui**.

Conclusão: incremento de sessões diárias validado em ambiente isolado, suíte
verde. A especificação cognitiva completa permanece em andamento.
