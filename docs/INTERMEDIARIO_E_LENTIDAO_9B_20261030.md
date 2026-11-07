# Intermediário (mini-modelo) e lentidão do 9B — 30/10/2026

Condução: Claude, com revisões independentes do Codex (gpt-6.1-sol, esforço xhigh, só leitura) a pedido humano.
Evidências em `compartilhado/runtime/ensaios/intermediario-20261029/` (README no topo) e
`compartilhado/runtime/ensaios/lentidao-9b-20261030/`. Runtime local; não vai ao Git.

## 1. Comparação de modelos para o intermediário

O humano autorizou baixar SmolLM3-3B, Qwen3-4B-Instruct-2507 e Phi-4-mini, um por vez. A comparação passou pelo
código real, só na CPU, **sem as travas por regra**. Por isso ela compara classificadores, mas não mede o benefício
no sistema.

| Modelo | Programação: acertos · alarmes falsos | Minecraft ação+resultado | tempo (prog./MC) |
|---|---|---|---|
| **Qwen3.5-2B** (ligado) | 22/25 · 2/5 | 7/8 · 58/98 | 4,1 / 7,3 s |
| Qwen3.5-4B original (referência) | 25/25 · 2/5 | 7/8 · 14/98 | 8,8 / 15,0 s |
| Qwen3-4B-Instruct-2507 | 25/25 · 4/5 | 8/8 · 49/98 | 8,9 / 14,6 s |
| Phi-4-mini 3.8B | 21/25 · 1/5 | 8/8 · 90/98 | 6,8 / 11,8 s |
| SmolLM3-3B | 21/25 · 3/5 | 6/8 · 23/98 | 6,5 / 10,9 s |

**Gabaritos usados:**
- **Programação:** 30 notas do gabarito por consenso de 29/10.
- **Minecraft:** 126 tentativas reais da tarefa das carnes, rotuladas às cegas por Claude e pelo Codex. Valem os 106
  casos com consenso, dos quais só 8 são repetições. Com tão poucos positivos, isto é exploração, não aprovação.

**Decisão:**
- **O 2B continua.** Nenhum modelo novo o supera no uso ligado (notas da programação, atrás das travas).
- **O intermediário no Minecraft fica desligado por padrão.** Para ensaio, liga com `HOSHINO_INTERMEDIARIO_MINECRAFT=1`.
- **O próximo desenho**, recomendado pelo Codex, tem três peças:
  - a regra compara a assinatura ação + motivo da recusa;
  - o modelo só decide a equivalência incerta entre duas tentativas;
  - os exemplos incluem repetições legítimas.

## 2. Defeitos achados pela revisão de design do Codex (`db820c0`)

Todos foram conferidos e corrigidos com testes:

- **Aviso que nunca chegava à Lilith.** No Minecraft, quando a decisão tem opções (quase sempre), `decision_view`
  descartava o campo `intermediario`. Por isso o aviso do 2B nunca chegou a ela.
- **Falha guardada como avaliação.** Uma resposta `None` ficava no cache como se fosse "avaliado sem aviso".
- **Motivo da recusa cortado.** Um corte de 700 caracteres apagava o motivo da recusa, que fica no fim da saída.
- **Prova atribuída ao modelo.** A tentativa citada no aviso, escolhida por `difflib`, aparecia como prova do modelo.
  O aviso agora diz que ela é a mais parecida pelo texto.
- **Consultas sem medição.** Agora cada consulta emite `intermediario.consulta`, com resposta, tempo, `done_reason`,
  `eval_count` e `falha`/`http_status`.
- **Pausa depois de estouros.** Três estouros de tempo seguidos pausam o intermediário por 300 s.

## 3. Lentidão das decisões no Minecraft

Análise do Codex sobre 1.478 chamadas e 510 intervalos entre ações, só com números extraídos dos diagnósticos:

- **Intervalo entre ações:** mediana de 43,5 s, p75 de 146 s e p90 de 314 s. A estimativa anterior, de "2–5 min por
  decisão", era a cauda, não o típico.
- **Pensamento longo:** as chamadas com mais de 8 mil caracteres de pensamento são 13% do total e somam 47% do tempo
  do Minecraft. A correlação entre pensamento e duração é 0,992.
- **Esperas longas:** 29 das 51 esperas de 314 s ou mais terminam em reconexão. Nelas, o 9B responde por menos de um
  terço do tempo.
- **Meta intermediária esquecida.** A meta intermediária ficou com 8192 tokens quando a decisão passou a 4096
  (`690238e`), e quando esgotava a meta era descartada. **Corrigido em `8e658b9`, com aval humano:** a meta usa 4096 e,
  se esgotar, ela conclui com o próprio raciocínio, numa chamada sem pensamento.
- **Medição por etapa.** Cada chamada do 9B no Minecraft passou a emitir `minecraft.llm_etapa` (`5728c6f`), com a etapa
  (`meta`, `meta_fechamento`, `escolha`, `fechamento`, `catalogo` ou `texto_faltante`). O `llm.end` seguinte pertence a
  essa etapa.

**Próximo experimento proposto pelo Codex, ainda não feito:** um A/B da escolha principal com 4096 contra 2048 tokens.
- O pensamento continua ligado nas duas versões.
- A qualidade é julgada pelos critérios confirmados no mundo.
- A meta mínima é reduzir o p90 em 20% sem perda de conclusão.
- A decisão de rodá-lo é do humano.

## 4. Ideia humana avaliada: mostrar os últimos conteúdos na próxima ação

**Já existe nos dois ambientes:**
- **Programação:** os 6 últimos recibos, a leitura mais recente quase inteira (7 mil caracteres), as fontes numeradas em
  `codigo_do_projeto`, a memória de trabalho e a pré-busca.
- **Minecraft:** os 4 últimos recibos de trabalho, a trajetória de 4 passos, as consultas com até 1.200 caracteres, as
  receitas compactadas e o estado atualizado.

**Não colocar acima.** Esses dados ficam no fim de propósito. O prefixo estável é reaproveitado pelo Ollama: 16,5 mil
tokens levam 29 s sem cache e cerca de 1 s com cache. Além disso, o modelo atende mais ao fim do prompt.
