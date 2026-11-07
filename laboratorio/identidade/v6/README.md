# Banco de treinamento v6 — a "super versão" (07/11/2026, pedido humano)

> "O banco de treinamento não precisa ser só do problema atual: é para criar uma super versão que melhore todos os
> aspectos." — Gustavo

O v5 ensinou nome, identidade, voz e costumes. O v6 mantém tudo isso e acrescenta o que faltava para elas viverem
bem aqui:
- perceber o básico, e conferir antes de afirmar;
- perguntar na dúvida e aceitar correção;
- usar a memória sem inventar e usar ferramenta de verdade;
- falar bem por voz, sem perder o conhecimento geral.

Status: **rascunho escrito pelo Claude, aguardando aprovação humana.** Nada é treinado sem pedido.

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
  - `<entidade>_train|validation|holdout.jsonl`: o que o treinador atual aceita (só texto pessoa/entidade, até 256
    tokens; o contexto `S` vai como prefixo da fala da pessoa);
  - `<entidade>_completo.jsonl`: com papéis `system`/`tool` e `tool_calls`, para quando o treinador aceitar
    ferramenta;
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

Não está ligado. `laboratorio/corpus_atual.py` continua no v5 até a aprovação humana. Depois de aprovar:
1. **SFT com `*_train.jsonl`** (o que o treinador já aceita).
2. **Estender o treinador** para `*_completo.jsonl`, com papéis `tool`/`system` e sequências maiores que 256 tokens.
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
