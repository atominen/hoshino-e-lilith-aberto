# Voz progressiva e percepção da própria fala — versão básica

Estado: desenho aprovado pelo usuário em 25/10/2026, implementado, verificado
e carregado na instalação atual. Resultados no
[relatório de entrega](../../VOZ_PROGRESSIVA_20261025.md).

## Intenção e decisões humanas

A voz deve acompanhar a resposta que já aparece continuamente no chat.
Hoshino e Lilith precisam perceber a reprodução real para coordenar suas
falas conforme a conversa. Uma nova mensagem, por si só, não corta a fala;
um pedido humano de interrupção ou uma decisão contextual pode encerrá-la.

O usuário escolheu manter a integração na instalação atual e usar uma
solução básica com seus fones, sem desenvolver cancelamento de ruído/eco.

## Abordagens

- **Integração básica com fones, escolhida pelo usuário:** aproveitar as
  frases estáveis já produzidas, o player e os workers existentes. Capturar
  e transcrever durante a reprodução, sem descartar uma fala apenas porque
  a entidade também está falando. Não adicionar ambientes ou dependências.
- **Cancelamento de eco do sistema:** ajudaria com alto-falantes, mas o
  usuário dispensou essa ampliação nesta etapa.
- **Cancelamento próprio no app:** acrescentaria desenvolvimento e
  calibração; não faz parte do recorte básico escolhido.

## Comportamento

- Começar a voz na primeira frase completa e validada; continuar com as
  próximas enquanto o LLM ainda gera a resposta. Reutilizar as vozes e
  provedores configurados, sem uma segunda geração do texto.
- Atender chat direto e global respeitando autoria, destinatários e sessão.
  Confirmar a resposta final sem falar de novo os trechos já reproduzidos.
- Manter a escuta disponível durante a fala no modo Detecção; o modo Comando
  só captura enquanto acionado. Abrir o microfone ou enviar uma mensagem
  comum não cancela automaticamente o áudio atual.
- Disponibilizar às entidades quem está falando, qual frase está em
  reprodução, quais frases terminaram e se houve interrupção ou falha.
  Áudio sintetizado não conta como áudio reproduzido nem prova de audição.
- Aproveitar o player único para organizar falas pendentes sem alternância
  fixa. A entidade pode consultar a situação e decidir aguardar ou encerrar
  a própria fala; preservar pedidos explícitos de parada feitos pelo usuário.
- A decisão contextual usa o modelo e os controles existentes; não criar
  falas prontas, decisões a cada palavra ou um novo ciclo de inferência.
- Estados ausentes ou antigos não podem afirmar que alguém ainda está
  falando. Falhas ficam registradas e não disparam repetição automática.

## Limites e verificação

Esta etapa não inclui transcrição palavra a palavra, agrupamento de mensagens,
painel por aplicativo, mudança de modelos/personalidades, gravação permanente
do microfone ou autorização de novos testes com quota de voz.

Testar voz antes do fim da geração, ordem/deduplicação, isolamento de
direto/global, microfone durante reprodução, mensagem comum sem corte,
parada explícita, estados reais de início/fim/falha e reconexão sem replay.
ASR e síntese precisam avançar sem um bloquear o outro, respeitando os
recursos e limites existentes. Usar testes offline com áudio sintético.

Trabalhar na instalação atual, preservando alterações preexistentes e dados.
Antes de editar/carregar módulos em uso, reconciliar jobs/processos/leases
e encerrar a Central cooperativamente, sem matar processos por nome/porta.
