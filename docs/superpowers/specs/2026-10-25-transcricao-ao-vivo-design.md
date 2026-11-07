# Transcrição ao vivo e fim de fala — 25/10/2026

## Intenção e decisões humanas

Mostrar a transcrição durante a fala, permitindo corrigir a hipótese conforme
chega mais áudio. As entidades esperam o usuário terminar para responder.
Pausas menores que **2000 ms** pertencem à mesma fala no modo Detecção;
no modo Comando, soltar a tecla/botão encerra a fala. O usuário confirmou
esse intervalo nesta conversa. Continuar na instalação atual, com fones,
sem cancelamento de eco, cloud ou novos pesos.

## Abordagem

Reutilizar o faster-whisper e o worker persistente já existentes. Enviar
instantâneos cumulativos do trecho em andamento para obter prévias reais,
com no máximo uma solicitação em processamento e uma prévia mais recente
em espera. Não enviar uma inferência por palavra. Substituir a prévia quando
o reconhecimento mudar, sem reproduzir artificialmente texto já pronto.

Um motor novo de streaming exigiria novos pesos, dependências e homologação.
Esperar todo o áudio preservaria o problema atual. O reaproveitamento é a
escolha técnica desta etapa; a latência depende do ASR e da carga local,
sem promessa de reconhecimento instantâneo de cada palavra.

## Captura e apresentação

- Identificar cada fala por um ID próprio, entidade, escopo e sessão de origem.
- Pedir a primeira prévia após pelo menos 1 s de áudio útil e atualizar no
  máximo uma vez por segundo, quando o worker e o RM permitirem.
- Exibir a hipótese em uma área de transcrição em andamento junto ao campo
  de mensagem. Preservar rascunhos digitados e seleção; a prévia é revisável,
  separada de mensagens confirmadas e nunca vira uma resposta da entidade.
- O limite físico existente de 45 s divide somente o áudio de trabalho.
  Ele não deve enviar uma mensagem antes do fim real da fala. Preservar a
  contagem de silêncio entre trechos; soltar o comando exatamente no corte
  ainda encerra a fala, mesmo sem áudio residual.
- Priorizar trechos definitivos sobre prévias. Limitar a quatro trechos
  definitivos aguardando; saturação interrompe a captura com aviso e impede
  envio automático incompleto. Preservar texto reconhecido para recuperação.
- A configuração de silêncio recebe 2000 ms; manter a possibilidade existente
  de ajustar esse valor em Áudio. O microfone continua sendo aberto pelo usuário.

## Confirmação e autoria

Ao fim da fala, reconhecer seu áudio definitivo e unir os trechos na ordem.
Com envio automático habilitado, fazer **um único envio** pelo caminho atual,
com ID de submissão estável. Sem envio automático, conservar como rascunho.
Não reenviar automaticamente um POST com resultado incerto.

Resultados parciais não disparam LLM/TTS, ferramentas, memória, aprendizado ou
revisão semântica da fala. Marcar prévias no job e rejeitá-las como prova de
uma mensagem confirmada. Quando houver vários trechos definitivos, verificar
todos os IDs: autoria, origem, fala, ordem, conclusão e ausência de duplicação.
Estender o contrato autenticado de transcrição e a evidência de origem do
envio com ID de fala, índice do trecho, sessão, escopo e tipo parcial/definitivo.
Esses campos acompanham o job até sua consulta; não confiar apenas na junção
de texto feita na interface.
O filtro de possível erro de transcrição continua incidindo uma vez sobre
a mensagem completa, preservando seu texto e sua origem.

Troca de entidade, sala, dia, sessão, conexão ou fim de captura não pode
atribuir um resultado atrasado à conversa atual. Captura descartada não se
torna envio tardio. Falha em um trecho definitivo impede envio automático
da fala inteira; não apresentar uma frase incompleta como sucesso.
Concluir (`stop_capture(True)`) e descartar (`stop_capture(False)`) são atos
distintos. Descarte invalida inclusive um aceite HTTP que chegue depois.
Falha de prévia não reprova um resultado definitivo válido. Ao concluir,
descartar prévias pendentes; o texto final é inserido sem apagar edição
humana ou seleção do rascunho.

## Limites desta etapa

Não agrupar mensagens digitadas já enviadas, substituir modelos ou modificar
identidade, permissões, memória ou treinamentos. Não implementar painel de
fontes por aplicativo nesta etapa. Nenhum novo scheduler, worker ou processo
de inferência paralelo; conservar a fila e os leases do RM existentes.

## Verificação e entrega

Testes com PCM sintético, ASR simulado, transporte controlado e Qt real:
2000 ms de silêncio; retomada antes desse limite; liberação do comando;
limite de 45 s sem envio antecipado; prévias revisadas sem duplicação;
fila limitada; erro e timeout; origem e ordem dos trechos; resposta tardia;
troca de conversa; rascunho preservado; um envio final e nenhuma inferência
de conversa durante a fala. Regressões de áudio, chat, sessões e autoria.
Cobrir silêncio atravessando 45 s, liberação exatamente no corte, prévia
falha seguida de definitivo válido e aceite HTTP após descarte.

Testes offline não comprovam velocidade/qualidade do reconhecimento físico.
Registrar esse limite e conferir no uso real depois de aplicar localmente.
Recarregar código somente após parada cooperativa e reconciliação de trabalhos;
preservar alterações alheias e todos os dados/modelos existentes.

Referências técnicas consultadas: [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
e [WhisperStreaming](https://github.com/ufal/whisper_streaming). A segunda
documenta revisão de hipóteses com áudio novo; não será instalada nem copiada
como um serviço adicional nesta etapa.
