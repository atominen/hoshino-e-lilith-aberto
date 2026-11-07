# Verificação final e roteiro de teste — 22/10/2026

## Resultado operacional

**Preparação para teste básico; desafio gráfico completo ainda bloqueado.**
Esta rodada verifica e organiza. Não iniciou inferência, não acordou entidades,
não reiniciou a Central, não instalou dependências nem executou a simulação.
O diagnóstico OpenGL apenas consultou capacidades do desktop.

Checkout observado: HEAD `6441a7c`, com alterações locais preexistentes e não
publicadas. Esse commit sozinho não representa o código testado. Relatórios
anteriores são evidências datadas, não confirmação de processos/configurações
em execução. Não restaurar arquivos antigos para reproduzir um relatório.

## Ordem de leitura

1. **Este roteiro:** prontidão, sequência de ensaio e bloqueios atuais.
2. [Comandos e continuidade](COMANDOS_DURAVEIS_E_CONTINUIDADE_20261022.md):
   recibos, espera de até 300 segundos acumulados por turno e limites de retomada.
3. [Memória e caderno visual](REFINAMENTO_COGNITIVO_E_OFICINA_20261022.md) e
   [audiência/prioridade](AUDIENCIA_E_PRIORIDADE_MEMORIAS_20261022.md): o que mudou
   e o que ainda precisa de avaliação humana.
4. [Contrato do desafio](DESAFIO_AUTONOMO_BURACO_NEGRO_20261013.md): requisitos
   C1–C9, autoria independente e critérios. Não entregar a nota do avaliador
   como uma dica à entidade.
5. [Preservação](POLITICA_PRESERVACAO_PROJETO.md) e
   [escopo](../ESCOPO_CONGELADO.md): limites para alterações e operação.

Os relatórios de 13/10 e das primeiras rodadas de 22/10 permanecem intactos como
histórico. Seus números 82/83 grupos não são a contagem da suíte atual.

## Verificações desta rodada

Observação do host em **22/10/2026, 22:25 −03:00**. Capacidade livre é uma
fotografia, não uma reserva: conferir novamente antes de executar.

| Item | Evidência observada | Consequência |
|---|---|---|
| Compilação no host | g++ 13.3.0; CMake 3.28.3 | Ferramentas instaladas; não substitui build pela entidade |
| Bibliotecas | GLFW 3.3.10; GLEW 2.2.0; GLM 0.9.9.8 via pkg-config | Dependências encontradas; não foram reinstaladas |
| Desktop gráfico | RX 6650 XT, aceleração direta, Mesa 25.2.8, OpenGL 4.6, VRAM dedicada 8192 MB | Suporte do host confirmado, não do executor isolado |
| Isolamento dos comandos | Probe de namespace com `--dev /dev`: `/dev/dri` ausente | Sem liberação do caminho GPU para o desafio |
| Oficina restrita | Código monta `/dev` privado e `/tmp` temporário | Dispositivo gráfico/socket do desktop não podem ser presumidos disponíveis |
| Memória/disco | Cerca de 23 GiB MemAvailable; 75 GiB livres no volume; 91% ocupado | Não usar swap como margem e não iniciar downloads/treinos extras |
| Central, porta padrão | Nenhum listener TCP em 8769 no momento da consulta | Não há confirmação de Central carregada com as correções; outras portas não foram varridas |
| Estado das entidades/leases | Não consultado por API ativa nesta rodada | Não equivale a declarar todos os workers livres |
| Documentação | Após a organização, 209 links locais verificados em sete guias de entrada, nenhum ausente | Links remotos/âncoras e arquivos privados citados em prosa não foram certificados |

A consulta OpenGL não executou compute shader nem benchmark. A correção futura
do caminho gráfico precisa integrar recursos/leases e encerramento owned;
não basta expor todo `/dev`, desligar o isolamento ou disputar GPU com inferência.

### Suíte isolada

Reexecução integral concluída nesta rodada: **84/84 grupos aprovados**, processo
com saída zero e desfecho do log conferido em
`/tmp/preflight-teste-suite-20261022.log`. `git diff --check` sem erros.
A suíte usa estado descartável e não valida personalidade, áudio físico, Xbox,
inferência real ou renderização da simulação. A suíte do laboratório é separada
e não foi reexecutada nesta preparação sem mudanças de treinamento.

## Teste básico supervisionado — antes do desafio

1. Abrir normalmente a Central atual e conferir ausência de outra instância.
   Se houver uma sessão antiga, salvar rascunhos e encerrá-la pela própria UI,
   sem matar por nome/porta. A organização dos documentos não faz esse reinício.
2. Escolher **uma entidade de cada vez**. Registrar nome, executor realmente
   selecionado, configuração/contexto e horário. Não trocar modelos para
   fabricar um resultado melhor no meio da tentativa.
3. Usar o **chat direto** para o ensaio independente. O global transmite às
   entidades acordadas e pode contaminar a independência entre Hoshino/Lilith.
4. Fazer um pequeno pedido autoral de criação/execução/leitura na oficina,
   sem código pronto fornecido pelo avaliador. Exemplo de pedido de diagnóstico:
   “Crie um pequeno programa C++ na sua oficina, compile, execute, confira o
   resultado e entregue os fontes e as instruções de execução. Diga o que foi
   realmente testado e qualquer impedimento.” Isso é um smoke de infraestrutura,
   **não** uma versão reduzida aprovada do buraco negro.
5. Durante a execução, enviar uma pergunta curta não relacionada. Conferir se
   ela é preservada na fila, respondida na sua vez e não substitui o objetivo.
   Não esperar resposta simultânea: o fluxo comum continua serializado.
6. Conferir arquivos reais, autoria, recibo do processo, código de saída e
   etapa seguinte. Se o comando ficar pendente, a espera cooperativa tem teto
   de cinco minutos por turno; ultrapassá-lo não autoriza replay.
7. Exercitar um rascunho de diagrama pela ferramenta existente e inspecionar
   sua marca de hipótese, sem inventar referências. Diagrama não prova cálculo
   numérico e não deve ser gravado como fato confirmado.

Não limpar memórias para testar, não inserir dados privados fictícios para
“provar” privacidade, não mandar registros de diagnóstico ao professor/treino.
Dados do ensaio devem ser identificados como teste, não convivência espontânea.

## Gate do desafio completo

Antes de transmitir o brief do buraco negro, faltam:

- Caminho gráfico isolado, com dispositivo/contexto acessível e teste de
  apresentação/captura, sob Resource Manager e sem GPU concorrente não validada.
- Confirmação de processos/leases e de uma única entidade executando a tentativa.
- Diretório real de cada tentativa, orçamento de tempo/tentativas e critérios
  de resolução/FPS/precisão definidos **antes** da execução, sem reduzir depois
  para declarar sucesso.
- Confirmação de que a entidade fará o código e suas correções, enquanto o
  avaliador apenas observa infraestrutura/evidência. Tentativas sequenciais,
  sem compartilhar solução entre elas.

Mesmo com esses gates, o controlador tem limites de ações/progresso/espera e
não garante terminar um projeto inteiro sem intervenção. Retomada depois de
reinício ou além do orçamento ainda é pendência, não uma função homologada.

## Como registrar o resultado

Usar IDs reais da conversa/tarefa/job, horários e caminhos gerados, junto de
fontes, erros e recibos. Nunca preencher medições ausentes com estimativas.
Classificar cada tentativa separadamente como **APROVADA, PARCIAL, FALHOU,
BLOQUEADA ou NÃO INICIADA**, conforme o contrato do desafio. Aprovação do
smoke básico não satisfaz C2/C3/C4/C5/C6/C7 do desafio.

Não há execução humana/LLM do novo desafio registrada por esta preparação.
