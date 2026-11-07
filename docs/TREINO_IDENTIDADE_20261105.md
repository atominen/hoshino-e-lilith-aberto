# Sessão única de treino de identidade: 05/11 às 23:00 → 06/11 às 12:00

Pedido humano (05/11):
- baixar os pesos originais, "provavelmente mais estáveis do que o sem censura";
- agendar das 23h às 12h do dia seguinte um treino dos três pesos, um 4B e os dois 9B;
- usar os materiais default já criados, depois de avaliados.

## Bases

| Treino | Base | Corpus |
|---|---|---|
| Hoshino 9B | Qwen/Qwen3.5-9B oficial, rev. `c2022362` (`laboratorio-local/modelos/qwen3.5-9b-oficial-hf`) | `pacote_identidade_v4/hoshino_*` |
| Lilith 9B | a mesma base oficial | `pacote_identidade_v4/lilith_*` |
| Alistair 4B | `modelos-extras/alistair-qwen35-4b/hf` | `pacote_identidade_v4/alistair_*`: seed com repetição ≤2 e banco de personalidade novo |

O 9B sem censura fica só como histórico de treino. A Hoshino continua rodando
nele até um candidato ser adotado por decisão humana.

## Avaliação dos materiais default (`pacote_neural_v3`)

- 758 exemplos por entidade, com 565 respostas distintas.
- **53%** dos prompts em comum têm resposta **idêntica** entre Hoshino e Lilith.
- 50% dos exemplos repetem uma resposta já usada (quase sempre em pares).
- Nenhum "a tia aqui" e só 7 menções a preguiça na Hoshino. O jeito de partida
  quase não aparece.
- O próprio `RELATORIO_QUALIDADE.md` diz que o pacote "não demonstra
  personalidade natural treinada" e pede revisão humana antes de treinar.
- Não há frases contra a identidade nova. `PERFIS_PERSONAGEM.md` já tinha as
  mesmas inspirações (Takanashi Hoshino e Lilith do jogo).

Daí o v4:
- o v3 com cada resposta repetida no máximo 2 vezes (saíram só 4 exemplos);
- as 34 referências novas (`laboratorio/identidade/referencias_v1.json`) com peso 2;
- 8 referências na validação.

São 822 exemplos de treino e 139 de validação por entidade. O holdout continua
o teste do v3.

As referências foram aprovadas pelo juiz 35B (34/42) e por revisão do Claude,
**não por humano**. Espera-se que este treino ensine mais os comportamentos do v3
(honestidade, pré-condições) do que o jeito de partida: 68 exemplos novos para
754 do v3.

## Bancos de personalidade (verificação pedida às 21:47)

**Hoshino e Lilith: os bancos default não servem para personalidade.**
Fração das respostas de treino em que cada traço de partida aparece:

| Traço | v3 | v4 |
|---|---|---|
| Hoshino: preguiça / sem pressa | 1% | 3% |
| Hoshino: "a tia aqui" | 0 | 4 de 822 |
| Hoshino: humor | 1% | 2% |
| Lilith: casa no computador | 3% | 4% |
| Lilith: existência / inquietante | 1% | 2% |

Mesmo no v4, 401 dos 758 pedidos em comum têm resposta idêntica para as duas.
Os bancos ensinam bem honestidade, pré-condições e limites, mas não a voz.

Esta noite é uma linha de base. Para a personalidade, o próximo corpus (v5)
precisa de centenas de falas no jeito de partida, geradas pelo professor 35B,
filtradas pelo juiz e aprovadas por humano.

**Alistair: não havia banco de personalidade.** O seed tinha 83 exemplos e só
49 respostas distintas, quase todas operacionais. Foi criado
`laboratorio/identidade/referencias_alistair_v1.json`:
- 36 pares tirados da identidade dele (formal com naturalidade, discreto,
  atento, confiável, ironia leve), com as mesmas regras de honestidade;
- nenhuma ação afirmada sem prova e nenhuma fala por Hoshino ou Lilith;
- 29 vão para o treino com peso 2 e 7 para a validação.

Aprovação humana pendente.

## Plano

Plano personalizado com os três originais (`CUSTOM_TRAININGS = 3`):
- cada um com 90 min de treino (teto do laboratório) e 30 min de avaliação;
- limite de 3 épocas e parada antecipada pela validação;
- reserva de 420 min na janela de 780.

Avaliação:
- perda na validação e no holdout, comparada à base;
- auditoria de comportamento.

Sem promoção automática (`automatic_data_approval` desligado): os candidatos
ficam para decisão humana.

A Central precisa estar aberta. É o supervisor dela que dispara às 23:00, com
tolerância de 1 minuto. Esta sessão não para se alguém usar o PC; isso só vale
para o ciclo noturno automático.

## Correções necessárias para a sessão rodar

1. **`laboratorio/treino_nf4_curto.py`:** o processo de treino importava `core`
   sem ter `app/` no `sys.path`, e todo treino falhava com
   `ModuleNotFoundError: core` desde 17/10. Ninguém notou porque o agendamento
   de 23/10 nem começou.
2. **Plano personalizado:** passou a treinar só os três originais. Antes eram
   sete, com Yi e 7B, cujos pesos já não existem. A confirmação agora é
   `AGENDAR_TRES_ORIGINAIS`, e os testes do laboratório foram atualizados.
3. **Medições físicas refeitas:** os registros de velocidade e de tamanho de
   checkpoint tinham ido embora com os checkpoints antigos. Foram refeitos com
   treinos curtos de 24 passos, que não são candidatos.

Script: `scripts/preparar_treino_noturno_20261105.py` (medir, curto, previa, agendar).

## Agendamento

- **Sessão:** `e3bd63c7b87341bc`, agendada às 22:14.

  A primeira, `74480d84dc1c487d`, foi cancelada. A Central tinha carregado o
  laboratório às 21:34 e agendou o Alistair com o corpus antigo dele; a
  assinatura não batia com o disco. A Central foi reiniciada e o plano refeito.
  A assinatura conferida por outro processo bate.
- **Prévia aprovada sem bloqueios:**
  - 6 etapas;
  - ~11,3 GB de checkpoints previstos, com 37,6 GB livres.
- **Medições:**
  - 9B Hoshino e Lilith: ~673 atualizações/h, checkpoints de ~130 MB, pico de 3,9 GB de VRAM;
  - 4B Alistair: ~1.388 atualizações/h, checkpoints de ~98 MB.

Com isso, cada 9B faz ~1.000 atualizações em 90 min, cerca de 1,2 época.

- **Central:** aberta sem janela às 21:34 (`python3 ./iniciar_entidades.py --no-browser`, log em
  `compartilhado/runtime/launcher/central-treino-20261105.log`).
- **Suspensão:** bloqueio temporário `systemd-inhibit` (sleep:idle) até 06/11 às 12:10.
- **Não alterar** `treino_nf4_curto.py`, `treinos_unificados.py`, `personalizacao.py`
  nem `pacote_identidade_v4` até o fim. A sessão confere a assinatura deles.
- **Pista de velocidade para depois:** as camadas recorrentes do Qwen3.5 usam a
  implementação de referência do PyTorch, porque `flash-linear-attention` não
  está instalado.

## Bloqueio de entidades durante treinos

`app/core/bloqueio_treino.py`, consultado em `entity_admission.guard`. Por esse
ponto passam a Central, o `iniciar_hoshino.sh` e os runners.

Bloqueia:
- desde 30 min antes de uma sessão agendada até o fim da janela;
- durante uma sessão noturna ativa;
- durante jobs de treino, medição ou avaliação.

A recuperação de modelos do boot não bloqueia. Um registro "started" preso não
bloqueia depois do fim da janela. Testes em `testes/test_bloqueio_treino.py`.
Hoje o bloqueio vale de 22:30 às 12:00.

## Personalidades padrão (melhoradas 22:15, para a próxima rodada)

- `tracos_*.json`: modos por situação, costumes e anti-padrões das três entidades.
- `referencias_v2.json`: 24 situações novas para Hoshino e Lilith.
  - O juiz 35B acertou 22/24 (92%), contra 81% no v1 e 75% nas antigas.
  - Os dois erros esperados: perigo, em que as duas ficam sérias de propósito, e erro técnico.
- Aprovação humana pendente. Nada disso entra no treino desta noite.

## De manhã

- `laboratorio-local/controle-laboratorio/treinamento-unificado/nights/scheduled-once.json`
  e `nights/current.json`: estado da sessão.
- `reports/<entidade>/`: avaliações dos candidatos (perdas e auditoria).
- Nenhum candidato muda a produção sem decisão humana.
