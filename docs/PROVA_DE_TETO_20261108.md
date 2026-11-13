# Prova de teto: o problema é o nosso código ou o 9B? (08/11/2026)

Pedido do Gustavo: "veja se o problema é o nosso código ou é a limitação do 9B".

**Como foi feita:** mesmo prompt, mesmas ferramentas oferecidas e mesmo código; troca só o modelo.
- **9B local:** o treinado da Lilith (corpus v5).
- **Gemini:** `gemini-flash-lite-latest`, pela API cadastrada na Central.
- **Privacidade:** resultados de ferramenta simulados e, com o Gemini, memória e histórico respondendo "nada registrado"; nada real saiu do PC.
- **Provas e resultados:** `compartilhado/runtime/ensaios/fatos-20261107/` (versão E) e `compartilhado/runtime/ensaios/teto-20261108/`.

## Resultado

| Prova | 9B (prompt reduzido, como roda) | 9B (prompt completo) | Gemini |
|---|---|---|---|
| Perguntas de fato (25) | ~32/33 (rodada E de 07/11) | — | 24/25 |
| Cenários reais de 07/11 (8 × 2) | 9/16 | 6/16 | 9/16 + 3/4 na nova rodada (10 passos e PC2 oferecido, como na Central) |

| Cenário (fala real) | 9B | Gemini | De quem é |
|---|---|---|---|
| criar pasta na área de trabalho | 0/2 (recusa; inventa `C:\Users\…`) | 2/2 | limite do 9B |
| chamar a janela do Firefox | 2/2 | 2/2 | resolvido |
| abrir vídeo, pedido do PC2 | 0/3 (só anuncia "vou abrir") | 1/2 (abre; uma vez no PC2) | 9B não age; a regra do PC2 ainda é fraca |
| "me diga que eu sou" | 1/2 | 2/2 | limite do 9B (o código já entrega o nome) |
| várias partes (T-34 + link do The Boxer) | 0/2 | 2/2 | limite do 9B |
| "que é você?" | 2/2 | **0/2 (cita Hoshino e Alistair)** | **nosso prompt** (`[CASA COMPARTILHADA]`) |
| "você sabe quem eu sou?" (sem nome) | 2/2 | 1/2 ("como quer ser chamada") | **nosso texto** também empurra o feminino |
| "você tá dando bastante trabalho" | 2/2 (completo: 1/2 "Obrigado") | 2/2 | treino, no prompt completo |

## Conclusões

1. **Fatos:** quem resolveu foi o código (ficha da máquina, pesquisa, trava de conferência, revisor). Os dois modelos
   ficam no mesmo nível.
2. **Agir:** criar, abrir, fazer várias coisas num pedido e dizer quem é a pessoa são **limite do 9B**.
   - **O que falha:** ele anuncia e não chama a ferramenta, ou se recusa.
   - **Saídas:** treino com uso de ferramenta (o banco v6 tem ~140 exemplos, mas o treinador atual não treina os
     papéis `tool`) ou a API para quem precisa agir.
3. **Saber das outras entidades:** é o **prompt**. O Gemini, sem treino, repete o bloco `[CASA COMPARTILHADA]`;
   treino nenhum resolve enquanto o prompt ensinar isso.
4. **Gênero presumido da pessoa:** vem em parte do nosso texto ("a pessoa… ela"). Falta uma regra explícita no prompt.
5. **Prompt completo não ajuda o 9B treinado** (6/16 contra 9/16).
6. **Defeito achado no código:** o executor por API descartava a "assinatura de pensamento" do Gemini. Toda
   resposta com ferramenta falhava no 2º passo (HTTP 400), e a Lilith voltava ao local sem ninguém perceber.
   Corrigido em `core/executor_api.py`.
