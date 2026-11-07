# Treino único dos sete originais — 23–24/10/2026

Estado confirmado em23/10: **agendado**, registro `fb9a25ae23d14be8`.
Início em **23/10/2026 às23:00**, fim máximo em **24/10/2026 às10:00**,
horário `America/Sao_Paulo`. Substitui o pedido anterior de22/10–23/10;
não é uma autorização diária. O pedido inicial de13h agora corresponde
a uma janela de11h de parede.

## Distribuição e fontes

Sete treinos sequenciais, cada um com até57min e avaliação independente de
até30min: Yi1.5 6B deHoshino/Lilith, Qwen2.5 7B deHoshino/Lilith,
Qwen3.5 9B deHoshino/Lilith e Qwen3.5 4B deAlistair.
São399min de treino,210min de avaliações e51min de reserva para carga,
transições e encerramento. Os limites devalidação/paciência e3epochs
permanecem: terminar antes é permitido, sem repetir dados para ocupar tempo.
Os57min não são uma promessa de57min efetivos de otimização.

Cada treino começa dos pesos HF **originais**. Não há checkpoint ou candidato
como entrada; cada avaliação usa `candidate_from_task` exato0,2,4,6,8,10,12.
Materiais default existentes: `pacote_neural_v3` paraHoshino/Lilith e
`datasets-alistair-seed` paraAlistair. Contexto de treino v2, rank4 e offload
físico medido de cada arquitetura; Yi permanece com `head_cpu1`.
Os corpus não foram alterados nesta rodada para conservar medições comparáveis.
As referências de personalidade já existentes continuam sendo a fonte editorial.

É uma nova rodada **experimental**, não homologada. Reprovações comportamentais
dos candidatos descartados continuam nos relatórios. Elas não são convertidas
em aprovações nem reutilizadas como pesos. O plano personalizado autoriza novos
candidatos dos originais quando suas medições físicas estão limpas. O plano
legado homologado conserva seus gates anteriores. Toda adoção posterior ainda
depende de avaliação e decisão explícita.

## Execução e acompanhamento

O registro vivo é
`laboratorio-local/controle-laboratorio/treinamento-unificado/nights/scheduled-once.json`;
seu histórico está em `schedule-fb9a25ae23d14be8.json` na mesma pasta.
Após iniciar, `session_id` aponta para a sessão existente em `nights/current.json`
e para o histórico durável dos jobs. O índice não é outra fila.

O supervisor da Central já foi iniciado, sem acordar entidades. **PC e Central
precisam permanecer ligados e o PC não pode suspender**. Reinício antes da
partida permite ler o agendamento pendente; reinício durante a tentativa não
autoriza replay. Atraso maior que1min bloqueia a partida; não há remarcação para
outro dia. Jobs/leases ativos ou incertos impedem sobreposição.

Antes da partida, revalidar corpus/base/contexto/código pinados, offload, saída
física exit0/pressure[], tamanho decheckpoint/throughput medidos e disco.
Projeção observada:19.652.436.208bytes de checkpoints, mais5GiB de reserva;
havia aproximadamente73GiB livres. A integridade integral dos quatro conjuntos
originais, reutilizados nas sete combinações por entidade, foi conferida em23/10.

A intenção de início é persistida antes da chamada mutável. Timeout, crash,
intenção incerta ou tarefa já criada não autorizam nova partida automática.
A drenagem cooperativa é solicitada às09:50 para salvar antes das10:00;
checkpoint/saída anormais podem exigir diagnóstico. Não se deve anunciar
conclusão às10:00 sem conferir processo e lease reais.

Acompanhamento Codex:
`acompanhar-treino-nico-de-sete-originais-23-24-10`, somente observação.
Silencioso sem mudança acionável; avisa partida, falha, decisão ou conclusão.
Não inicia/reinicia jobs e se exclui ao terminar/bloquear ou após24/10 às10:30.
O antigo disparo de16/10 continua pausado.

Sem professor, aprovação automática de dados, promoção automática, cloud,
concorrência GPU ou desligamento do computador. Política diária continua
desativada. Os candidatos novos ficam separados da produção.

## Interface personalizada

Laboratório Neural → Treinamento → Sessão noturna →
**Sessão única personalizada · sete originais**.
Permite escolher início/fim, minutos de avaliação, conferir a divisão e os
impedimentos, agendar uma sessão, consultar o registro e cancelar somente
um agendamento pendente. Alterar um campo invalida o preview anterior.
Datas sem fuso explícito são interpretadas emSão Paulo.

As telas mostram o estado salvo e usam o mesmo supervisor, worker e Resource
Manager. Abrir ou verificar o painel não carrega modelos. Candidatos/checkpoints
sem os arquivos de pesos não são oferecidos como executores utilizáveis.

## Limpeza anterior e preservação

Em22/10 foram retirados de uso245 arquivos de adaptadores/checkpoints/aliases
treinados,11.889.976.066bytes, incluindo seleções em uso no PC. Os sete seletores
locais passaram aos originais verificados. Logs, provenance e resultados foram
preservados. A retirada é **recuperável**, na pasta
`laboratorio-local/quarentena-pesos-treinados-20261022`, com manifesto exato;
portanto não equivale a liberar esse espaço nem a purgar definitivamente.
Não houve alteração das memórias ou identidades. A cópia física do console
Xbox não foi apagada nesta operação local.

## Verificações de software

- 84/84 grupos oficiais offline: `/tmp/treino-agendado-oficiais-20261023.log`.
- 353 testes de laboratório: `/tmp/treino-agendado-laboratorio-20261023.log`.
- 21 testes específicos finais do agendador e teste de navegador com transporte
simulado, incluindo bloqueio por pressão/disco, divergência dehash, atraso,
job incerto, timeout sem retry e preservação dos gates do plano legado.
- Painel real conferido com as datas 23/10 às 23h e 24/10 às 10h.

Esses testes verificam software; o treino futuro e sua qualidade só serão
confirmados pelos relatórios físicos da execução.
