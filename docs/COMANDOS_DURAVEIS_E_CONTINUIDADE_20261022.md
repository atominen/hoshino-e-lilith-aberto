# Comandos duráveis e continuidade — 22/10/2026

## Escopo aplicado

Correções no executor e no controlador existentes, sem nova fila, serviço ou
scheduler. A Central não foi reiniciada; processos já carregados só recebem
essas alterações quando forem reiniciados normalmente. Nenhum modelo, memória,
configuração ativa ou treinamento foi alterado. O desafio do buraco negro não
foi iniciado, nem foi fornecida sua solução às entidades.

## Comandos em segundo plano

- Um observador pequeno, somente com biblioteca padrão, espera o processo real
  e salva atomicamente seu código de saída. O comando continua usando o mesmo
  isolamento, ambiente e grupo de processos do executor existente.
- O recibo é vinculado ao identificador, PID, token de execução, entidade e raiz
  de runtime. Logs não determinam o código de saída. Essa vinculação previne
  confusão entre execuções; não constitui uma barreira contra um programa com
  acesso de escrita ao próprio runtime.
- O timeout da espera síncrona promove a mesma execução a job; não a repete.
  O observador pode registrar seu desfecho mesmo se a Central já não estiver
  esperando. A leitura posterior depende dos arquivos, não de um handle Python
  do processo antigo.
- Processos são recolhidos, sem interpretar um zumbi como trabalho ativo.
  Falta de recibo, observador interrompido ou resultado cancelado continuam
  incertos. Jobs antigos sem recibo não são promovidos artificialmente a sucesso.
- Código zero confirma somente término do comando. Não certifica correção
  científica, qualidade visual, satisfação dos requisitos ou ausência de bugs.

## Continuidade

- A tarefa conserva o ID exato do job que deverá consultar. Essa consulta vem
  antes das operações dependentes, inclusive dentro do mesmo marco.
- O controlador monta o argumento da consulta sem pedir ao LLM para inventar
  um ID. Recibo de outro job não conclui a operação vinculada. Replanejamento
  não descarta essa consulta para repetir o comando original.
- Consultas vinculadas que ainda estão pendentes podem esperar cooperativamente
  no próprio turno, com até **300 segundos acumulados de espera por turno**.
  A espera não consome chamadas adicionais ao modelo nem repete o comando.
  Ao observar término, o controlador segue a próxima etapa. Cancelamento,
  revisão humana, drenagem, troca de tarefa e estados incertos continuam sendo
  respeitados; a espera não mata o processo por conta própria.
- Esgotado esse orçamento, a etapa permanece registrada e a execução do turno
  é pausada. Não foi implementada retomada automática depois de reiniciar o app
  ou uma promessa de execução ilimitada. O limite de ações e o detector de falta
  de progresso continuam ativos.
- Pergunta lateral sem nova tarefa não pausa nem se incorpora ao objetivo
  existente. Nova tarefa explícita, pedido de pausa/cancelamento e restrições
  humanas continuam distintos. Isso não transforma a fila em conversa paralela
  instantânea: mensagens comuns ainda podem aguardar sua vez.

## Evidências offline

`test_comandos_duraveis`: **19 testes**, incluindo processos curtos reais em
diretórios descartáveis, saída zero/não zero, timeout com efeito único,
recibo ausente/divergente, falha de lançamento, leitura durável e isolamento
da conversa lateral, corrida entre recibo/PID e comandos multilinha.
O teste do ciclo da UI usa ferramentas/modelo substituídos
por fixtures e comprova a sequência comando → consulta → próxima etapa, sem
nova mensagem humana. Não comprova capacidade de planejamento de um LLM real.

- Contratos: `/tmp/comandos-duraveis-contratos-20261022.log`.
- Suíte geral isolada: `/tmp/comandos-duraveis-suite-20261022.log`.

Resultado: **84/84 grupos da suíte geral aprovados**, além da reexecução dos
**19/19 testes específicos** após os últimos ajustes e dos **19/19 contratos
de consolidação**. `git diff --check` sem erros de whitespace.

## Pendências que não foram mascaradas

1. Executor gráfico com GPU controlada, arbitragem pelo Resource Manager e
   apresentação/captura da janela, mantendo o isolamento entre entidades.
2. Ensaio real supervisionado de criação, compilação, renderização e avaliação
   visual/científica; biblioteca instalada não prova que o fluxo completo funciona.
3. Continuidade além dos limites do turno e após reinício, com correlação ao
   contexto original e sem mensagens humanas sintéticas nem replay de efeitos.

O teste gráfico/autônomo completo continua sendo uma etapa posterior, não uma
capacidade declarada pronta por esta rodada de testes offline.
