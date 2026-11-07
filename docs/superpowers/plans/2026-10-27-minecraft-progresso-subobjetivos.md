# Minecraft: progresso observado e subobjetivos autorais

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Execução direta já escolhida pelo humano; Claude orienta em leitura, Codex implementa.

**Goal:** fazer a Lilith reconhecer estagnação e escolher etapas intermediárias próprias até fabricar a picareta, depois testar kit de ferro.

**Architecture:** preservar Central, Mineflayer, dispatcher, RM, tarefas e recibos. Distinguir efeito físico de aproximação do resultado. Acrescentar trajetória curta e, quando necessário, uma escolha estruturada de subobjetivo pelo mesmo LLM. Nenhum roteiro automático de jogo.

**Tech Stack:** Python, SQLite existente, Ollama9B local, Mineflayer1.16.5.

**Spec:** pedido humano atual e `docs/COORDENACAO_CODEX_CLAUDE_20261027.md`. A sessão Claude4fd85b9d foi retomada em uma cópia5d19dd78, somente leitura. Relatório integral local: `/tmp/claude-minecraft-architecture-20261027.json`.

## Global Constraints

- Hoshino/Lilith somente7B/9B, mínimo7B; Alistair4B/Xbox inalterado.
- Nada de cheats, presentes, ações de jogo do condutor ou fabricação em cadeia escondida.
- Sono e0jobs/leases antes de editar código em uso; um implementador por arquivo.
- Resultado incerto exige reconciliação atribuída; nunca retry cego.
- Recibo antigo de equipamento reconciliado por Codex: erro síncrono antes de`b.equip`, com backup, código9ea03de e diagnóstico exato do pedido. Sem replay.
- Memórias/identidades preservadas; notas operacionais não são história humana.

## Review Focus

- Movimento/coleta útil intermediária não equivale a conclusão, nem merece pausa automática só porque o resultado final ainda falta.
- Percepção ausente é desconhecida; não converter ausência de receita em déficit zero.
- Subobjetivo deve ser autoria do LLM, usar item observado e quantidade válida; sua conclusão exige observação.
- Plano errado ou subobjetivo já cumprido precisa de retorno factual; não limpar falhas/incertezas para continuar.
- Trajetória e notas não podem ocultar erros, fabricar recibos ou promover progresso intermediário à aprovação do objetivo.

## Tasks

1. [x] Núcleo puro de progresso e trajetória em`app/core/minecraft_cognition.py`, testes em`testes/test_minecraft_agent.py`.
   - RED→GREEN: troncos adicionais/movimento não reduzem déficit final; tábuas reduzem falta de ingredientes; informação ausente permanece desconhecida; transição contém delta real.
   - Contador informativo separado do limite de ausência de efeito existente.
2. [x] Integrar trajetória e escolha estruturada de subobjetivo em`app/main.py`; registrar transições em`minecraft_agent.run`.
   - RED→GREEN: subobjetivo inválido não executa ação, quantidade final já atendida é recusada; plano/intermediário são persistidos com autoria; campo factual chega à decisão nativa.
   - Até300tokens para escolha estruturada sem ferramenta, pelo mesmo executor; decisão de ação continua nativa com argumentos escolhidos pela entidade.
   - Sem máscaras adicionais, novas habilidades ou mudança de temperatura de produção antes de medir esta alteração.
   - Medição inicial refutou suficiência: duas escolhas de meta plausível seguidas de consulta/coleta; baseline tentou equipar item ausente nas duas temperaturas.
   - Ruling posterior: oferecer operações concretas derivadas de receitas/inventário/locais observados, escolhidas pelo LLM por ID. `outra` abre o catálogo completo, pesquisa/receitas continuam diretas. Não há cadeia automática de receitas nem novo executor. Custo se errado: catálogo pode omitir uma possibilidade útil, preservando a saída explícita para ferramentas livres.
3. [ ] Concluir validação física até o kit de ferro; testes focados, suíte geral e snapshots já executados. Mundo atual34993.
   - Registrar configuração, chamadas válidas e escolhas, sem expor raciocínio privado.
   - Confirmar picareta por fabricação+inventário; bancada por posição observada. Depois kit de ferro em tarefa própria.
   - Se6decisões consecutivas não aproximarem resultado/subobjetivo, registrar refutação e investigar causa; não ampliar limites só para passar.
   - Picaretas de madeira e pedra confirmadas por fabricação+inventário; tarefa de ferro`ct-06c691fa40` ativa. Snapshot07:51:12coal/33cobblestone, sem ferro. Investigar estagnação; não declarar o marco final aprovado.
4. [x] Revisão fresca final, correções importantes, documentação e commits próprios; passagem operacional para o Claude preparada a pedido humano.
   - Continuação:[handoff atual](../../HANDOFF_CLAUDE_MINECRAFT_20261027.md).

## Base técnica e decisões

O [Voyager](https://voyager.minedojo.org/assets/documents/voyager.pdf) usa feedback do ambiente, erros e verificação para melhorar ações. Aqui adotamos feedback factual; não importamos seu executor de código nem dependência de outro modelo/cloud.

Ruling: não executar a matriz extensa sugerida pelo Claude nesta primeira passagem. Ensaiar amostras pequenas e estados relevantes antes de ampliar; custo se errado: menor confiança estatística, explicitamente sem alegação de benchmark.

Ruling: não fazer movimento automático até bancada nesta passagem. Movimento é efeito adicional e deve continuar escolhido pela entidade; custo se errado: mais decisões e latência para navegar.

## Ledger

- Pré-voo: entidades dormindo,0jobs/leases,40613respondendo. Histórico da sessão original lido e cópia Claude concluída sem alterações.
- Reconciliação de`tool-6320f4a0fb`: original preservado, pendência removida com autoria Codex e evidência de ausência de envio; registro local em`compartilhado/runtime/ensaios/minecraft-reconciliation-20261027/`.
- Núcleo:52testes; integração:141testes verdes. A primeira versão passou96/96grupos antes da projeção de possibilidades. O ensaio congelado dessa versão NÃO comprovou benefício suficiente; resultados preservados em`/tmp/minecraft-frozen-results-20261027.json`.
- Protótipo sem jogo da projeção de possibilidades: o9B escolheu`fabricar:oak_planks` em17,621s. Isso é escolha em snapshot, não fabricação real. Nova versão deve passar suíte e ensaio físico.
- Projeção integrada: duas amostras congeladas escolheram fabricar tábuas, com0,75/0,3 e mesma semente.96/96grupos verdes nessa versão.
- Revisão fresca Claude02894c00:2importantes+2menores. Um passe RED→GREEN corrigiu os quatro: meta opcional para ações diretas, preservação de recibos informativos, comparação de observações e precedência de plano sem depender do passo.54núcleo/145prontidão verdes; suíte posterior e mundo pendentes. Ruling: transição com perda/ganho fictício foi regraduada importante por afetar recuperação de contexto — custo se ignorada: lembranças operacionais falsas.
- Suíte final após revisão:96/96grupos, exit0, `/tmp/minecraft-reviewed-suite-20261027.log`. Nova amostragem congelada: uma fabricação escolhida e uma consulta legítima; não é garantia de progresso a cada decisão. Próximo passo é ensaio físico, sem mais mudanças de código durante a execução.
- Ensaio físico3130060:4tábuas e1bancada fabricadas por decisão do9B. Seis propostas repetidas de meta já cumprida pausaram antes de nova ação; nenhum efeito pendente. A correção inicial do achado1 ainda era insuficiente. RED→GREEN passou a recusar a proposta opcional com feedback e permitir nova escolha independente de ação.145prontidão e96/96grupos verdes. Sono/0jobs/leases conferidos; snapshot após a bancada escolheu equipamento válido. Reconciliação atribuída de sessão será necessária após recarga.
- Humano pediu fecharMinecraft travado: SIGTERM exato em6619, saída confirmada; nenhum job/lease/efeito pendente. Depois reabriu em34993, ping confirmou1.16.5. Não reutilizar identidade do listener40613.
- A recarga3160380 repetiu estado antes de conectar e pausou sem nova conexão. Defeito mecânico: consulta técnica estava no esquema de setup, mas faltava na lista pré-conexão do agente. RED→GREEN incluiu estado/descobertaLAN e opção de ligação com destino explícito, preservando catálogo livre.56núcleo/146prontidão verdes; suíte e nova porta pendentes.
- Suíte da ligação técnica:96/96grupos, exit0. Nova porta34993 autorizada pelo humano foi aplicada ao objetivo/target da mesma tarefa em transação, com backup; critérios/recibos/falhas preservados. Sessão/mundo não foram aprovados automaticamente. Próxima etapa: conexão, revisão atribuída da continuidade e retomada física.
