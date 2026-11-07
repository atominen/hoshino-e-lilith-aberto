# Admissão de entidades por VRAM e ensaio Minecraft4B

> Execução direta nesta conversa, conforme preferência humana já expressa.

**Objetivo:** permitir somente uma entidade ativa enquanto não houver uma GPU
de classe16GiB ou superior, e medir o4B emMinecraft sem resetar o progresso.
**Arquitetura:** sonda física independente do teto atual de8GiB doRM; admissão
atômica por lock compartilhado na Central e entradas diretas. Manter oRM e suas
reservas: hardware elegível não habilita inferência concorrente automaticamente.
**Tecnologias:** Python, sysfsAMD, consulta localNVIDIA, flock e testes offline.
**Especificação:** pedido humano de28/10 nesta conversa; Hoshino, Lilith e
Alistair contam, inclusive em inicialização/drenagem e destino remoto.

**Execução encerrada:** trava ativa,97/97grupos offline, ensaio4B registrado
com contexto16.000 após instrução humana posterior. Objetivo da picareta não
concluído em12decisões. Ver [desfecho e evidências](../../ADMISSAO_16GB_E_MINECRAFT_4B_20261028.md).

## Restrições e revisão

- Uma única placa deve satisfazer o limite; não somar placas, RAM ou swap.
- Capacidade desconhecida permite uma entidade, bloqueia a segunda.
- Admitir a reserva de até64MiB dos drivers em placas nominais de16GiB;
  não arredondar12GiB ou15GiB para16GiB.
- Presença expirada não permite ignorar lock real de outro runner.
- Corridas de início não podem admitir duas entidades em GPU menor.
- Não matar processos existentes nem repetir efeitos incertos. Todas as três
  estão dormindo e jobs/leases vazios na conferência anterior à implementação.
- O ensaio4B é temporário e identificado; preservar aliases, pesos e dados.

## Tarefa1 — trava de execução

- [x] Acrescentar testes em`test_entidades_16gb.py` e regressão de restauração
  em`laboratorio/tests/test_noite_supervisor.py`; confirmar vermelho/verde.
- [x] Sonda`dedicated_capacity()` em`app/core/gpu_metrics.py`, sem alterar
  `snapshot()` nem o teto de inferência já validado.
- [x] Módulo`app/core/entity_admission.py`: verificação por destino de entidade,
  locks reais, presença e processos geridos, sob lock de admissão comum.
- [x] Integrar`Supervisor.start`, `entity_runner` e`alistair_runner`; entrada
  direta de`main.py` encaminha ao runner. Mostrar recusa clara na Central.
- [x] Verificar testes novos, grupos afetados e suíte offline completa.

## Tarefa2 — ensaio4B e entrega

- [x] Conferir ponte, mundo, inventário e ausência de efeito pendente.
- [x] Usar alias4B local verificado e decisões estruturadas existentes, um
  executor por vez. Registrar condição inicial e limitar o ensaio; sem reset,
  novos recursos dados pelo condutor ou roteiro atribuído aoLLM.
- [x] Medir latência, ações, erros, recuperação, recursos e resultado; manter
  assistência explícita. Não confundir tentativa com aprovação.
- [x] Atualizar relatório/índice e carregar a trava na Central cooperativamente.
