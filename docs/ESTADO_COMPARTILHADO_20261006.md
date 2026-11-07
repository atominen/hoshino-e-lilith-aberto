# Estado factual compartilhado e planejamento de capacidades — 06/10/2026

Etapa posterior a [áudio central](AUDIO_CENTRAL_20261006.md). O material novo foi
[arquivado integralmente](planejamento/conversa_cloud_20261006_referencia.txt),
com SHA-256 `25c85497fee2251a25b652e147d371fcbee726759e6331b072de88b305d76b07`,
igual ao original. Conversas e sugestões dentro do anexo são referências, não
autorizações para contratar servidores, pagar ou transmitir dados.

## O que está integrado

`app/core/world_state.py` mantém observações na infraestrutura compartilhada,
sem copiar bancos mentais, personalidade ou memórias das entidades. A central
inicia um único coletor barato. Hoshino/Lilith reutilizam esse retrato no loop
de percepção, mantendo suas avaliações e experiências em seus próprios bancos.
Alistair recebe um resumo factual na consulta de estado, sem pensar por elas.
Os três LLMs existentes continuam separados e no PC principal.

O coletor observa janela em foco, mídia, ociosidade de entrada, carga, RAM, disco,
CPU, presença dos processos, trabalhos, leases, atividade do áudio e residência
dos modelos. Consulta apenas `/api/ps` dos três daemons em `127.0.0.1`: não carrega
LLMs, não gera texto, não liga microfone e não consulta provedores cloud.
Títulos de janela são observações locais, nunca comandos a executar.

Cada fato traz origem, instante de observação, validade e confiança. A coleta
usual ocorre a cada dez segundos e usa validade de trinta segundos. Ausência de
leitura é desconhecida, não zero, ausência física ou sucesso vazio. Fatos vencidos,
confiança zero e origens discordantes são excluídos dos valores utilizados.
O snapshot bruto preserva essas diferenças para diagnóstico.

Eventos registram linha de base e mudanças, sem transformar variação de carga
ou ociosidade em novidade cognitiva. O histórico retém até 5.000 eventos. A
consulta paginada oferece `next_event_id`; `last_event_id` é o último evento
global e não deve ser usado para saltar uma página incompleta. `event_gap`
indica que o cursor ficou atrás do histórico retido. Eventos são históricos,
não prova de que um fato continua válido nem gatilho automático de inferência.

Consultas ao módulo não criam banco nem coletam dispositivos. Sem coletor vivo,
a interface individual usa sua sonda local existente. A central encerra o
coletor antes do áudio; falha de telemetria não impede a drenagem. Não existe
rota HTTP de publicação de fatos. `/api/world`, `/api/routing` e `/api/state`
permanecem autenticadas no endereço local.

## Erros corrigidos na interpretação

- A última janela da lista de janelas abertas não substitui uma janela em foco
  que não pôde ser identificada.
- Inicialização do processo e mensagem entre entidades não contam como interação
  humana. Mensagens entre entidades também não acionam o aviso humano de sono.
- Presença é uma interpretação privada com três estados. Entrada recente ou
  interação recente sugerem presença; inatividade sugere ausência; sem evidência
  fica desconhecida. Nenhum desses casos comprova presença física ou identidade.
- Presença desconhecida não ativa diretivas exclusivas de ausência. Os textos
  de diagnóstico não afirmam que alguém saiu fisicamente do computador.
- Perda da leitura do foco encerra a sessão anterior; recuperação é uma nova
  linha de base, não uma novidade inventada.
- A abertura simultânea dos bancos compartilhados podia falhar na inicialização
  de WAL. O helper `sqlite_runtime.py` fecha conexões que falharam e tenta novamente
  apenas erros BUSY/LOCKED, com prazo limitado. Canal, jobs, recursos e novos
  bancos usam essa inicialização; esquemas e mensagens existentes são preservados.

## Exatamente quatro destinos, ainda sem execução remota

| Destino | Situação atual | Escopo preparado |
| --- | --- | --- |
| PC principal | Ativo, fallback obrigatório | LLM, TTS, ASR, imagem |
| Athlon | Desativado | Proposta de LLM de Alistair |
| Cloud leve | Desativada | LLM, TTS, ASR, imagem; pelo menos 24 GiB VRAM / 32 GiB RAM |
| Cloud normal | Desativada | LLM, TTS, ASR, imagem; pelo menos 48 GiB VRAM / 64 GiB RAM |

Alistair continua sem TTS. `compartilhado/config/capacidades.json` e
`app/core/capability_router.py` preparam somente planejamento. O executor atual
não foi substituído: nenhuma proposta muda destino, provisiona máquina, abre
endpoint remoto, copia contexto ou acessa a mente de outra entidade. Mesmo
configuração habilitada em um teste continua com `execution_migrated=false`.
Não há terceiro nível cloud nem quarto LLM de standby.

Propostas exigem sinal de saúde recente e previsão baseada em medição que inclua
fila e carregamento. Para sair do local sem contenção observada é necessária
comparação local recente; quando há comparação, exige-se ganho superior a 20%.
Residência aquecida apenas desempata: não reduz artificialmente a duração medida.
Cloud leve/local têm preferência sobre normal entre alternativas elegíveis.
Isso é um planejador conservador, não um scheduler distribuído, mecanismo completo
de afinidade nem garantia de desempenho. Telemetria de latência remota ainda não
está conectada à execução.

## Orçamento: preparação, não proteção de uma conta real

Tetos copiados da parte final do rascunho: R$ 24/dia global, limite operacional
R$ 22/dia, preferência de leve abaixo de R$ 1/h, leve até R$ 1,50/h e normal até
R$ 2,30/h. São política proposta, **não preços atuais de provedores**.
RunPod e gpuLabs aparecem como fornecedores configurados, sem adapters conectados.

O planejador rejeita câmbio sem origem ou com mais de uma hora, oferta com mais
de dois minutos, custos associados não confirmados, memória insuficiente ou
contabilidade diária desconhecida. Considera pelo menos vinte minutos de período
estimado; não promete faturamento apenas pelo tempo de processamento.

`BudgetLedger` oferece reservas locais atômicas e conservadoras em milionésimos
de real, compartilhadas pelos níveis e fornecedores, com dia em São Paulo.
Liquidação é idempotente; custo real acima da previsão permanece registrado e
impede novas reservas quando excede o teto. Cancelamento não apaga custo liquidado.
**O ledger não lê saldo/fatura, não cobra, não desliga servidores e não garante
o teto real.** Ainda faltam reconciliação com o provedor, taxas, duração que cruza
meia-noite e confirmação de término/armazenamento faturado. Não existe rota da
central para reservar ou gastar dinheiro.

## Verificação e próximos limites

Os **27 grupos da suíte passaram**, incluindo **61 regressões novas** nesta etapa.
Os testes novos cobrem validade, conflito, concorrência, paginação, fallback,
interpretações independentes, orçamento e limites decimais. A suíte completa usa
diretórios temporários, sem modelos ou memórias reais. O controle de concorrência
do planejador foi repetido vinte vezes. Coleta real de treze campos e consultas
HTTP foram verificadas, sem criar conversas de teste nas entidades.
Veja [registro da verificação](verificacao_estado_compartilhado_20261006.json).

A central foi encerrada por drenagem e reiniciada; Alistair retomou o standby.
A interface mostra origem, idade, desconhecidos e destinos desativados. Hoshino
e Lilith não foram acordadas nem receberam mensagens sintéticas nesta etapa.

Ainda faltam: executor/RPC autenticado no Athlon com benchmarks LAN, integração
cloud real e autoridade específica para contratação/transmissão, scheduler por
prioridade e quotas completas de RAM/CPU, relações/valores evolutivos, primeiro
despertar não roteirizado e o benchmark completo `aa`. Discord/Minecraft ao vivo,
microfone com fala humana e aprovação subjetiva das vozes continuam pendentes;
os testes offline não aprovam esses cenários.
