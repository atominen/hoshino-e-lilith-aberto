# Minecraft — autonomia, recuperação e estado em 27/10/2026 (noite)

> Continuação em 28/10: [continuidade do Codex](MINECRAFT_CONTINUIDADE_20261028.md) e
> [etapas depois do kit (Claude)](MINECRAFT_ETAPAS_POS_KIT_20261028.md).

Autor: Claude (condutor do ensaio). Continua
[a cognição e validação de 27/10](MINECRAFT_COGNICAO_E_VALIDACAO_20261027.md) e
[as referências e retomada do Codex](MINECRAFT_REFERENCIAS_E_RETOMADA_CODEX_20261027.md).
Este documento registra o que foi feito entre 17:20 e 21:25, o que ainda falha
e o plano para levar o comportamento ao projeto principal. **Nada aqui aprova o
kit de ferro**: a aprovação continua exigindo inventário, equipamento e recibos.

## Pedido humano que orienta esta etapa

> "Como ela vai ser uma entidade individual própria se não consegue fazer o
> básico? Ela não deve parar por nada naturalmente, e sim organizar-se,
> recalcular, pesquisar, concretizar informações e tentar falar com o usuário."

Também pedido: documentar tudo, organizar o projeto e só depois implementar
"de verdade" no projeto principal, olhando como os grandes projetos fazem.

## Estado real às 21:25

| Item | Valor conferido |
|---|---|
| Mundo | LAN 127.0.0.1:**32803**, Java 1.16.5 Fabric, sobrevivência, LilithMC |
| Tarefa | `ct-06c691fa40` (conversa `codex_mc34993_ferro`), passo ~141 |
| Equipado | **capacete e peitoral de ferro** (fabricados e vestidos por ela) |
| Inventário | 3 iron_ingot, 28 coal, 116 cobblestone, 195 oak_planks, 10 dark_oak_log, 4 crafting_table, sem picareta |
| Forno | vazio; 16 lingotes fundidos e retirados por ela (`tool-911e40c838`, `tool-6a5c41e1a7`, `tool-805c6c7a32`) |
| Falta | calças, botas, espada, picareta, machado e pá de ferro: 20 lingotes, ela tem 3 |
| GPU | 9B com **32 camadas fixas**, ~25–30 tokens/s |

Marcos confirmados por recibo e mundo nesta etapa: forno fabricado
(`tool-727b113500`) e colocado; 16 lingotes; capacete (`tool-f504c7efc8`) e
peitoral fabricados e equipados. A meta final ganhou uma etapa nova do humano:
depois do kit equipado, **matar um mob qualquer** (a verificação dessa morte
ainda não existe e deve ser feita antes de aprovar essa etapa).

## Intervenções humanas e do condutor (não contam como autonomia)

- Teleporte humano para perto do forno e da bancada às ~19:20, mais um
  deslocamento de 2 blocos. Regra do humano: "qualquer mudança repentina sou eu".
- Tábuas e deslocamentos anteriores (131→195) já registrados como ajuda humana.
- Portas trocadas pelo humano: 34993 → 37235 → 32803. A tarefa foi
  redirecionada com registro atribuído (`target_changes` no checkpoint) e a
  continuidade foi conferida por posição e inventário em cada reconexão.
- **Esclarecimento único** do condutor (autorizado pelo humano) às 21:00 e,
  depois, a **sequência em ordem** pedida pelo humano às 21:15, ambos no texto
  do objetivo com autoria identificada (`clarification`/`ordered_guidance`).
- Duas perguntas de conversa do condutor foram tratadas pelo sistema como
  tarefas novas (`ct-e5861686a8`, `ct-93f5f0b052`); só leram estado/pesquisaram,
  foram marcadas como canceladas com nota. Ver limitação L3.

Reconciliações, backups e revisões de sessão estão em
`compartilhado/runtime/ensaios/minecraft-reconciliation-20261027/`.

## Correções desta etapa (todas com causa demonstrada, suíte 96/96)

| Commit | Causa observada | Correção |
|---|---|---|
| `30073ec` | 8 iron_ore no forno sem opção de retirar; o plano dela tentava recarregar o forno ocupado; duas decisões esgotaram 4096 tokens e pausaram a tarefa | Fundição própria persistida pela ponte e visível no estado; opção `retirar:<produto>`; `fundir` some enquanto aquele forno tem carga dela; raciocínio esgotado vira recusa, não pausa |
| `68c6763` | Estado repetia `phase: processing` do depósito, 26 min antes; ela buscava carvão "para manter o forno" | Estado mostra depósito, combustível e hora; opções estimam prontos (~10 s/item, 8 por carvão) |
| `b2abef4` | Pedido humano: histórico poluído e sem lista de planejamento | Janela de recibos sem reconexões/recusas; plano opcional de até 6 passos com `feito_quando` conferido pelos fatos e aviso após 4 ações sem avanço |
| `1f804a2` | 7 de 36 decisões com raciocínio esgotaram 4096 tokens | 8192 para decisão e meta (só o executor principal); passo `ter coal_ore` volta com o item certo |
| `e5a690b` | Pedido humano: pesquisar e consolidar habilidades (padrão Voyager/JARVIS-1/GITM) | `pesquisar` direto; `registrar_aprendizado` após produção confirmada, com recibos como evidência; `meu_conhecimento` recuperado pela meta; `coleta_sem_ferramenta` |
| `0d46216` | 8192 tokens passavam do prazo fixo de 300 s | Prazo do stream proporcional ao orçamento pedido |
| `0999be7`, `33ceb64` | 9B preso em 20/33 camadas (CPU 409%, GPU 15%, ~40 W): métrica incerta e residência velha caíam em silêncio no perfil base | Degrau incerto pode subir uma vez; residência velha é relida antes de concluir pressão |
| `8820f9c`, `9f746b5` | Pedido humano: camada fixa | `gpu_layers_fixed: 32` em `executores.json` de Lilith e Hoshino (não versionado; backups no diretório de reconciliação); caminho fixo também relê residência |
| `0deae8e` | Com o modelo já carregado, cada requisição somava +512 MiB de workspace e esperava 120 s | Mesmos pesos residentes no degrau pedido não recontam workspace; margem de 768 MiB mantida |
| `0f81254` | Meta autoral `coal_ore 4` impossível (o bloco solta coal; sem picareta); capacete/peitoral fabricáveis sem ligação ao objetivo | Candidatos de meta usam o item solto; fabricar peça que falta é anotado como parte do objetivo |
| `5c43ec3` | Pedido humano: barreira não pode parar a entidade | Primeira sequência sem progresso registra `barreira` e pede revisão, recálculo, pesquisa ou pergunta; só uma segunda sem avanço pausa; nova opção `perguntar_humano` |

Erros do condutor registrados: duas edições de código logo após pedir o sono,
antes de confirmar a saída (sem efeito, mas contra a regra); o caminho fixo de
GPU introduziu uma espera de 120 s corrigida em `9f746b5`.

## O que os grandes projetos fazem diante de falha e como isso se aplica

| Referência | Prática | Situação aqui |
|---|---|---|
| [DEPS (ICML 2023)](https://arxiv.org/abs/2302.01560) | Na falha, um descritor resume estado e resultado; o LLM **explica o erro do plano anterior** e replaneja | Parcial: `barreira`, recusas e trajetória chegam à decisão; falta pedir explicitamente "o que deu errado no plano" |
| [Reflexion (NeurIPS 2023)](https://arxiv.org/abs/2303.11366) | Reflexão verbal sobre o retorno, guardada em memória episódica e usada nas próximas tentativas | Parcial: notas autorais e procedimentos; falta uma reflexão curta persistida por barreira |
| [Voyager](https://arxiv.org/abs/2305.16291) | Três retornos (ambiente, erro de execução, autoverificação por crítico) até a tarefa ser validada; habilidade só entra na biblioteca depois de verificada | Recibos físicos fazem o papel do crítico; `registrar_aprendizado` só após produção confirmada |
| [JARVIS-1](https://arxiv.org/abs/2311.05997) | Memória de planos que deram certo, com a situação | Procedimentos com evidência de recibos; recuperação por meta |
| [GITM](https://github.com/OpenGVLab/GITM) | Conhecimento textual da internet + memória de listas de ações bem-sucedidas | `pesquisar` + procedimentos |
| [Odyssey](https://arxiv.org/abs/2407.15325) | Planejador, executor e crítico; habilidades compostas que conferem pré-requisitos | Pré-condições na ponte; habilidades compostas (ex.: fundir e retirar) ainda são passos separados |
| [Mindcraft](https://github.com/mindcraft-bots/mindcraft) | Objetivo persistente e "self-prompting" contínuo | Tarefa durável + ciclo existente; sem segundo scheduler |
| [KnowNo (CoRL 2023)](https://arxiv.org/abs/2307.01928) e [Requesting Expert Reasoning (2026)](https://arxiv.org/abs/2602.22546) | Pedir ajuda humana quando a incerteza é alta ou depois de N autocorreções falharem, equilibrando autonomia e carga humana | `perguntar_humano` + barreira: primeiro autocorreção, depois pergunta/pausa |

## Limitações ainda abertas (para a implementação definitiva)

- **L1 — Ainda há paradas "naturais"**: troca de sessão após recarga (trava de
  continuidade, exige revisão do condutor), erro de backend do LLM, efeito
  incerto pós-envio e a segunda barreira sem avanço. As duas primeiras são de
  manutenção; as duas últimas deveriam virar pergunta ao humano com contexto,
  não silêncio.
- **L2 — A pergunta ao humano** chega como mensagem de pausa da conversa do
  ensaio; não há ainda caminho para a resposta humana voltar ao checkpoint como
  fato atribuído, nem retomada automática quando ele responde.
- **L3 — Conversa e tarefa se misturam**: mensagens simples na mesma conversa
  viram tarefas novas, e a resposta de conversa não recebe o estado do
  Minecraft (ela respondeu "coletar madeira" com 195 tábuas e "anel mágico").
  Falta um canal de conversa que veja o estado da tarefa sem criar tarefa.
- **L4 — Crença presa**: mesmo com o esclarecimento, o plano dela seguia
  "retirar os lingotes do forno" vazio. Falta o passo DEPS de explicar o erro
  do plano antes de replanejar, e uma observação ativa do forno quando ela
  está ao lado dele.
- **L5 — Morte no jogo** não é tratada: não há sinal de perigo (vida, queda,
  lava, mobs próximos com linha de visão) na decisão nem recuperação após morte.
  Morrer derruba o equipamento; isso precisa ser prevenido antes da etapa de
  matar um mob.
- **L6 — Comentário e escolha às vezes divergem** ("minerar carvão" escolhendo
  tronco). A projeção estruturada deve recusar a nota que descreve outra ação,
  ou pelo menos registrar a divergência.
- **L7 — Verificação de "matar um mob"** inexistente no verificador.
- **L8 — Raciocínio longo**: decisões confusas usam 12–22 mil caracteres
  (2,5–5,8 min). A GPU não é o gargalo; a clareza do contexto é.

## Plano para levar ao projeto principal (depois de funcionar no ensaio)

1. Contrato "nunca parar em silêncio" no ciclo de tarefas: toda condição de
   parada não manutenção gera (a) reflexão curta da entidade sobre o que deu
   errado, (b) replanejamento, e só então (c) pergunta ao humano com o contexto;
   a pausa passa a ser "aguardando resposta", com retomada quando ele responde.
2. Canal de conversa com contexto de tarefa ativa, sem criar tarefa nova.
3. Sinais de perigo e sobrevivência na percepção, antes de combate.
4. Verificador de morte de mob por evento da ponte (entidade alvo, recibo).
5. Generalizar plano conferido, recibos de trabalho e aprendizado confirmado
   para tarefas fora do Minecraft.
6. Atualizar a documentação geral e o README só depois dessas validações.

## Como retomar

Ver o [handoff](HANDOFF_CLAUDE_MINECRAFT_20261027.md). Resumo: Central em
`iniciar_entidades.py --entity lilith --no-browser`; a cada recarga, sono
cooperativo e saída confirmada; revisão de sessão com
`scripts/minecraft_revisar_sessao.py` (o diagnóstico da ponte troca de arquivo
à meia-noite UTC: `entidades/lilith/runtime/diagnostics/minecraft_AAAA-MM-DD.jsonl`).
Mudança repentina de posição ou itens é intervenção humana: registrar sem crédito.
