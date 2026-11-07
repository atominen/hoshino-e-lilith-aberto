# Acompanhamento somente leitura — treino único de 23–24/10/2026

Agendamento observado: `fb9a25ae23d14be8`.
Janela autorizada:23/10 às23:00–24/10 às10:00, `America/Sao_Paulo`.

## Impedimento observado às23:04–23:07 de23/10

O treino não iniciou. O arquivo `scheduled-once.json` e o histórico
`schedule-fb9a25ae23d14be8.json` continuam `state=scheduled`, com
`session_id=null`. Esses registros originais não foram alterados pelo monitor.

Evidências reconciliadas:

- `nights/current.json` aponta para `ada753feed6048fb`, `completed`, não para
  uma sessão criada pelo agendamento observado. Os demais registros de sessão
  também estão encerrados; nenhum novo ID foi encontrado.
- 59 arquivos de jobs de treinamento foram conferidos: nenhum em estado
  `started`, `running`, `cancel_requested` ou `queued`.
- Nenhum job compartilhado queued/running nem lease ativo no RM.
- Nenhum processo da Central, runner das entidades ou supervisor de treinamento
  foi encontrado nas verificações. O endpoint loopback salvo da Central recusou
  conexão (`ConnectionRefusedError`).
- Hoshino/Lilith estão sleeping, Alistair offline. Não foram acordados.

O código existente `laboratorio/sessao_personalizada.py:tick` recusa a partida
quando `now > starts_at +60s`, com “Janela de partida perdida; sem reagendamento”.
Essa tolerância já havia vencido na primeira verificação. Não é possível
determinar apenas desta inspeção o instante/autor do fechamento anterior da
Central. Sua indisponibilidade atual e a ausência de sessão são confirmadas.

## Conduta e resultado

Nenhuma tentativa de `/start`, execução de `tick`, reinício de serviço,
reprogramação, cancelamento de job ou alteração de código/parâmetros foi feita.
O monitor não transforma `scheduled` em `blocked`: o impedimento acima é sua
conclusão de observação, não uma mudança inventada no estado do supervisor.

Não existem resultados desta rodada para avaliar loss, validação/holdout/base,
comportamento, pressão térmica ou qualidade de candidatos. Nenhum sucesso foi
inferido de registros de sessões anteriores.

O acompanhamento `acompanhar-treino-nico-de-sete-originais-23-24-10` foi
excluído pelo `automation_update`, com confirmação `deleteStatus=deleted`,
ao encerrar este impedimento, conforme sua instrução original. Essa exclusão
não apagou o agendamento, relatórios, evidências ou processos.
Uma nova partida/reprogramação depende de nova orientação humana; este monitor
não possui autoridade para iniciar atrasado ou escolher outro horário.
