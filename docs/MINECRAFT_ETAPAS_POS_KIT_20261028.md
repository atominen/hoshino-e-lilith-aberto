# Minecraft — etapas depois do kit de ferro (28/10/2026, tarde)

> Atualização posterior doCodex: [regra16GB e ensaio real4B com contexto16.000](ADMISSAO_16GB_E_MINECRAFT_4B_20261028.md).
> Ensaio encerrado às17:06, todas dormindo e tarefa das carnes ainda pausada.
> Usou o mesmo jogador com banco de teste separado; coletou/fabricou materiais
> e mudou de posição. O snapshot e a receita de retomada simples abaixo são
> anteriores a isso. Conferir recibos antes da continuidade; não presumir
> inventário/posição idênticos nem repetir ações ou reconciliação antiga.

Autor: Claude (condutor do ensaio). Continua
[a continuidade do Codex de 28/10](MINECRAFT_CONTINUIDADE_20261028.md) e
[autonomia e recuperação de 27/10](MINECRAFT_AUTONOMIA_E_RECUPERACAO_20261027.md).
Nada aqui aprova autonomia geral: cada etapa só conta com recibo e estado real,
e as ajudas humanas estão listadas abaixo.

## Estado real na pausa (16:26, pedido humano)

| Item | Valor conferido |
|---|---|
| Servidor | `10.0.0.200:25565`, Java 1.16.5, sobrevivência, **Fácil** desde ~13:06, keepInventory ligado pelo humano |
| Tarefa atual | `ct-d76da17105` (“consiga 30 carnes assadas, iguais ou diferentes”), conversa `claude_mc_servidor_ferro`, **pausada** no passo 74, sem pendência, 0 jobs |
| Lilith | dormindo (bot fora do servidor), última posição (-211, 63, -222) |
| Inventário | 6 cooked_salmon, 1 salmon, 14 bread, 10 coal, 2 string, espada/picareta de ferro, kit vestido |
| Forno dela | (-238, 63, -242) com **8 salmões** depositados às 16:11 (prontos para retirar) |
| Progresso da etapa | 6/30 assadas no inventário + 8 no forno |

## Etapas e resultado

| Etapa (pedido humano) | Tarefa | Resultado |
|---|---|---|
| Kit completo de ferro | `ct-4acf234a28` | Concluído 11:12 **com assistência** (ver doc do Codex) |
| Matar um mob qualquer | `ct-9d3b7b7cd3` | Concluído 13:07: morcego, 3 golpes, recibo `tool-ced4eb29e5`, morte pelo evento `entityDead` |
| 30 carnes assadas | `ct-d76da17105` | Em andamento: 6 assadas + 8 no forno |
| Arco (caçar aranhas) | — | Pendente; critério já reconhecido (`bow`) |
| 30 flechas | — | Pendente; critério já reconhecido (`arrow`) |
| Domesticar 2 gatos e nomeá-los com 2 etiquetas | — | Pendente; exige verificação de dono, pesca/troca para name tag, bigorna+XP |

## Intervenções humanas e do condutor (sem crédito a ela)

- Humano: Pacífico → Fácil; keepInventory; matou 2 creepers, 3 esqueletos e 1
  zumbi quando ela ficou parada entre tarefas; deu 20 pães (vida 4, fome 2);
  teleportou-a da caverna (y≈15) para a superfície.
- Condutor (autorizado pelo humano): respostas factuais no chat como jogador
  **ClaudeCondutor**; esclarecimento único do mundo (forno/combustível, 33
  lingotes); sonos de segurança com vida baixa (o bot sai do servidor).
- Todas registradas em `external_observations` do checkpoint de cada tarefa.

## Correções da tarde (todas com causa observada; suíte 96/96 em cada recarga)

| Commit | Causa | Correção |
|---|---|---|
| `d274e8a` | Etapa “matar mob” não era representável | Critério `killed`; caça (`perseguir`) até 30 s; morte só por `entityDead` de golpe dela; jogadores/aldeões recusados |
| `2dd6bd0` | 30 carnes iguais ou diferentes | Critério de grupo `cooked_meat`; forno e receitas aceitam carne crua; caça recolhe drops |
| `63ba93e`, `89a1b22` | Parada entre tarefas quase morreu; depois a vigia nova fazia dar voltas | Vigia de 1 s; alcance por tipo; foge de creeper/grupo; empunha espada; em ação só ameaça ≤3 blocos interrompe |
| `1938a51`, `ae62329` | Caçava morcegos/zumbis achando que davam carne | Opção diz o drop; com drops pedidos, só mobs que os soltam |
| `6369745` | Na caverna sem animais | `subir_a_superficie` para o último ponto sob céu aberto (luz do céu) |
| `5ff039e`, `2f04e65` | Recusas sem código viravam incerteza (alvo sumiu, forno ocupado) | `attack_preconditions`/`furnace_preconditions` sem efeito |
| `befe9c5` | Vida 7/fome 3 sem opção de comer; rota longa estourava 5 s; pedido humano: seguir jogador e visão maior | `comer:<item>`; pathfinder 15 s; tempo esgotado devolve posição; `seguir:<jogador>`; entidades a 48, blocos a 32, caça a 32 |
| `c29af24` | Com pão, a decisão pegou a bancada (vida 4) | Reflexo come com vida ≤12 e fome ≤17 |
| `295831a`, `ce9bd1c` | Reflexo/pathfinder trocavam o item da mão; colocação a 11 blocos | Reflexo devolve o item; colocar com `nome` equipa antes; distância >5 recusada |
| `9f9e9c3` | Na água ficava parada, afundava | Caça termina indo à terra firme; reflexo de afogamento a oxigênio ≤12 |
| `3da1598` | Coleta interrompida pelo reflexo ficava incerta | Devolve o ganho medido |
| `80952d3` | Forno dela fora da visão com 8 salmões; catálogo completo estourou 16K (ValueError pausou) | `ir_ao_forno` pela fundição registrada; estouro do catálogo vira recusa |

Correções da manhã até o kit: `e993107` (veio), `a38862d` (lava/fogo),
`690238e` (orçamento de raciocínio com conclusão forçada), `758c07e` (prazo
total da coleta), `e6073b0` (peça repetida/excedente do plano), `02a3002`
(pathfinder não cava estações). Medição GPU: 33 camadas cabem mas dão só +8%
(25→27 tok/s) com ~440 MiB livres; mantidas 32 (doc do professor registra
hotspot ~100 °C com offload total).

## Padrões observados (para o projeto principal)

1. **Efeito fora da ação dela muda o mundo** (reflexo, pathfinder com andaime,
   caça que se afasta): toda ação precisa devolver resultado *medido* quando
   outro mecanismo interrompe, e o estado da mão/posição deve ser reconferido
   antes de agir. Recusas anteriores ao efeito precisam de código estruturado.
2. **Comentário e escolha divergem** com frequência (“vou cozinhar” → caça).
   O que funcionou foi tornar as opções relevantes e factuais (drops, distância,
   prontos estimados), não ditar a sequência.
3. **Sobrevivência não pode depender do modelo**: comer, sair da água, fugir de
   creeper e lava são reflexos; o modelo decide objetivos.
4. **Crenças presas** (fuel=null, carne podre assa, 6 por pilha) cedem a fatos
   no texto das opções ou a um esclarecimento identificado; repetir a pergunta
   no chat sem resposta humana consome passos.
5. **Visão por tarefa**: perceber mais longe só ajuda se as opções filtrarem pelo
   que a tarefa pede.

## Limitações abertas

- Auditoria do Codex (`AUDITORIA_LOGICA_E_ROTEIRO_20261028.md`): T1–T8 e P1–P6
  ainda não implementadas (recibo de erro HTTP, janelas de forno concorrentes,
  retirada com inventário cheio, propriedade de forno por mundo etc.).
- Reflexo de fome registra “fome X → X” (valor atualiza depois); cosmético.
- Etiquetas de nome, domesticação, pesca e bigorna não existem ainda.
- Verificação de “matar mob” aceita qualquer mob (morcego); etapas futuras
  podem exigir espécie.

## Como retomar

1. Central ativa; acordar Lilith (`POST /api/start`, token de `central.url`, nunca imprimir).
2. Entrada `continue` em `entidades/lilith/runtime/bus/entrada/` (autor_id `codex_teste`,
   responder_para `claude_mc_servidor_ferro`, `synthetic_test: true`).
3. Ao reconectar, se a tarefa pausar pela trava de sessão:
   `scripts/minecraft_revisar_sessao.py revisar ct-d76da17105 <last-state>.json "motivo"`
   (estado salvo em `compartilhado/runtime/ensaios/minecraft-reconciliation-20261027/`).
4. Ela deve ver `ir_ao_forno` (8 salmões prontos). Depois das 30 carnes, enviar
   a etapa do arco e, em seguida, das 30 flechas, como objetivos separados.

## 30 carnes assadas — CONCLUÍDA (30/10/2026 01:18, `ct-d76da17105`)

Retomada a pedido humano para testar o intermediário 2B no Minecraft. A tarefa
foi conferida no mundo pelo próprio ciclo (`completed`) com **30 cooked_salmon**
no inventário de LilithMC (servidor 10.0.0.200).

**Retomadas e revisões, todas com evidência e autoria:**

- Revisões de continuidade de sessão depois das quedas de luz e de cada
  recarga. Evidência: posição e inventário do último estado no diário igual ao
  atual; numa delas, um deslocamento parcial já revisado.
- Recibos incertos (colocações recusadas pelo servidor perto do spawn; uma
  caminhada com timeout) revisados via `job_bus.resolve_reviewed`, com cópia do
  checkpoint em `compartilhado/runtime/ensaios/minecraft-reconciliation-20261027/`.
- O condutor respondeu uma pergunta factual dela no chat sobre os parâmetros de
  `minecraft_forno`, como ClaudeCondutor. Script persistente e registro em
  `compartilhado/runtime/ensaios/minecraft-chat/`.

**O que ela fez sozinha:**

- Pescou 5 salmões e retirou salmões do forno antigo.
- Morreu afogada (keepInventory).
- Perto do spawn, falhou 4 vezes colocando a bancada. Quando o recibo passou a
  dizer a distância ao ponto de nascimento (−137,83,−223), se afastou.
- Colocou a bancada fora da proteção, fabricou e colocou um forno, processou
  6 salmões com 1 carvão e retirou.

**Defeitos reais encontrados e corrigidos, cada um com teste:**

| Commit | Correção |
|---|---|
| `3607392` | Reflexo de afogamento sobe até a cabeça sair da água e só relata o que mediu |
| `a3625aa` | Cache do intermediário 2B no Minecraft pela chave do conteúdo, não pelo tamanho da lista (cheia em 128) |
| `9079849` | `activity_context` respeita a revisão atribuída no `job_bus` |
| `e67b0c3` | Recibo incerto mostra a resposta da ponte; a recusa perto do spawn diz a distância |
| `17d26a9` | Caminhada da ponte com orçamento de 50 s devolve o trecho medido, em vez de virar incerta |

**Observações em aberto:**

- **Decisões lentas no Minecraft:** cerca de 15 mil caracteres de raciocínio,
  2–5 min por decisão, batendo no limite de geração. O afogamento ocorreu
  enquanto ela pensava.
- **Intermediário 2B:** acertou quando consultado diretamente ("repete" em
  2,8 s). Nesta tarefa não chegou a avisar: as travas e regras resolveram, e as
  decisões repetidas vieram sem comentário.

**Próxima etapa da sequência humana:** arco (caçar aranhas). Enviar só com novo
pedido.

**Depois da conclusão (`88d7005`).** A fala final de uma tarefa Minecraft
conferida no mundo era tratada pela guarda de apresentação como "alegação sem
recibo", porque `frame.verificacoes['minecraft']` não era marcado. A correção
pedida pela guarda a fez dizer "a tarefa segue pendente".

- **Correção no código:** com `ultima_acao=minecraft_goal_verified`, o Minecraft
  conta como verificado, e o relatório dos critérios vira a evidência principal.
- **Correção para ela:** o condutor mandou uma correção factual. Ela conferiu o
  inventário e reconheceu a conclusão. Na resposta, chamou os salmões de
  "sardinhas" e atribuiu o erro à conexão.

## Arco — CONCLUÍDO (30/10/2026 18:37, `ct-6827e8b387`, passo 54)

Etapa pedida pelo humano. O arco foi fabricado com recibo e conferido no mundo: 1 bow no inventário de LilithMC.

**Como ela chegou lá:**

- Coletou madeira e fabricou tábuas e gravetos.
- Procurou aranhas. Perguntou no chat; o condutor respondeu com fatos, e depois combinou que o chat é do humano.
- Morreu cercada por zumbis e esqueletos à noite (keepInventory).
- O fio que faltava veio de uma aranha que se aproximou e foi morta pelo reflexo de defesa; ela recolheu 2 fios.
- Ela colocou a bancada e fabricou o arco.

**Defeitos encontrados ao vivo e corrigidos, cada um com teste e revisão do Codex:**

| Commit | Correção |
|---|---|
| `41bb164` | Parada pendente da ponte não cancela mais a caminhada seguinte |
| `9c9c2b9` | Ficar presa no lugar não aparece mais como "Andei 50 s" |
| `e2db3b1` | Estações lembradas; entregar item; o olhar acompanha o alvo; resposta junto com a ação; chat relido antes da escolha; ATO = Gustavo |
| `67225ca` | Rastrear o alvo mesmo longe; explorar até encontrar; trava de excesso; inventário cheio; aviso sem picareta |
| `a767c74` | A caça diz quanto acima ou abaixo a presa está |

**Pendentes:**

- **Reflexo de fuga.** A fuga cava e gastou as duas picaretas, e se repetiu 57 vezes numa caverna.
- **Ação contínua (proposta).** Hoje cada ação para no prazo e o corpo espera parado enquanto ela pensa.

**Próxima etapa da sequência humana:** 30 flechas. Enviar só com novo pedido.

### Revisão offline de 04/11

A fuga atual usa movimentos temporários sem cavar ou empilhar, e a ponte
distingue a presa da caça de uma ameaça independente. A revisão reproduziu
uma corrida entre a restauração do item na mão e um novo pedido de equipamento.
Enquanto a troca já iniciada aguarda confirmação, outro pedido recebe
`reflex_busy` com efeito `not_started`. O prazo continua impedindo que o
reflexo abra uma nova etapa após expirar.

A ponte já reage a quedas de vida e verifica ameaças próximas a cada segundo.
O teste seguinte de defesa deve medir separadamente o tempo até enviar o
comando e até observar seu efeito no servidor. A regressão offline confirma
a exclusão entre ações e usa respostas simuladas do servidor.

Validação em 04/11: 102 regressões da ponte, 102 testes do agente Minecraft
e 100/100 grupos da suíte offline. Não houve recarga da ponte ou ensaio no mundo.
