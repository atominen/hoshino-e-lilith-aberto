# Continuação coordenada: visão existente e integridade do Minecraft

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans para execução direta. Claude foi solicitado pelo humano para orientação/revisão; sem dois implementadores nos mesmos arquivos.

**Goal:** validar a visão do9B já instalado, integrar as melhorias do Claude e manter progresso verificável e decisões próprias da entidade.

**Architecture:** preservar Central, dispatcher, banco de tarefas e RM existentes. Visão é uma observação auxiliar; o mundo estruturado e seus recibos continuam a verificar ações. Correções se limitam a defeitos reproduzidos; não escrever a progressão de jogo pelo modelo.

**Tech Stack:** Python, Ollama local/Vulkan, Mineflayer/Node, SQLite, testes isolados existentes.

**Spec:** pedido humano atual de ler/organizar/aprimorar o trabalho do Claude; [handoff](../../CONTINUACAO_CLAUDE_MINECRAFT_E_DESEMPENHO_20261026.md) e [ensaio](../../TESTE_MINECRAFT_LILITH_20261026.md). Execução direta e instalação atual já escolhidas pelo usuário.

## Global Constraints

- Hoshino/Lilith conservam identidade/memórias e7B/9B; Alistair conserva4B/Xbox.
- Não baixar/substituir pesos quando o9B local já possui visão confirmada.
- Nenhuma ação Minecraft pelo condutor; RP identificado e separado de história humana.
- Sem edição de código carregado; entidades dormindo e0jobs/leases durante edição.
- Não tratar snapshot sem mudança após timeout como prova de que nenhuma ação foi enviada.
- Não certificar parte de um pedido como se todas as suas etapas tivessem sido concluídas.
- Áudio mantém fontes de aplicativos separadas, integração já existente.

## Review Focus

- Colocação enviada pode produzir efeito tardio: manter resultado incerto e não repetir.
- Mesmo endereço/jogador em nova sessão não identifica sozinho o mundo salvo.
- Pedido misto com construção não coberta não pode ser concluído pelo verificador de itens.
- Visão exige capacidade/projetor e inferência com imagem, não somente nome comercial do modelo.
- Pausa/retomada não elimina recibos, ingredientes, plano autoral ou efeitos pendentes.

## Task1: verificação e orientação

- [x] Ler handoff, diff, estado atual e sessão do Claude, sem editar suas alterações.
- [x] Consultar modelos/manifests:9B da Lilith já tem projetor e capability vision.
- [x] Ensaio visual controlado sem tela privada: reconhecer formas/cores/número.
- [x] Orientar uma revisão Claude somente leitura; API429 encerrou antes do relatório. Sem alegação de revisão aprovada, sem retry automático.
- [x] Registrar orientação durável e corrigir afirmação desatualizada sobre visão no handoff.

## Task2: integridade e validação

Files: `app/core/minecraft_agent.py`, `app/main.py`, `app/tools/minecraft.py`, `compartilhado/servicos/minecraft/bridge.js`; testes correspondentes.

- [x] Reproduzir conclusão parcial e efeito tardio em testes isolados antes de corrigir.
- [x] Corrigir somente os casos comprovados, preservando recusa anterior ao efeito.
- [x] Revisão independente:2P1adicionais reproduzidos/corrigidos em um passe; cobertura integral e vínculo revisado de sessão.
- [x] Verificar visão pelo helper existente e registrar VRAM/tempo sem substituir pesos.
- [x] Executar testes focados e suíte completa:42núcleo,137prontidão,23cliente,30ponte e96/96grupos, exit0. Registrar limitações reais.

## Task3: ensaio e organização

Ruling: o ensaio revelou bloqueio de risco por esqueleto5blocos abaixo, somente
pela distância. Acrescentar linha de visão medida pelo plugin instalado do
Mineflayer, com regressões para oclusão/visível/desconhecido; não desativar a
proteção por vida baixa nem supor oclusão só pela altura. Custo: sem informação
confiável mantém proteção conservadora. Nova verificação antes da recarga.

Ruling: a nova contribuição Claude após o reset confirmou lacuna concreta de
percepção: ingredientes disponíveis não tinham análise de fabricação visível.
Adicionar um nível de fatos de receitas, até3produtos/6nomes, e neutralizar a
descrição coleta/fabricação. Sem roteiro de ações, sem ampliar paciência nem
limpar o plano dela; medir antes de atribuir melhora.138regressões verdes.
Conjunto posterior verificado:96/96grupos offline, exit0, no log
`/tmp/continuacao-ingredientes-final-20261027.log`.

- [x] Reconciliar tarefa `ct-822b8dd433`, destino40613 e inventário; não usar37837 sem novo pedido.
- [x] Retomar o marco bancada/picareta pelo LLM, incluindo subobjetivo `ct-525f53c453`: ensaio executado, marco NÃO aprovado.
- [ ] Kit de ferro é o próximo marco registrado no handoff; não aprovar sem peças fabricadas/equipadas.
- [x] Atualizar índice e documentos com estados completos, pendentes e intervenções; preservar delta6B/SNIPER alheio.

Resultado da retomada00:55: visão de inimigo oculto corrigida, mas três escolhas
de coleta apesar da receita intermediária disponível. Hipótese de percepção
suficiente refutada. Tentativa de equipar item ausente gerou erro prévio ao
efeito, mal classificado como incerteza; reprodução e correção em24testes do
cliente/33regressões da ponte. Recibo antigo preservado; tarefa pausada e
entidades dormindo. Evolução cognitiva/novo ensaio ainda necessários.
Verificação final da correção de equipamento:96/96grupos offline, exit0,
`/tmp/continuacao-equip-final-20261027.log`.
