# Lógica, recuperação de contexto e próximos refinamentos — 28/10/2026

Esta rodada atende ao pedido de procurar problemas, pesquisar soluções e
organizar o projeto. **Auditoria concluída; correções abaixo ainda propostas.**
Ela registra a etapa de leitura encerrada às12:45. Posteriormente, o humano
autorizou [trava16GB e ensaioMinecraft4B](ADMISSAO_16GB_E_MINECRAFT_4B_20261028.md),
implementados como outra etapa; não confundir seus testes com correção dos
achados de planejamento/transações deste snapshot.
Não alterou código de produção, modelos, configurações ou memórias; não
reiniciou serviços nem iniciou outra etapa do jogo. O resultado físico e a
cronologia anterior estão em [Minecraft em28/10](MINECRAFT_CONTINUIDADE_20261028.md).

## Resultado real e critério de avaliação

Lilith concluiu o **kit completo de ferro**, tarefa`ct-4acf234a28`, passo256,
com conclusão registrada às11:12:08 de28/10, horário local. Na conferência
das12:40, a ponte confirmou as quatro peças vestidas e espada, picareta,
machado e pá no inventário. O checkpoint registra a fabricação dos oito itens;
os recibos finais são`tool-9155777606`(machado) e`tool-4bc9d6e27c`(pá).
O verificador do objetivo também retornou verdadeiro para esses critérios.

Servidor dedicado`10.0.0.200:25565`, Java1.16.5, jogador`LilithMC`, sobrevivência.
A dificuldade foi alterada pelo humano paraPacífico durante o ensaio. Houve
manutenção e respostas factuais do condutor. Portanto: **objetivo material
concluído com assistência**, não aprovação de autonomia integral, combate,
qualidade geral do modelo ou consciência. Até o fechamento desta etapa da
auditoria, às12:45, ela não iniciou outra etapa. A continuação posterior do
Claude está em [etapas após o kit](MINECRAFT_ETAPAS_POS_KIT_20261028.md).

O critério humano é perceber o estado/erro, recalcular, registrar uma nota útil
e tentar novamente até conseguir. A avaliação deve verificar se o retorno
real modifica a decisão seguinte, sem substituir as escolhas da entidade por
um roteiro do condutor. Notas servem à recuperação de contexto, com autoria e
fonte; não devem transformar intenção ou hipótese em experiência confirmada.

## Evidência e limites da auditoria

- Referência de código: commit`a501a809c519121b687305a457eeef5b71940031` mais a
  árvore local existente. As fontes examinadas foram identificadas porSHA256.
  Números de linha abaixo pertencem a esse snapshot. Houve commits posteriores
  doClaude; reconferência estática identificou os mecanismos de transações
  ainda presentes, sem atribuir o snapshot antigo à tarde.
- Dependências instaladas: Mineflayer4.39.0, pathfinder2.4.5 e collectblock1.6.0.
- Dois domínios independentes revisados: planejamento e transações. Foram
  reproduzidos **12 achados principais e2 complementares**, sem mundo real,
  inferência, inicialização da aplicação ou acesso aos bancos mentais.
- Ensaios usam funções reais extraídas porAST e a ponte emVM com transporte
  simulado. O teste de capacidade usa os plugins de inventário/forno instalados.
  Não substituem ensaio integrado, timing real ou avaliação doLLM.
- As três execuções offline terminaram com código0. **Seus asserts confirmam
  comportamentos defeituosos atuais; passar não significa estar corrigido.**
- Evidências locais: [índice da auditoria](../compartilhado/runtime/ensaios/auditoria-logica-20261028/README.md),
  [snapshot da conclusão](../compartilhado/runtime/ensaios/auditoria-logica-20261028/kit-completion-evidence.json),
  [casos de planejamento](../compartilhado/runtime/ensaios/auditoria-logica-20261028/planejamento/resultados.json),
  [revisão de transações](../compartilhado/runtime/ensaios/auditoria-logica-20261028/transacoes/ACHADOS.md).
  Runtime é local e ignorado peloGit; esses links dependem desta instalação.

## Falhas confirmadas de execução e integridade

P1: pode causar perda, crédito indevido, repetição de efeito ou impedir a
recuperação. P2: distorce retorno/contexto ou exige intervenção desnecessária.
A prioridade é desta auditoria, não uma declaração de incidente já ocorrido.

| ID | Prioridade | Reprodução e consequência | Proposta e referência |
|---|---|---|---|
| T1 | P2 | A ponte entrega erroHTTP400 com recibo e identidade; o cliente relata “enviado sem recibo” e perde a causa específica. | Ler e validar o envelope também em erroHTTP, separando erro reportado, ausência de resposta e efeito parcial. `app/tools/minecraft.py:77`; `bridge.js:1053`. |
| T2 | P1 | Saída8, inventário cheio com uma pilha de ferro63: o plugin aceita1 e emite descarte dos7 excedentes. A ponte credita8, encerra a carga e devolve inventário anterior ao fechamento. | Conferir capacidade compatível e cursor antes da retirada; verificar deltas finais após fechar a janela; distinguir retirado, guardado e descartado. `bridge.js:849`; plugins instalados. |
| T3 | P1 | Uma consulta de forno pode abrir e fechar outra janela durante depósito. A transação seguinte passa a usar `currentWindow` substituída/fechada. | Exclusão por bot/sessão para todo o ciclo de janelas, inclusive consultas, com fila/recusa observável. `bridge.js:809`, `858`, `1048`. |
| T4 | P1 | Propriedade persistida usa jogador, dimensão e coordenadas; outro servidor nas mesmas coordenadas pode herdar a autorização de retirada. | Identificar destino e mundo; reconciliar registros legados sem atribuí-los automaticamente ao novo mundo. `bridge.js:66`, `808`, `845`. |
| T5 | P2 | Intenção de8minérios é salva antes do clique. Se o clique falha sem mover itens, o estado projeta count8/remaining8/depositedAt sem fase e impede nova carga; esses campos não confirmam depósito. | Preservar intenção durável, mas publicar fase e quantidades solicitadas/confirmadas/desconhecidas separadamente. `bridge.js:273`, `836`. |
| T6 | P1 | Craft com quantidade omitida e com quantidade1 gera o mesmo efeito, mas duas assinaturas e duas reservas enquanto a primeira segue sem resolução. | Normalizar argumentos conforme os defaults do handler antes da assinatura; versionar sem desproteger pendências antigas. `app/core/cognition.py:31`; `app/core/dispatch.py:918`; `app/core/job_bus.py:203`. |

T2 eT3 foram reproduzidos offline; **não demonstram a causa exata** da rejeição
real de clique no slot1 ou o destino do carvão no incidente
`tool-9fd7f51462`: inventário4→0 e slot de combustível12→12 nas observações.
Não ficou comprovado quanto do combustível solicitado foi depositado.
O item caído visto no jogo não teve tipo/quantidade
identificados. T1 explica a perda do erro específico pelo cliente. A revisão
anterior preservou o original e registrou efeito parcial sem repetir depósito.

EmT6, a guarda local de pending ainda protege a retomada daquele checkpoint;
o ensaio demonstra a lacuna da assinatura durável entre chamadores. Não prova
que houve fabricação duplicada no teste real. EmT4, host+porta ajuda, mas não
distingue substituição do mundo no mesmo servidor: a associação precisa de
evidência da identidade/geração do mundo e revisão em caso de mudança.

Complementares reproduzidos:

- **T7, P2:** resposta de sucesso sem request/entity/parent/session é aceita,
  pois a comparação só acontece quando o campo existe. No protocolo vigente,
  exigir correlação completa ou classificar resultado insuficientemente atribuído;
  não dar sucesso automático nem repetir (`app/tools/minecraft.py:97`).
- **T8, P2:** dois stacks de4minérios somam8, mas a validação olha apenas o
  primeiro e recusa8 como insuficientes. Somar stacks compatíveis com os mesmos
  critérios de tipo/metadata da transferência (`bridge.js:832`).

## Falhas confirmadas de planejamento e recuperação

| ID | Prioridade | Reprodução e consequência | Proposta e referência |
|---|---|---|---|
| P1 | P1 | Forno fora de alcance falha; depois de navegar até ele, a mesma chamada continua bloqueada porque a impressão de pré-requisitos omite posição/alcance. | Impressão por tipo de operação e motivo da falha. Mover não libera craft sem material; alcançar a estação deve liberar uma recusa comprovadamente anterior ao efeito. `minecraft_agent.py:301`, `349`. |
| P2 | P1 | Retirada com saída vazia retorna sucesso. Quando surge produto no forno, a mesma retirada é recusada como repetição sem mudança, pois os slots não entram na comparação. | Integrar observação real de forno e versão da carga à guarda, mantendo bloqueio de efeitos incertos. `minecraft_agent.py:293`, `352`. |
| P3 | P2 | Consulta `minecraft_forno(estado)` interrompida fica marcada como mutação do mundo e bloqueia retomada por possível efeito físico. | Classificar por ação/argumentos e domínio de efeito; separar limpeza da janela de transferência de itens. `minecraft_agent.py:310`, `364`. |
| P4 | P2 | Plano aceita “equipado furnace, quantidade64”; segurar1 basta para marcar cumprido. Também não há predicado de plano para colocação verificada. | Validar quantidade por predicado; distinguir possuir, segurar, vestir, estar perto e ter colocado no mesmo mundo. `minecraft_cognition.py:97`, `265`. |
| P5 | P1 | “Equipe uma picareta de ferro” vira apenas posse no inventário; o verificador retorna verdadeiro com graveto na mão. | Contrato explícito de resultado/slot, ou esclarecimento quando não representável; teste negativo obrigatório. `minecraft_agent.py:114`, `209`. |
| P6 | P2 | Quatro recusas com nome de ferramenta expulsam o último recibo físico da janela de trabalho, deixando só rejeições repetidas. | Separar últimos efeitos/observações e resumo de recusas, sem apagar a evidência que explica o estado atual. `minecraft_cognition.py:314`. |

P5 não invalida o kit atual: seu contrato exige as quatro peças em slots
específicos e as quatro ferramentas no inventário, além da fabricação. Isso
foi conferido. O defeito é de outros pedidos cujo verbo exige segurar/equipar.
EmP4, a entidade também escolheu um predicado inadequado para “colocar”; há
simultaneamente limitação de representação e validação insuficiente.

**A consulta ao forno próximo já existe** em `app/main.py:3017–3023` e fornece
`perception.forno_proximo`. Não acrescentar outra consulta redundante. As
opções em `minecraft_cognition.py:520–542` ainda enfatizam tempo estimado e
combustível solicitado. Integrar o que já foi observado, distinguindo
estimativa, depósito confirmado e slots atuais, deve reduzir contradições.
A descrição “forno vazio” também precisa distinguir entrada/produto/carga
própria de combustível residual compatível, já aceito pelo ajuste anterior.

Uma inspeção de forno abre janela no cliente: classificá-la como observação
do mundo **não permite concorrência irrestrita**. P3 depende da disciplina
deT3; não resolver simplesmente incluindo toda ferramenta de forno em READ_ONLY.

## Pesquisa: o que aproveitar e o que não presumir

As adaptações abaixo são propostas para nossa arquitetura e modelos locais.
Os resultados publicados não são previsões de desempenho do nosso9B/4B.
Não foi treinado seletor, instalado framework ou trocado executor nesta rodada.

| Referência primária | Contribuição útil | Adaptação proposta e limite |
|---|---|---|
| [DEPS](https://arxiv.org/abs/2302.01560) | Usa descrição do resultado, explicação de falha e revisão do plano; também estuda seletor treinável de submetas. | Após falha, pedir diagnóstico curto amarrado ao recibo, pré-requisito alterado e nova tentativa. Nosso verificador barato não equivale ao seletor treinado do artigo. |
| [Reflexion](https://arxiv.org/abs/2303.11366) | Feedback textual e memória episódica ajudam tentativas posteriores sem atualizar pesos. | Guardar correção concisa com fonte e resultado posterior. Autorreflexão não torna uma lembrança verdadeira e não justifica registrar raciocínio privado detalhado. |
| [SayCan](https://arxiv.org/abs/2204.01691) | Combina planejamento em linguagem com viabilidade das habilidades no ambiente. | Conferir recursos, alcance, ferramenta, espaço e propriedade antes de oferecer efeitos. A adaptação usa condições verificáveis, não as funções de valor treinadas dos robôs. |
| [Voyager](https://voyager.minedojo.org/) | Biblioteca de habilidades, currículo e melhoria por retorno do ambiente/erro/verificação. | Habilidades mecânicas reutilizáveis escolhidas pela entidade, com recibos. O sistema usaGPT4; não importar sua taxa de sucesso nem execução arbitrária de código para nosso9B. |
| [Mindcraft: habilidades de forno](https://github.com/mindcraft-bots/mindcraft/blob/develop/src/agent/library/skills.js) | O código consulta entrada/combustível e recolhe produto durante a fundição; adiciona combustível conforme o slot existente. | Comparar a composição da habilidade, sem copiar sua limpeza de slots compartilhados. Usa itens de versões modernas; `raw_iron` não substitui `iron_ore` em1.16.5. Não é prova de segurança contra falha parcial. |
| [JARVIS-1](https://arxiv.org/abs/2311.05997) | Combina memória multimodal e controle orientado a metas. | Experiências recuperáveis por contexto, mundo, pré-condições e resultado; visão própria sob demanda como etapa posterior. Não implica que o pipeline de câmera do bot já existe aqui. |
| [LLM+P](https://arxiv.org/abs/2304.11477) | Traduz problemas para planejamento clássico formal. | Começar com conferência pequena de receitas, saldo e condições finais. Modelar todoMinecraft emPDDL agora adicionaria custo e fragilidade; não substituir a autoria por rota fixa. |
| [Inner Monologue](https://arxiv.org/abs/2207.05608) | Usa retorno do ambiente, sucesso e interação humana para planejamento em ciclo fechado. | Receber a consequência observável antes de decidir a próxima tentativa, preservando perguntas/respostas úteis. Narrativa otimista não substitui sucesso detectado. |
| [Generative Agents](https://arxiv.org/abs/2304.03442) | Memória, recuperação, reflexão e planejamento sustentam comportamento individual/social em uma simulação. | Manter preferências, interesses e relações separados de fatos operacionais. Comportamento plausível nesse ambiente não demonstra consciência nem confiabilidade irrestrita noPC. |
| [Requesting Expert Reasoning / AHCE](https://arxiv.org/abs/2602.22546) | Estuda quando solicitar orientação e como incorporá-la noMinecraft. | Reutilizar respostas já recebidas e solicitar apenas o fato ausente, com autoria. Não existe aqui a política treinada do estudo nem autorização para fabricar ajuda humana. |
| [VRL-Bench, preprint](https://arxiv.org/abs/2609.12404) | Relata resultados dependentes da tarefa/modelo; reflexão e replay também podem piorar o desempenho. | Comparar notas fundamentadas com controle sem notas. Mais texto ou mais chamadas não é critério de melhora; resultados deMiniWoB/WebShop não se transferem diretamente aoMinecraft. |

Na execução, a [API oficial doMineflayer](https://github.com/PrismarineJS/mineflayer/blob/master/docs/api.md)
documenta leitura dos slots e operações assíncronas; o comportamento exato foi
verificado nos plugins instalados. O [Requests](https://requests.readthedocs.io/en/latest/user/quickstart/#response-status-codes)
explica a exceção deHTTP e que umJSON pode conter um erro: receber esse erro não
comprova ausência de efeito.

Para durabilidade, a [documentação doTemporal sobre ferramentasMCP](https://docs.temporal.io/develop/python/integrations/mcp)
expõe o risco de repetir um efeito quando sua resposta é perdida. Aplicar a
lição ao job_bus existente, sem instalarTemporal ou criar outro scheduler.
A [separação de eventos e estado projetado](https://learn.microsoft.com/en-us/azure/architecture/patterns/event-sourcing)
ajuda a manter intenção e fato distintos; a recomendação é evoluir os recibos
existentes, sem migrar toda a aplicação. Uma
[compensação](https://learn.microsoft.com/en-us/azure/architecture/patterns/compensating-transaction)
não é necessariamente o inverso exato: emMinecraft não se deve “desfazer”
cliques incertos automaticamente ou consumir outro lote para esconder a falha.

## Ordem de implementação proposta

### 1. Tornar o efeito e seu recibo confiáveis

PriorizarT1/T7, T3, T2, T4 eT6 antes de aumentar a complexidade do planejador.
Normalizar a operação no mesmo contrato usado pelo handler e preservar
associações antigas ainda pendentes. Um recibo precisa identificar entidade,
destino/mundo, sessão, pedido e fase; não prometer exatamente uma execução
apenas porque existe uma linha no banco.

Aceitação: erro com recibo preserva a causa e continua parcial/incerto quando
necessário; duas operações de janela não interferem; capacidade1/saída8 não
retira nem descarta; defaults equivalentes encontram a mesma pendência; outro
mundo não herda propriedade. Reinício entre input e combustível preserva fase,
cursor/slots conhecidos e necessidade de reconciliação, sem replay.

### 2. Devolver um estado coerente para a decisão

TratarT5/T8 eP1/P2/P3/P6, integrando a inspeção existente. Evoluir o registro
para solicitado → iniciado → parcial/confirmado → reconciliado, com quantidades
e observações datadas. Manter saldo de inventário, materiais em processo e
produtos disponíveis separados; tempo decorrido não confirma quantidade pronta.

Aceitação: aproximar-se libera falha de alcance; andar não libera falta de
ingrediente; saída nova permite retirar depois de consulta vazia; falha antiga
incerta nunca é liberada apenas por mudar de posição. Recusas resumidas não
apagam o último fato; consulta interrompida exige limpeza de janela adequada,
sem inventar transferência de itens.

### 3. Corrigir o contrato do plano e as notas de recuperação

TratarP4/P5 e adicionar conferência de receita/saldo ao plano autoral.
Representar possuir, segurar, vestir, fabricar e colocar como resultados
distintos. Permitir revisar ou abandonar uma submeta com motivo, preservando
o objetivo e registrando a decisão; não impor uma sequência escrita peloCodex.

Registro compacto proposto: **intenção; observação/recibo; resultado confirmado
ou desconhecido; correção; próximo ponto a conferir**. O comentário autoral
pode ter personalidade, mas a síntese operacional não deve ser confundida com
fala doLLM. Manter fonte, autoria e data; registrar fatos úteis e decisões,
sem exigir cadeia de pensamento nem gravar cada token como memória.

Aceitação: picareta no inventário/graveto na mão não cumpre “equipar”; forno
segurado não cumpre “colocar”; quantidades inválidas são recusadas; nova nota
não afirma efeito que o recibo não demonstra. Uma resposta humana factual já
recebida permanece recuperável, evitando a mesma pergunta a cada poucos passos.

### 4. Reutilizar habilidades e medir autonomia

Com a base confiável, compor habilidades genéricas de fundir, fabricar e
equipar, com pré/pós-condições e cancelamento cooperativo. A entidade escolhe
quando usá-las e pode preferir exploração, conversa ou outro interesse. O
propósito da ação deve ser claro: tarefa, interesse próprio ou manutenção;
uma atividade própria não precisa avançar o kit para ser legítima.

Depois, avaliar câmera do próprio bot sob demanda e memória multimodal com
o9B existente. Antes é necessário verificar captura, horário, perspectiva,
custo de contexto/GPU e correspondência com a entidade/mundo. Inferências
anteriores com imagens não validam esse circuito. Adiar planejador geralPDDL,
treino extra e substituição de modelos até haver comparação que justifique o
custo. As famílias vigentes continuam [4B/9B, professor à parte](ORGANIZACAO_4B_9B_20261027.md).

## Como testar melhora, sem fabricar aprovação

Primeiro transformar as reproduções desta auditoria em testes de regressão
com o comportamento corrigido esperado. Conservar os probes históricos como
evidência da versão defeituosa; não mantê-los como asserts permanentes de erro.

Depois usar cenários controlados e comparáveis: forno distante; saída surgindo
após consulta vazia; combustível residual; inventário cheio; stacks partidos;
perda de resposta após um clique; reinício de sessão; mundo novo; pedido de
equipar versus fabricar; pergunta respondida; conversa enquanto há tarefa.
Validar1.16.5, pois exemplos públicos de versões mais novas não bastam.

| Medida | Evidência necessária |
|---|---|
| Sucesso | Condição física/artefato final e recibos corretos, não fala ou `completed` isolado. |
| Recuperação | Estado antes/depois do erro; mudança de diagnóstico/plano; tentativa que resolveu ou impedimento real. |
| Eficiência | Tempo, chamadas/tokens, ações, repetição do mesmo erro e latência até corrigir. |
| Integridade | Recursos conservados, descartes explícitos, saldo desconhecido visível, nenhuma duplicação após incerteza. |
| Continuidade | Objetivo e respostas úteis recuperados após conversa lateral/reinício; nota fiel ao resultado. |
| Autoria | Ajuda humana/condutor, manutenção e indisponibilidade contabilizadas à parte. |
| Memória útil | Comparação com/sem síntese fundamentada, incluindo retenção de uma correção na sessão seguinte. |

O ciclo perceber → agir → conferir → corrigir → anotar pode servir também a
pesquisa, arquivos, comandos e criação gráfica. Cada domínio precisa de seu
verificador: arquivo existente não prova conteúdo correto; retornoHTTP não
prova ação concluída; som reproduzido não prova compreensão. Não ampliar
permissões externas ou iniciar outros projetos apenas por esta generalização.

## Integração reversível e organização feita nesta rodada

As implementações futuras devem entrar em incrementos pequenos, aproveitando
Central, dispatcher, RM, job_bus e checkpoints existentes. Sem migração
destrutiva: acrescentar campos versionados, leitores compatíveis e associação
conservadora de registros antigos. Reverter código não pode apagar recibos
ou desbloquear efeitos ainda incertos. Recarregar código em uso somente após
drenagem cooperativa e conferência de jobs/leases/processos.

Nesta rodada, os guias de entrada foram atualizados para4B/9B, servidor
dedicado e kit concluído; handoffs antigos foram identificados como históricos.
Relatórios e evidências foram indexados dentro do projeto, sem duplicar pesos,
mover bancos ou apagar registros necessários. Não houve publicação noGitHub.

**Próxima prioridade recomendada:** integrar primeiro a validação do recibo e
a exclusão de janelas, acompanhadas pelos testes de capacidade/efeito parcial;
depois corrigir as guardas e os contratos do planejador. Aumentar o orçamento
doLLM antes disso pode ampliar a exposição aos mesmos retornos defeituosos;
essa hipótese não foi medida por comparação nesta auditoria.
