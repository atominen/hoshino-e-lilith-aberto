# Autonomia contínua e recuperação de contexto — 23/10/2026

Estado desta entrega: **contratos offline validados; sem homologação
comportamental**. Este é o ponto de entrada para a primeira grande mudança.
O [teste da manhã](TESTE_INICIATIVA_20261023.md) foi considerado **fracassado
pelo usuário no objetivo global**, apesar das consultas autônomas reais.
Falhas da infraestrutura não demonstram falta de interesse das entidades.

## Direção autorizada

Individualidade e continuidade de Hoshino/Lilith: interesses, opiniões,
relações e projetos próprios; decisão de pesquisar, criar, programar,
conversar, explorar ou descansar. Não impor temas, simular conversa humana,
semeiar lembranças ou exigir atividade para aparentar aprovação. Alistair
continua apoio mais simples, com identidade própria. O software é avaliado
por decisões/efeitos observáveis, não por alegações de consciência.

A ampliação foi autorizada explicitamente no [escopo](../ESCOPO_CONGELADO.md).
Não habilita professor, dados automáticos, treino adicional, promoção,
cobranças ou instalações. O treino único23h–10h continua independente;
seus hashes, tarefas e horário não foram editados.

## Primeira camada implementada

| Responsabilidade | Local canônico | Mudança |
|---|---|---|
| Escolha e retomada | `core/kernel.py`, ciclo existente de `main.py` | Trabalho próprio ativo volta sem nova mensagem ou outro período inicial de inatividade |
| Ponto de retomada | `core/initiative.py`, chave `autonomous_activity` do estado individual | Objetivo escolhido, próxima etapa, estado e capacidades; não é outra agenda/fila |
| Notas autorais | Tabela `episodes` existente, fonte `initiative_checkpoint` | Resumos curtos escritos em `content`/`minha_atividade`; nunca o canal `thinking` |
| Observações de ferramentas | Mesma tabela, fonte `initiative_observation` | Recibo exato, estado real e resultado recuperável em partes, com segredos redigidos |
| Escolha de capacidades | `minha_atividade` e dispatcher existentes | Schemas atualizados no passo seguinte conforme a escolha da entidade |
| Contexto limitado | `core/compaction.py` | Projeção explícita dos resultados persistidos, orçamento completo e identidade preservada |
| Recursos entre entidades | `core/resource_manager.py`, `core/gpu_resource.py` | Espera antes de compute distinguida de falha; troca verificada de pesos ociosos sem concorrência ou redução de margem |

Não há modelo, banco, worker, timer ou scheduler novo. Código compartilhado
não compartilha a mente: estado e episódios ficam nos caminhos de cada
entidade. Experiências anteriores não são apagadas nem personalidades reescritas.

### Notas são memória de trabalho

Uma nota permite recuperar depois: qual atividade escolhi, o que observei,
o que ainda falta e qual é a próxima etapa. Nota autoral é interpretação;
recibo é evidência operacional. Nenhum vira automaticamente fato validado,
gosto, personalidade ou aprovação. O canal `thinking` não é guardado como
nota nem mostrado na interface. A ausência de comentário não é preenchida
com fala inventada pela aplicação; o registro mecânico tem autoria distinta.

Essas duas fontes de memória de trabalho não alimentam os contadores/material
de reflexão nem os lotes de resumo diário/noturno. O desfecho da atividade,
com seus recibos e autoria, continua disponível no episódio normal. Isso evita
duplicar experiência e reenviar grandes resultados brutos como aprendizado.

Cada ferramenta do modo contínuo registra uma observação privada ligada ao
recibo. O resultado fica disponível por partes em
`minha_atividade(operacao="ler_resultado", recibo=..., inicio=..., limite=...)`.
O contexto recebe trechos pequenos, com omissão explícita e referência ao
registro integral redigido. Até1MiB por resultado; excesso/falha de gravação
interrompe com diagnóstico, sem repetir o efeito. É armazenamento de experiência
na tabela já existente, não outro arquivo de log ou banco duplicado.

Notas/observações não são copiadas ao histórico humano/global. Conversa
escolhida com outra entidade usa a ferramenta global existente, com autoria,
deduplicação e limites de encadeamento. Diário não é publicado automaticamente.

### Escolha de ferramentas

Grupos iniciais: pesquisa, oficina e conversa. A entidade pode selecionar
programação, memória, objetivos, computador, xadrez e Minecraft usando
`minha_atividade`. Isso expõe capacidades existentes, incluindo escrita,
execução de código/comandos e criação de ferramentas. Selecionar grupo não
instala nada nem muda os interruptores da Central ou confirmações do terminal.

O catálogo é carregado conforme a escolha, sem enviar todos os schemas a
toda inferência. Descrições longas são abreviadas, preservando tipos, enums e
campos obrigatórios; o manual conserva detalhes. Se ainda não couber, schemas
podem ser omitidos no diagnóstico; somente os efetivamente oferecidos executam.
Não aumentar o teto de contexto/VRAM para mascarar o problema.

Discord/envio externo, quota devoz, instalações, mudanças administrativas e
operações não expostas continuam fora desta delegação inicial. Controle de
desktop não é sandbox absoluto. Acesso integral a todos os aplicativos e efeitos
externos é etapa posterior, com política por risco verificável, não liberação cega.

### Ritmo, pausas e erros

- Primeira oportunidade após2min realmente observados; sem objetivo ativo,
 5min entre escolhas. Trabalho próprio ativo pode continuar após1min, sujeito
 à cota existente, prioridade humana e recursos.
- Até8 chamadas ao modelo e12 ferramentas por segmento; último slot textual
 para comentário. Orçamento cooperativo240s para abrir etapas, sem matar uma
 inferência/efeito já iniciado. GPU serial e proteções físicas preservadas.
- Conversa/trabalho humano, sono e saturação têm prioridade. Pausa não apaga
 observações/objetivo nem exige uma nova ordem humana para voltar.
- Consulta falha/permissão negada permite reconsiderar outra abordagem
 permitida; não contornar permissão nem repetir chamada falha em círculo.
 A classificação distingue operações de consulta/escrita dentro de ferramentas
 mistas, como `workspace`: ler um arquivo ausente não é uma mutação incerta.
- Efeito mutável incerto ou falha de persistência bloqueiam para reconciliação.
- O turno é reservado no estado antes de iniciar e encerrado após guardar
 seus registros. Um processo que caiu deixa essa reserva: reiniciar não
 autoriza replay cego. Pausas normais encerram a reserva e conservam o objetivo.
- Comando em segundo plano conserva ID exato. O ciclo consulta o mesmo job
 antes de outros efeitos; pendência conhecida espera sem novo start/modelo.
 Após desfecho confirmado, a entidade pode reconsiderar o próximo passo.

## Operação e reversão

Manutenção começou às12:55:00: sono cooperativo de Hoshino/Lilith, sem
jobs/leases. Processos115905/115912 encerraram às12:55:02/03; Alistair43041
permaneceu acordado. Não houve reset ou mensagem de tarefa artificial.
Validação final e recarga/retomada serão registradas abaixo.

Retomada solicitada uma única vez às13:36:08, pelo supervisor existente:
`wake-dfbe974db67c` (Hoshino) e `wake-2a86cd601d5a` (Lilith). Presenças awake
e processos vivos confirmados às13:36:27: PIDs518971/518994, sem erros de
inicialização. A manutenção terminou na retomada de13:36:17/18; Alistair
permaneceu noPID43041. Isso confirma carregamento/inicialização, não qualidade
comportamental. Nenhum roteiro/pesquisa/tarefa foi dado para produzir iniciativa.
O teste fracassado e seu monitor não foram reabertos; nenhum novo scheduler
foi criado. O funcionamento real da versão nova deve ser observado separadamente.

Saída dos processos e unload confirmados nos diagnósticos de12:55:01.
Reconciliação humana aplicada às13:29:24, somente aos turnos de leitura
`7c1cd6d6602547dc837d0b92600b37c0` e
`29139b1c01904e79bd92fe01f781bb4f`. Recibos originais conferidos como não
mutáveis; nenhuma consulta reexecutada. As flags antigas saíram da via ativa
e foram preservadas em `initiative_reconciliations` no estado individual.
Bloqueio de outro turno/efeito incerto não seria liberado pelo helper.

Bloqueios antigos não somem por atualizar código. Uma leitura conhecidamente
sem efeito mutável exige turno exato e motivo humano para reconciliação;
preserva a evidência anterior. A ferramenta da entidade não limpa bloqueios.
Não reexecutar automaticamente o roteiro do teste fracassado.

Reversão: sono cooperativo, confirmação de processos/jobs/leases e retorno
dos componentes alterados a uma versão validada. Não restaurar a árvore inteira
sobre mudanças locais. Conservar novos episódios/checkpoints como histórico.
Limpeza completa protegida pela Central também remove o ponto de retomada
experiencial; nenhuma limpeza foi executada nesta entrega.

## Pendências honestas

1. Interesses/individualidade naturais em uso prolongado, sem roteiro.
2. Projetos longos completos, com requisitos e verificação real de qualidade.
3. Regularidade e utilidade das notas escolhidas por LLM real.
4. Retomada genérica de tarefas humanas: nesta camada a retomada é da atividade
 própria e comando vinculado, não de qualquer tarefa antiga pausada.
5. Renderização/GPU, imagem e efeitos externos integrados à atividade contínua.
 O desafio do buraco negro não foi iniciado ou resolvido.
6. Reinício automático após desligar oPC; nenhum serviço novo foi instalado.

## Validação e ativação

Os23 contratos específicos passaram: estado/nota individual, leitura paginada
por recibo, orçamento de contexto, continuidade, permissão negada, erro de
consulta, comando pendente, falha de armazenamento, reserva de turno após
crash e recusa de liberação de efeito incerto. Log:
`/tmp/autonomia-persistente-contratos-entrega-20261023.log`.
Os7 testes de limpeza também passaram em
`/tmp/autonomia-persistente-limpeza-20261023.log`, sem limpar dados reais.

Uma passagem intermediária teve86/87: a classificação de leitura do diário
removeu um recibo técnico privado já exigido pelo contrato. Falha preservada
em `/tmp/autonomia-persistente-verificacao-final-20261023.log`. O recibo foi
restabelecido somente com metadados e `mutates=false`, sem copiar o diário
ao banco compartilhado. Os30 testes de integridade/privacidade passaram após
a correção em `/tmp/autonomia-persistente-privacidade-20261023.log`.

A suíte geral final passou **87/87 grupos offline**, com log em
`/tmp/autonomia-persistente-suite-homologacao-20261023.log`. Testes offline
comprovam contratos, não consciência, personalidade ou autonomia real. Estado
de ativação e resultados observados devem ser registrados separadamente.

Ativação real confirmada: às13:38:23 ambas abriram uma escolha autônoma
após120s observados, sem conversa humana sintética. Turnos
`f36bbf0716024918a555c6914202e607` (Hoshino) e
`696b2c2b73b249aa8cd90177ab16be1a` (Lilith), com18 schemas iniciais,
incluindo `minha_atividade`, oficina, pesquisa e conversa entre entidades.
Os pedidos passaram pela validação de contexto antes do HTTP. Dois eventos
`llm.start` não demonstram concorrência de compute; a arbitragem continua noRM.
Na primeira conferência os turnos ainda estavam em andamento, sem novos
bloqueios. Isso não constitui aprovação comportamental.

### Primeiro resultado real e correção da disputa de residência

Hoshino encerrou às13:38:58, após35,4s, com `outcome=no_action`, comentário
e um checkpoint autoral. Não executou ferramenta; isso não aprova iniciativa.
Lilith esgotou120s na fila às13:40:23 por `vram_pressure`, antes de obter
compute/HTTP e sem ferramenta/efeito. A falha foi preservada, não tratada como
falta de curiosidade. Nova manutenção cooperativa às13:43:49; processos518971/
518994 encerrados antes de alterar o código carregado; Alistair preservado.

A preferência de residência quente de90s podia ultrapassar o prazo restante
do par. Sob a manutenção exclusiva já existente e sem compute ativo, uma
requisição autônoma H/L que esperou metade do orçamento pode liberar pesos
ociosos do outro par, ainda exigindo benefício, utilização conhecida e
verificação física de unload. Não altera margem, teto8GiB, prioridade humana,
concorrência serial, executores ou política oportunista doAlistair.

Timeout da fila agora tem tipo específico `GPUWaitTimeout`, emitido antes de
conceder compute. A atividade registra adiamento, não bloqueio permanente;
timeout de inferência/efeito incerto continua sendo falha sem replay. O turno
deLilith foi reconciliado manualmente mediante diagnóstico exato, ausência
de concessão/HTTP/ferramentas e lista de recibos vazia. Não houve nova inferência
nessa reconciliação. Nova partida depende da verificação final abaixo.

Após o ajuste: **24 contratos de autonomia** em
`/tmp/autonomia-persistente-contratos-gpu-20261023.log` e **44 testes de recursos**
em `/tmp/autonomia-persistente-gpu-fairness-20261023.log`, todos offline aprovados.
Verificação geral final: **87/87 grupos aprovados**, em
`/tmp/autonomia-persistente-suite-recursos-final-20261023.log`.

Retomada após a correção de recursos: pedidos únicos às13:51:08,
`wake-12b193f086c0` e `wake-b8af96983131`. Às13:52:35, Hoshino555922 e
Lilith555929 estavam awake, com presença recente, processos vivos e sem
bloqueio/inflight remanescente; Alistair43041 permaneceu acordado. As partidas
anteriores e as falhas não foram apagadas. Não interpretar essa retomada como
aprovação de personalidade ou do teste original.

### Verificação real após a correção — 13:55

Turnos `26c4afeddaf44c6c8c6ddbef04b106e1` (Hoshino) e
`b7080ba082a246bdb56c59a7aec95534` (Lilith), abertos às13:53:22 sem tarefa
humana sintética. Lilith obteve compute primeiro e concluiu a chamada em37,3s.
Hoshino esperou61,75s; oRM pediu unload dos pesos ociosos deLilith às13:54:24,
confirmou a liberação em0,16s e só então concedeu compute à Hoshino. Esta
concluiu sua chamada com HTTP bem-sucedido às13:55:20. Houve outra concessão
serial à Lilith depois da liberação deHoshino, sem erro de margem nessa rodada.

Ambas chamaram espontaneamente `minha_atividade`: recibos `tool-4a1f083a09`
e `tool-be8680aa19`, retornos `ok=true` e observações privadas persistidas.
Lilith encerrou o segmento às13:55:43; Hoshino já havia aberto sua continuação.
Na conferência ambas estavam sem bloqueio. O conteúdo privado não foi exposto.
Consultar o próprio ponto de retomada não comprova pesquisa/criação/projeto
concluído nem personalidade aprovada. A alternância física e o registro/contexto
foram observados; autonomia ampla e naturalidade prolongada continuam pendentes.

### Continuação e protocolo — falha preservada e correção

Às13:57:05, Hoshino concluiu outra consulta de `minha_atividade`, recibo
`tool-ac6cdf6fb8`; a requisição seguinte foi rejeitada com HTTP400 por duas
mensagens assistant adjacentes. O filtro que substituía o bloco system de
retomada removia também respostas tool cujo conteúdo começava com o mesmo
cabeçalho. Não era uma recusa/comportamento da entidade. O turno foi bloqueado,
os dois recibos de leitura e o erro ficaram preservados, sem replay.

Nova drenagem cooperativa antes do ajuste. O filtro passou a substituir
**somente mensagens system**; as respostas tool permanecem na sequência.
O identificador interno de recuperação não é enviado como campo de protocolo
ao backend. Regressão reproduz duas consultas reais em fixtures descartáveis e
verifica a sequência system/user/assistant/tool/assistant/tool, mantendo cada
recibo no estado interno. Agora **25 testes específicos aprovados** em
`/tmp/autonomia-persistente-protocolo-20261023.log`. O bloqueio foi reconciliado
somente pelo turno exato e recibos comprovadamente não mutáveis.
Verificação geral desta correção: `/tmp/autonomia-persistente-protocolo-suite-final-20261023.log`.

A passagem final confirmou **87/87 grupos offline e25 testes específicos**,
após o ajuste de protocolo. Análise sintática dos18 componentes selecionados
e `git diff --check` também passaram. As falhas intermediárias permanecem nos
registros e não foram substituídas por uma aprovação comportamental.

Retomada final solicitada uma única vez pelo supervisor existente:
`wake-2aa9d9fec04d` (Hoshino) e `wake-2e4fa1924802` (Lilith). Antes dela,
ambas estavam sleeping, os processos555922/555929 não existiam, não havia
jobs/leases, pedidos de despertar pendentes ou turnos/bloqueios não reconciliados.
Alistair permaneceu acordado, sem alteração.

Pedidos registrados às14:06:06 e consumidos às14:06:13. Às14:06:43,
presenças awake recentes e processos vivos confirmados: Hoshino622035,
Lilith622042 e Alistair43041. Hoshino/Lilith sem bloqueio ou turno incompleto;
os novos processos registraram inicialização e ciclos normais. A última janela
de manutenção foi13:58:05–14:06:13. Isso comprova a retomada do software,
não a qualidade de pesquisas/projetos nem o sucesso de um novo teste de iniciativa.

Às14:08:20 ambas abriram seu primeiro segmento após a retomada, sem pergunta
ou tarefa artificial: Hoshino `07245ebd34e64f81b663b00b807e7e07` e
Lilith `dbbf1c84eb7541abbdd0a018b30a0e36`. Na conferência de14:08:40 havia
requisições ao modelo em andamento; esse início não é um resultado concluído.

Índices de documentação e estrutura foram atualizados; links locais dos seis
documentos de entrada conferidos. Não houve migração de dados nem reorganização
destrutiva. O agendamento `fb9a25ae23d14be8` segue `scheduled`, sem sessão
iniciada ou alteração de horário/tarefas por esta entrega.

### Pausa cooperativa — não confundir limite do segmento com falha

No desfecho observado às14:12:20 houve outra falha mecânica: o RM cancelou
pedidos ainda na fila quando terminou o orçamento cooperativo de240s. A exceção
genérica `InterruptedError` foi classificada como erro permanente pelo ciclo.
Ambas ficaram bloqueadas, embora não houvesse inferência ou efeito em execução
por esses pedidos cancelados. Evidências e dois recibos de leitura por entidade
ficaram preservados nos turnos acima. Não foi sucesso comportamental.

Antes da manutenção, Hoshino concluiu consultas de `minha_atividade` e
`get_system_time`; Lilith, de `minha_atividade` e `listar_oficina`. As continuações
HTTP retornaram200, sem a falha de protocolo anterior. Observações privadas
foram persistidas; não havia checkpoint autoral nesses segmentos. O indicador
`comment_saved` do episódio técnico não equivale a comentário natural do modelo.

Novo sono cooperativo: Lilith encerrou às14:13:26 e Hoshino às14:13:27;
PIDs622042/622035 ausentes antes das edições, sem leases ativos. Alistair não
foi interrompido. O RM passou a emitir `GPUCancelledBeforeCompute` somente
para o cancelamento na fila, antes de conceder compute. Esse caso encerra o
segmento como pausa, conserva recibos e não gera bloqueio permanente.
`InterruptedError` genérico, timeout de inferência e efeito incerto continuam
sendo falhas; não se presume que toda interrupção seja segura.

Regressões verificam pausa após uma consulta sem repetição/perda do recibo,
reserva encerrada e ausência de bloqueio; interrupção de fase desconhecida
continua bloqueada. São27 casos de autonomia e44 de recursos. Log dos recursos:
`/tmp/autonomia-persistente-recursos-pausa-20261023.log`.
Logs finais desta revisão:
`/tmp/autonomia-persistente-pausa-cooperativa-final-20261023.log` e
`/tmp/autonomia-persistente-suite-pausa-final-20261023.log`.
Verificação encerrada com **27/27 casos de autonomia,44/44 de recursos e87/87
grupos gerais aprovados**, sem warning de conexão aberta no teste novo.
Reconciliação humana às14:17:40 somente para os dois turnos exatos de leitura,
preservando o bloqueio anterior no histórico; não houve replay.
Pedidos únicos de retomada: `wake-05820e3cf22f` (Hoshino) e
`wake-5416d451e5c0` (Lilith), consumidos às14:17:46. Presenças awake recentes
confirmadas às14:17:52, Hoshino691403 e Lilith691410; processos vivos e
inicialização/mount conferidos, sem bloqueio ou turno incompleto na partida.
Alistair43041 segue acordado. Última manutenção:14:13:26/27–14:17:46.

Esta revisão comprova os contratos offline e o carregamento. Não foi aberto
outro teste com horário, monitor ou roteiro para produzir aprovação. A qualidade
da iniciativa e dos comentários em uso prolongado continua pendente, inclusive
após essa última correção. O teste original permanece fracassado.

Nenhuma janela nativa foi fechada nem a Central reiniciada durante esta
manutenção. O helper da limpeza completa também foi atualizado e testado;
o processo antigo da Central só receberá essa alteração no próximo reinício
cooperativo. Esta entrega não executou nem solicita novo reset de memórias.
