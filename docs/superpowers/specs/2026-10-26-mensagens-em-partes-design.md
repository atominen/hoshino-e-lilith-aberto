# Mensagens digitadas em partes — 26/10/2026

Decisão humana: cada envio permanece visível e persistido; Hoshino/Lilith
esperam **2 segundos desde o último envio** e tratam os fragmentos juntos.
Essa escolha foi confirmada durante o ensaio GPU. Executar na instalação
atual, depois do spike e antes do painel sonoro/Minecraft.

Reutilizar o barramento e workers por conversa existentes. O barramento
retém para entrega as mensagens digitadas recentes até a janela de silêncio
se completar; observação sem entrega não altera envelopes, sem novo
scheduler ou segunda fila. O worker combina somente fragmentos consecutivos
da mesma pessoa, entidade, sala/escopo e sessão/dia. Cada ID conserva seu
recibo/desfecho e sua posição no histórico; uma resposta referencia todos
os IDs que efetivamente consumiu.

Não combinar mensagens de entidades entre si, voz já confirmada, conversas
diretas/globais, dias ou sessões diferentes. Comandos explícitos de parada
continuam imediatos pelo caminho existente. Mensagens que chegam durante
trabalho em andamento ficam para o próximo turno e não substituem o objetivo
ativo sem uma correção/interrupção real. Não reexecutar envelopes com efeito
incerto, falha ou processamento em andamento.

A extração usa um snapshot transacional: uma mensagem recém-chegada não pode
herdar a quietude de uma consulta anterior. Na entrega real, uma correção ou
parada já persistida invalida os pedidos anteriores ainda pendentes do mesmo
fio, inclusive além da página de20. Cada envelope superado conserva texto,
ID e recibo `superseded`, ligado à correção; não é execução ou resposta do
LLM. Não retirar estado incerto/em processamento nem cancelar outra sala ou
sessão. Consultar sem entregar não dispara essa barreira.

O caminho atual já tem debounce e batching em TUI/voz, mas força lote1 no
localhub. Estender o caminho local, conservando o comportamento de Discord
e demais canais. Evitar aplicar duas esperas de2s: envelopes que já ficaram
estáveis no barramento podem entrar no lote assim que importados.

Até20 fragmentos por lote; se houver mais, preservar ordem e conteúdo em
lotes subsequentes, sem apagar ou truncar mensagens. Essa é uma escolha
técnica para manter os limites existentes de importação/contexto. Novos
envios prolongam a espera; não usar o teto antigo de3,6s para cortar uma
sequência ainda em andamento. Não é promessa de início de geração em2s
exatos se modelo/RM estiverem ocupados.

Verificar relógio com timestamps reais de recebimento no servidor, mensagens
no limite, retomada antes de2s, bursts com correção, voz/texto misturados,
outra sessão/sala, mensagens durante inferência e recibos reais sem modelo.
Depois rodar regressões e revisar a integração. Memórias, identidades,
modelos, GPU/ASR ativo e preferências alheias são preservados.
