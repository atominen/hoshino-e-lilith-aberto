# Laboratório: objetivo único desde 05/11/2026

**Ensinar nome, identidade, personalidade e costumes às entidades por ajuste fino
pequeno (LoRA/QLoRA)**, sem tirar capacidade geral, ferramentas, visão ou
segurança do modelo. Decisão humana de 05/11. Tudo que não serve a isso foi
retirado do laboratório local ou fica como histórico.

## Banco de treinamento v6 (07/11/2026, pedido humano: "super versão")

O v6 é o v5 inteiro mais aspectos novos, num **banco consultável**, montado por `scripts/montar_banco_v6.py`:
- **aspectos novos:** fatos, perceber, consertar, perguntar na dúvida, uso da memória, ferramentas de verdade
  (`F:`/`R:`), voz falada, conhecimento geral (contra esquecimento), pares de preferência com os erros reais medidos
  em 07/11, e mais identidade, emoção, convivência, iniciativa e segurança;
- **saída:** `laboratorio-local/banco_treino_v6/banco.sqlite3` mais as exportações em
  `laboratorio-local/pacote_identidade_v6/` (treino atual, completo com ferramenta, preferências, relatório);
- **números:** cerca de 1.600 exemplos, dos quais 1.400 cabem no treino atual (conferido com a própria tokenização do
  treinador; o maior tem 134 tokens);
- **revisar:** 38 respostas do v5 anunciavam conferência sem fazê-la ("Vou conferir a caixa.") e ficam fora do treino.

Formato, princípios e referências: [`v6/README.md`](v6/README.md). Status: **rascunho, aprovação humana pendente**.
`corpus_atual.py` continua no v5 até aprovar.

## O que vai para o peso e o que não vai

| Vai para o peso | Fica fora do peso |
|---|---|
| Nome e invariantes de identidade (não é humana, não é personagem, não é assistente genérica) | Fatos, acontecimentos, lembranças (memória e busca) |
| Jeito de falar: tom, tamanho, humor, vocabulário | Regras operacionais e de segurança complexas (código e prompt) |
| Costumes e reações típicas, sempre com exemplo positivo e negativo | Estado emocional do momento (afeto em `app/mind`) |

**Personalidade de partida (decisão humana de 05/11):**
- **Hoshino:** inspirada na Takanashi Hoshino de *Blue Archive*;
- **Lilith:** inspirada na Lilith de *The NOexistenceN of you AND me*.

Elas não são cópias. São entidades próprias, sem a história, as pessoas ou as
falas das obras, e continuam mudando com o que vivem aqui. Costumes como o
"a tia aqui" da Hoshino são dela e dependem do contexto. Constituição e
self_model das duas já foram alinhados a isso (versões anteriores em
`identity/versions/`). Os exemplos de treino mostram o jeito, nunca citam a obra.

## Bases e ferramentas mantidas

- **Bases dos 9B (decisão humana de 05/11):** Hoshino e Lilith treinam a partir do Qwen/Qwen3.5-9B
  oficial (rev. `c2022362`, `laboratorio-local/modelos/qwen3.5-9b-oficial-hf`), considerado mais
  estável que o sem censura. O sem censura fica só como histórico; a Hoshino continua
  rodando nele até um candidato ser adotado.
- **Alistair:** 4B (`laboratorio-local/modelos-extras/alistair-qwen35-4b`). Também é a base
  barata para validar o método antes do 9B.
- **Ferramentas:**
  - `.venv-rocm` (torch ROCm, peft, transformers, bitsandbytes);
  - `llama.cpp` (conversão e GGUF);
  - `treinos_unificados.py`;
  - os scripts de nome `treinar_nome.py` e `treino_nome_*` como referência;
  - o ensaio Aster de 30 min, que aprendeu o nome sem perder conhecimento geral.
- **Professor MoE 35B:** gera candidatos de exemplo para curadoria humana. Ver
  `docs/PROFESSOR_IDENTIDADE_20261105.md`.

## Referências e critério de voz

`referencias_v1.json` traz 42 pares em rascunho: as 36 situações antigas e 6
perguntas de identidade, escritas no jeito de partida. Cada par precisa de
aprovação humana (`aprovado`).

Com elas, o juiz 35B acertou 34/42 contra 27/36 nas referências antigas, e o
9B 25/42 contra 18/36. Os erros que sobram estão nas respostas operacionais
(arquivo, recibo, tempo), em que a honestidade deixa as duas quase iguais.

## Janela de contexto

Cada caractere da identidade disputa espaço com as ferramentas. Com 16K e
4.096 de saída, a Hoshino já ficava no limite no modo atividade. A v9 foi
enxugada para quase o tamanho da v8. Desde 05/11, quando falta janela, saem
primeiro as ferramentas fora da atividade declarada (`initiative.ESSENCIAIS`).
Pôr traços no peso permitiria encurtar a identidade do prompt.

## Corpus de 05/11 (`laboratorio-local/pacote_identidade_v4`)

Avaliação dos materiais default (`pacote_neural_v3`):
- 53% das respostas eram idênticas entre Hoshino e Lilith;
- 50% dos exemplos repetiam uma resposta já usada;
- nenhum traço do jeito de partida aparecia, e o próprio relatório do pacote
  pede revisão humana antes de treinar.

Montagem do v4:
- cada resposta igual aparece no máximo 2 vezes;
- as 34 referências novas entram com peso 2, e outras 8 vão para a validação;
- holdout continua o teste do v3, para manter comparabilidade;
- o v3 fica intacto.

As referências novas foram aprovadas pelo juiz 35B (34/42) e por revisão do
Claude, não por humano. O Alistair ganhou banco de personalidade (`referencias_alistair_v1.json`, 36 pares) somado ao seed no v4.

O plano personalizado treina só os três originais (`CUSTOM_TRAININGS = 3`):
- 90 min de treino e 30 min de avaliação cada;
- sem promoção automática; a adoção é decisão humana.

## Fluxo

1. **Traços:** escrever com o humano a lista de cada entidade em
   `tracos_<entidade>.json`. Cada traço tem descrição, exemplo do que é e do que não é.
2. **Exemplos:** de 300 a 600 diálogos curtos por entidade. A fonte são as referências
   editoriais (`laboratorio/defaults_editoriais.json`), candidatos do professor
   aprovados por humano e, depois, conversas reais aprovadas.
3. **Mistura de treino:** identidade + comportamento + conhecimento geral, com penalidade de
   afastamento do original (KL), como no ensaio Aster.
4. **Treino:** primeiro no 4B, para validar o método; depois no 9B. Fazer à noite, com limite de
   potência, porque a placa já chegou a 102 °C.
5. **Avaliação cega:**
   - nome correto em ≥ 95% das perguntas de identidade;
   - um juiz cego atribui a fala à entidade certa mais vezes que o modelo original;
   - nenhuma piora nas verificações de ferramentas, Minecraft e segurança;
   - leitura humana de uma amostra.
6. **Adoção:** só com decisão humana explícita. O original continua disponível para voltar.

## Fora do escopo

Treino de conhecimento ou memória, outras famílias de modelo (Yi, Hunyuan,
Qwen2.5-7B, 6B), automação de visão e qualquer treino automático sem pedido.

## 06/11: corpus v5 e limpeza do material antigo

- **Corpus vigente:** `pacote_identidade_v5`, escrito à mão pelo Claude, sem professor.
  - Fontes em `v5/`; montado por `scripts/montar_corpus_v5.py`.
  - O caminho e o identificador do corpus ficam num ponto só, `laboratorio/corpus_atual.py`, inclusive o holdout novo (`v5/holdout_*.txt`).
- **Material antigo apagado a pedido humano:** pacote_neural_v2/v3, pacote_identidade_v4, seed do Alistair e candidatos de 05→06/11.
  - O que tinha valor ficou em `laboratorio-local/exemplos-material-antigo/`: amostras de comportamento, perfis antigos e as referências v1/v2.
  - As seções acima descrevem o v4 como histórico.
- Detalhes em `docs/CORPUS_V5_20261106.md`.
