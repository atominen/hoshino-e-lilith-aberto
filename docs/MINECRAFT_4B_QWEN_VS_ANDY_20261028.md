# Minecraft 4B — Qwen3.5-4B original × Andy-4.2-Air (28/10/2026, noite)

Autor: Claude (condutor do ensaio), a pedido humano: "testar o Qwen3.5-4B no
Minecraft e baixar aquele 4B que conseguiu montar uma armadura de diamante
para teste e análise". Continua o
[ensaio 4B do Codex](ADMISSAO_16GB_E_MINECRAFT_4B_20261028.md). Nenhuma
seleção permanente de executor foi alterada; a tarefa das carnes
`ct-d76da17105` continua pausada e intocada.

## O modelo baixado

- **Andy-4.2-Air** da equipe Mindcraft-CE, ajuste fino do `Qwen/Qwen3.5-4B`
  (mesma arquitetura `qwen35`, 4,2B). O cartão afirma ser o primeiro modelo local a
  obter armadura completa de diamante sem interação humana. Essa afirmação
  vale para o *framework Mindcraft* (comandos `!acao`), 16 bits, contexto 32K
  e LM Studio; **não foi verificada aqui**. O cartão desaconselha Ollama
  (laços e template).
- Origem: `huggingface.co/Mindcraft-CE/Andy-4.2-Air-GGUF`, revisão
  `b865bc58f13394a9ab2e75a868cf54b03614d83f`. Baixados `andy-4.2-air.q4_k_m.gguf`
  (sha256 `4c6eed50…6af4`) e `mmproj-BF16.gguf` (`e53e50a6…4dfd`), ambos
  conferidos com o LFS do Hugging Face. A mesma quantização Q4_K_M + projetor
  do Qwen3.5-4B em uso, para o par ser comparável.
- Local: `compartilhado/modelos/huggingface/Mindcraft-CE__Andy-4.2-Air-GGUF__b865bc58/`
  (cartão, licença Andy 2.0, hashes, Modelfile). Alias somente no daemon da
  Lilith (11436): `lilith-andy-4.2-air-q4km-4c6eed506ddf:latest`, com o mesmo
  SYSTEM/parâmetros do 4B original e sem template próprio. O Ollama usa o mesmo
  renderizador `qwen35`, então o problema de template do cartão não se aplica.
  Licença: uso local livre; redistribuição exige crédito a Sweaterdog e Mindcraft.

## Método

Uma cópia parametrizada do script do Codex (modelo e objetivo) fica junto da
evidência, sem alterar o original. O protocolo é idêntico:

- mesmo decisor, dispatcher, RM/leases e ponte;
- contexto 16.000, saída leve 1.024, até 12 decisões e 600 s;
- banco de tarefa isolado e jogador LilithMC no servidor `10.0.0.200`;
- sem rota, itens ou resposta do condutor no chat;
- efeito incerto interrompe e não é repetido.

O estado inicial de cada ensaio é o estado final do anterior: mesmo mundo, sem
reset. Isso é um viés, registrado abaixo.

## Resultados

| Ensaio | Modelo | Objetivo | Resultado | Decisões | Tempo | Mediana/decisão | Respostas (cortadas por limite) | Tokens gerados | tok/s |
|---|---|---|---|---|---|---|---|---|---|
| Codex `7d4505ec` | Qwen3.5-4B | picareta de pedra | **não concluiu** | 12 | 474 s | 35,4 s | 24 (11) | 14.215 | 41,9 |
| 1 `190e2ec2` | Andy-4.2-Air | picareta de pedra | **concluiu** | 8 | 284 s | 31,7 s | 15 (5) | 7.709 | 42,3 |
| 2 `c89a3476` | Qwen3.5-4B | forno | **concluiu** | 3 | 107 s | 29,4 s | 6 (2) | 3.314 | 42,7 |
| 3 `492605b8` | Andy-4.2-Air | forno | interrompido (incerteza mecânica) | 3 | 91 s | 31,9 s | 5 (2) | 3.063 | 42,7 |
| 4 `70af7e14` | Andy-4.2-Air | forno | **concluiu** | 3 | 95 s | 26,5 s | 5 (0) | 2.390 | 42,9 |

VRAM do modelo carregado é igual nos dois, cerca de 3,68 GB com janela de 16.000.
A geração também empata, cerca de 42 tok/s, como esperado com a mesma base e a
mesma quantização.

### O que diferenciou

- **Recuperação depois de recusa (o ponto em que o Qwen falhou).** Os dois
  receberam "não há chão sólido livre" ao colocar a bancada:
  - O Qwen (Codex) repetiu a colocação sem se mover, perguntou duas vezes no
    chat, tentou uma referência a 5,9 blocos e acabou o orçamento.
  - O Andy repetiu uma vez e foi barrado pela regra de repetição. Depois
    minerou pedra ali perto, perguntou uma vez no chat e, sem resposta,
    **escolheu ir para perto do forno conhecido** (coordenada vinda da memória
    de fundição do mundo, sem ajuda). Colocou a bancada e fabricou a picareta.
  - Como ele começou com a bancada já na mão e as varetas prontas, é um par
    favorável a ele. Mas foi exatamente o impasse em que o Qwen ficou 7 decisões.
- **Raciocínio mais curto.** O Andy gerou cerca de 800–1.020 tokens por decisão,
  contra cerca de 1.100–1.200 do Qwen, e teve menos respostas cortadas pelo
  limite (0–5 contra 2–11). Isso bate com a promessa do cartão de "pensar mais
  rápido". O ganho de tempo é moderado (mediana 26–32 s contra 29–35 s), porque
  o ciclo tem custo fixo além da geração.

### Erros do Andy

- **Ensaio 3:** ele tinha no inventário o forno feito pelo Qwen. Em vez de
  fabricar outro, **colocou esse forno no chão**, perdendo o critério "no
  inventário", e tentou retirar algo de um forno vazio. A ponte recusou sem
  efeito (ver falha mecânica abaixo). O Qwen, na mesma situação do ensaio 2,
  disse corretamente que "ainda preciso fabricar um segundo".
- **Ensaio 4:** comentou "200 pedregulhos, preciso fabricar agora", mas escolheu
  minerar mais 4 pedras antes de fabricar. Ainda é a divergência entre
  comentário e escolha.
- **Os dois modelos** escreveram que o forno precisa de "4 blocos" (são 8) e
  usaram nomes deformados ("cobalho", "cobaltstone"). A confiança no texto não
  garante que o fato está certo.

### Falha mecânica encontrada (não é do modelo)

Em `compartilhado/servicos/minecraft/bridge.js:952`, `furnace take` sem
processamento próprio registrado lança um `Error` comum, sem código. O Python
então trata o caso como `RESULTADO_INCERTO` e pausa, mesmo a recusa sendo
anterior a qualquer efeito: diag 21:18:39Z, 4 ms, "nada retirado". Isso seguiu
a regra de "não repetir" e foi revisado à mão em
`…/20261028T211708Z-492605b8/operator-review.json`. **Correção proposta, não
aplicada:** usar `NoEffectError(..., 'furnace_preconditions')`, como já se faz
para o forno ocupado (`2f04e65`).

## Conclusão

- **Com n tão pequeno**, o Andy-4.2-Air foi **pelo menos tão bom quanto o
  Qwen3.5-4B original** no nosso ciclo. Mostrou uma vantagem visível na
  autocorreção após recusa, com raciocínio mais curto e o mesmo custo de VRAM e
  velocidade. Errou de um jeito diferente (usou o forno errado), e não há
  amostra para dizer que é melhor em geral.
- **Não confirma a armadura de diamante.** A afirmação do cartão vale para outro
  framework, outra precisão e outro contexto. Testar isso exigiria rodar o
  Mindcraft-CE com o próprio Andy, o que é outra arquitetura de agente e fica
  fora do nosso ciclo de entidade.
- **Identidade.** O Andy é um especialista de jogo, sem os dados da Lilith. Usá-lo
  como executor leve dela é decisão humana: mudaria a seleção vigente 9B + 4B
  ([organização 4B/9B](ORGANIZACAO_4B_9B_20261027.md)). Hoje ele só existe
  como alias de teste.
- **Próximos testes úteis**, se o humano quiser:
  1. Pares com estado inicial realmente igual e objetivos mais longos (ferro,
     arco), alternando a ordem dos modelos.
  2. A correção do código da recusa do forno.
  3. Opcionalmente, o Andy no Mindcraft-CE em mundo separado, só para checar a
     afirmação do cartão.

## Mudanças no mundo (para a retomada das carnes)

Recibos nos bancos isolados de cada ensaio. Lilith agora está em
(-237, 60, -238), **num buraco de 3 blocos** aberto pela coleta de pedra do
ensaio 4. Vida 17,5 e fome 9.

- **Inventário:** +1 picareta de pedra, +1 forno; pedregulho 207→196,
  terra 14→28, varetas 5→3; a bancada saiu do inventário.
- **Blocos colocados:** bancada em (-237, 63, -240) e forno vazio em
  (-237, 63, -241), ao lado do forno antigo dela em (-238, 63, -242).
- Comparar com estas evidências antes de revisar a sessão da tarefa
  `ct-d76da17105`. O snapshot das 16:26 não vale mais.

## Evidências e encerramento

`compartilhado/runtime/ensaios/minecraft-4b-andy-20261028/`:
- uma pasta por ensaio, com `report.json` e banco isolado;
- `operator-review.json` do ensaio 3;
- `operator-cleanup.json`: a ponte criada no ensaio 1 (PID conferido, ociosa e
  desconectada) foi encerrada com SIGTERM;
- `ensaio_pareado.py` e `resumo.py`, para reproduzir.

No fim: três entidades dormindo, 0 jobs ativos, nenhum modelo carregado.
