# Voz progressiva básica — 25/10/2026

Estado: implementada, revisada, verificada e carregada na Central local. O desenho foi aprovado
pelo usuário, que escolheu fones e a instalação atual, sem cancelamento de eco.

## Comportamento

Para usar, marque **Ler novas respostas em voz** na conversa. A opção continua
desmarcada ao abrir/reconectar a Central, preservando o controle de quota.

- Hoshino/Lilith podem iniciar a voz na primeira frase completa validada,
  enquanto o restante da resposta ainda é gerado. Usa a voz/provedor já
  configurados e a geração existente; não simula áudio instantâneo.
- Chat direto e global respeitam autoria, sala e sessão. A confirmação da
  resposta final não repete um stream já admitido para reprodução.
- Enviar uma mensagem comum ou abrir o microfone não corta a voz. Pedidos
  explícitos de parada e a ferramenta de parar a própria voz continuam
  disponíveis. Correções que invalidem uma resposta preservam a proteção
  existente contra continuar pronunciando conteúdo invalidado.
- Detecção mantém a captura e envia falas ao ASR durante o áudio com fones.
  Comando captura enquanto acionado. Esta versão não cancela eco de caixas.
- O player informa início, progresso aproximado em segundos, término,
  cancelamento e falha. O contexto da conversa e `estado_voz` mostram quem
  está falando; somente a própria entidade recebe o texto de suas frases.
  `parar_voz` pede o encerramento próprio e aguarda confirmação do player.
- O player único ordena falas pendentes, sem alternância fixa entre entidades.
  A decisão contextual continua sendo do modelo; a infraestrutura fornece
  estado e controles, sem criar comentários/decisões fictícios.

## Implementação e limites

A fila existente mantém capacidade 4 e contabilidade única. Dois consumidores
fixos atendem ASR e TTS, usando `cpu_audio` exclusivo por chamada de motor.
Esperar nova frase do LLM não segura esse lease nem impede transcrição.
Uma chamada longa deixa o outro trabalho em espera cancelável, sem apagar
a gravação por um limite fixo de 20 segundos. ASR tem prioridade entre frases.
Workers liberam RAM após ociosidade; ASR frio verifica folga de 4 GiB mais a
margem do RM antes de iniciar. Nenhuma GPU concorrente foi habilitada.

Recibos nativos carregam sequência e instante de observação para lidar com atraso de transporte.
Um estado de fala sem atualização por 4 segundos se torna desconhecido.
Uma nova Central não adota reprodução de instância anterior. Nenhum recibo
afirma que um humano ouviu; síntese pronta também não prova reprodução.
Uma solicitação de parada só vira cancelamento confirmado quando o processo
do player encerra. Falta de recibo permite solicitar parada mesmo no estado
desconhecido. Turnos globais ocultam o texto de uma reprodução privada.

O início depende do tempo para gerar e sintetizar a primeira frase. O ASR
continua por trechos, não por palavra; agrupamento de entradas e painel de
fontes por aplicativo ficam para as próximas etapas. Alistair permanece
textual com o executor atual. Não houve troca de modelos, alteração mental,
treino, download, nova dependência ou teste de voz com quota.

## Evidências

Regressões foram observadas falhando antes das correções: audiência global,
captura durante reprodução, microfone sem corte, envio sem corte, ASR durante
espera do stream, playback vencido, ordem dos recibos e isolamento de instância.
Testes usam bancos temporários, áudio sintético e transporte/processos
simulados. Qt usa seus widgets reais em modo offscreen: não valida microfone,
fones, qualidade de voz nem comportamento real dos LLMs.

Verificação final: **92/92 grupos offline aprovados**, sem supressões. O grupo
novo executou efetivamente **16 testes** pelo runner oficial. O recorte
combinado de áudio, global e Central passou **163 testes**; o processo Qt
exercitou **127 contratos** em modo offscreen.

Uma revisão independente encontrou seis problemas importantes: audiência,
parada após progresso, parada pendente/desconhecida, contenção entre motores,
recibo atrasado e cancelamento antes da saída física do processo. Todos foram
corrigidos com regressões observadas falhando e depois passando. A posição
do progresso também foi limitada ao chunk atual. Expectativas antigas de
corte e fixtures de player/sono foram reconciliadas com o novo contrato e a
origem da Central. As verificações de
sessão, autoria, deduplicação e separação das entidades foram preservadas.

Uma rodada intermediária apresentou falha temporal em comandos duráveis ao
rodar outros testes em paralelo. O grupo passou 19/19 sem mudança no código;
a execução completa final, sem ensaios paralelos, passou integralmente.

Reabertura confirmada: backend PID **185675**, UI nativa PID **185684**,
janela mapeada no desktop. `GET /api/state` e `GET /api/audio/state`
autenticados responderam 200. Três entidades em `sleeping`, zero jobs ativos,
zero leases e workers ASR/TTS desligados; não houve despertar, treino ou voz.

Logs locais: `/tmp/voz-basica-focados-final.log`,
`/tmp/voz-basica-qt-final.log` e `/tmp/voz-basica-suite-entrega.log`.

Referências: [desenho](superpowers/specs/2026-10-25-voz-progressiva-basica-design.md)
e [plano](superpowers/plans/2026-10-25-voz-progressiva-basica.md).
