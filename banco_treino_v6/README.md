# Banco de treinamento v6 (compilado)

Gerado por `scripts/montar_banco_v6.py` a partir de `laboratorio/identidade/v5` e `v6`. Rascunho: ainda não
usado em treino. Formato e princípios em [`laboratorio/identidade/v6/README.md`](../laboratorio/identidade/v6/README.md).

- `banco.sqlite3`: tabelas `exemplos`, `aspectos`, `fontes`, `meta` e a view `resumo`.
- `pacote/<entidade>_train|validation|holdout.jsonl`: o que o treinador atual aceita (texto, até 256 tokens).
- `pacote/<entidade>_completo.jsonl`: com papéis `system`/`tool` e `tool_calls`.
- `pacote/<entidade>_preferencias.jsonl`: pares `chosen`/`rejected` (os `rejected` incluem erros reais do 9B).
- `pacote/RELATORIO.md`: contagens por entidade e aspecto.
