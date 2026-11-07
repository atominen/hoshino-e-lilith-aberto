# Transcrição ao vivo — 25/10/2026

Estado: implementada, revisada, verificada e aplicada na Central local.

## Uso e comportamento

Abra o microfone em **Áudio**, no modo Comando ou Detecção. A área de
transcrição em andamento mostra hipóteses reais reconhecidas pelo ASR,
podendo corrigir palavras conforme chega mais áudio. Ela não altera seu
rascunho digitado e não é uma mensagem enviada às entidades.

No modo Comando, soltar a tecla/botão encerra a fala. Em Detecção, a
preferência foi atualizada para **2000 ms de silêncio**; pausas menores
continuam na mesma fala. O corte interno de 45 segundos divide o trabalho
do transcritor e não envia a mensagem antes da hora.
Uma cauda menor que 200 ms após esse corte é preservada e completada com
silêncio até o mínimo aceito pelo transporte, sem perder o áudio residual.

Com **envio automático** habilitado na aba Áudio, a fala confirmada gera
um único envio. A opção existente foi preservada: estava desabilitada nesta
instalação; sem ela, o resultado fica no rascunho para revisão/envio manual.
Abrir a Central continua sem iniciar microfone nem acordar entidades.

## Implementação

- `native_asr.py` mantém fala, revisões, fila limitada, textos provisórios
  e definitivos. No máximo uma solicitação em andamento, uma prévia recente
  em espera e quatro trechos definitivos aguardando. Limite de 64 trechos
  por fala e de 6000 caracteres para envio automático; exceder um limite
  preserva texto disponível para revisão e bloqueia envio incompleto.
- `native_asr_client.py` conecta a captura à fila de áudio atual. Definitivos
  precedem prévias. Os instantâneos são solicitados no máximo uma vez por
  segundo quando há áudio novo suficiente; não há inferência por palavra.
- `asr_provenance.py` valida ID de fala, parte, revisão, tipo de resultado,
  sessão e escopo. Prévias não podem ser prova de uma mensagem. A origem
  composta exige trechos definitivos concluídos, únicos e em ordem, da mesma
  entidade/fala/sessão/escopo/origem. Preserva sinais acústicos para a revisão
  semântica existente, aplicada sobre a mensagem completa.
- O worker faster-whisper existente permanece CPU/int8, serializado por
  `cpu_audio`. Não há outro motor, modelo, scheduler ou GPU concorrente.
  WAVs temporários seguem a remoção já existente após o trabalho.

Parar para enviar e descartar são ações distintas. Descarte, troca de
entidade/conversa/conexão e resultados atrasados não enviam a fala à sala
errada. Erro definitivo impede o envio automático completo; prévia falha
não invalida um definitivo correto. Texto reconhecido disponível fica no
rascunho para recuperação. Um envio com resultado incerto não é repetido
automaticamente; seu ID de submissão é preservado.

Ausência de fala reconhecível, como em um ruído/risada, não desliga Detecção.
O erro `no_speech` conserva o processo ASR saudável; não é tratado como crash.
Se faltar um trecho de uma fala longa, ela não é enviada parcialmente e sua
continuação é ignorada até seu fim real. Falas independentes são preservadas.
Pressionar Comando novamente enquanto a fala anterior está pendente não a
descarta: o cliente aguarda a conclusão. Descarte solicita cancelamento dos
jobs owned, inclusive aceites tardios, e confirma o terminal por leitura.
Nova captura aguarda cancelamentos conhecidos pendentes; IDs não migram para
outro backend. Não há repetição automática do POST de cancelamento.

## Limites

Prévia é reconhecimento parcial, não garantia de palavra instantânea.
Faster-whisper reprocessa instantâneos; velocidade e precisão dependem da
CPU, carga e qualidade do áudio. Não há animação que simule palavras antes
do resultado real. Os testes de transporte/Qt não medem latência física.
Um corte de áudio longo pode afetar uma palavra na fronteira; qualidade de
fala real continua exigindo teste humano.

Agrupar mensagens digitadas já enviadas e escolher fontes de som por
aplicativo permanecem etapas futuras. Identidades, modelos, memórias,
permissões e treinamentos não foram modificados.

## Evidências

Regressões observadas RED→GREEN: fim real versus corte físico; revisão da
hipótese; recuperação após falha; prévia proibida como prova; origem composta;
metadados pelo HTTP real; UI antes de soltar; envio único; aceite após
descarte; rascunho e seleção preservados. PCM/ASR simulados, bancos temporários
e Qt real em modo offscreen. A prévia visual foi inspecionada.

O teste antigo de fones foi reconciliado para conferir o pedido ASR real
no novo fluxo, em vez de interceptar o método legado de transcrição final.
O aviso de microfone indisponível foi preservado.

Primeira execução completa: **93/93 grupos offline aprovados**, incluindo
**135 contratos Qt**, **47 testes de áudio/HTTP** e **11 de captura/controlador**.
Log: `/tmp/asr-live-suite-20261025.log`.

Também foi executado o worker ASR real, com o RM, sobre áudio sintético
declarado gerado por espeak-ng. A prévia de 2 s levou **10,17 s** na chamada
fria, incluindo início/carga; a frase completa levou **6,04 s** com o mesmo
worker aquecido. As duas retornaram texto e o worker foi encerrado. Isso
confirma o caminho real, mas demonstra que o `large-v3` em CPU ainda tem atraso:
o limite de pedidos de 1 s não é promessa de resultados a cada segundo.
Não houve microfone, conversa de entidade, download, GPU ou voz com quota.
Log: `/tmp/asr-live-real-smoke-20261025.log`.

A revisão independente encontrou cinco problemas importantes: no_speech
encerrando escuta, novo Comando descartando fala concluída, jobs abandonados
no descarte, prévia tardia perdida e cauda curta rejeitada. Todos receberam
regressões RED→GREEN. O limite de quatro trechos foi também corrigido para
valer sobre todas as falas, por seu impacto no backlog/latência. A rodada
focada após os ajustes passou49 testes de áudio/HTTP,42 da Central com Qt e11
do controlador. Relatório: `/tmp/asr-live-review-final-20261025.md`.

Depois das correções, a suíte integral passou novamente **93/93 grupos**,
sem supressões. Log final: `/tmp/asr-live-suite-final-20261025.log`.
Não foram realizadas novas inferências de conversa ou sínteses com quota.

Central reaberta com o mesmo intérprete Python do launcher anterior:
backend **43638**, UI nativa **43645**, janela mapeada no desktop. As leituras
autenticadas confirmaram silêncio de **2000 ms**, modo Comando, envio automático
**desabilitado**, três entidades em `sleeping`, zero jobs ativos e zero leases.
O usuário pode habilitar envio automático em Áudio para usar a confirmação
automática ao terminar. O microfone não foi aberto pela aplicação desta mudança.
Prova local: `/tmp/asr-live-deployed-20261025.json`.

Referências: [desenho aprovado](superpowers/specs/2026-10-25-transcricao-ao-vivo-design.md),
[plano](superpowers/plans/2026-10-25-transcricao-ao-vivo.md),
[faster-whisper](https://github.com/SYSTRAN/faster-whisper),
[WhisperStreaming](https://github.com/ufal/whisper_streaming).
