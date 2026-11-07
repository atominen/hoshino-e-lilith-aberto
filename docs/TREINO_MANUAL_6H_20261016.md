# Nova autorização manual — seis horas efetivas, 16/10/2026

Atualização posterior: o usuário autorizou ajuste do bloqueio e um novo reteste
físico; ver [reteste térmico Yi](RETESTE_TERMICO_YI_20261016.md).
O corte100 e o bloqueio abaixo são históricos preservados, não apagados.
**Situação atual às07:32:** o reteste105 concluiu com pico102°C, mas a candidata
Yi/Hoshino reprovou identidade e regra de resultado incerto (6/8contratos).
O ciclo6h permanece NÃO iniciado, agora por bloqueio comportamental, não por
falha térmica nessa última execução. Ver evidências no relatório acima.

## Situação na partida

O usuário autorizou um novo ciclo imediato, reduzido de12h para6h. Isso não
reativa a antiga autorização da meia-noite, os dois agendamentos pausados,
a rotina diária, professor, promoção automática ou desligamento. Continuam
sete pares de entidade/base: Hoshino/Lilith Yi6B, Qwen2.5-7B e Qwen3.5-9B;
Alistair Qwen3.5-4B. Bases originais para todos os novos treinos, sem retomar
os candidatos antigos. Nenhum download, troca de modelo ou banco novo.

**Ainda não está tudo aprovado.** A GPU estava livre e a40°C às06:42, RAM
disponível26,39GiB, disco43,32GiB, nenhum worker/lease ativo. Os quatro gates
6B/7B de piloto/recarga/comportamento continuavam sem aprovação. A avaliação
Yi/Hoshino anterior foi interrompida pelo corte térmico; o treino salvo não
substitui a avaliação completa. Relatório anterior preservado em
[treinos de15–16/10](TREINOS_MANUAIS_DEFAULTS_20261015.md).

## Correção mínima e reteste sem repetir treinamento

O runner já cedia entre updates, amostras e casos, mas uma chamada de geração
executava até160tokens sem voltar à checagem térmica do filho. O monitor pai
continuava impondo o corte100°C. A avaliação interrompida completou os losses,
mas não o controle/comparação final. Não atribuir uma causa mais específica a
uma etapa sem registro suficiente.

`GenerationCoolingGate`, no próprio runner, passa o mesmo controle de
resfriamento à lista de critérios da geração existente. Ele consulta entre
tokens e não altera logits, texto, EOS, prompts, orçamento de160tokens, pesos
ou resposta esperada. O corte100°C, histerese, prazo60s e margem768MiB continuam
iguais. Cancelamento não se converte em EOS nem em resposta concluída.
Eventos de início/fim por caso distinguem candidata/base e registram duração,
tokens, término e número de checagens, sem publicar o texto ou segredos no log.

Dois testes novos cobrem chamada por token sem mutação de entrada/saída,
cancelamento e propagação de falhas. Backup anterior às alterações:
`laboratorio-local/controle-laboratorio/treinamento-unificado/backups/pre-6h-20261016-0645.tar.gz`.

Às06:45 foi autorizada a sessão de **avaliação somente leitura**
`987fcef07c8b4453`, job `b729e690fe8749f9`, sobre o candidato íntegro
`cdbf18c6ff1e46b0-yi-6b`. Janela35min, avaliação25min, margem do supervisor
preservada. Não reexecuta treino nem sobrescreve relatório anterior. Índice de
observação em `plans/manual-6h-20261016.json`, no registro existente. A fonte
de verdade continua nos jobs e na sessão do supervisor.

**Treinamento grande NÃO iniciado: bloqueado após novo corte térmico.**
O reteste físico confirmou a correção EOS, mas não resolveu a estabilidade
térmica. Não retirar os gates nem repetir automaticamente.

O reteste acima foi cancelado cooperativamente ao identificar outro defeito:
no Yi instalado, o tokenizer original declara `<|im_end|>` (ID7), enquanto
`generation_config.json` conserva somente EOS2. As cinco respostas medidas
chegaram a160tokens sem término confirmado. Não alterar pesos/config da base.
`generation_end_tokens` passa a união verificada `[2,7]` à geração e à auditoria,
recusando IDs inválidos ou EOS nativo não registrado como especial. A união
foi conferida com o tokenizer real instalado, em CPU, sem inferência.

O worker anterior saiu e a GPU/lease foram liberados antes da alteração.
Novo reteste somente leitura: sessão `aaee8f03c349431e`, job
`9091adc7c2904157`, avaliação30min/janela40min. Mesma candidata intacta;
sem repetir treino. A hipótese de EOS contribuindo para duração/temperatura
ainda depende desse resultado físico. Nenhuma falha anterior é apagada.

Primeira evidência física após a correção: `candidate identity`7tokens,
3,14s, término confirmado (antes160tokens/40,83s sem término). Os casos
`unknown_memory`22tokens/6,86s, `authorship`4/1,62s,
`correction`14/4,93s e `uncertain_action`49/13,90s também terminaram no EOS.
Mesma candidata e prompts; sem modificar respostas esperadas. Não é ainda
aprovação de conteúdo dos oito casos, controle base ou estabilidade prolongada.

### Desfecho físico — registrado às07:14 de16/10

A sessão `aaee8f03c349431e` encerrou `completed_with_errors`; job
`9091adc7c2904157` falhou. O monitor registrou hotspot/junction100°C e
interrompeu somente o filho owned (SIGTERM, exit-15; wrapper241). Não houve
kill forçado (`forced_owned_child_stop=false`), replay ou nova sessão.
Duração física409,97s; pico de VRAM4,434GiB; menor RAM disponível16,812GiB.
A lista de pressão contém somente o corte térmico, não OOM.

Os oito casos da candidata tiveram término confirmado: além dos cinco acima,
`absence`17tokens/5,63s, `revision`9/3,32s e `tools`4/1,96s. A validação de131
exemplos produziu loss2,114119804769982 e o holdout104 loss2,134590189044292.
O corte ocorreu depois desses eventos; o controle completo da base não terminou
e não existe relatório final de avaliação. Não aprovar conteúdo ou generalização
com esses resultados parciais. A checagem entre tokens não protege o interior
de um forward; a evidência não identifica um kernel específico como causa.

Relatório físico preservado:
`reports/hoshino/9091adc7c2904157-yi-6b.hardware.json`, SHA256
`391ca4a9a4e8e60eb8e1c08384ab8841d14d8d2e2c17980c54767ebe5bc810b0`.
O supervisor loopback confirma a falha, não há worker unificado ativo,
`_busy()` retornaNone e o Resource Manager não tem leases. Às07:14 a GPU estava
ociosa, hotspot41°C. A candidata e as bases permanecem intactas.

**Decisão desta autorização:** não iniciar pilotos adicionais, rodada20min ou
ciclo6h após esse bloqueio; não mudar parâmetros/temperatura/fans/energia por
conta própria. Encerrar o acompanhamento único conforme sua regra de falha,
preservando o antigo disparo da meia-noite pausado. Próxima etapa depende de
diagnóstico térmico e correção concreta autorizada, antes de novo reteste.
A ferramenta do aplicativo confirmou a exclusão deste acompanhamento
(`acompanhar-treinos-manuais-de-15-16-10`); não apenas pausa em RAM.

## Orçamento e sequência

**Resposta humana confirmada: “6 horas de otimização; avaliações depois”.**
O alvo é21600s efetivos somados entre os sete treinos, não seis horas por
modelo. Cargas, resfriamento, checkpoints e avaliações são adicionais. A
interpretação provisória anterior de6h de parede foi substituída, não executada.

`default_cycle_plan(...,nightly=True,optimization_seconds=21600)` reutiliza
o relógio efetivo e o supervisor existentes: cinco treinos com3086s e dois
com3085s, total exato21600s. Limite de52min efetivos por tarefa, avaliação30min
fora desse relógio, janela máxima de12h de parede. São14tarefas sequenciais.
Early stop e teto de3epochs permanecem: não repetir corpus pequeno apenas
para preencher seis horas. O tempo alcançado deve ser relatado separadamente
do alvo, inclusive se Alistair encerrar cedo pelo limite de exemplos.

Esta preparação exige throughput e tamanho de checkpoint realmente medidos.
Um smoke sem adaptador não é suficiente para projetar disco do treino longo.
A leitura de evidência foi corrigida para aceitar arquivo de smoke ou pasta
de candidato, sem inventar medições ausentes. A rodada curta9B/9B/4B previamente
autorizada fornece essas medições quando os gates6B/7B estiverem satisfeitos.
As opções antigas de6h/12h de parede e rodada curta continuam compatíveis.

O plano não remove os gates nem executa automaticamente. Primeiro concluir a
revalidação; se segura e com contratos atendidos, concluir os pilotos faltantes
com os próprios corpora e avaliação independente. Não refazer o piloto salvo
da Hoshino. Só preparar/iniciar o ciclo6h se todos os gates forem demonstrados,
corpora/bases conferirem e houver recursos seguros. Se o reteste falhar, não
trocar parâmetros/repetir automaticamente nem instalar candidatas para fingir
aprovação. Preservar originais, memórias, evidências e candidatas separadas.

## Validação e pendências

Arquivos alterados nesta nova rodada: `laboratorio/treino_nf4_curto.py`,
`laboratorio/treinos_unificados.py`, `laboratorio/tests/test_consolidacao.py`
e este relatório. Demais alterações preexistentes são preservadas. Não editar
o código do runner enquanto o reteste estiver executando.

Baseline anterior310testes; após as correções e a clarificação humana, a suíte
completa do laboratório passou **317/317**, 13,995s, exit0. A suíte oficial
passou novamente **74/74grupos**, exit0, depois da correção EOS/plano efetivo.
`git diff --check` também passou. Os logs estão em
`/tmp/treino6h-tests-laboratorio-20261016.log` e
`/tmp/treino6h-tests-oficiais-20261016.log`.
Regressões cobrem janela6h, soma exata21600s, avaliação fora do relógio,
preservação dos gates, base original, limite3epochs, leitura de evidência
arquivo/pasta, recusa de checkpoint inventado e EOS nativo verificado sem
modificar a base. O callback também foi executado com a
lista de critérios real do Transformers/Torch instalada, em CPU, sem carregar
pesos nem acessar GPU. Isso comprova o contrato da chamada, não estabilidade
térmica ou qualidade da inferência. Resultados e IDs posteriores devem ser
registrados antes de declarar esta rodada concluída.

Pendentes: resolver o bloqueio térmico reproduzido, pilotos6B/Lilith e7B/Hoshino/Lilith,
aprovação técnica das recargas, partida/desfecho do ciclo6h e avaliação humana
da naturalidade. Professor com histórico humano real continua para depois de
existir conversa humana pertinente; não usar este ensaio como biografia real.
