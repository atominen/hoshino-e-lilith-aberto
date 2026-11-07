# Sequência autorizada — áudio e Minecraft — 26/10/2026

## Pedido atual

Executar em ordem: ensaio de transcrição na GPU; agrupamento de mensagens
digitadas em partes; painel de fontes de áudio; depois ensaio interativo de
Minecraft. O usuário escolheu **Lilith**, informou mundo LAN **1.16.1** e
porta **35229**. A consulta de status confirmou protocolo736 e um jogador,
em127.0.0.1; isso não é prova de bot conectado nem de objetivo cumprido.

O assistente pode fazer RP identificado como teste para avaliar interação e
dar objetivos progressivos, corrigindo falhas até o objetivo final: fabricar
e equipar armadura completa de diamante. Usar sobrevivência normal, sem
comandos de itens/teleporte ou ações feitas pelo assistente contadas como
autoria de Lilith. Não fabricar respostas, relatos de sucesso ou histórico
humano. Registrar intervenções, resultados e limitações separadamente.

## Primeiro: spike de GPU

Ensaio separado dos executores ativos, usando whisper.cpp/Vulkan oficial.
Hardware observado: RX6650XT/RADV, Vulkan disponível, cerca de0,78GiB de
VRAM ocupada pelo desktop/jogo, sem lease de compute. Vulkan disponibiliza
também llvmpipe: selecionar e comprovar a GPU AMD física, nunca apresentar
execução em software como aceleração por GPU.

O ASR atual usa faster-whisper/CTranslate2 large-v3 CPU/int8. Para comparar a
mesma família/pesos, o ensaio usa a distribuição GGML oficial large-v3,
mantendo o ASR ativo preservado. O formato extra é material necessário ao
ensaio, não um novo modelo de conversa ou aprovação automática de adoção.
Testar precisão, latência, VRAM/RAM, temperatura, exit real e liberação;
usar RM existente, sem inferência GPU concorrente das entidades.

Fonte whisper.cpp fixada no commit231638a0717b7822784297e5980965ffcec05810.
GGML large-v3 publicado por ggerganov/whisper.cpp:3095033483bytes,
SHA25664d182b440b98d5203c4f9bd541544d84c605196c4f7b845dfa11fb23594d1e2.
Confirmar hash antes de carregar e registrar a revisão Hugging Face usada.

Código compilado, pesos e logs extensos ficam em `laboratorio-local/`, já
ignorado; somente fontes próprias, manifestos e resultados necessários
devem ser versionados. Sem limpeza de dados/modelos preexistentes, alterações
de drivers/sistema, novo scheduler ou alterações silenciosas de configuração.

## Etapas posteriores

Refinar o comportamento do agrupamento e do painel com as escolhas humanas,
preservando salas, autoria, revisão de ASR, contexto e permissões individuais.
Antes de editar código carregado, fazer manutenção cooperativa/reconciliação.
O teste Minecraft só começa depois dessas etapas, pelo controle existente,
com recibos exatos do mundo e ações decididas pelo LLM de Lilith.

## Desfechos da execução

- GPU: ensaio físico concluído; resultados e restrições em
  [ASR Vulkan](ASR_VULKAN_ENSAIO_20261026.md). Backend ativo não foi trocado:
  velocidade maior no ensaio não compensou automaticamente a regressão no
  nome próprio e a alucinação em silêncio.
- Texto em partes: escolha humana de2s aplicada ao barramento/worker local.
  Envios permanecem individuais; um turno combina fragmentos compatíveis.
  Revisão independente encontrou e a implementação corrigiu duas lacunas:
  snapshot inconsistente sob envio concorrente e pedido retido que poderia
  ressurgir depois de uma parada/correção. Regressões usam SQLite temporário
  e o fluxo inbox→worker real, sem mensagens nas entidades instaladas.
  Verificação final: **94/94 grupos offline**, incluindo10 testes do filtro e
  47 de causalidade/worker; log `/tmp/mensagens-partes-review-suite-20261026.log`.
  Aplicado no código local; a Central estava fechada e usará a mudança na
  próxima abertura. Sem novo ambiente, despertar, merge ou publicação.
- Painel sonoro: decisão seguinte do usuário foi executar tudo integrado ao
  aplicativo único. Captura por aplicativo e ASR compartilhado implementados;
  controles em Áudio → Fontes e atenção. Detalhes/evidências em
  [Áudio unificado e Minecraft](AUDIO_UNIFICADO_E_MINECRAFT_20261026.md).
- Minecraft: ainda sem bot conectado e sem aprovação de objetivos. A ponte
  existente foi corrigida para bancada de trabalho, receitas, forno e leitura
  de armadura equipada; ensaio real ainda deve comprovar a progressão.
