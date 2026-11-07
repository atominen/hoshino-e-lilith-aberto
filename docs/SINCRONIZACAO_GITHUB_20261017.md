# Sincronização do projeto — 17/10/2026

Pedido: atualizar o GitHub com o estado local, sem reinstalar, limpar dados,
iniciar treinamento ou reconstruir funcionalidades.

## Destino e preservação

- Repositório consultado pela API: `atominen/hoshino-e-lilith`, **privado**,
  acesso de escrita confirmado. Visibilidade não foi alterada.
- Checkout local: `codex/laboratorio-consolidacao-20261012`.
- Branch de entrega existente: `laboratorio-v11-organizacao-20261012`, no
  [PR #1](https://github.com/atominen/hoshino-e-lilith/pull/1), preservado em
  rascunho. Atualizar este PR não significa mesclar automaticamente na `main`.
- Antes da sincronização, HEAD local e branch remota coincidiam em
  `ccd0133b310255d13269e8f0e91dde9fbb739ea2`; `fetch` confirmou ausência de
  commits divergentes. As alterações posteriores estavam no diretório de
  trabalho e foram incluídas, não descartadas.
- Envio por avanço normal da branch existente, sem force push, rebase ou
  reescrita do histórico. O SHA de entrega deve ser conferido pelo `ls-remote`
  e pelo head do PR; a resposta da operação de push, isoladamente, não basta.

## Conteúdo preparado

1. Laboratório: aprimoramentos do professor/curadoria por exemplo, referências
   editoriais, revisão de defaults, relógio efetivo, checkpoints, recarga,
   avaliações, versões e recuperação/conversão local de executores. Mantidas
   as separações original/candidato/estável e as falhas registradas.
2. Sessão manual/noturna no supervisor existente, controles de autorização e
   preservação das decisões humanas posteriores. A sincronização **não**
   autoriza treino, professor, promoção ou agendamento.
3. Central: seleção de versões originais/checkpoints/treinadas, feedback nas
   conversas, correções de destinos e envio, voz/ASR/atalho global, cartões de
   conhecimento e encerramento cooperativo verificável. Ícone/lançador
   versionados; a fixação do painel é configuração local, não arquivo do Git.
4. Resource Manager e executor de Alistair: integração dos mecanismos existentes,
   sem novo scheduler, cloud ou GPU concorrente.
5. Regressões e relatórios de13–16/10, com índices e guias atualizados. Leituras
   antigas de6h/12h foram identificadas como substituídas pela decisão posterior
   de10h agregadas, condicionada a novo aviso humano e aos gates existentes.

Foram preservadas todas as modificações preexistentes. A única correção de
formatação durante a sincronização foi remover uma linha vazia extra no fim de
`laboratorio/recuperacao_modelos.py`, detectada ao conferir também os arquivos
novos preparados para o commit. Nenhuma lógica foi alterada para publicar.

## Verificações desta rodada

| Verificação | Resultado observado |
|---|---|
| Suíte oficial offline | **74/74 grupos**, exit 0 |
| Laboratório, execução separada | **333/333 testes**, exit 0 |
| Conteúdo preparado | Código, UI, testes, SVG, lançador e Markdown/JSON editorial |
| Caminhos privados/pesos/caches preparados | Nenhum encontrado na checagem |
| Padrões de credenciais e valores sensíveis locais conhecidos | Nenhum encontrado; valores não impressos |
| Código Python ignorado indevidamente em app/scripts/laboratorio | Nenhum arquivo-fonte novo encontrado nessa condição |
| Espaços/linhas da alteração preparada | `git diff --cached --check` sem erros após a correção descrita |

Logs locais: `/tmp/github-sync-oficiais-20261017.log` e
`/tmp/github-sync-laboratorio-20261017.log`. Não são enviados ao GitHub.
O laboratório também é executado pelo grupo oficial correspondente; a contagem
de333 acima registra a execução separada, não novos grupos da suíte oficial.

Testes offline/fixtures não demonstram personalidade, funcionamento físico de
microfone/Discord/Minecraft ou estabilidade de treinamento prolongado. Não houve
novo ensaio físico de modelos, treino, captura de voz ou consumo de ElevenLabs
nesta sincronização. Permanecem as limitações documentadas nas rodadas originais.

## O que fica somente no computador

Pesos e adaptadores, datasets privados, bancos/vetores/diários/históricos,
configurações reais e credenciais, ambientes, dependências compiladas, caches,
logs e backups/recibos locais continuam fora do Git. As regras existentes não
foram contornadas e esses arquivos **não foram apagados** por estarem ignorados.
Os pequenos arquivos editoriais do código do laboratório não são cópias dos
bancos mentais nem de conversas privadas reais.

A limpeza de testes e a redefinição de senha relatadas em
[PAINEL_SENHA_E_LIMPEZA_TESTES_20261016.md](PAINEL_SENHA_E_LIMPEZA_TESTES_20261016.md)
pertencem à autorização anterior. Esta rodada de GitHub não executou nova
limpeza, não mudou identidades ou configurações e não reiniciou serviços.

## Continuação

A avaliação humana continua sendo necessária. Publicar o código não promove
adaptadores experimentais nem aprova automaticamente o professor. Para operar,
usar o [README atual](../README.md), o [seletor de versões](SELETOR_VERSOES_MODELOS_20261016.md)
e os [limites da Central](MIC_CONHECIMENTO_E_ENCERRAMENTO_20261016.md).
