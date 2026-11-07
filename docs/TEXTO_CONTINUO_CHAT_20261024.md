# Texto contínuo no chat — entrega iniciada em 24/10/2026

Atualizado em 25/10/2026. Estado: código integrado ao projeto local por decisão
humana; revisão independente realizada e quatro achados corrigidos com
regressões. Central atualizada aberta, com as três entidades dormindo.

## Decisão humana e escopo

O usuário escolheu acompanhar texto continuamente na mesma mensagem e manter
sua posição ao subir no histórico. Aprovou esta primeira etapa para Hoshino e
Lilith, sem mudar voz, transcrição ou o executor Xbox de Alistair, e confirmou
execução direta com testes e uma revisão independente final.

Referências:

- `docs/superpowers/specs/2026-10-24-texto-continuo-chat-design.md`
- `docs/superpowers/plans/2026-10-24-texto-continuo-chat.md`

## Implementação

- Aproveita a chamada incremental atual do Ollama: nenhuma inferência extra
  para a prévia e nenhuma animação de uma resposta já pronta.
- Publica um estado limitado por stream no diário existente: primeiro prefixo
  público validado disponível imediatamente, atualizações agrupadas em 100 ms e texto até
  12000 caracteres. Isso não é promessa de latência da inferência real.
- Separa texto em geração, geração encerrada e publicação final confirmada.
  Somente o recibo físico do envelope final confirma conclusão; falha e
  interrupção não são sucesso nem autorização de replay.
- Origem vinculada ao envelope humano físico. Chats diretos filtram entidade
  e sessão; sala global filtra o dia da sala, permitindo Hoshino/Lilith sem
  confundir suas diferentes sessões individuais.
- Retém possíveis marcadores internos divididos entre frames e invalida
  prévias contaminadas. Não publica campos de raciocínio, prompts ou
  argumentos de ferramentas. Os validadores atuais continuam em vigor.
- Consulta compacta autenticada `GET /api/chat/streams`; consultas genéricas
  de jobs não exportam o texto de prévias sem escolher seu público.
- Na Central nativa, uma consulta de prévias a cada 250 ms somente na conversa
  corrente sem filtros, com no máximo uma em voo e cache de 8 streams.
  Consulta geral permanece em 2 segundos; nenhuma gravação por token.
- A mensagem final substitui a prévia por identificador, sem repetição. A
  interface conserva leitura, seleção, foco e rascunho; acompanha o fim apenas
  quando a pessoa já está nele. Prévia não ganha avaliação humana como se
  fosse mensagem final, nem é consolidada como memória.

Neste corte, prévias atendem turnos humanos localhub elegíveis pelos gates
atuais. Turnos operacionais, fala autônoma e conteúdo que depende de validação
final conservam a publicação final existente; não se relaxou a verificação
para antecipar conteúdo. As prévias projetadas são recentes (até 120 s desde
a atualização do produtor), não um segundo histórico persistente de chat.

## Evidências de testes

Python principal já instalado, chamado por caminho absoluto; Qt no Python do
sistema. Nenhuma dependência ou modelo instalado. Bancos de ensaio temporários,
transporte/modelos/processos simulados; não houve captura de mic ou quota TTS.

| Verificação | Resultado observado |
| --- | --- |
| Prévia e origem, RED antes de implementação | 15 falhas esperadas por função ausente |
| Prévia e origem, GREEN | 15/15 |
| Transporte real do cliente com frames simulados, HTTP, publicação e regressão de voz/global | 56/56 |
| Projeção e contratos Qt, RED antes da interface | ausência da projeção/polling reproduzida |
| Grupo novo completo + subprocesso de contratos Qt antes da revisão | 29/29 testes pais, incluindo o processo Qt |
| Novas regressões da revisão + grupo novo + Qt após as correções | 31/31 testes pais |
| Feature + voz/global + subprocesso Qt após as correções | 64/64 testes pais |
| Quatro grupos focados completos após as correções | 104/105; uma falha de baseline aceita, descrita abaixo |
| `bash rodar_testes.sh` — suíte offline completa repetida após as correções | 90/91 grupos; mesma falha de baseline |
| Inventário `testes/catalogo.py` | válido, 91 grupos automatizados |
| `git diff --check` | sem erro |

Logs locais de execução: `/tmp/texto-continuo-task1-red.log`,
`/tmp/texto-continuo-task1-green.log`, `/tmp/texto-continuo-task2-red.log`,
`/tmp/texto-continuo-task2-green.log`, `/tmp/texto-continuo-task3-red.log`,
`/tmp/texto-continuo-task3-green.log`, `/tmp/texto-continuo-conjunto.log` e
`/tmp/texto-continuo-suite-completa-preparada.log`. Evidência final:
`/tmp/texto-continuo-review-red.log`, `/tmp/texto-continuo-review-qt-red.log`,
`/tmp/texto-continuo-review-green.log`, `/tmp/texto-continuo-review-qt-green.log`,
`/tmp/texto-continuo-conjunto-final.log` e `/tmp/texto-continuo-suite-final.log`.

## Revisão independente e correções

Uma revisão somente leitura cobriu `acbf042..1c19ad4`, seguindo o plano e seus
cinco pontos de atenção. Não encontrou achados críticos ou menores; identificou
quatro problemas importantes, todos reproduzidos antes da correção:

1. Crescimento de uma prévia acima de outra mudava a seleção/leitura por
   restaurar apenas posições absolutas. A interface agora usa âncoras de
   mensagem, cabeçalho e corpo e preserva a linha visível e o texto selecionado.
2. Descartar uma prévia já interrompida não removia seu texto durante um retry
   existente. Descarte agora atualiza o mesmo estado terminal, sem reabrir job.
3. Cancelamento durante o primeiro prefixo podia deixar o job em `running`.
   Trava curta torna estado/publicação atômicos; validação fica fora da trava
   para o cancelamento não precisar esperá-la.
4. Encerramento bloqueado não reativava o timer novo de prévias. A recuperação
   da janela agora reativa esse timer.

Regressões: `test_discard_after_interruption_clears_obsolete_preview`,
`test_cancellation_during_first_prefix_cannot_leave_running_job`,
`test_text_stream_growth_above_selection_keeps_same_message_and_visible_line`
e `test_text_stream_polling_resumes_after_shutdown_is_blocked`.
As quatro falharam antes e passaram depois. Houve uma única rodada de correção,
com nova execução da suíte completa, sem segunda revisão independente.

### Falha preexistente mantida, sem suprimir teste

`test_central_refinamento.Refinamento.test_desktop_launcher_uses_login_environment_without_embedding_keys`:
o teste exige que o `.desktop` aponte para o ROOT do worktree, enquanto o
arquivo instalado e versionado aponta para `/home/gustavo/hoshino e lilith`.
A falha existia na verificação inicial, antes de qualquer código da mudança.
O usuário autorizou explicitamente continuar com essa limitação registrada.
Não se alterou o atalho ou o teste para forçar aprovação.
O mesmo teste foi executado separadamente no checkout instalado, sem mudar seu
código, e passou (1/1): `/tmp/texto-continuo-atalho-instalacao.log`.

Foram resolvidos somente pré-requisitos de ensaio no worktree: referência ao
ambiente instalado, configuração local de capacidades para leitura e cópias
locais das identidades necessárias ao isolador. A guarda de identidade recusou
links para fora da pasta da entidade; os links de identidade criados para a
preparação foram removidos, sem alterar originais, e não se relaxou a guarda.
Esses arquivos de preparação não entram no Git; nenhum banco ou peso foi
copiado. A tentativa sem preparação não é contada como validação do código.

## Decisões de execução e limitações

1. Reutilizar o Python principal instalado por caminho absoluto evita
   instalações/cópias de dependências. Risco residual: ensaio isolado não
   comprova a experiência no desktop ou a latência do modelo real.
2. Manter a falha de baseline aceita em vez de reescrever/suprimir o teste:
   recibos de tarefa usam o novo grupo e o caso Qt real; os grupos completos e
   a suíte completa também foram rodados e suas falhas estão explícitas.
   A limitação de portabilidade do teste do atalho permanece sem correção.
3. Manter Xbox, áudio, modelos e memória fora desta etapa respeita o escopo
   aprovado; suas melhorias posteriores continuam pendentes.
4. A revisão não avaliou a recuperação dos timers antigos de áudio/detalhes/
   foco; ela é preexistente e não foi modificada. A limitação antiga permanece,
   mesmo com o novo timer de texto corrigido.
5. Alterações de produção após o range revisado são as correções verificadas
   por regressões e suíte completa, não uma segunda revisão independente. O
   risco residual é não haver outro revisor avaliando esses commits finais.

## Preservação e carregamento — antes da integração

Trabalho em `codex/texto-continuo-chat`, no worktree gerenciado de mesmo nome.
O checkout instalado continua com suas mudanças preexistentes preservadas.
Sem merge, push, publicação, reset de dados, alteração de modelos/personalidade
ou inicialização de entidades/treinos. Não há aprovação de novo TTS/ASR aqui.

Em 25/10, uma consulta autenticada ao endereço local registrado da Central
retornou conexão recusada. Isso não prova, sozinho, que não existam processos
ou leases ativos; nenhum restart foi feito. Aplicação no checkout instalado e
carregamento real permanecem pendentes de decisão de integração, reconciliação
e, quando necessário, fechamento cooperativo. Os testes Qt isolados não são
apresentados como validação de desktop real ou de inferência real.

## Integração local autorizada — 25/10/2026

O usuário escolheu “Aplicar ao projeto local”. A branch instalada
`codex/laboratorio-consolidacao-20261012` recebeu por fast-forward os commits
da implementação até `c6db644`, sem pull, push ou alteração do GitHub.

Antes da aplicação, não havia processos de Central/entidades identificados,
jobs ativos, leases ou pedidos GPU. O registro noturno corrente estava
encerrado e o agendamento único anterior bloqueado; nenhum deles foi alterado.
Também foram conferidos zero pedidos pendentes de despertar e política
noturna automática desabilitada, sem aprovação automática de dados.

A única sobreposição era `testes/catalogo.py`. Sua alteração local anterior
foi guardada temporariamente em stash próprio, a integração foi aplicada e a
alteração foi restaurada. O diff restante desse arquivo continua contendo
somente a inclusão preexistente do ensaio local de Qwen3 6B. Os demais arquivos
modificados ou não versionados anteriores permaneceram intactos e fora dos
commits desta entrega.

Verificação no checkout instalado: `bash rodar_testes.sh`, **91/91 grupos
aprovados**, sem excluir ou modificar o teste antigo do atalho. A falha
específica do caminho do worktree não acontece na instalação original.
Log: `/tmp/texto-continuo-integracao-local-suite.log`.

A primeira tentativa de lançamento em background não deixou processo ativo
ou log de inicialização; o endereço da Central permaneceu inalterado. Após
confirmar processo ausente e porta livre, o mesmo comando foi executado em
sessão acompanhada, sem alteração de código: Python principal com `-B
iniciar_entidades.py --port 8769`, sem `--entity`. Backend observado em PID
34182 e janela nativa em PID 34190. Esses PIDs são evidência desta verificação,
não prova permanente de posse ou funcionamento.

Conferências reais após o carregamento:

- Janela nativa mapeada no desktop.
- `GET /api/state` autenticado e `GET /api/chat/streams` autenticado responderam.
- Nova consulta devolveu lista vazia de prévias, como esperado sem geração.
- Hoshino, Lilith e Alistair em `sleeping`; zero jobs ativos e zero leases.
- Nenhuma mensagem de teste enviada às entidades, inferência ou síntese de voz
  solicitada. Uso real de conversa/qualidade da resposta ainda cabe ao usuário.

Voz, transcrição, agrupamento de mensagens, Alistair/Xbox, modelos e dados
mentais continuam fora desta etapa. A área isolada integrada foi arquivada
pela ferramenta gerenciada, com recuperação disponível nos anexos da tarefa;
a branch temporária já integrada foi removida. O stash temporário foi
descartado somente após confirmar a restauração da alteração local. A
instalação principal e suas alterações preexistentes permanecem preservadas.
