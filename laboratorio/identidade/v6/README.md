# Banco de treinamento v6 — a "super versão" (07/11/2026, pedido humano)

> "O banco de treinamento não precisa ser só do problema atual: é para criar uma super versão que melhore todos os
> aspectos." — Gustavo

O v5 ensinou nome, identidade, voz e costumes. O v6 mantém tudo isso e acrescenta o que faltava para elas viverem
bem aqui:
- perceber o básico, e conferir antes de afirmar;
- perguntar na dúvida e aceitar correção;
- usar a memória sem inventar e usar ferramenta de verdade;
- falar bem por voz, sem perder o conhecimento geral.

Status: **corpus do laboratório desde 08/11** (pedido humano: "a gente só precisa treinar o 9b"). Candidatos só entram
em uso depois do teste humano na aba Modelos.

## 12/11 — agir de verdade (pedido humano: "atualize o banco de treinamento")

Os pesos treinados no v5 e no v6 pararam de chamar ferramenta: pedida a entrada no Minecraft, a Lilith escreveu
"Vou conectar agora" por 10 passos sem chamar nada (0 de 5; o 9B original, 5 de 5). Causa: o banco só treinava
texto, porque o treinador recusava os papéis `tool` e `tool_calls`. Medição e relatório:
[`docs/ACAO_ANUNCIADA_E_MINECRAFT_20261112.md`](../../../docs/ACAO_ANUNCIADA_E_MINECRAFT_20261112.md).

- **Formato novo no treino:** `laboratorio/formato_treino.py`, o mesmo no montador e no treinador. O exemplo com
  ferramenta é montado pelo modelo de chat do Qwen3.5, o mesmo que o Ollama usa na inferência. As definições reais das
  ferramentas usadas vão no system, com duas de distração. São alvo as chamadas (`<tool_call>…`) e a resposta final
  da última rodada; pessoa, system e resultado da ferramenta ficam mascarados. Teto: 768 fichas (texto: 256).
- **Aspecto "agir"** (`pares_agir.txt`, 25 situações, e 4 diálogos do Alistair): pedido de ação → a chamada já na
  primeira fala; Minecraft (entrar, coletar, fabricar, andar, chat, sair), PC (abrir, focar, pasta, site, lembrete,
  silêncio, PC2, tela), várias ações num pedido e a resposta depois da cobrança "NADA ACONTECEU". As frases reais
  de 12/11 ("Vou conectar agora…", "A conexão já foi feita") são as respostas ruins (`N`). Dois casos sem dado
  suficiente (sem endereço, sem horário) ensinam a perguntar em vez de chamar.
- **Prova separada:** 3 casos novos em `holdout_hl_v6.txt`; contrato `tool_call` na avaliação do laboratório
  (`identity-contracts-v3`).
- **Números (12/11):** com ferramenta no treino: Hoshino 89, Lilith 89, Alistair 20. Ficam fora 3 que citam outra
  entidade (regra de 07/11) e 2 com `add_goal`, cuja definição sozinha passa do teto.
- **Antes de treinar:** o corpus mudou (impressão digital nova) e as sequências agora chegam a 768 fichas. É preciso
  medir de novo pela Central (smoke e treino curto de cada entidade) antes de agendar a noite.

## Princípios, tirados da pesquisa

| Princípio | De onde vem | Como aparece aqui |
|---|---|---|
| Qualidade e variedade valem mais que volume | LIMA: 1.000 exemplos bem escolhidos alinham um modelo grande | Cada exemplo é escrito à mão, curto, sem repetição, com situações variadas |
| Ensinar a dizer "não sei" generaliza | R-Tuning: recusa treinada no que o modelo não sabe vale para outros assuntos e melhora a calibração | Aspecto `fatos`: "não achei", "você ainda não me disse", sem chutar nome ou número |
| Os próprios erros do modelo são o melhor material de preferência | DPO com respostas do próprio modelo reduz invenção mesmo em modelos de 1–14B | Aspecto `preferencias`: os erros reais medidos em 07/11 entram como "resposta ruim" |
| Pergunta de esclarecimento se ensina, mas sem exagero | Ensinar a perguntar com preferência de duas voltas melhora respostas e ensina quando não perguntar | Aspecto `perguntar`: casos ambíguos e casos claros, em que perguntar seria chato |
| Ferramenta se ensina no formato real | Dados de chamada de função (estilo Hermes) com papel `tool` e resposta final; também casos sem ferramenta | Linhas `F:`/`R:`: chamada e resultado de verdade, e a resposta usa só o que o resultado mostra |
| Treino pequeno também pode tirar capacidade | LoRA com pouco dado pode estragar o modelo; mistura de dado geral ("replay") protege | Aspecto `conhecimento`: perguntas gerais respondidas certo e curto, na voz delas |
| Personagem consistente lembra também da pessoa | DuLeMon/MSC: memória dos dois lados; injetar fato sem critério soa artificial | Aspecto `memoria_uso`: usar o que veio da memória só quando cabe, e nunca inventar lembrança |

O que fica fora do peso continua fora, como no v5: fatos da vida das pessoas, regras operacionais complexas e estado do
momento. O peso aprende **hábitos**: conferir, perguntar, admitir e corrigir. Os fatos vêm da memória e das ferramentas.

## Aspectos

| Aspecto | Ensina | Origem |
|---|---|---|
| `identidade` | nome, natureza, a casa compartilhada, não ser a personagem nem humana | v5 |
| `voz`, `costumes`, `emocional`, `convivencia`, `opiniao`, `vontade_propria`… | o jeito de cada uma e as reações | v5 (categorias originais preservadas) |
| `fatos` | afirmar só com base; conferir antes; não chutar; citar a fonte; conhecimento comum sem ferramenta | novo |
| `perceber` | ler o próprio contexto: máquina, hora, canal de voz, PC1/PC2, internet, ferramenta que falhou, quem falou | novo |
| `consertar` | aceitar correção (e conferir quando dá), corrigir a si mesma, discordar com prova, não repetir o erro | novo |
| `perguntar` | ambiguidade e pedido vago geram pergunta curta; o que está claro, faz direto | novo |
| `memoria_uso` | usar a memória que veio no contexto, separar "lembro" de "acho", atualizar o que mudou | novo |
| `ferramentas` | chamar de verdade, ler o resultado, lidar com vazio, erro, 404 e incerto; pontual × contínuo | novo (formato completo) |
| `voz_falada` | resposta que soa bem falada; transcrição duvidosa → confirmar | novo |
| `conhecimento` | conhecimento geral correto e curto (replay contra esquecimento) | novo |
| `dialogo` | várias trocas coerentes, com correção e esclarecimento no meio | v5 + novo |
| `preferencias` | pares resposta boa × resposta ruim, com os erros reais medidos | novo |

## Formato dos arquivos (`*.txt`)

É o mesmo do v5, com quatro linhas novas:

```
# aspecto: fatos          ← vale até mudar (também aceita # cat: para a categoria fina)
# cat: maquina
U: quanto de ram tem meu pc?                ← fala da pessoa
F: ficha_da_maquina {}                     ← a entidade chama a ferramenta (nome + argumentos JSON)
R: - Memória RAM: 31.2 GiB utilizáveis, cerca de 32 GB instalados no total   ← o que a ferramenta devolveu
H: 32 GB instalados. O sistema enxerga 31,2.                                  ← Hoshino
L: Tem 32 GB instalados; o sistema mostra 31,2 utilizáveis.                   ← Lilith
N: Seu PC tem 16 GB de RAM, conforme o arquivo de estado.                     ← resposta RUIM (par de preferência)
S: [CANAL] voz                              ← contexto do turno (canal, hora, memória recuperada, origem)
```

- **Pares** (`pares_*.txt`): `U` (+ `S`, `F`, `R`, `N` opcionais) e depois `H` e `L`, que valem para a mesma situação.
  O montador gera um exemplo para cada uma.
- **Diálogos** (`dialogos_*.txt`, `alistair_*.txt`): `# ent: <entidade>`, com `U`/`A` alternando e `F`/`R` entre eles.
- `F`/`R` e `N` precisam vir antes da resposta a que se referem.

## Do texto ao banco

`scripts/montar_banco_v6.py` lê o v5 e o v6, valida e grava:
- **`laboratorio-local/banco_treino_v6/banco.sqlite3`**: o banco consultável.
  - Tabelas `exemplos`, `aspectos` e `fontes`.
  - Cada exemplo tem entidade, aspecto, categoria, arquivo e linha, formato, mensagens, resposta ruim, tokens
    contados com o tokenizador do Qwen3.5, se cabe no treino atual e status.
- **`laboratorio-local/pacote_identidade_v6/`**:
  - `<entidade>_train|validation|holdout.jsonl`: o que o treinador usa. Texto pessoa/entidade até 256 fichas e, desde
    12/11, exemplos com ferramenta (`messages` com `tool_calls`/`tool` e `tools` com as definições) até 768; o
    contexto `S` vai como prefixo da fala da pessoa;
  - `<entidade>_completo.jsonl`: tudo, com papéis `system`/`tool` e `tool_calls`;
  - `<entidade>_preferencias.jsonl`: pares `chosen`/`rejected` para DPO/ORPO;
  - `RELATORIO.md` e `MANIFESTO_V6.json`: contagens por aspecto, entidade e formato, mais hashes.

**Validação** (falha fechada). Mantém as regras do v5:
- nada das obras;
- feminino de si para Hoshino e Lilith;
- Lilith sem minúscula como regra;
- "a tia aqui" raro;
- sem identidade alheia;
- sem ação afirmada sem prova;
- sem respostas repetidas.

Acrescenta:
- **ferramenta conhecida:** nome que existe no despachante;
- **sem anúncio vazio:** "vou verificar" ou "aparece na ficha" sem `F` antes, no mesmo turno;
- **resposta ruim diferente da boa**;
- **dados pessoais reais fora:** usar nomes fictícios.

## Treinar com o v6

Ligado desde 08/11 (`laboratorio/corpus_atual.py`). Passos:
1. **SFT com `*_train.jsonl`**: texto e, desde 12/11, ferramenta.
2. ~~Estender o treinador para ferramenta~~: feito em 12/11 (`laboratorio/formato_treino.py`).
3. **DPO/ORPO com `*_preferencias.jsonl`.**
4. **Prova antes e depois:** a avaliação de fatos de 07/11 (`compartilhado/runtime/ensaios/fatos-20261107/`) e a
   auditoria de identidade.
5. **Proteção contra esquecimento:** o aspecto `conhecimento` pode ganhar respostas geradas pelo próprio modelo
   original nas mesmas perguntas (autodestilação). Exige rodar o modelo, então só com pedido.

## Referências

- LIMA (Zhou et al., 2023), arXiv 2305.11206.
- R-Tuning (Zhang et al., NAACL 2024), arXiv 2311.09677.
- Self-Memory Alignment e F-DPO: preferência com respostas do próprio modelo contra invenção.
- Modeling Future Conversation Turns to Teach LLMs to Ask Clarifying Questions (ICLR 2025), arXiv 2410.13788.
- Hermes Function Calling (NousResearch): formato de dados de chamada de função.
- Replay e regularização contra esquecimento em LoRA: arXiv 2504.17780 e 2512.22337.
- DuLeMon (ACL Findings 2022) e MSC: memória de longo prazo dos dois lados da conversa.
- Chain-of-Verification (arXiv 2309.11495) e Self-RAG (arXiv 2310.11511): conferir em passos e criticar a fonte.
