# Xadrez padrão da Hoshino

O módulo usa as regras normais do xadrez e mantém a partida em SAN/PGN.

## Regras cobertas

- movimento legal de todas as peças;
- xeque, xeque-mate e afogamento;
- roque curto e longo;
- en passant;
- promoção para Dama, Torre, Bispo ou Cavalo;
- obrigação de remover o próprio rei do xeque;
- repetição tripla como empate reivindicável;
- repetição quíntupla como empate automático;
- regra dos 50 lances como empate reivindicável;
- regra dos 75 lances como empate automático;
- posições mortas nos casos clássicos de material insuficiente;
- SAN com desambiguação correta e marcação de `+`/`#`;
- UCI (`e2e4`, `g1f3`, `e7e8q`);
- PGN com cabeçalhos e resultado.

## Importante

Regras reivindicáveis não encerram uma partida automaticamente. A Hoshino pode usar
`reivindicar_empate_xadrez` quando decidir exercer esse direito. Abandono é registrado
como derrota da Hoshino, e não como empate.
