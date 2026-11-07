# Texto contínuo no chat — primeira etapa

Estado: desenho aprovado pelo usuário em 24/10/2026; implementado, verificado e
integrado à instalação local em 25/10/2026.

## Intenção e decisões humanas

Reduzir a espera percebida durante a conversa, mostrando a resposta enquanto
o modelo a gera. O usuário pediu trabalhar por partes, começando pelo mais
simples, e escolheu:

- Texto surgindo continuamente, não por frases completas.
- Manter a posição da leitura quando ele rolar para mensagens antigas.

## Abordagens consideradas

1. Publicar o texto conforme chega do modelo, atualizando uma única mensagem.
   Foi a opção escolhida pelo usuário: oferece acompanhamento contínuo, mas
   exige distinguir geração em andamento de uma resposta concluída.
2. Esperar cada frase completa antes de atualizar o chat. Simplifica o
   aproveitamento do fluxo de voz existente, mas foi preterida pelo usuário.

Não simular digitação de uma resposta já pronta.

## Comportamento proposto

- Uma única bolha cresce durante a geração; a confirmação final substitui a
  prévia correspondente, sem duplicar a mensagem.
- Identificar a prévia como resposta em geração. Falha ou interrupção não pode
  aparecer como conclusão bem-sucedida; o trecho eventualmente mantido deve
  continuar identificado como incompleto.
- Se a leitura estiver no fim, acompanhar o crescimento. Quando o usuário
  subir no histórico, preservar a posição até ele voltar ao fim. Não mudar o
  foco nem o rascunho.
- Respeitar entidade, destinatários, chat direto/global e sessão atual. Texto
  privado de outro fio não pode aparecer no chat global, em outra entidade,
  em pesquisa ou em histórico arquivado.
- Transmitir somente texto destinado à resposta pública. Não mostrar campos
  de raciocínio interno, prompts, argumentos de ferramentas ou saídas privadas.
  Preservar os controles existentes de publicação e de verificação de ações.
- Prévia não é mensagem final, memória consolidada ou prova de execução de
  ferramenta. A persistência final continua no caminho existente.

## Escopo técnico proposto pelo assistente

Reaproveitar a geração incremental de Hoshino/Lilith já existente em
`app/main.py`, com atualização limitada e agrupada de estado para a interface
nativa. Não gravar um registro por token, adicionar um scheduler ou criar uma
segunda geração para produzir a prévia. O fluxo de texto não deve depender de
voz automática habilitada.

Cobrir conversas diretas e globais das entidades com suporte atual a geração
incremental. A integração Xbox de Alistair hoje recusa `stream=True`; adaptar
seu protocolo/app fica para etapa separada, não para uma animação falsa. Até
lá, ele mantém o comportamento atual de resposta completa. Esta divisão foi
incluída na aprovação humana desta primeira etapa.

## Fora desta etapa

Voz simultânea, transcrição incremental, agrupamento de falas/mensagens,
interrupção automática por microfone e painel de fontes sonoras. Não alterar
modelos, pesos, personalidades, memórias, permissões, treino ou configurações
de áudio. Não consumir quota de voz nem reiniciar serviços neste desenho.

## Verificação e preservação

Testar trechos recebidos antes do fim, deduplicação na confirmação, falha e
interrupção, isolamento de destinatário/sessão, exclusão de conteúdo interno,
independência do TTS e rolagem com leitura no fim e fora dele. Ensaios isolados
não devem modificar bancos reais nem ser apresentados como teste de uso real.
Antes de carregar código novo, reconciliar processos e usar fechamento
cooperativo ou isolamento apropriado. Preservar mudanças preexistentes.

Detalhes de identificadores, limites de atualização e testes específicos
pertencem ao plano de implementação, após a aprovação deste desenho.
