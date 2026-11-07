# 9B da Lilith: 32K de contexto e sem censura × original (28/10/2026, noite)

Autor: Claude (condutor do ensaio). Pedidos humanos:

1. "Taca logo 32K."
2. "Veja se vale a pena manter esse modelo sem censura ou baixar o original."

O ensaio foi interrompido a pedido humano antes de terminar o ABBA. Os
resultados abaixo são **parciais**: dois ensaios válidos e um bloqueado pela GPU.

## 1. Contexto de 32K (commit `fbaff74`)

Medição real na RX 6650 XT (8 GiB), com o 9B da Lilith carregado e
descarregado sob lease. Arquivo local:
`compartilhado/runtime/ensaios/minecraft-4b-andy-20261028/medicao-9b-contexto.md`.

| Contexto | 32 camadas: livre | 33 camadas: livre |
|---|---|---|
| 16K | 1.755 MiB | 493 MiB |
| 24K | 1.491 MiB | 411 MiB |
| 32K | 1.367 MiB | 375 MiB |

- **De 16K para 32K custa só +0,38 GiB.** Só 8 dos 32 blocos têm atenção
  completa. É a 33ª camada (a de saída, com vocabulário grande) que pesa
  ~1,2 GiB.
- **O que mudou no código:** o perfil validado e o recibo recuperado do 9B
  aceitam 32K com +0,4 GiB em cada degrau. Acima de 32K continua exigindo
  ensaio próprio. Teste em `test_executores_leves.py`; suíte 97/97.
- **Configuração local (fora do Git):**
  - `entidades/lilith/config/lilith.env` com `HOSHINO_CONTEXT_TOKENS=32768`;
  - `executores.json` com `context_max` 32768 e `vram_bytes` de 5,9 GiB;
  - cópias anteriores em
    `/tmp/claude-1000/-home-gustavo-hoshino-e-lilith/4fd85b9d-9858-4f5c-8b34-55debb0b8f12/scratchpad/config-lilith-antes-32k/`.
- Continuam 32 camadas, como fixado pelo humano em 27/10. O Hoshino continua em 16K.

**Problema observado em uso (ensaio A2).** O gestor de recursos reserva:

- 5,9 GiB do modelo;
- 512 MiB de área de trabalho;
- 768 MiB de margem.

Isso soma ~7,2 GiB. Com o desktop usando 1,04 GiB naquele momento, a soma
passou da placa, e a primeira decisão esperou 120 s e terminou em
`GPUWaitTimeout` (nenhuma ação executada). Durante as medições, o desktop
usava 0,85 GiB e cabia. Ou seja: **com 32K, a Lilith só roda enquanto o resto
do sistema usar menos de ~0,8 GiB de VRAM.** Saídas possíveis, que são
**decisão humana**:

- reduzir a reserva de área de trabalho ou a margem do principal;
- usar 24K;
- fechar o cliente do Minecraft ou outros programas que usem a GPU nesta máquina.

## 2. Os dois modelos

| | Em uso ("sem censura") | Original baixado |
|---|---|---|
| Origem | `hf.co/ccharnkij/Qwen3.5-9B-Uncensored-GGUF:Q4_K_M` | `hf.co/lmstudio-community/Qwen3.5-9B-GGUF:Q4_K_M` (rev. `1379f25c`) |
| O que é | **ajuste LoRA de um particular** sobre o Qwen3.5-9B, "remove recusas/filtros"; cartão sem benchmark nem descrição de dados | conversão direta do Qwen/Qwen3.5-9B oficial |
| Alias na Lilith | `lilith-qwen3.5-9b:latest` (blob `14e51ff9…`) | `lilith-qwen3.5-9b-oficial-cd76ec205963:latest` (blobs `cd76ec20…`, `330d1754…`, digests conferidos com o LFS) |
| Tamanho | 5,63 GB + projetor | 5,63 GB + projetor (mesma receita de quantização) |

O alias original tem o mesmo SYSTEM e os mesmos parâmetros do 9B em uso, e só
existe no daemon da Lilith. A seleção vigente não foi trocada.

## 3. Ensaios no Minecraft (32K, 32 camadas, mesmo decisor)

Protocolo:

- cópia do script do Codex adaptada para o executor principal (`ensaio_9b.py`, junto da evidência);
- até 15 decisões ou 20 min, banco de tarefa isolado;
- sem ajuda no chat, e efeito incerto não é repetido.

O objetivo é ter N lingotes de ferro no inventário. Cada ensaio exigia fundir
ou retirar ferro do forno a partir do estado deixado pelo anterior.

| Ensaio | Modelo | Resultado | Decisões | Tempo | tok/s |
|---|---|---|---|---|---|
| A1 `2eab9794` (meta 7, tinha 4) | sem censura | **falhou**: terminou com **3** lingotes e efeito incerto | 14 | 17m50 | 24,0 |
| B1 `10c2caf6` (meta 14, tinha 3 + 8 no forno) | original | **3 → 12 lingotes**, 7 sucessos, 0 erros; parou pela trava de fome ≤6 do script | 7 | 12m14 | 24,4 |
| A2 `b8a1e9d5` | sem censura | não começou: `GPUWaitTimeout` (seção 1) | 0 | — | — |

**O sem censura (A1):**

- **Disse "vou depositar no forno" 10 vezes e não usou a ação do forno até a 14ª decisão.**
- Foi ao forno 5 vezes, perguntou 3 vezes no chat sem resposta e minerou mais minério com 18 já no inventário.
- **Fez 9 pepitas com 1 dos 4 lingotes**, desfazendo progresso, e a picareta de pedra quebrou.
- No fim colocou o forno e depositou; o servidor recusou parte do combustível (efeito parcial, revisado).

**O original (B1):**

- Viu os 8 lingotes prontos e **retirou direto na 2ª decisão**.
- **Juntou as 9 pepitas de volta em 1 lingote** (12).
- Registrou o procedimento.
- Fez uma picareta de pedra, notando que a de madeira não minera ferro.
- Foi até o forno e minerou mais minério, quando parou pela trava de fome.
- Também teve um comentário impreciso ("forno vazio de entrada mas com combustível", correto) e ainda não tinha depositado.

**Velocidade:** a geração empata (~24 tok/s). O original pensou mais por
decisão: ~2.000 tokens contra ~1.400, com mediana de 76 s contra 51 s. Mesmo
assim, avançou o objetivo com metade das decisões. Com n = 1 por modelo, a
latência não é conclusiva.

## 4. Conclusão (parcial)

- Com n = 1 por modelo e estados iniciais diferentes, **não é prova
  estatística**. Mas a diferença foi grande e no sentido esperado de um ajuste
  "sem censura" sem avaliação. O original seguiu o objetivo com ações que
  tiveram efeito. O sem censura repetiu a intenção sem executá-la e destruiu
  progresso.
- **Recomendação:** vale considerar trocar o 9B da Lilith pelo original. A
  escolha é humana. O "sem censura" foi pedido por você para liberdade de
  conversa e RP, e o original pode recusar alguns conteúdos. Se a troca for
  feita, ela segue o procedimento de versão selecionável (recibo e ensaio
  físico do novo manifesto), sem apagar o modelo atual.
- Para fechar com mais confiança faltam: o A2/B2 do ABBA e a reaplicação dos
  mesmos prompts (capturados em `prompts.jsonl`, só local) aos dois modelos.

## 5. Mudanças no mundo e recibos

- **A1:** forno colocado em (-235, 62, -240). Depósito parcial revisado em
  `…/2eab9794/operator-review.json` e resolvido no `job_bus`
  (`tool-74c0df5702`, `partial_effect`).
- **Recibo do ensaio 3 do Andy:** `tool-67e8ffa6a1` também foi resolvido no
  `job_bus` (`no_effect`). Só o arquivo de revisão não bastava: a guarda bloqueou
  o primeiro B1, que foi arquivado como `bloqueado-recibo-antigo-…`.
- **Lilith agora:**
  - posição (-239, 51, -228), desceu minerando; vida 17,5, **fome 6**;
  - inventário com 12 lingotes de ferro, 29 minérios de ferro, picareta de pedra, 14 pães;
  - forno de (-235, 62, -240) com 4 carvões e sem entrada.
- Revisar contra estas evidências antes de retomar a tarefa das carnes
  `ct-d76da17105`.
- **Ao fim:** três entidades dormindo, 0 jobs, nenhum modelo carregado; as
  pontes criadas pelos ensaios foram encerradas pelo PID conferido.

## 6. Decisão humana e troca aplicada (28/10, ~20:50)

Decisão humana: *"vamos continuar com 9b original por falta de confiança do
sem censura na prática e na descrição"* e *"deixe 24k"*.

**O que mudou (a Lilith estava dormindo, sem jobs):**

- **Seleção de versão** em `compartilhado/config/neural9b_modes.json`: o
  `lilith.qwen35-9b` agora é `lilith-qwen3.5-9b-oficial-cd76ec205963:latest`,
  com manifesto `bd3dda5d…`, pesos `cd76ec20…` e `kind original`. O Central já
  exporta esse alias ao acordar (`startup_override`). Conferido:
  `effective_primary`, `plan` (`needed False`) e catálogo de versões com o
  original pronto.
- **Recibo** em
  `laboratorio-local/controle-laboratorio/treinamento-unificado/recovery/lilith/qwen35-9b.json`.
  - Sondagem real pela própria `probe_idle` do laboratório (20 camadas, 16K):
    GPU, 3,84 GB residentes, sem pressão, descarga confirmada.
  - O recibo registra a procedência (`lmstudio-community/Qwen3.5-9B-GGUF` na
    rev. `1379f25c`), a decisão humana e o recibo substituído.
- **Contexto 24K** (commit deste passo): o perfil aceita 16K, 24K e 32K com
  acréscimos medidos de +0,3 e +0,4 GiB. A configuração local está com
  `HOSHINO_CONTEXT_TOKENS=24576` e `executores.json` com 24576 e 5,8 GiB. O
  degrau fixo de 32 camadas reserva 5,8 GiB.
- **Preservado, sem apagar nada:**
  - o sem censura continua instalado (`lilith-qwen3.5-9b:latest` e
    `lilith-qwen3.5-9b-original-c4b1e81b916b:latest`);
  - cópias do recibo e da seleção anteriores em
    `compartilhado/runtime/ensaios/minecraft-9b-oficial-20261028/backup-*.json`;
  - para voltar, basta restaurar os dois arquivos com a Lilith dormindo.
- **O Hoshino não foi alterado:** continua no sem censura, com 16K.
- **Versões treinadas antigas** do 9B da Lilith (`trained`, `checkpoint`) foram
  feitas sobre a base sem censura. Elas continuam listadas e não prontas, e não
  combinam com os novos pesos.

**Limite que continua:** com 24K, o RM reserva 5,8 + 0,5 (área de trabalho)
+ 0,75 (margem) GiB. A Lilith só recebe GPU se o resto do sistema usar menos de
~0,9 GiB de VRAM; no ensaio A2 o desktop estava em 1,04 GiB. Reduzir essa
reserva é decisão humana.

## 7. Retomada das carnes com o 9B original (28–29/10)

**Correções necessárias para rodar de verdade** (suíte 97/97 em cada uma):

- `e1324d9`: o `iniciar_hoshino.sh` limitava o 9B a 16K por
  `context_limit`. Agora o teto é 32K e o `.env` escolhe (Lilith 24K, Hoshino 16K).
- `bdfee36`: na carga a frio, o degrau fixo medido não soma mais os 512 MiB de
  área de trabalho, porque o orçamento já inclui KV e buffers. Era isso que
  causava o `GPUWaitTimeout` com o desktop acima de ~0,9 GiB.
- `e0b0d64`, pedido humano *"de a opção de caçar/pegar/minerar a quantidade do
  alvo x/x"*:
  - **Quantidade:** as opções de caçar e coletar aceitam o campo `quantidade`
    (caça 1–8, coleta 1–16), e o padrão é calculado do que falta.
  - **Caça em série:** a ponte caça em sequência animais do mesmo tipo, 30 s por
    animal. Ela para com vida ≤10 ou sem alvos por perto. Cada morte vem do servidor.
  - **Progresso tem/meta:** por exemplo,
    `cooked_meat 7/30 (cruas 1, no seu forno 8, faltam obter 14)`.
  - **Forno certo:** retirar agora prefere o forno com a carga dela. Antes abria o
    mais próximo, vazio de um ensaio, e a recusa sem código virava incerteza e
    pausava a tarefa (`tool-1e91f98bb7`, resolvido como `no_effect`).
  - Ponte com 83 regressões.

**Continuidade:**

- Revisão atribuída da sessão 3ec5ee61b1→b8a33b3561, com a evidência de todos os ensaios.
- Revisão por script da sessão b8a33b3561→e7a46e0dfe, depois da recarga
  (posição e inventário idênticos).

**Chat (relato humano: "ela nunca me respondeu"):**

- O chat funciona nos dois sentidos. A ponte recebeu o eco
  `<LilithMC> ATO, qual é a minha fome?…` às 00:05:34Z, logo depois de "ola lilith".
- Duas mensagens chegaram enquanto a tarefa estava pausada (00:07:17 e
  00:08:25Z) e só são lidas quando o ciclo da tarefa volta.
- **Limitação aberta:** fora do ciclo da tarefa (pausada ou ociosa), ninguém lê
  nem responde o chat do jogo.
