# Minecraft — progresso, decisões e validação de27/10

O humano pediu continuar junto ao Claude, recuperando sua sessão aberta, e fazer
o Minecraft funcionar preservando decisões próprias da Lilith. A sessão original
`4fd85b9d-9858-4f5c-8b34-55debb0b8f12` foi lida e retomada numa cópia
`5d19dd78-475f-4577-8c9c-a7af8eded417`, somente leitura. A janela interativa
original não foi controlada ou interrompida. Codex implementa; Claude orienta
e faz uma revisão fresca separada. Relatórios CLI ficam em`/tmp/claude-minecraft-architecture-20261027.json`
e`/tmp/claude-minecraft-code-review-20261027.json`.

## Problema e implementação

O laço antigo tratava movimento, fome e qualquer item adicional como progresso.
Isso conservava um plano errado indefinidamente. Cada decisão também recebia
recibos extensos e22ferramentas, sem uma trajetória curta de efeitos.

- `minecraft_cognition.py` projeta faltas finais, materiais observados e até6
  transições com deltas reais e recibos. Falta de receita permanece desconhecida.
  O sinal de estagnação é informativo e separado do limite de ausência de efeito.
- O próprio9B escolhe uma meta intermediária estruturada quando necessário.
  Item/total são validados contra fatos observados; ter o item não comprova
  fabricação do objetivo. O plano textual anterior permanece guardado e marcado
  quando foi anterior à nova meta. Notas são identificadas como propostas pendentes.
- A entidade escolhe entre possibilidades concretas: fabricação cujo inventário
  atende à receita, aproximação de estação observada, coleta de recurso visto,
  equipamento realmente disponível e colocação do bloco segurado. Os argumentos
  vêm desses fatos, sem segunda inferência para reinterpretá-los.
- `outra` abre o catálogo nativo completo; pesquisa e consulta de receitas
  continuam disponíveis diretamente. Não houve remoção de permissões nem cadeia
  automática de receitas. O dispatcher reconfere as pré-condições antes do efeito.

Essa estrutura usa o princípio de feedback de ambiente/erro/verificação descrito
no [Voyager](https://voyager.minedojo.org/assets/documents/voyager.pdf), preservando
o executor local e os recibos deste projeto. Não importou seu executor de código,
currículo ou dependências cloud.

## Reconciliação anterior

O pedido`mc-e4615642dff04370a0e778916425fca2`/recibo`tool-6320f4a0fb`
foi revisto explicitamente por Codex. O diagnóstico próprio da ponte registra
item ausente no guard síncrono anterior a`b.equip`; o corpo da função no commit
9ea03de confirma que não há envio anterior. Backup do checkpoint e revisão
atribuída estão em`compartilhado/runtime/ensaios/minecraft-reconciliation-20261027/`.
O recibo incerto original permanece; a pendência foi reconciliada como sem envio,
sem repetir equipamento nem limpar outros erros. Isso é manutenção do condutor,
não ação autônoma da Lilith.

## Ensaios sem efeitos no mundo

Estado congelado da última percepção do runner2976057:6oak_log,2oak_planks,
4stick, sem bancada no inventário. O teste usa o caminho real de inferência do
9B e o RM, mas substitui observações por esse snapshot e bloqueia execução,
gravação da tarefa e notas nas memórias. Não há fabricação real nesse teste.

Mesma semente20261027, temperaturas0,75e0,3, duas amostras por versão:

| Versão | Escolha0,75 | Escolha0,3 |
|---|---|---|
| Baseline | equipar bancada ausente | equipar bancada ausente |
| Só meta/retorno compacto | consultar estado | coletar mais troncos |
| Meta + possibilidades observadas | fabricar tábuas | fabricar tábuas |
| Após correções da revisão | consultar inventário via catálogo completo | fabricar tábuas |

Arquivos locais:`/tmp/minecraft-frozen-results-20261027.json`,
`/tmp/minecraft-frozen-options-results-20261027.json` e
`/tmp/minecraft-affordance-spike-20261027.json`. A versão final foi reconferida
em`/tmp/minecraft-frozen-reviewed-results-20261027.json`: uma fabricação escolhida
e uma consulta legítima; isso não comprova que todas as próximas decisões avançam.
Amostra pequena, sem afirmação
estatística ou comparação válida de velocidade: cache/carga fria diferem.

Testes focados após a revisão:54do núcleo e145de prontidão passaram. A suíte geral da versão
com possibilidades passou96/96grupos, exit0, em
`/tmp/minecraft-options-suite-20261027.log`. Isso verifica software, não aprova
ainda a progressão real no jogo.

## Revisão fresca e correções

Claude, sessão nova`02894c00-e1af-4203-9eae-a8408bc8e681`, encontrou dois
problemas importantes: a meta só admitia crescimento do inventário e podia
barrar colocação/equipamento; e o resumo cortava informação útil de pesquisa,
busca de blocos e forno. Também apontou transições não comparáveis produzindo
ganhos/perdas fictícios, e empate de número de passo no aviso do plano anterior.

Um passe de correção RED→GREEN resolveu os quatro: escolha explícita
`acao_direta/total0`, sem exigir outra aquisição; caminho do Alistair conserva
protocolo anterior; saídas informativas mantêm até1200caracteres; deltas são
desconhecidos entre observações inválidas/sessões diferentes; e o plano anterior
é marcado pela ordem real de escolha, inclusive sem incremento de passo.
O achado da transição foi tratado como importante por afetar contexto factual.
Nenhum achado foi descartado ou diferido. Não houve segunda revisão.
Verificação posterior às correções:96/96grupos, exit0, em
`/tmp/minecraft-reviewed-suite-20261027.log`.

## Ensaio físico e limitações

Retomada física iniciada às06:49de27/10, entrada única
`in-local-test-minecraft-40613-picareta3`, runner3130060, tarefa preservada
`ct-525f53c453`. Ponte iniciada por escolha da entidade; um nome de jogador
divergente foi recusado antes de executar e ela corrigiu paraLilithMC.
Fabricação real da picareta e progressão ao kit de ferro ainda pendentes.
Nada foi aprovado por texto otimista, meta intermediária ou ensaio congelado.
Relatório será atualizado com recibos.

Nessa retomada a entidade fabricou4oak_planks (`tool-ab9a8db255`, troncos6→5,
tábuas2→6) e1crafting_table (`tool-3f92942a4c`, tábuas6→2). Sessão
`32751da3f2`; inventário real confirmou a bancada e nenhuma picareta ainda.
Há também uma bancada já colocada em(-96,69,-61), observada a0,3bloco.

Após a fabricação, o seletor de meta repetiu seis propostas de obter uma bancada
que já estava disponível. A correção anterior oferecia uma saída explícita,
mas ainda barrava a ação se a proposta fosse inválida: o achado1 da revisão
não estava suficientemente resolvido. Tarefa pausada sem efeito pendente.
Sono cooperativo e0jobs/leases foram conferidos antes de corrigir.

Regressão reproduzida e corrigida: proposta opcional recusada agora vira retorno
factual para uma escolha de ação independente, sujeita às mesmas validações.
Não aceita o item inválido, não executa sua proposta nem limpa falhas. Há intervalo
de3operações entre revisões, inclusive se a meta anterior está cumprida.145testes
de prontidão verdes; ensaio congelado do estado após a bancada escolheu equipar
o bloco realmente presente, em17,217s, sem agir no mundo. Log:
`/tmp/minecraft-after-table-probe-20261027.log`.
Suíte posterior a essa correção:96/96grupos, exit0,
`/tmp/minecraft-optional-meta-suite-20261027.log`.

Antes da manutenção foi preservada a identidade do listener40613 (java6619,
fd275, inode41330), além dos recibos e inventário. Nova sessão do bot após a
recarga exigirá revisão atribuída da continuidade antes de aproveitar progresso.

## Encerramento pedido pelo humano e nova porta34993

O humano informou que o Minecraft travou mouse/teclado e pediu fechá-lo.
Codex conferiu UID, classeKnotClient e identidade de início do processo6619,
enviouSIGTERM e confirmou sua saída em menos de1segundo. A porta40613 foi
liberada. Lilith dormiu cooperativamente,0jobs/leases; tarefa pausada sem ação
pendente. Não houveSIGKILL nem encerramento por nome/porta.

Não foi estabelecida a causa do travamento: a janela consultada do kernel tinha
avisos de duração de trabalho doAMDGPU, mas nenhumOOM/reset deGPU. Isso não
prova relação causal com a inferência. Nenhum ajuste de driver, modelos ou
parâmetro físico foi feito para mascarar o problema.

O humano reabriu o mundo e informou **34993**. Ping do protocolo confirmou
Minecraft1.16.5/protocolo754,1jogador. O listener antigo não vale como prova
de continuidade desse mundo reaberto. Recibos anteriores permanecem preservados;
a nova etapa deve conferir inventário e fabricar a picareta com novo recibo.

Na tentativa anterior de recarga, depois de iniciar a ponte, o modelo repetiu
`minecraft_estado` antes da conexão. O esquema permitia essa consulta no setup,
mas o agente exigia mundo já conectado para executá-la. Reprodução RED→GREEN:
consulta de estado e descobertaLAN agora são operações pré-conexão; a escolha
técnica oferece conectar ao destino explícito, consultar estado e catálogo livre.
Host/porta/versão/jogador vêm do pedido humano, não de uma inferência adicional.
56testes do núcleo e146de prontidão passaram; suíte posterior96/96grupos,
exit0, `/tmp/minecraft-setup-new-port-suite-20261027.log`.

A tarefa existente`ct-525f53c453` teve somente a porta do objetivo/destino
alterada por Codex, a partir da nova instrução humana explícita. Backup e
registro atribuído ficaram em`port-40613-to-34993.before.json` no diretório
de reconciliação. Critérios físicos e recibos foram preservados, sem limpar
falhas ou autorizar transferência automática de sessão. A sessão anterior
permanece registrada até conferir o inventário/mundo após a conexão34993.

## Picareta de madeira concluída; próximo objetivo humano

Runner3179529 conectou por escolha`conectar_destino` em34993, recibo
`tool-c56f875b55`, sessão`13e24e03d4`. Inventário completo coincidiu com a
última fabricação e a bancada(-96,69,-61) foi reencontrada. Codex registrou
revisão atribuída32751da3f2→13e24e03d4 com recibos de observação
`tool-3e1fdc1ae5`/`tool-046f12a8ed`; não houve ação de jogo do condutor.
Entrada`in-local-test-minecraft-34993-picareta2` retomou a mesma tarefa.

Às07:19:23 a Lilith fabricou mais4oak_planks (`tool-098bf43a84`). Às07:19:35
fabricou1wooden_pickaxe (`tool-bdf255730b`), consumindo3tábuas e2gravetos.
O verificador concluiu`ct-525f53c453` com recibo+inventário. Observação independente
`tool-24cfa6ff95` confirmou a picareta; `tool-f9c189a0d5` confirmou a bancada
já colocada. Isso conclui esse marco supervisionado, com intervenções de
manutenção/recortes registradas; não prova autonomia integral ou kit de ferro.

O humano orientou explicitamente: primeiro picareta de pedra, depois procurar
ferro e carvão, informando que existem recursos por perto sem coordenadas.
Nova tarefa`ct-24e782eb06`, entrada`in-local-test-minecraft-34993-pedra1`,
mantém o kit de ferro como objetivo posterior. A entidade coletou3pedras,
obtendo3cobblestone (`tool-3cbdcfac87`, `tool-a117263b7f`, `tool-f9dcc8357f`).
Às07:27:44, fabricou1stone_pickaxe, recibo`tool-69b64c4056`, consumindo
3cobblestone e2stick. A tarefa`ct-24e782eb06` concluiu com5passos e sem
efeito pendente; consulta independente da ponte confirmou o item no inventário,
vida20 e sobrevivência, sessão`13e24e03d4`. A meta intermediária autoral de
10bancadas era inadequada, mas não impediu a fabricação final; o registro foi
preservado. Não transformar esse subobjetivo em recomendação ou prova de bom planejamento.

Após confirmar o marco, Codex enviou uma única entrada de condução identificada,
`in-local-test-minecraft-34993-ferro1`, conversa`codex_mc34993_ferro`.
Tarefa criada:`ct-06c691fa40`. Objetivo verificável: fabricar/equipar o kit
completo de ferro. O RP transmite
a orientação humana de procurar ferro/carvão por perto, sem inventar coordenadas
nem executar ações de jogo pelo condutor. Ainda não há aprovação desse marco.

Às07:33:39 e07:33:57 a entidade escolheu/coletou carvão, recibos
`tool-5ec9ef3ae2` e`tool-6ffca1d786`. Observação independente confirmou2coal,
picareta de pedra preservada, vida20 e nenhuma ação pendente naquela consulta.
São resultados intermediários reais; não comprovam obtenção de ferro ou o kit.

Não foi acrescentado renderizador da câmera do bot. A visão do9B já comprovada
com imagens não equivale a receber visão em primeira pessoa do Minecraft.

## Passagem solicitada para o Claude Code

O humano pediu organizar/documentar o estado para o Claude continuar. Snapshot
de27/10 às07:51:28: tarefa`ct-06c691fa40` ativa,29passos, sem efeito pendente;
runner3179529 e Central136924 vivos, inferência com leaseRM em andamento.
Inventário:12coal,33cobblestone, ambas as picaretas, nenhum ferro/forno/armadura.
Vida20, comida14, posição(-111,64,-61), mesma sessão`13e24e03d4`/porta34993.

O aumento de pedregulho sem ferro é estagnação do objetivo a investigar, não
aprovação. A meta autoral`iron_ingot18` foi escolhida no passo28 e não substitui
o contrato final. Hipóteses e procedimentos seguros estão no
[handoff operacional](HANDOFF_CLAUDE_MINECRAFT_20261027.md). A passagem é documental:
nenhuma nova entrada, despertar, repetição, recarga ou ação de jogo do condutor.

## Estagnação pedra/carvão: causa demonstrada e correção (Claude, 27/10 manhã)

Reconciliação às07:58: a tarefa`ct-06c691fa40` já estava **pausada desde07:54:08**
pelo limite de ausência de efeito (`no_progress`6),32passos, sem pendência, 0jobs/
leases; runner3179529 ocioso. Nada foi interrompido em execução.

Trajetória: ~20coletas seguidas de`stone`/`coal_ore`, três `web_search` sobre ferro,
um`ir_para` até y232 (sem movimento real) e meta autoral`iron_block`18. Nunca
houve tentativa de`iron_ore`.

**Causa demonstrada:** a percepção`arredores` do último recibo continha somente
`stone` com quantidade256. A ponte fazia uma única busca de todos os tipos úteis
limitada a256resultados; numa área de pedra, a pedra ocupava todas as vagas.
Consulta somente leitura do condutor (`find_blocks`, sem efeito de jogo, autoria
Claude) encontrou`iron_ore` a9,7blocos (y55–58) e`coal_ore` a5,7. As opções
observadas derivam dessa percepção; por isso ferro nunca foi oferecido.
O limite de256 foi introduzido pelo próprio Claude em26/10.

Lacunas relacionadas na mesma cadeia:

- `recipesAll` não contém fundição; para`iron_ingot` a análise mostrava só
  `iron_block`→9 e`iron_nugget`×9, induzindo a meta`iron_block`.
- metas autorais aceitavam apenas itens do inventário/receitas, não blocos vistos.
- forno ausente lançava erro comum antes do efeito (viraria resultado incerto).

Correção (commit`a50959d`), RED→GREEN, sem sequência de jogo:

- uma busca por tipo de bloco (até64, “64+” quando saturado);
- variante de fundição como fato (`processo: fornalha`, minério→lingote, forno a
  4blocos, combustível), nunca convertida em`minecraft_craft`;
- `furnace_preconditions` sem efeito com recibo exato;
- metas aceitam blocos obtíveis observados (minério, tronco, pedra);
- opções observadas: fundir quando há forno próximo, minério e combustível; vestir
  armadura do inventário no slot real.

Contribuição não corrigida: coletar pedra muda o inventário e conta como efeito,
então o limite de ausência de efeito não pausa uma coleta incidental repetida;
o monitor auxiliar reinicia a base quando a meta muda. Mantido como observação
até medir o comportamento com a percepção corrigida.

Verificação:59casos do núcleo,146de prontidão,24de integração e35regressões
da ponte; suíte96/96grupos. Sono cooperativo antes da edição (runner e ponte
saíram, porta8766 liberada,0jobs/leases, sem pendência). Retomada com uma única
entrada identificada`in-local-test-minecraft-34993-ferro-resume1`.

## Resultado real do ferro e nova parada (Claude, 27/10 08:06–08:28)

Com a percepção corrigida, na **primeira decisão** após a retomada
(`in-local-test-minecraft-34993-ferro-resume1`, 08:07:16) a entidade escolheu
`minecraft_coletar iron_ore` e obteve o primeiro minério. Antes da correção,
em ~20 coletas seguidas, nunca havia tentado ferro.

Progresso com recibo nessa janela: 3 coletas unitárias de `iron_ore`
(08:07:16, 08:07:50, 08:08:21), tentativa de fundir sem forno recusada como
pré-condição sem efeito (08:09:26, comportamento novo e correto), consulta da
receita do forno, mais 1 minério (08:21:38), **10 minérios numa coleta só**
(08:24:13) e pesquisa própria da fundição (08:24:43). Último estado observado
(sessão `8f4cf4bac4`, 08:28): **16 iron_ore**, 12 coal, 94 cobblestone,
3 crafting_table, 7 oak_planks, vida 20, fome 13, armadura vazia.
**Kit de ferro continua não aprovado:** nenhum lingote, forno, ferramenta ou
peça de armadura de ferro existe.

### Parada 1: ponte Node sem memória (não é decisão da entidade)

Às 08:28:41 a ação `collect` recebeu `RemoteDisconnected`. O log próprio da
ponte (`entidades/lilith/runtime/minecraft/laboratorio.log`) termina com
`FATAL ERROR: Ineffective mark-compacts near heap limit — JavaScript heap out of
memory`, após ~477 s de execução, com heap em ~3,9 GB/4 GB. A ponte (PID
3458778) morreu durante o pedido; o runner seguiu vivo e a tarefa pausou.

Consequência tratada corretamente: o pedido
`mc-84424afba5044534b741d6e1af61651b` / recibo `tool-95808ea944` ficou
**incerto e preservado**, com `pending` do checkpoint intacto. Não houve replay,
nem reconciliação: foi enviado de verdade e o desfecho é desconhecido. O
inventário observado depois mostra 16 `iron_ore`, mas isso não identifica se a
unidade final veio desse pedido.

Causa do consumo de memória **ainda não investigada** (hipóteses: acúmulo em
pathfinder/collectblock durante coletas longas, ou retenção do próprio
diagnóstico). Não houve ajuste de limite de heap nem reinício automático para
mascarar o problema.

### Parada 2 (anterior, corrigida): revisão aplicada só ao checkpoint

Às 08:10:32 o ciclo parou porque `minecraft_equipar crafting_table` foi barrado
por assinatura idêntica ao recibo antigo `tool-6320f4a0fb`, que o Codex já havia
revisado como “não enviado” — mas só no checkpoint, não no `job_bus`. O
dispatcher agiu certo ao recusar. Correção em `0630956`: `job_bus.resolve_reviewed`
aplica a revisão atribuída ao diário (exige revisor, resolução e evidência,
preserva o desfecho original, recusa recibo inexistente ou já revisado) e
libera apenas a assinatura. A tentativa nova (`tool-e84e78821f`) foi registrada
como `blocked_before_send` com evidência (sem RPC de equip na ponte, 6 ms entre
`tool.start` e o desfecho). Backups e revisões em
`compartilhado/runtime/ensaios/minecraft-reconciliation-20261027/`.

### Achado aberto: meta autoral incoerente com a própria nota

O histórico de metas mostra a escolha repetida de `crafting_table` **total 20**
(quatro vezes), com a nota dizendo “colocar/equipar a mesa de trabalho para
fundir minério”. A nota descreve uma ação direta; o item/total pedem 20 bancadas
no inventário. Isso coincide com a observação humana de que ela refaz tábuas e
bancadas em vez de avançar: ela já fabricou 3 bancadas e segue “faltando 17”.
A saída `acao_direta`/`total 0` existe e não foi usada. Hipótese a reproduzir:
o seletor de meta pede item+total mesmo quando o próximo passo é posicional,
e a validação aceita um total alto sem relação com a nota. Não corrigido nesta
pausa; nenhuma sequência de jogo foi inserida para contornar.

### Achado aberto: desgaste de ferramenta invisível

A `stone_pickaxe` fabricada às 07:27 **não está mais no inventário** observado
às 08:28 (quebrou por durabilidade). No 1.16.5 a picareta de madeira não minera
ferro, então novas coletas de `iron_ore` tendem a falhar sem que percepção ou
retorno expliquem a causa. Hoje nada informa durabilidade ou ferramenta exigida
por bloco. Material para refazer existe (94 cobblestone, 7 oak_planks), mas a
decisão é dela.

### Sobre “ler o pensamento dela”

O canal `thinking` **não é armazenado** neste projeto: os diagnósticos guardam
apenas tamanho e hash (ex.: `thinking_chars: 1086`), por decisão registrada em
`CLAUDE.md` (não expor cadeia de pensamento privada). O que existe e é legível
são as **notas de meta** e os comentários autorais ligados a recibos; no caminho
de opções observadas ela não escreveu comentários nesta janela, e as notas estão
transcritas acima.

### Estado na pausa

Lilith dormindo por sono cooperativo (runner e ponte saíram, porta 8766 livre,
0 jobs/leases). Tarefa `ct-06c691fa40` pausada, 53 passos, **com efeito incerto
preservado**. Suíte offline 96/96 após as duas correções
(`/tmp/claude-1000/.../scratchpad/suite-review.log`). Commits desta sessão:
`a50959d` (percepção por tipo, fundição, forno) e `0630956` (revisão no diário).
Alterações alheias no working tree preservadas e não commitadas.

## Continuação (Claude, 27/10 08:40–14:05): infraestrutura e ligação meta→ação

Todas as correções com RED→GREEN, sono cooperativo antes de recarregar
(saída confirmada por `ps`), suíte 96/96 antes de cada commit e revisão
atribuída de sessão a cada reconexão. Nenhuma ação de jogo foi executada pelo
condutor; leituras de saúde da ponte e uma consulta `find_blocks` (somente
leitura) estão registradas como observação do condutor.

### Correções carregadas (commits)

| Commit | Causa demonstrada | Correção |
|---|---|---|
| `89c2a6b` | Ponte morreu por heap (3,9 GB) numa coleta: pathfinder `searchRadius -1` cavando no subsolo | Limite de desvio da busca; heap por pedido no diagnóstico. Coletar/minerar sem a ferramenta exigida (`harvestTools`) recusa antes do envio; percepção mostra `ferramenta_ok`. Meta de estação já possuída com total >1 vira retorno |
| `887fd53` | `goto()` da biblioteca rejeita `NoPath` mas mantém o objetivo; ela andou de y51 a y69 depois do erro | Objetivo limpo em qualquer falha; `goto_no_path` sem efeito só se a posição não mudou |
| `c47cf9e` | O mesmo na coleta (andou e cavou depois de `NoPath`); limite 32 gerava `NoPath` ao sair de cavernas | Objetivo limpo; `collect_no_path` só com posição, inventário e bloco alvo intactos; desvio 64 |
| `0b78831` | Metas sem raciocínio: `crafting_table 20`, `coal 20`, `coal_block 30`; opção de fabricar bancada com 3 no inventário | Meta segue `THINKING`; estação possuída não é oferecida para fabricar |
| `7469616` | Meta com raciocínio esgotou a saída e derrubou a decisão inteira | Falha da meta opcional vira retorno; decisão segue; saída 4096 |
| `1c7e2e1` | Revisão de sessão repetida com código manual | `scripts/minecraft_revisar_sessao.py` (salvar/revisar; só com estado idêntico) |
| `20cb728` | `collectBlock` pegou o carvão e não resolveu; cliente expirou em 90 s | Orçamento de 75 s; resultado pelo inventário, `interrompida` |
| `0a1a108` | Fundição dizia `exige_forno`, mas `furnace` nunca era analisado | Forno entra na percepção e nas metas como a bancada |
| `b977383` | Com 20 carvões ela seguia coletando carvão | Opção de coleta informa o que o bloco solta e quanto já há |
| `2f5b57a` | Meta autoral certa (`furnace 1`), ação seguinte errada; `fabricar:furnace` era a 1ª opção e não foi escolhida | Opções indicam quando atendem a meta atual ou quando ela exige bancada próxima. **Não carregado ainda** |

Heap da ponte com limite: 31–41 MB por pedido (contra 3,9 GB sem limite).

### Reconciliações atribuídas (sem replay)

Em `compartilhado/runtime/ensaios/minecraft-reconciliation-20261027/`, com
`.before.json` e `.review.json`, aplicadas por `job_bus.resolve_reviewed`
(desfecho original preservado):

- `tool-95808ea944` coleta durante o OOM: desfecho desconhecido; o inventário
  posterior mostrou que nenhum minério foi obtido.
- `tool-23deb9b12d` ir_para `NoPath` → efeito tardio real observado.
- `tool-6d2f9e3380` coleta `NoPath` → deslocamento e escavação tardios reais.
- `tool-57b036c8d3` coleta pendurada → 1 carvão obtido, conforme pedido.
- `tool-be4b4eeb73` coleta `NoPath` depois de cavar 3 pedras, sem carvão.
- Seis revisões de continuidade de sessão, todas com posição e inventário idênticos.

### O que a Lilith fez (recibos)

Escolhas por opção nesta data: `coletar:coal_ore` 21, `coletar:stone` 18,
`outra` 10, `conectar_destino` 9, `coletar:iron_ore` 9, `fabricar:oak_planks` 5,
`aproximar:crafting_table` 5, `fabricar:crafting_table` 4, `estado` 4.
Recusas corretas antes do efeito: ferro com picareta de madeira (13:18:19).
As metas evoluíram com raciocínio para `iron_ingot 8` e depois `furnace 1`.
**Ainda não fabricou o forno nem lingotes.** Kit de ferro não aprovado.

Último estado observado antes da pausa (sessão `abe35da337`): 16 iron_ore,
20 coal, 116 cobblestone, 4 crafting_table, 1 oak_log, 3 dark_oak_log,
1 wooden_pickaxe (a de pedra quebrou), posição (-98, 69, -62).

### Mudança externa não explicada (não atribuída à Lilith)

Entre 13:59:52 (último pedido dela, coleta reconciliada acima) e a leitura de
saúde do condutor antes do sono, `oak_planks` passou de 3 para **131** e a
posição de (-101, 62, -55) para (-98, 69, -62). **Não há nenhum pedido da
entidade à ponte nessa janela** e ela tinha só 1 `oak_log` (4 tábuas).
Origem a confirmar com o humano (jogador no mundo, comando ou outro meio).
Esse inventário não pode ser usado como progresso da entidade.

### Limitações honestas

- A interface agora oferece fatos e opções corretos; a escolha da ação
  continua sendo o limite principal do 9B (laço de carvão/pedra).
- Cada recarga custa ~5–6 min (sono, despertar, reflexão, trava de sessão,
  revisão). Ajustes pequenos foram agrupados quando possível.
- Uma checagem do condutor com `pgrep -f` deu falso positivo (casava com a
  própria linha de comando); substituída por `ps` filtrado. Não houve duplicata.

### Estado na pausa (≈14:05)

Lilith dormindo (0 processos, 0 jobs/leases), tarefa `ct-06c691fa40` pausada
sem pendência, 85 passos. Commit `2f5b57a` testado mas ainda não carregado.
Próximo passo ao retomar: recarregar, revisar sessão com o script e observar se
a ligação meta→opções leva ao forno; depois fundição e ferramentas de ferro.
