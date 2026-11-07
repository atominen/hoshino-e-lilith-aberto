# Áudio integrado ao aplicativo único — 26/10/2026

Decisão humana: fazer o conjunto diretamente, na instalação atual, reunido
na Central. Não exigir execução de painel, transcritor ou capturadores à
parte. Preservar modelos, identidades, memórias e dados nas localizações
existentes. Uma abertura do app supervisiona os serviços internos necessários;
não significa carregar todos os pesos na GPU nem fundir as identidades.

Escolha de implementação: usar o AudioService compartilhado existente, com
um gerenciador de escuta por fonte no mesmo backend. Alternativas descartadas:
um Whisper por canal/entidade duplica RAM; somente um monitor geral não permite
atribuir som a um aplicativo. Isolar streams com PipeWire, copiando suas portas
para fontes virtuais pertencentes à Central, sem mover a reprodução original,
alterar a saída padrão ou interceptar aplicativos diferentes.

O painel Áudio → Fontes e atenção lista entradas reais, mistura da saída e
streams de aplicativos. Hoshino/Lilith/Alistair escolhem fontes e atenção
individual (ativa/passiva/ignorar). A autorização ambient existente permanece
válida. Consultas não iniciam captura. Seleção explícita inicia; ignorar e
fechar removem a assinatura e encerram a captura quando não há ouvintes.
Fonte desaparecida fica indisponível: nunca migrar silenciosamente para o
microfone padrão ou para outro app. Identificar stream por object.serial e
confirmar PID/starttime, não por nome ou índice reciclável.

Capturar cada fonte uma vez; transcrever um trecho uma vez e distribuir
observações somente às entidades assinantes autorizadas. Reutilizar o ASR
CPU ativo e sua fila/RM, com prioridade inferior à fala dirigida à Central.
Limites: até4 fontes simultâneas, trecho PCM até45s, no máximo uma solicitação
pendente por fonte; sobrecarga é indisponibilidade explícita, não fila infinita.
Buffers recentes limitados, voláteis; PCM temporário apagado ao concluir.
Áudio de programas é observação de origem conhecida e pessoa desconhecida,
nunca fala do usuário nem instrução confiável. Sem gravar continuamente em
disco, voz cloud, identificação biométrica ou alteração de memórias.

Os runners usam cliente autenticado da mesma Central. Ferramentas de escuta
consultam/alteram o gerenciador real; o ciclo existente consulta observações
com cursor. Não criar segundo scheduler ou um estado fictício só na UI.
No aplicativo supervisionado, Central indisponível não dispara transcritor
privado de fallback. O caminho legado fora da Central continua compatível.

Encerramento: cancelar transcrições próprias, fechar capturas e loopbacks
por handles/PIDs próprios e confirmar término. Helpers existentes com
PDEATHSIG evitam órfãos. Erro de captura não escolhe outra fonte nem repete
efeito incerto. Estado do painel distingue solicitado, capturando e falha.

Verificar seleção, isolamento, assinatura por entidade, revogação, fonte
removida/ID reciclado, backlog, cancelamento, desligamento e transcrição que
termina após o canal fechar. Ensaio local com áudio sintético para provar
isolamento, sem capturar conversa humana ou enviar mensagem fictícia.

Depois: conferir/corrigir ferramentas de bancada e forno da ponte Minecraft,
iniciar a Central uma vez e executar o teste autorizado da Lilith no mundo
LAN1.16.1 porta35229. Comandos/ações devem ser escolhidos pelo LLM; progressão
normal até24 diamantes e quatro peças fabricadas/equipadas, com recibos.
Se o mundo ficar indisponível, registrar o bloqueio sem inventar aprovação.
