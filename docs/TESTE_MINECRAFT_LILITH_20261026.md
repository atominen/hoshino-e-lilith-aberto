# Ensaio interativo — Lilith no Minecraft — 26/10/2026

Continuação e revisão em27/10:[coordenação Codex/Claude](COORDENACAO_CODEX_CLAUDE_20261027.md).
Esse registro traz a visão9B confirmada, correções de recibos pós-envio e
conclusão integral, e a exigência de reconciliação atribuída após mudança de
sessão com progresso. O alvo mais recente é40613;37837 abaixo é histórico.

## Critério

Autorização humana: Lilith, mundo LAN atualizado pelo usuário para **Java1.16.5,
Fabric, porta37837** (substitui36365,40601 e o alvo inicial1.16.1/35229); interação com
RP conduzido por Codex, progressão normal e objetivo final de fabricar e
equipar quatro peças de armadura de diamante. Sem cheats, itens concedidos,
teleporte ou ações do assistente contadas como decisões da Lilith.

As primeiras mensagens do condutor usaram `teste_local`; a execução corrigida
usa o adaptador operacional existente `local`, autor Codex, com
`synthetic_test=true`. A origem é `sistema_teste`; o escriba não usa o roteiro
para aprender nomes, personalidade ou fatos humanos. Resultados do mundo,
tentativas operacionais e comentários autorais são evidências distintas.

## Partida durável

- Central aberta uma vez pelo lançador existente: supervisorPID144667,
  API autenticada respondeu200, painel de fontes respondeu e a UI nativa foi
  solicitada pelo mesmo app. PIDs são amostras da execução, não prova permanente.
- Lilith foi iniciada pelo supervisor; os originais9B/7B selecionados estavam
  instalados. Nenhuma conversão, instalação, treinamento ou troca de pesos.
- Entrada inicial: `in-test-minecraft-lilith-20261026`, recebida às12:15:51
  America/Sao_Paulo. Objetivo persistido como `ct-25e41471cc`.
- Primeira tentativa: bloqueio do controlador, antes da conexão. O plano expôs
  apenas fabricação e estado; o modelo tentou colocar um nome de ferramenta
  no argumento de item. Isso não fabricou item nem conectou ao servidor.
  **Tentativa sem progresso de jogo.**

## Manutenção e correção

Sono cooperativo solicitado, sem kill. Conferidos sleeping, zero jobs ativos
e zero leases antes de editar o runner. Duas regressões foram reproduzidas:
o planejador não podia escolher pré-requisitos de Minecraft, e o gate exigia
um bot já conectado para iniciar sua própria ponte.

Corrigido no controlador: ferramentas Minecraft autorizadas ficam disponíveis
como opções do planejador, sem virar uma lista obrigatória nem liberar outras
capacidades; iniciar a ponte é permitido antes da conexão. Testes focados:
113 de prontidão e41 de contexto/execução. Roteiro e objetivo preservados.

Retomada pelo supervisor, nova amostraPID208887. Entrada
`in-test-minecraft-lilith-20261026-resume1` informa a manutenção com autoria
de teste e pede retomada do mesmo objetivo. Sem repetir login, mineração ou
fabricação já executados — essas ações ainda não tinham ocorrido.

## Resultado em andamento

### Atualização humana do mundo

O usuário substituiu o alvo por **Minecraft Java1.16.5, Fabric, porta40601**.
Consulta de status confirmou versão1.16.5, protocolo754 e um jogador. Isso
não comprova login do bot nem compatibilidade de todos os mods. Não usar os
parâmetros antigos nas ações seguintes.

Segunda tentativa ainda esbarrou no recorte do controlador: texto com nomes
`minecraft_*` não era reconhecido como domínio Minecraft pela expressão de
palavra inteira. Novo caso RED→GREEN;114 testes de prontidão verdes. Sono
cooperativo, zero jobs/leases antes da correção; sem ações de jogo nesse trecho.

Nova conversa operacional do mesmo ensaio (`codex_minecraft_40601`) isola o
alvo atualizado do plano antigo pausado. Entrada
`in-test-minecraft-lilith-20261026-world40601`, recebida às12:33:48 locais.
Primeiro marco explícito: conectar e observar o mundo, sem declarar aprovação
da sobrevivência/armadura. O modelo elaborou às12:34:20 locais a sequência
manual→ponte→conexão→estado→inventário→relato, escolhendo dentre ferramentas
Minecraft autorizadas. Plano não é execução; os próximos recibos ainda devem
confirmar cada efeito.

### Correções do condutor e inicialização integrada

O canal inventado `teste_local` não possuía permissões de ferramentas. A política
foi preservada e o condutor passou a usar o adaptador `local` existente, com
autoria `sistema_teste` explícita. O ensaio não atualiza a presença/nome do humano,
não alimenta extração automática de memórias humanas e não dispara TTS pago.
Roteiro, recibos e falas da entidade continuam identificáveis como teste.

Versão/IP de rede estavam acionando a heurística de cálculo, e a palavra
Minecraft estava acionando a de fabricação pela substring `craft`. Casos
RED→GREEN corrigem a identificação de dados e do domínio, preservando expressões
matemáticas reais. Porta explícita usa conexão direta; descoberta LAN continua
disponível quando o endereço não foi informado.

`minecraft_conectar` agora prepara a ponte interna própria quando ausente, sem
criar outro servidor, baixar dependências ou exigir outro executável do usuário.
Processo próprio sem saúde confirmada bloqueia uma duplicata. Recarga cooperativa
da mesma Central: PID144667 saiu e porta8769 ficou livre antes do novo
supervisor320518. Nenhuma janela foi morta; modelos e dados preservados.

### Primeiro efeito real confirmado

Entrada `in-local-test-minecraft-40601-bootstrap`, runner320532. Às12:57:39
America/Sao_Paulo, recibo `mc-e520461a003b43759b28e867eaceda39` confirmou conexão
`ready`, sessão `92e944a482`, **LilithMC,1.16.5,survival**, posição(-95,69,-63),
vida20, fome20, inventário vazio e quatro slots de armadura vazios. Uma consulta
posterior independente de saúde e estado confirmou os mesmos fatos. Isso prova
entrada no mundo informado; não prova progressão ou armadura.

O relato posterior falhou antes de inferir: necessidade estimada16689tokens
excedeu16384. O gatilho antigo compactava somente após doze mensagens; um
manual grande esgotou o orçamento antes disso. Sono cooperativo confirmado,
runner320532 encerrado, zero jobs/leases. Dois casos RED→GREEN passaram dentro
de116 testes de prontidão: etapas textuais agora medem tokens e projetam as
transições antigas pelo estado persistente, preservando identidade, pedido,
últimos pares de ferramenta e fontes integrais duráveis. Janela, pesos e limite
de saída não foram ampliados, e a ação de conexão não foi repetida às cegas.

A ponte própria encerrou com o runner; ausência confirmada antes da nova partida.
Runner348880 acordado pelo mesmo supervisor. Entrada nova e identificada
`in-local-test-minecraft-40601-survival1` informa a manutenção e solicita o marco
de recursos/ferramentas básicos, com nova conexão somente se desconectada.

### Negação e contrato de argumentos

Essa tentativa foi classificada como estrategista por conter “não apenas planeje”,
e suas ações foram bloqueadas antes da ponte. O controlador agora distingue
essa frase de “não execute”; casos RED→GREEN em41 testes de atividade. Nova
partida cooperativa, runner382186, entrada `survival2`.

Às13:10:26, a própria entidade conectou pela descoberta LAN ao mesmo mundo
`10.0.0.102:40601`,1.16.5,survival. Tentou coletar com `nome=minecraft_coletar`,
confundindo nome de ferramenta e bloco. O pedido
`mc-2e40b0af2f1c4f40aef6d7dd0d34ae38` recebeu erro400 e o cliente o preservou
como incerto, sem replay. Reconciliação do log próprio da ponte mostrou rejeição
na linha368, por bloco inexistente, antes de definir ação ou iniciar coleta.
Estado posterior: vida20, fome20, inventário vazio. **Nenhum recurso obtido.**

Investigação encontrou o contrato JSON apenas no campo de formato do transporte,
sem seus campos e significados no pedido textual do formatador. Esse contrato
agora é explícito no prompt, as ferramentas descrevem IDs de blocos/itens e a
validação rejeita nome de ferramenta usado como item antes de qualquer RPC.
Teste RED→GREEN verifica correção dos argumentos dentro da inferência, sem
executar a chamada inválida;117 testes de prontidão verdes.

Sono cooperativo, runner382186 saiu, zero jobs/leases. A evidência incerta antiga
foi preservada; não foi repetida nem apagada. Runner407983, entrada
`in-local-test-minecraft-40601-survival3`, pede novamente o marco básico após
explicar a manutenção e a rejeição comprovadamente anterior a qualquer efeito.
O condutor não forneceu uma sequência de mineração/fabricação pronta, e não
executou ferramentas de jogo em lugar do modelo.

### Recursos reais e marco de fabricação

`survival3` conectou diretamente às13:14:13 e a entidade escolheu `oak_log`.
A coleta `mc-5a91816bbaf74466bd7258bc206d7c6b` obteve **3 troncos** e então
falhou no pathfinder (“Took to long to decide path to goal”). Log exato e estado
posterior confirmaram término: ação/navegação nulas, vida20, fome20 e3oak_log.
O resultado parcial é real e foi preservado. Nenhuma coleta foi repetida pelo
condutor. Não é falha de conexão nem aprovação da meta de equipamentos.

Novo pedido identificado `tools` informou essa reconciliação e pediu bancada e
picareta com os recursos existentes. A projeção de contexto funcionou em inferência
real, com resposta200. Porém, a entidade somente consultou inventário/estado e
produziu uma fala sobre o que faria: **não fabricou**, apesar de o pedido ser de
execução. Esse marco continua reprovado.

O contrato do controlador exigia apenas `minecraft_estado`. Correção específica
passou a exigir as operações de fabricação/colocação explicitamente pedidas,
sem escolher os materiais ou a sequência pelo modelo. Casos negativos conservam
“não fabrique”/“sem executar” sem mutação obrigatória. RED→GREEN,118 testes de
prontidão. Novo sono cooperativo,0jobs/leases e processo anterior encerrado antes
de carregar a mudança. Entrada `in-local-test-minecraft-40601-tools2` solicita
o mesmo marco real após a manutenção, sem contar plano ou fala como efeito.

Verificação da integração anterior:95/95 grupos offline e exit0 em
`/tmp/minecraft-argument-contract-suite-20261026.log`; commit local83ea08e.
Novas verificações e o desfecho do mundo ainda devem ser registrados abaixo.

### Integridade do plano e nova porta36365

`tools2` mostrou uma falha do controlador: ações obrigatórias ausentes no plano
eram acrescentadas em ordem alfabética. A colocação veio antes da fabricação e
tentou colocar o tronco que estava na mão; o servidor recusou, inventário e
terreno confirmados sem esse efeito. Esse preenchimento não é decisão autoral
do modelo e foi retirado do fluxo Minecraft. Agora um plano incompleto recebe
uma revisão do próprio modelo antes de executar; se continuar incompleto, a
tarefa pausa, sem substituir o plano por mutações criadas pelo controlador.
Dois casos RED→GREEN cobrem autoria/ordem e rejeição sem persistir plano inválido.

`tools3` confirmou a proteção em execução real: duas propostas omitiram
fabricação/colocação/estado, e a tarefa pausou **antes de qualquer ação no mundo**.
O modelo ainda não passou no marco. Investigação mostrou que o planejador
forçava raciocínio desligado mesmo com THINKING habilitado. Novo caso RED→GREEN
mantém a preferência da entidade no planejamento Minecraft; formatação isolada
de argumentos permanece leve.121 testes de prontidão verdes. Melhora de
planejamento ainda exige resultado real; configuração não prova capacidade.

Tentativas de comparação isolada: dois perfis diferentes do runner foram
recusados pelo RM por pressão de VRAM antes de inferir; não são falhas do modelo.
O ensaio com perfil correto adquiriu GPU20camadas, mas o encerramento da execução
não deixou recibo final. **Comparação inconclusiva**, sem efeito de jogo.
Depois, supervisor320518 e runner509998 foram conferidos ausentes, API fechada,
zero jobs/leases e GPU ociosa; nenhuma duplicata foi iniciada.

Decisão humana mais recente: **porta36365**, uso dos recursos disponíveis para
continuar o teste. Handshake atual confirmou1.16.5/protocolo754/1jogador.
Mesma Central reaberta, supervisor10007 e runner10021, API `/api/state`200.
Entrada `in-local-test-minecraft-36365-tools1` usa o alvo novo e solicita conferir
inventário antes de fabricar. O alvo antigo permanece somente como histórico.

Verificação pós-autoria teve94/95 grupos: `test_comandos_duraveis` falhou uma vez
em `test_recibo_ausente_nunca_vira_sucesso`, observando job ainda pendente.
Reexecução isolada19/19 passou; a ocorrência temporal foi preservada nos logs
`/tmp/minecraft-plan-authorship-suite-20261026.log` e
`/tmp/minecraft-plan-terminal-rerun-20261026.log`. Nova suíte completa está em
`/tmp/minecraft-36365-verificacao-20261026.log`; conferir saída final.

### Pré-condição de fabricação e alvo mais recente

Na porta36365, raciocínio habilitado produziu um plano contendo as operações
pedidas em200,586s. Isso melhorou a cobertura do plano, mas não comprovou
dependências corretas: a entidade tentou fabricar `crafting_table` diretamente
com3oak_log. Conexão às13:48:55 confirmada, inventário3oak_log preservado.
RPC `mc-0a65a051b5af4194967f6971e4ae61bf` falhou antes de chamar `b.craft`,
por ausência de receita utilizável. Não houve fabricação.

O erro de pré-condição agora tem recibo explícito `phase=preflight`,
`effect_state=not_started`, código específico e os dados reais de inventário e
receitas. O cliente só aceita essa distinção para craft com request, entidade,
origem e sessão exatos. Ausência/divergência de recibo, erro depois de iniciar a
fabricação ou outra falha parcial continuam incertos e não autorizam replay.
Essa rejeição segura solicita revisão do plano pelo modelo; o controlador não
fabrica ingredientes por ele. Descrição da ferramenta esclarece que ingredientes
e bancada não são preparados automaticamente.

RED→GREEN:17 regressões de ponte em VM e17 de integração Python. O recibo antigo
`tool-428cf943e3` foi reconciliado manualmente por Codex como sem efeito, usando
o log exato, a posição da exceção anterior a `b.craft` e o inventário posterior.
O estado histórico e a evidência original foram preservados, sem replay.

A suíte concorrente anterior terminou94/95 por timeout em
`test_central_refinamento`, durante a inferência longa; não foi ocultada.
Com entidades dormindo, zero jobs/leases e sem inferência concorrente, a
verificação final `/tmp/minecraft-preflight-verificacao-20261026.log` terminou
**95/95 grupos offline aprovados**.

Decisão humana mais recente: **porta37837**. Handshake confirmou1.16.5,
protocolo754 e1jogador. A Central10007 já havia encerrado; conferidos processo
ausente e zero jobs/leases antes de nova partida. Não usar36365/40601 em novas
ações; são apenas evidência histórica. Inventário precisa ser reconferido no
mundo reaberto antes de usar os recursos anteriores.

**Ainda não aprovado:** além dos3troncos, faltam recibos de fabricação e quatro peças
de diamante equipadas. Preparação da ponte, testes offline, plano e relato textual
não equivalem ao objetivo cumprido. Registrar próximos marcos com evidência do
mundo, separando intervenção do condutor e decisões do modelo.

### Ciclo de observação e próxima ação

Na37837 a tarefa antiga `ct-51db91aa9d` voltou a terminar mecanicamente depois
de conectar/observar. O planejador atingiu300s e a alternativa primitiva não
cumpriu bancada/picareta. Esse resultado continua reprovado. Uma comparação
isolada do7B levou17s e também omitiu dependências; não foi habilitado por isso.

O novo caminho restrito a metas Minecraft nomeadas consulta o mundo e solicita
uma próxima ação ao modelo, recebe seu resultado e decide novamente. Usa o mesmo
executor, permissões, trava, gerenciador de recursos e banco de tarefas. O Codex
não fornece uma sequência de jogo. Critérios independentes exigem fabricação,
inventário/equipamento e presença atual das bancadas colocadas. Falhas do antigo
planejador agora pausam em vez de executar uma operação primitiva e concluir.

Uma revisão independente encontrou5problemas importantes, nenhum crítico.
Todos foram reproduzidos e corrigidos: objetos adicionais não somem do objetivo,
destino/sessão são conferidos até depois da trava de execução, posições colocadas
são únicas e reconferidas, retomada explícita renova orçamento sem apagar
incerteza e observações respeitam o dispatcher/permissões. Sem segunda revisão
nem alegação de aprovação independente após as correções. Recibos duplicados,
alteração de sessão e pré-condições de ingredientes têm regressões adicionais.

Verificação offline atual:23casos do núcleo,126de prontidão,18da ponte e18da
integração Minecraft. A suíte completa terminou96/96grupos em
`/tmp/minecraft-observed-delivery-20261026.log`. Interfaces usam valores reais
do Mineflayer para posições de equipamento e do cliente para ações do forno.
Lilith permaneceu dormindo durante edição e testes, sem jobs/leases ativos.
**Ainda falta validar esse novo ciclo no mundo real; teste offline não aprova
a capacidade de sobrevivência.**

Primeira execução observada: tarefa `ct-a7f977c6d3`, entrada
`in-local-test-minecraft-37837-observed1`, runner473872. O modelo escolheu manual
três vezes, sem iniciar a ponte. Parada por falta de progresso funcionou; não
houve conexão nem fabricação. Sono cooperativo confirmado às18:27:20local,
zero jobs/leases, antes de alterar o contrato de decisão.

O schema era imposto pelo decodificador, mas não estava no prompt. Foi incluído
o mesmo contrato no texto fornecido ao modelo, conforme a orientação oficial de
[saídas estruturadas do Ollama](https://github.com/ollama/ollama/blob/main/docs/capabilities/structured-outputs.mdx).
Regressão RED→GREEN,127casos de prontidão. Comparação real sem executar ferramentas
no jogo, mesmo9B/perfil/RM e estado simulado indisponível: contrato antigo escolheu
manual em13,70s e alegou impossibilidade; contrato explícito escolheu
`minecraft_iniciar_ponte` em7,56s. Log
`/tmp/minecraft-decision-grounding-benchmark-20261026.log`. Isso verifica a escolha
nesse caso, sem aprovar a progressão no mundo. Retomar a mesma tarefa preservada.

Retomada `observed-resume1`: conexão real confirmada, seguida de consultas de
receitas e navegação real para(-90,76,-42), sem fabricar. A decisão declarou
transformar troncos em tábuas, porém usou instrução genérica `minecraft_craft`;
a segunda inferência montou `nome=crafting_table`. A repetição da pré-condição
foi barrada, sem fabricar. Esse desvio de alvo justifica remover a tradução
intermediária, não substituir a decisão pelo Codex.

Agora o9B recebe os schemas nativos e escolhe ferramenta/argumentos juntos,
conforme [chamadas de ferramenta do Ollama](https://docs.ollama.com/capabilities/tool-calling).
Nenhum JSON de formato é imposto simultaneamente; zero ou várias chamadas pausam
sem efeito. Testes RED→GREEN comprovam que `oak_planks` não é convertido novamente
para o alvo final e que nenhuma segunda inferência de argumentos ocorre;128casos
de prontidão verdes. Ensaio real sem executar: o modelo escolheu consultar a receita
de `stick`, com argumento correspondente, em15,40s. Sono cooperativo às18:33:42local,
ação de navegação concluída e0jobs/leases antes de alterar código carregado.

Verificação após chamada nativa:96/96grupos offline, exit0 confirmado em
`/tmp/minecraft-native-final-20261026.log`. Sem inferência física concorrente.

Retomada `observed-resume2` não agiu: três chamadas nativas de receita/navegação
foram rejeitadas antes do efeito porque a ponte ainda estava desligada após a
manutenção. Corrigida a exposição de capacidades: sem destino/conexão validados,
o modelo só recebe ferramentas de preparação/conexão; permissões e guarda de
execução continuam obrigatórias. Não há sequência de fabricação imposta.
Regressão RED→GREEN,129casos de prontidão. A suíte96/96 acima precede esse filtro;
não é alegada uma nova suíte inteira para essa mudança pequena. Sono,0jobs e
0leases novamente confirmados antes de carregar a correção.

### Continuação por Claude: falhas de formato, receitas e raciocínio

Condutor a partir daqui: Claude (mesmo `autor_id` operacional `codex_teste` para
manter a conversa/tarefa; o nome registrado da pessoa de teste continua “Codex ·”).
Regras mantidas: sem sequência de jogo fornecida, sem ações no lugar do modelo.

- `resume3` (18:42) pausou por três decisões sem progresso; o texto de pausa
  “Objetivo Minecraft…” acionou o verificador de agenda, que pediu nova inferência
  e excedeu 300s. Status de aplicação passou a dizer “Tarefa”; RED→GREEN.
- Após reconexão, a visão mostrava só os 4 últimos recibos e perdia as receitas
  já consultadas. `known_recipes` mantém uma linha compacta por item, inclusive
  de recibos antigos ainda legíveis; output cortado não é inventado.
- `resume5`/`resume6` (19:50–19:57, 37837): conexão real e quatro respostas de
  ~3.3k caracteres **sem chamada nativa** (limite de 1024 tokens consumido em
  prosa). Nenhum efeito além da conexão. Resposta sem chamada agora é recusa
  registrada (`rejected_before_effect`) e retorno para a próxima decisão, com o
  mesmo limite de falta de progresso; outros erros de decisão ainda pausam.
- Ensaio de decisão com o 9B real, sem executar no jogo, mesmo estado/checkpoint:
  instrução “não reescreva o estado” restaurou chamadas (6/6), mas 0/6 fabricaram
  o ingrediente. Esclarecida a ferramenta `minecraft_craft` (ingrediente com
  receita é fabricado por ela, em ação separada; exemplo de ID não induz o alvo
  final): 1/5 sem raciocínio, **4/5 com raciocínio** (uma com ID inexistente).
  A decisão observada agora segue `THINKING` da entidade, saída 4096.
- ID inexistente em `craft` era `RESULTADO_INCERTO` e travaria o ciclo sem
  reconciliação manual, embora recusado antes de efeito. A ponte o devolve como
  pré-condição `not_started` (`unknown_item`); 19 regressões de ponte.
- Suíte offline: 96/96 grupos. Logs anteriores em `/tmp` foram perdidos na queda
  de energia; resultados resumidos aqui.

Queda de energia às ~20:08. Bancos `quick_check ok`. Decisão humana: **porta
40613** e autorização para usar a capacidade máxima da máquina, preservando a
autonomia das entidades. Nova tarefa via `in-local-test-minecraft-40613-start1`
(conversa `claude_mc40613`), mesmo marco bancada/picareta.

### Porta 40613: primeiros marcos reais e intervenção registrada

- 20:44–20:49: com raciocínio ligado e a ferramenta de fabricação esclarecida, ela
  fabricou sozinha `oak_planks` (×2) e **duas** `crafting_table` (a segunda gastou
  as tábuas da picareta; decisão dela, não corrigida pelo condutor).
- Correções no caminho, todas RED→GREEN e sem roteiro de jogo: roteamento por
  critérios (RP com "depois" desviava para o plano fixo); recusa de repetição
  idêntica sem mudança; colocação recusada pelo servidor com alvo intacto vira
  `place_not_applied` (antes travava como incerta; recibo `tool-a97ffd2275`
  reconciliado como sem efeito, com evidência, sem replay); item na mão entra nas
  pré-condições; sessão nova no mesmo mundo e jogador continua a tarefa (outro
  jogador pausa); "o que falta" e plano próprio (`PLANO:`) na visão; paciência 6;
  jogador do objetivo (LilithMC) faz parte do destino (ela chegou a entrar como
  "Lilith", outro jogador, e a trava recusou corretamente); regras de colocação
  explicadas antes de tentar e modo sem coordenadas (chão livre ao lado).
- Desempenho: o 9B rodava com 20 camadas (43% CPU). Escada medida nas duas
  entidades (33/32/31/30/28/26/20 camadas) escolhida pela VRAM livre; com o
  Minecraft (~0,8 GiB) usa 32 camadas, ~25 t/s contra ~13 t/s. Camadas mantidas
  enquanto o modelo está residente, janela fixa no perfil medido (sem recarga por
  `num_ctx`) e `keep_alive` `-1m` (o Ollama recusa `-1` sem unidade).
- 22:30:47 ela fabricou `stick` (×4) seguindo o próprio plano.
- **22:38:16 bancada colocada e reconferida no mundo em (-98, 69, -62). Intervenção
  humana:** ela vinha tentando colocar no bloco onde estava parada; o usuário a
  empurrou com um golpe no jogo e a mesma tentativa passou a ser válida. A decisão
  de colocar foi dela; a mudança de posição não. Não conta como colocação autônoma
  pura. A causa já foi tratada na ponte (alvo no próprio corpo recusado com
  explicação e modo sem coordenadas).
- Falha temporal conhecida `test_comandos_duraveis` (job ainda pendente) apareceu
  uma vez com a máquina carregada; isolado 3/3 aprovado. Demais suítes: 96/96.
