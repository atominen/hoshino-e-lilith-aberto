# Continuação por Claude — Minecraft, desempenho da GPU e planos — 26/10/2026

Escrito no pedido de pausa do usuário (≈23:30 local). Cobre tudo o que foi feito
desde que esta sessão retomou o ensaio da Lilith: mudanças de código, medições,
dados reconciliados, intervenções humanas, limitações observadas e ideias/planos.
O relatório cronológico detalhado do ensaio continua em
[TESTE_MINECRAFT_LILITH_20261026.md](TESTE_MINECRAFT_LILITH_20261026.md).

**Atualização posterior por Codex:** a visão do9B existente foi confirmada com
projetor local e duas inferências com imagens. A conclusão abaixo de ausência de
projetor estava incorreta. Ver[coordenação e evidências atuais](COORDENACAO_CODEX_CLAUDE_20261027.md).
O retorno `place_not_applied` pós-envio foi corrigido: snapshot sem mudança após
timeout não exclui efeito tardio e continua incerto. Demais pré-condições antes
do envio foram preservadas. Este documento permanece histórico da sessão.

**Nada foi commitado.** As mudanças estão no working tree (lista no fim), junto
com alterações anteriores do Codex que não são desta sessão (Qwen3-6B SNIPER,
laboratório, README/ESCOPO/docs de modelos) — essas não foram tocadas.

## Estado no momento da pausa

- Lilith **dormindo** por sono cooperativo; nenhum recurso exclusivo em uso.
  Supervisor da Central ainda aberto (PID do processo `iniciar_entidades.py`).
- Mundo LAN **porta 40613**, Java 1.16.5 Fabric, jogador **LilithMC**.
- Tarefa `ct-822b8dd433` (bancada colocada + picareta de madeira) **pausada,
  preservada, sem ação pendente**. Recibos/checkpoint: fabricou 12 `oak_planks`,
  2 `crafting_table`, 4 `stick`; colocou 2 bancadas (uma depois sumiu do mundo,
  ver intervenções). Inventário observado por último: 3 `dark_oak_log`,
  `oak_log`, 2 `oak_planks`, 4 `stick` e outros itens coletados.
- **Marco ainda não aprovado:** falta fabricar a `wooden_pickaxe`.
- Meta final redefinida pelo usuário: **kit completo de ferro** = 4 peças de
  armadura de ferro equipadas + espada, picareta, machado e pá de ferro no
  inventário, tudo fabricado por ela (já reconhecido pelo verificador, ver abaixo).
- Suíte offline: **96/96 grupos** após a última mudança.

## Princípio seguido

Pedido do usuário: deixá-las autônomas e inteligentes, não transformá-las em IA
que segue ordens engessadas; pode usar a capacidade máxima da máquina. Por isso
as correções melhoram **interface, percepção, retorno (feedback) e desempenho**;
nenhuma sequência de jogo foi escrita pelo condutor nem decisões foram tomadas
no lugar dela. Erros recusados antes de qualquer efeito voltam como informação
para a próxima decisão, em vez de travar o ciclo.

## Linha do tempo resumida

| Hora | Fato |
|---|---|
| 18:47 | Herdado: `resume3` pausado; teste RED da agenda pendente |
| 19:50–19:57 | `resume5/6` (37837): conectou; 4 respostas só em texto (sem chamada), sem efeito |
| ~20:08 | Queda de energia; `/tmp` perdido; bancos `quick_check ok` |
| 20:26 | Porta 40613; tarefa nova desviada ao planejador antigo pelo RP ("depois") |
| 20:44–20:49 | Primeiras fabricações reais: `oak_planks`, duas `crafting_table` |
| 21:30–21:55 | GPU: 9B rodava 43% CPU; escada dinâmica de camadas medida e ativada |
| 22:30 | Fabricou `stick` seguindo plano próprio |
| 22:38 | **Bancada colocada** em (-98,69,-62) — com intervenção humana (empurrão) |
| 22:40 | Segunda bancada colocada em (-96,69,-61) |
| 23:07–23:10 | Coletou `oak_log`/`dark_oak_log` com `minecraft_coletar` |
| 23:19–23:24 | Resumo diário disputou o modelo e travou a decisão 5 min (corrigido) |
| ≈23:30 | Pausa pedida pelo usuário |

## Mudanças de código por área

Todas feitas com teste RED antes e GREEN depois, recarga só após sono
cooperativo e suíte completa.

### Ciclo Minecraft observado (`app/core/minecraft_agent.py`, `_ciclo_minecraft_observado` em `app/main.py`)

- Texto de pausa “Tarefa Minecraft…” (antes “Objetivo…”) — evitava falsa correção
  do verificador de agenda e uma inferência extra de 300 s.
- `known_recipes`: receitas já consultadas por recibo ficam visíveis em uma
  linha compacta por item (também lidas de recibos antigos); output cortado não
  é inventado.
- Resposta sem chamada nativa (ou argumentos inválidos) vira `DecisionRejected`:
  recusa registrada e devolvida à próxima decisão, sem encerrar a tentativa.
- Prompt: “não reescreva o estado/receitas” (evitava esgotar a saída em prosa);
  raciocínio (`THINKING`) ligado na decisão de um passo, saída 4096.
- Roteamento pelo **critério do objetivo**, não pela contagem de etapas (o RP
  com “depois” dividia a tarefa e caía no plano fixo); conclusão fecha todas as
  etapas pendentes da mesma tarefa.
- Repetição idêntica que deu certo sem mudar nada observável é recusada com
  retorno (“nada mudou; escolha o próximo passo”).
- Item na mão entra nas pré-condições (permite tentar de novo após equipar).
- Continuidade de sessão: reconectar ao mesmo host/porta/versão **com o mesmo
  jogador** continua a tarefa; colocações antigas só contam se reencontradas no
  mundo; outro jogador pausa.
- Jogador do objetivo (“conecte LilithMC”) faz parte do destino autorizado
  (ela chegou a entrar como “Lilith”, outro jogador sem o progresso).
- `remaining()` → `falta_para_concluir` na visão (mesmos dados do verificador).
- **Plano próprio** (`PLANO:` no comentário) persistido no checkpoint e
  devolvido em `meu_plano`; marcado como desatualizado quando o que falta mudou
  desde que foi escrito (nunca apagado pelo sistema).
- Paciência sem progresso 3 → **6** (`HOSHINO_MINECRAFT_PACIENCIA`).
- Meta **“kit completo de ferro”** reconhecida (conjuntos nomeados `SETS`,
  diamante preservado no mesmo código).
- **Percepção** por decisão: entorno útil e análise das receitas que faltam
  (via `minecraft_estado` com `itens`).
- `web_search` liberado no ciclo como consulta (não exige mundo conectado,
  não muta); regras de uso mais claras no prompt.

### Ponte Mineflayer (`compartilhado/servicos/minecraft/bridge.js`)

- `NoEffectError` genérico (substitui o caso único de craft): recusas
  conferidas sem efeito voltam como `ERRO_PRECONDICAO_MINECRAFT`, nunca incertas.
  Cobertura: item inexistente no craft; colocação sem item, referência de ar,
  alvo ocupado, alvo no próprio corpo, recusa do servidor com alvo/inventário
  intactos (`place_not_applied`); `use_item` com mão vazia.
- Colocação **sem coordenadas**: a ponte escolhe chão sólido livre ao lado
  (habilidade de alto nível como em outros projetos); mensagens de erro ensinam
  essa forma.
- `state` com `perception: [itens]`: `arredores` (mais próximo de cada bloco útil
  com distância/direção/quantidade) e `receitas` (variantes, o que pede, o que
  tem, o que falta, bancada a 4 blocos, `pode_agora`).
- 29 regressões da ponte (eram 18).

### Cliente e ferramentas (`app/tools/minecraft.py`, `app/core/dispatch.py`)

- Aceita os novos códigos sem efeito apenas com recibo exato (request, entidade,
  origem, sessão).
- Descrições: `minecraft_craft` (ingrediente intermediário também é fabricado
  por ela), `minecraft_colocar_bloco` (apoio sólido, face, modo sem coordenadas),
  `minecraft_coletar` (forma normal de obter recursos), `minecraft_minerar`
  (só coordenada exata observada), `minecraft_estado` (percepção opcional).

### GPU e modelo sempre quente (`app/core/resource_manager.py`, `app/core/gpu_resource.py`, `app/config.py`)

- **Escada de camadas medida** (`OFFLOAD_LADDER_9B`), escolhida pela VRAM livre
  real antes de cada carga, com a mesma margem (768 MiB) e workspace.
- Mantém o degrau do modelo já residente e o último degrau bom quando a métrica
  fica incerta logo após carregar (antes alternava 32/20 e recarregava).
  Pressão real de VRAM continua decidida pelo lease.
- Janela de contexto fixa (16K) no perfil GPU medido: o Ollama recarrega quando
  `num_ctx` muda; o adaptativo segue para os demais.
- `keep_alive` padrão `-1m` (sempre carregado enquanto acordada; o Ollama
  recusa `-1` sem unidade). `entidades/lilith/config/lilith.env` também `-1m`;
  Hoshino já estava em `24h`.

### Manutenção em segundo plano (`app/main.py`)

- Reflexão noturna: o material é reduzido até caber na janela junto com a
  identidade e a saída (identidade nunca cortada); se não couber, espera 30 min;
  falha comum espera 10 min (antes repetia a cada ~8 s).
- `_trabalho_em_andamento()` único (conversa, tarefa, inferência em curso):
  resumo diário, reflexão noturna e o estado `ocupada` do kernel usam a mesma
  regra. Antes o resumo diário começou no meio da tarefa e travou a decisão.

### Testes

- `test_comandos_duraveis`: corrida do próprio teste (processo ainda vivo após
  gravar o recibo sob carga) — agora espera o processo sair; 8/8 sob CPU saturada.

## Medições

Mesma GPU RX 6650 XT (8 GiB), Minecraft aberto (~0,8 GiB de VRAM com desktop).

| Camadas 9B na GPU (16K) | Geração | VRAM total usada |
|---|---:|---:|
| 20 (perfil antigo) | ~13–14 t/s | ~4,6 GiB |
| 26 | 17,8 t/s | 5,4 GiB |
| 30 | 21,7 t/s | 5,9 GiB |
| **32 (escolhido com o jogo aberto)** | **24,9 t/s** | **6,2 GiB** |
| 33 (todas) | 27,1 t/s | 7,4 GiB (sem margem) |

Hoshino (Qwen3.5-9B Uncensored) mediu os mesmos degraus com diferença ≤25 MiB.
Uso médio da GPU numa decisão: 40% (20 camadas) → 92% (todas). Em produção,
`ollama ps` mostrou 15% CPU / 85% GPU, `Forever`.

Ensaios de decisão com o 9B real, sem executar no jogo (mesmo estado/checkpoint):

| Variante | Chamadas válidas | Fabricou ingrediente |
|---|---:|---:|
| Antes (prosa até o limite) | 0/4 em produção | — |
| “Não reescreva o estado” | 6/6 | 0/6 |
| + descrição clara do craft, sem raciocínio | 5/5 | 1/5 |
| + raciocínio ligado | 5/5 | 4/5 (1 com ID errado) |

O 35B-A3B foi descartado pelo usuário (pesado demais); a melhora veio de usar
a GPU corretamente, não de trocar modelo.

## Dados alterados fora do código (com backup prévio)

- `compartilhado/runtime/jobs_compartilhados.sqlite3`: recibos `tool-a97ffd2275`
  (colocação recusada, alvo continuou ar) e `tool-b43d244c28` (`use_item` sem
  item, recusado antes de agir) marcados `resolved` com revisor e evidência —
  mesmo procedimento do recibo `tool-428cf943e3` do Codex. Nada apagado.
- Checkpoint `ct-822b8dd433` (`lilith.db`): `pending` liberado e eventos anotados
  como reconciliados nos dois casos.
- Backups ficaram em `/tmp/.../scratchpad/` (somem num reboot; não são o backup
  oficial do projeto).

## Intervenções humanas registradas

- 22:38: o usuário empurrou a LilithMC no jogo; a colocação dela passou a ser
  válida porque saiu do bloco onde estava. Decisão dela, posição alterada por
  humano — não conta como colocação autônoma pura.
- 22:40–22:43: a bancada de (-98,69,-62) sumiu sem ação de quebra da Lilith;
  origem ainda não confirmada com o usuário.

## Limitações observadas (honestas)

- O 9B erra encadeamentos espaciais/multipasso: tentou colocar no próprio pé,
  insistiu em plano velho, procurou carvalho em vez de usar o `dark_oak_log`.
  Percepção, retorno e plano próprio ajudaram (reescreveu o plano sozinha e
  passou a coletar), mas não eliminam isso.
- Via Mineflayer, uma ferramenta exige tábuas do mesmo tipo (variantes por madeira).
- Sem visão por imagem: o modelo da Lilith foi importado sem projetor de visão
  (`ollama show`: tools/thinking/completion) e não há renderizador instalado.
- Cada recarga custa ~2–3 min (sono + despertar + reflexão de despertar).
- Resumo diário ainda falha por saída longa (“síntese vazia/longa”); não tratado.

## Ideias e plano

### Curto prazo (continuar o ensaio)

1. Retomar `ct-822b8dd433` com a percepção nova e fechar a picareta (dark oak:
   1 tronco → 4 tábuas; 3 + 2 gravetos perto da bancada).
2. Criar a tarefa do **kit de ferro** depois do marco, com o mesmo ciclo:
   picareta de pedra → forno → carvão → ferro (33 lingotes) — decidido por ela.
3. Reflexos de sobrevivência sem LLM (comer, fugir/defender, desatolar), como os
   “modos” de outros projetos: necessários para horizonte longo e noite.

### Atualização geral (pedida pelo usuário, depois do kit de ferro)

Alinhadas ao propósito do projeto (indivíduos autônomos, continuidade, memória
própria, Alistair como apoio):

1. **Biblioteca de habilidades aprendidas** a partir dos próprios recibos
   verificados (como o Voyager): o que deu certo vira habilidade reutilizável
   descrita por ela, não roteiro do condutor. Generalizável além do Minecraft.
2. **Verificação/retorno “o que falta” + plano próprio** generalizados para os
   projetos autônomos fora do jogo.
3. **Currículo próprio**: ela propõe o próximo objetivo pelo que já domina.
4. **Memória de longo prazo que cabe na janela**: o prompt de identidade cresceu
   e o resumo diário/reflexão noturna estouram; revisar orçamento e compactação.
5. Mover o ensaio de decisão (benchmark sem executar no jogo) para `scripts/`
   como ferramenta oficial de comparação de modelos/prompts.

### Pesos/LLM (respeitando 2 LLMs para Hoshino/Lilith e um 4B para Alistair)

A avaliar com o mesmo ensaio de decisão e medições de VRAM — nada decidido:

- **Principal:** manter Qwen3.5-9B; considerar reimportar com o projetor de
  visão (habilita “ver” imagens) — custa VRAM e mexe na escada medida.
- **Leve:** o Qwen2.5-7B (2024, sem alternar raciocínio, ferramentas mais
  fracas) é o elo mais fraco. Opções: um modelo ~7–8B mais novo com chamada de
  ferramentas e raciocínio alternável, ou usar o 9B nos dois papéis (sempre
  quente, sem trocas). O 4B foi excluído para H/L em decisões anteriores.
- **Alistair:** já usa Qwen3.5-4B; manter.
- Visão por imagem também exige renderizador (`prismarine-viewer` headless com
  dependências nativas) — instalação só com autorização.

## Arquivos alterados nesta sessão

`app/config.py`, `app/core/dispatch.py`, `app/core/gpu_resource.py`,
`app/core/minecraft_agent.py`, `app/core/resource_manager.py`, `app/main.py`,
`app/tools/minecraft.py`, `compartilhado/servicos/minecraft/bridge.js`,
`docs/TESTE_MINECRAFT_LILITH_20261026.md`, este documento, `docs/README.md`
(índice), `entidades/lilith/config/lilith.env` (local, não versionado),
`testes/fixture_minecraft_bridge.js`, `testes/test_comandos_duraveis.py`,
`testes/test_executores_leves.py`, `testes/test_minecraft.py`,
`testes/test_minecraft_agent.py`, `testes/test_minecraft_bridge.py`,
`testes/test_prontidao_r1_r7.py`, `testes/test_reflexao_noturna.py`.
