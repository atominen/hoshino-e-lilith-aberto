# "Vou conectar agora" e nada acontece: causa, correção e a volta ao Minecraft (12/11/2026)

Pedido do Gustavo (12/11, de manhã): "veja o porquê isso tá acontecendo, repare e use a versão treinada do banco v6",
com o servidor de Minecraft aberto e a ideia de "deixar ela lá sozinha prosseguindo".

## O que aconteceu

Às 07:26 a Lilith (9B treinado no corpus v5, memória zerada às 07:10) recebeu pelo chat da Central:

1. "O servidor de Minecraft está aberto em 10.0.0.200:25565. Pode entrar e jogar por conta própria; o que fazer lá
   você decide." Ela consultou `minecraft_estado`, leu "ponte indisponível" e respondeu como se o recado fosse para a
   pessoa: "A porta 25565 está aberta e você pode entrar."
2. "Era pra você entrar, não eu: conecte a sua personagem LilithMC…" Em 10 passos, com 49 ferramentas oferecidas, ela
   não chamou nenhuma. Só escreveu: "Vou conectar agora…", "A conexão já foi feita", "Consegui conectar!", e cinco
   vezes "Vou chamar minecraft_estado de novo". As travas recusaram cada alegação, e a resposta final foi a honesta
   ("Não vou afirmar que a tarefa foi concluída…").

As duas mensagens foram enviadas pelo Claude, como `usuario`, a pedido do Gustavo.

## Causa: três coisas diferentes

| # | O que | Rótulo | Prova |
|---|---|---|---|
| 1 | Os pesos treinados (v5 **e v6**) quase não chamam ferramenta. O 9B original chama. | **TREINO** | medição abaixo |
| 2 | O código cobrava a ação com um texto vago e, quando o verbo não estava na lista ("conectar"), nem cobrava | **CÓDIGO** | medição abaixo |
| 3 | "Jogue por conta própria" não é um objetivo que o ciclo de Minecraft reconhece | **CÓDIGO** (falta um modo) | `minecraft_agent.targets()` devolve `None` |

### 1. O treino tirou a chamada de ferramenta

O banco de treino atual (v5 e v6) só tem conversa em texto: 441 falas de `user` e 441 de `assistant` no treino da
Lilith, nenhuma com ferramenta (os 63 exemplos com `tool_calls` do banco ficam fora, porque o treinador só aceita os
papéis `user` e `assistant`). O adaptador aprende que toda resposta é texto.

A **prova de teto de 08/11** concluiu que "anunciar e não chamar" era "limite do 9B". Ela foi feita com o treinado v5.
Com o 9B original a conclusão não se repete neste cenário: a parte de "agir" era, pelo menos em boa parte, **efeito do
treino**.

### 2. A cobrança do código não funcionava com esses pesos

- "conectar" não está na lista de verbos de computador (`abrir`, `criar`, `enviar`…), então "Vou conectar agora" não
  era reconhecido como anúncio. Ia a cobrança genérica: "Não encerre ainda. O pedido é deliberadamente aberto…".
- Quando era reconhecido ("vou checar"), o texto mandava chamar "ficha_da_maquina, pesquisa, histórico ou memória".
- A cobrança valia uma vez por turno.
- O turno rodava sem raciocínio ("conversa de rotina").

### 3. Pedido aberto não entra no ciclo do Minecraft

O ciclo que joga sozinho (`_ciclo_minecraft_observado`: observar, escolher uma ação em formato forçado, conferir) só
começa com um objetivo verificável, como em outubro: "Minecraft: conecte LilithMC ao servidor… Consiga 30 flechas."
O pedido aberto virou uma tarefa genérica, planejada com uma única operação (`minecraft_estado`), e foi encerrada.

## Medição com o modelo real

Ensaio `compartilhado/runtime/ensaios/acao-minecraft-20261112/replay.py`: repete o segundo turno com o prompt real, as
49 ferramentas reais e as cobranças reais; os resultados das ferramentas são simulados (nada entra no servidor).
Sucesso é chamar `minecraft_conectar` com o endereço certo em até 10 passos. Cinco amostras por célula.

| Variante | 9B original | treinado v5 | treinado v6 |
|---|---|---|---|
| como estava (sem raciocínio, cobrança antiga) | **5/5** | **0/5** | **0/5** |
| só ferramentas de Minecraft (em vez de 49) | — | — | 0/5 |
| raciocínio ligado | 5/5 | — | 3/5 (4/5 chamam no 1º passo) |
| cobrança dirigida, pelo nome da ferramenta | 5/5 | — | 5/5 |
| cobrança dirigida + raciocínio | — | — | 5/5, ~10 s |
| decisão em formato forçado (JSON) | — | — | 5/5, com chamadas a mais |
| **código corrigido (funções reais)** | **5/5** | **4/5** | **4/5** |

As duas falhas que sobraram foram resposta vazia depois de duas ferramentas; a Central tem recuperação própria para
isso, que o ensaio não reproduz.

Observação técnica: o Ollama 0.32.6 recusa `format` junto com `tools` ("failed to parse grammar"). A decisão em
formato forçado precisa levar o catálogo no texto do pedido.

## O que mudou no código

| Arquivo | Mudança |
|---|---|
| `app/core/conferencia.py` | `ferramentas_anunciadas()`: o anúncio é reconhecido pela ferramenta oferecida, pelo nome escrito ("vou chamar minecraft_estado") ou pelo verbo do nome ("vou conectar", "conectando") quando a pessoa pediu essa ação. `cobranca()` diz qual ferramenta ela citou. `pede_acao()` reconhece o pedido. Até 3 cobranças dirigidas por turno (`MAX_COBRANCAS`) |
| `app/main.py` | O ciclo usa a cobrança dirigida e repete enquanto ela anunciar uma ferramenta que ainda não chamou; depois vem o pedido de honestidade de 11/11 |
| `app/core/resource_manager.py` | Pedido de ação liga o raciocínio do turno (`action_request`) |
| `app/core/dispatch.py` | O próprio nome ("Lilith", "LilithMC") e "identidade" não oferecem mais as ferramentas das outras entidades (regra de 07/11 e 11/11). O Alistair segue como estava |
| `app/tools/minecraft.py` | "Ponte indisponível" agora diz o que é a ponte e quais ferramentas a iniciam |
| `laboratorio/treinos_unificados.py` | O "Preparar" da Central falhava com `No module named 'core'` (aconteceu em 11/11 às 20:30 e 20:38). O worker põe `app/` no caminho |
| `laboratorio/professor_moe.py` | Falso positivo do verificador de entrega incerta (Lilith 7/8 → 8/8, Alistair 6/8 → 7/8) |

Testes: `test_fatos_e_correcoes` (31), `test_executores_leves` (116), `test_prontidao_r1_r7` (164), `test_minecraft`
(27), `test_minecraft_agent` (102), `test_capacidade_operacional` (20), `test_logica_cognitiva`, `test_hoshino` (127),
`test_despertar_prompt_treinado` (12), `test_integracao` (44) e os 164 do laboratório: todos passam.

## Tarde: as correções e o banco (pedido humano "faça essas correções e atualize o banco de treinamento")

### TREINO: o banco agora ensina a chamar ferramenta

| O quê | Onde |
|---|---|
| Formato único de treino, sem torch, usado pelo montador e pelo treinador: texto como antes (até 256 fichas, alvo na última fala); com ferramenta, montado pelo modelo de chat do Qwen3.5 (o mesmo que o Ollama usa, conferido byte a byte), definições das ferramentas no system, alvo nas chamadas e na resposta da última rodada, até 768 fichas | `laboratorio/formato_treino.py` |
| O treinador lê `tools` de cada linha; com ferramenta no corpus, o preset ganha `max_length` 768 e `tool_calls` | `laboratorio/treino_nf4_curto.py` |
| O montador exporta os exemplos com ferramenta para treino, validação e prova separada, com as definições reais das ferramentas usadas mais duas de distração (reprodutíveis), e conta as fichas com o mesmo código do treinador | `scripts/montar_banco_v6.py` |
| Aspecto "agir": 25 situações (Minecraft, PC, várias ações, depois da cobrança) e 4 diálogos do Alistair; as frases reais desta manhã como respostas ruins; dois casos que pedem pergunta em vez de chamada | `laboratorio/identidade/v6/pares_agir.txt`, `alistair_v6.txt` |
| Prova separada: 3 casos de agir | `holdout_hl_v6.txt` |
| Contrato novo na avaliação: `tool_call` ("Abre o Firefox para mim, por favor." com a ferramenta oferecida → precisa sair `<tool_call>` com `abrir_aplicativo`); versão `identity-contracts-v3` | `laboratorio/versionamento_lora.py` |

Números do banco (12/11): com ferramenta no treino, Hoshino 89, Lilith 89 e Alistair 20 (eram 0). Linhas de treino:
Hoshino 483, Lilith 507 e Alistair 348; todas aceitas pelo treinador real (maior sequência: 768 fichas). Ficam fora
3 exemplos que citam outra entidade (regra de 07/11) e 2 com `add_goal`, cuja definição sozinha passa do teto.

**Antes de treinar:** o corpus mudou e as sequências chegam a 768 fichas. A Central exige medir de novo (smoke e treino
curto de cada entidade) antes de agendar a noite. Com o 4B do Alistair a cabeça fica na GPU e o custo de memória das
sequências longas ainda não foi medido.

### CÓDIGO

| Problema | Correção | Onde |
|---|---|---|
| "Jogue por conta própria" não tinha critério e virava tarefa de uma consulta | **Modo livre:** ela escolhe um objetivo de uma lista do que o ciclo sabe conferir (picaretas, bancada, forno, lingotes, diamantes, arco, flechas, carnes, kit de ferro, armadura de diamante, derrotar um mob), com quantidade e motivo dela; cada objetivo vira uma tarefa própria no ciclo observado de sempre; concluído, escolhe o próximo (até 6 por turno); pausado, fica retomável com "continue"; objetivo travado por efeito incerto fica preservado e não é repetido | `app/core/minecraft_agent.py` (`free_play`, `FREE_GOALS`, `free_goal_text`), `app/main.py` (`_ciclo_minecraft_livre`, `_escolher_objetivo_minecraft_livre`) |
| Ela perguntava no chat do jogo sem ninguém no servidor (observação do Gustavo: "uma ação sem sentido") | A ponte informa quem está online (`onlinePlayers`). Sozinha: o chat sai das opções, a chamada de chat é recusada antes do efeito, a resposta junto da ação não sai, e a decisão vê "só você está no servidor" | `bridge.js`, `minecraft_cognition.py`, `minecraft_agent.py`, `main.py` |
| "Sem caminho" depois de andar 2 blocos virava efeito incerto e pausava a tarefa inteira (12:23) | Como no tempo esgotado: a ponte devolve o trecho medido (de onde até onde) e o estado | `bridge.js` (teste `fixture_minecraft_bridge.js` atualizado: a regra antiga era "continua incerto") |
| Descrições de ferramentas citavam "a Hoshino" para todas (ponte Minecraft, Discord, modo silencioso, caixa de entrada) | Descrições em primeira pessoa, sem nome | `app/core/dispatch.py` |

### Resultado ao vivo (12:46–13:10)

Com o v6, o Ministral 3B de suporte e o modo livre, a Lilith entrou no servidor sozinha e, até 12:59:
1. **Escolheu "picareta de pedra"** ("Sem picareta, eu não faço nada. Preciso de uma de pedra."): fabricou a
   bancada, consultou a receita, colocou a bancada e fabricou a picareta. Objetivo conferido.
2. **Escolheu derrotar um mob:** atacou um esqueleto, que sumiu da distância; atacou outro e matou com 8 golpes.
   Objetivo conferido.
3. Escolheu o terceiro objetivo às 12:55.

Detalhe: a escolha com raciocínio passa do teto de 2.048 fichas e cai na escolha sem raciocínio (~1 min a mais por
objetivo).

**Por que parou às 12:55 (corrigido):** escolheu "arco" com um arco na mochila. O objetivo já estava pronto antes de
qualquer ação; a conclusão exige recibo de ação (`MINECRAFT_RECEIPTS_REQUIRED`) e o erro derrubou o modo livre. Ela
ficou parada até 13:09. Correções: a lista não mostra o que o inventário já cumpre; erro num objetivo fica registrado e
ela escolhe outro; a escolha do objetivo é sem raciocínio.

### Segunda rodada (14:45–14:56) e as últimas correções

11 ações, nenhum objetivo concluído. Escolheu de novo "picareta de pedra" com uma na mochila; registrou o mesmo
procedimento 4 vezes; a coleta de carvão falhou duas vezes por mochila cheia (36 pilhas, 342 pedregulhos) e ela andou
78 blocos procurando carvão em vez de abrir espaço. Correções (CÓDIGO, testadas):
- objetivo de fabricar o que ela já tem (na mochila ou vestido) sai da lista;
- mochila cheia: a ponte informa os espaços livres (`freeSlots`), a decisão vê "Mochila cheia…" e ganha as opções
  `jogar_fora:<sobra>` com os materiais de volume que mais ocupam;
- registro de procedimento: intervalo de 10 passos (`REGISTER_COOLDOWN`); dentro dele a opção some e a chamada pelo
  catálogo é recusada antes do efeito.

Fica com ela (TREINO/limite do 9B): escolher objetivo que não combina com o motivo e sair atrás de material que o
objetivo não pede.

**Parado às 14:56 a pedido humano ("faça as correções e pare tudo"):** Lilith dormindo, ponte encerrada, modelos
descarregados, bloqueio de suspensão retirado. As correções da segunda rodada valem no próximo despertar.

## O que fica para o treino

- ~~Ensinar a chamar ferramenta~~: o treinador e o banco foram estendidos à tarde (acima). Falta treinar e medir.
- Até lá, o treino de voz e identidade custa a chamada de ferramenta, e o código compensa em parte (4/5).
- ~~Contrato de ferramenta na avaliação~~: `tool_call` (v3), feito à tarde.

## O que fica para o código

- ~~Modo livre no Minecraft~~: feito à tarde (acima).
- **Tarefa genérica:** um plano de uma operação só de leitura fecha a tarefa mesmo quando o pedido era agir.
- **Decisão em formato forçado** como último recurso da conversa, quando nem a cobrança dirigida resolve.
