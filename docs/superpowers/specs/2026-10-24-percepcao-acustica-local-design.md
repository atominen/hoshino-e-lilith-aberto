# Percepção acústica local — desenho aprovado em princípio

## Objetivo e autorização

O usuário quer escuta contínua capaz de perceber risadas, gargalhadas e outros
sons, além de transcrever fala. Em24/10 aprovou expressamente **detector local
separado do transcritor**, mantendo Comando/Detecção, sem cloud e sem gravação
permanente contínua. O componente não está implementado nem instalado por
este documento. O usuário aprovou depois o plano e a execução direta; o ledger
e o relatório de implementação distinguem o que já foi entregue.

## Abordagem

Aumentar apenas a sensibilidade do gate de volume não resolve classificação;
pedir ao Whisper para nomear ruídos também não demonstra reconhecimento acústico.
A abordagem aprovada separa transcrição e detecção de eventos. A proposta técnica
é começar com YAMNet oficial, em CPU e ambiente isolado, sem tocar nos7B/9B,
4B de Alistair, GPU, Xbox, identidades ou memórias existentes.

Referências primárias: [YAMNet](https://github.com/tensorflow/models/tree/master/research/audioset/yamnet),
[classes](https://github.com/tensorflow/models/blob/master/research/audioset/yamnet/yamnet_class_map.csv),
[runtime de classificação](https://developers.google.com/edge/litert/libraries/task_library/audio_classifier).
Scores de classes não são probabilidades calibradas; validar com áudio antes de
prometer sensibilidade. Não existe garantia honesta de detectar **toda** risada.

## Contrato

- Apenas Comando e Detecção. A escuta começa por ação explícita, com indicador,
  e respeita a permissão existente de ouvir o ambiente e seu desligamento.
- Em Detecção, o fluxo PCM também alimenta o classificador sem passar pelo VAD
  de fala. Janelas curtas sobrepostas em RAM; filas limitadas e perdas visíveis.
- Risada/gargalhada, choro, suspiro, tosse e sons ambientais são eventos
  possíveis, não palavras transcritas, ordens ou provas de emoção/identidade.
- Usar a fonte e o horário reais. Sem evidência de autoria, não registrar
  “o usuário riu”. Não despertar entidades nem enviar mensagens a terceiros.
- A captura deve continuar durante análise. Sobreposição com a própria voz
  do app deve ser marcada; não atribuir esse áudio ao usuário. Cancelamento
  de eco real precisa ser verificado, não simulado por uma promessa.
- Desligar captura/permissão cancela análise pendente. Não carregar modelos
  na importação, baixar em runtime ou guardar áudio contínuo no disco.
- O armazenamento técnico existente guarda somente eventos/metadados mínimos;
  bancos mentais não são espelhados nem alterados em uma checagem de áudio.

## Aceitação e reversibilidade

Testes isolados de janelas, continuidade, permissão, fila, eco, cancelamento e
autoria; depois áudios de referência de origem/licença documentada, silêncio,
fala, risadas baixas/curtas, ruído e misturas. Medir recall/falsos positivos,
latência e CPU/RAM separadamente. Um teste simulado não aprova o microfone real.
Ausência/falha do detector aparece explicitamente; Comando/ASR continuam
disponíveis. Remover/desativar o detector não altera LLMs, conversas ou memórias.
