# Sincronização do projeto privado — 10/10/2026

## Escopo

Repositório: `https://github.com/atominen/hoshino-e-lilith.git`, branch `main`.
Base remota encontrada e conferida por fetch/ls-remote:
`f23ba0d721fac6cb53534b55fcc5b48547e1dec8`. Sem divergência inicial.
A integração GitHub confirmou `visibility=private` e acesso de escrita.

Esta rodada sincroniza o desenvolvimento existente; não implementa outra mente,
não altera modelos/configurações de execução e não faz limpeza de dados.
O Git local já estava autenticado. A identidade de commit estava ausente na
configuração local: foi reutilizada, somente neste repositório, a mesma autoria
dos três commits anteriores, sem modificar autenticação ou configuração global.

## Organização dos commits

- `d05e0af`: código, Central/UI, memória cognitiva, cache RAM, Resource Manager
  e regressões existentes. Inclui os sete módulos Python de `app/memory`, antes
  ignorados pela regra destinada a dados mentais.
- `03490e0`: iniciadores, exemplos não secretos, atalhos, serviços/verificadores
  e PC2. As dez exclusões de manifesto/templates antigos já existiam na árvore
  antes desta rodada; foram registradas, não recriadas como limpeza nova.
- Commit de documentação: relatórios originais/consolidados, screenshots de UI,
  planejamento, README atualizado, origens e política de preservação. O hash
  definitivo deve ser consultado em `main` e comparado com `origin/main` após
  o envio; este documento não pode conter o próprio hash de commit.

Incluídos resumos incrementais, diário privado/compartilhamento seletivo,
aprendizado experiencial/conceitual, oficina visual, sessões diárias,
continuidade temporal, recuperação de memória e correções de contexto,
execução, autoria, áudio e backend já presentes. Não houve nova implementação
dessas capacidades para preparar o GitHub.

## Verificações

- Suíte oficial nesta rodada: **74/74 grupos offline**, processo terminou com
  código zero. Runner isolado, sem inferência real, microfone ou quota externa.
- Verificação de whitespace/diff e do conteúdo do índice Git antes dos commits.
  O check completo apontou apenas espaços finais no rascunho literal
  `planejamento/conversa_cloud_20261006_referencia.txt` e uma linha vazia final
  no relatório consolidado. Foram preservados, sem reformatar os originais.
  Excluindo esses dois documentos da verificação, o check passou.
- Auditoria básica por formatos de credenciais/chaves privadas, valores secretos
  configurados no ambiente e arquivos pesados; sem imprimir valores de segredos.
  Índice final: 341 arquivos (331 textuais e dez binários de screenshots), sem
  correspondências nas regras conferidas. Não equivale a uma auditoria exaustiva
  de segurança.
- Sem pesos, bancos, `.env`, logs/JSONL, ambientes ou repositórios Git aninhados
  no índice. Nenhum arquivo versionado excedeu 5 MiB na conferência.
- Envio normal para `main`, sem force push. A confirmação final exige fetch,
  igualdade do SHA local/remoto e nova consulta da visibilidade privada; só
  depois o atendimento pode declarar sincronização concluída.

## O que permanece local

Identidades reais, constituições, configurações fundamentais, bancos, vetores,
histórico e diários permanecem nas entidades. Também ficam locais credenciais,
pesos, ambientes, caches, runtime, evidências brutas e pacotes gerados do PC2.
Nada disso foi apagado nesta rodada. Exemplos de configuração não contêm chaves.

O checkout/build externo `stable-diffusion.cpp` (aproximadamente 1,1 GiB local)
foi explicitamente ignorado, sem remoção. Origem e revisões estão registradas
em `third_party/ORIGENS.md`. O clone Git não instala sozinho dependências,
pesos ou estado privado. Código de integração e fontes próprias foram incluídos.

## Limites e prioridade

Os relatórios históricos permanecem íntegros, com suas falhas e números originais.
Sincronização e testes offline não aprovam os 9B ou uso prolongado: o ensaio
cognitivo registrou decisão estruturada incorreta e falha de carga ROCm, entre
outras pendências descritas em `CONSOLIDACAO_COGNITIVA_20261010.md`.

A política atual está em `POLITICA_PRESERVACAO_PROJETO.md`: preservar estrutura,
identidade e configuração, manter testes isolados, evitar proteção excessiva de
fixtures descartáveis e priorizar confiabilidade/desempenho/personalidade e
aprendizado em uso real. Não foi solicitado nem realizado outro reset mental.
