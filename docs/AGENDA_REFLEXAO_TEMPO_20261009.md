# Agenda, reflexão e intervalos de iniciativa — 09/10/2026

## Escopo

Continuação incremental da Fase 2 do plano cognitivo, após histórico, sessões diárias e continuidade observada. Não conclui a especificação inteira. Código de referência `f23ba0d721fac6cb53534b55fcc5b48547e1dec8`, com muitas alterações anteriores preservadas; o commit não representa sozinho a árvore atual.

Sem modelos novos/trocados, inferência, wake, restart de serviços, quota externa, cloud, concorrência GPU, mudanças de personalidade ou migração mental. Reutilizados SQLite, relógio configurado de `history`, diagnóstico e limitadores existentes; não há outro scheduler, serviço de relógio ou banco.

## Consumidores localizados antes de alterar

| Área | Escritor/leitor e consumidores |
|---|---|
| Agenda | `tools/agenda.py`: ferramentas, parser, listagem, vencimentos, entrega e reagendamento; chamado pelo dispatcher, `main`, `autonomy` e `situation` |
| Objetivos | Agenda escreve datas; `situation._pendencias` calcula janela de seis horas, `strategies.proximo_objetivo_novo` e reflexão noturna ordenam criação; outros leitores consultam IDs/estado, não datas |
| Reflexões | `mind/reflection.py` conta episódios e determina intervalo/material; `night_reflection.py` filtra o dia e salva conclusões. A Central inspeciona por rowid, manutenção usa IDs; não depende de comparação textual dessas datas |
| Iniciativa | Guardas de `core/kernel.py` chamadas por `deliberar`; API legada `autonomy.pode_falar` preservada. `main` alimenta estado, cota da hora e horários de interação/fala/ação/visão |
| Eventos do dia | `main.registrar_evento` escreve JSONL; `night_reflection._eventos_arquivo_do_dia` lê. Arquivo usa data local, registro novo usa UTC |
| Conexão mental | `bd.conexao` e conexão existente da agenda registram função de comparação, sem DDL ou alteração de dados |

O inventário não autoriza converter `bd.agora` globalmente. Episódios, propriedades, memórias, relações e outros consumidores ainda precisam de revisão coordenada.

## Correções e contratos

### 1. Agenda compara instantes, não strings

Reproduzido: um prazo futuro local aparecia vencido, enquanto um anúncio com offset positivo não aparecia na ordem correta. Ordenar ISO textual não ordena instantes quando se misturam UTC, offsets e legado sem fuso.

`history.timestamp_epoch` retorna instante ou `None`. A função SQLite `project_epoch` é registrada nas conexões existentes; entradas inválidas retornam NULL, nunca "muito antigas". A função não escreve nem chama diagnóstico dentro da consulta, evitando reentrância de SQLite.

Vencimentos/ordenação da agenda, janela de seis horas e ordenação de objetivos passam a usar instantes. Novas datas de criação/prazo/disparo/reagendamento da agenda são UTC explícito. Listagem mostra horário no fuso configurado; parser continua retornando datetime local sem offset por compatibilidade com seu contrato antigo, inclusive quando recebe `agora` em UTC.

Datas legadas ingênuas usam o fuso configurado **somente como aproximação de cálculo**; sua origem temporal não se torna confirmada. Nenhuma linha antiga é reescrita durante leitura.

### 2. Recorrência inválida não trava nem parece entregue

Reproduzidos loop em `intervalo:0` e exceção em regra ilegível. Recorrências agora calculam saltos de uma vez, sem percorrer cada minuto perdido durante anos. Diário/semanal preservam horário do calendário local; intervalo usa duração em UTC. Regra desconhecida/intervalo menor que um minuto é recusado.

Entrega com horário/regra inválido retorna falha explícita, preservando `pending`, `due_at` e `fired_at`. O registro continua visível na listagem, mas não dispara fala automática a cada tick. Datas/regra inválidas produzem `clock.unreliable` no diagnóstico atual sem incluir texto do timestamp, chave ou credencial.

Não foram redesenhados recibos de entrega, identidade dos lembretes ou autorização de ferramentas. Marcar entrega continua o contrato existente de agenda, não prova de que alguém ouviu áudio.

### 3. Reflexão usa evidência temporal válida

Reproduzidos escolha errada da última reflexão, contagem incorreta de episódios e `TypeError` ao subtrair aware/naive. Agora as consultas comparam instantes e preservam IDs, conteúdo, fonte, tipo e evidências. Registros futuros/sem data válida não viram evidência nova por comparação lexicográfica.

Sem reflexão anterior, permanece o contrato de ausência de cooldown. Com reflexão de data inválida/futura, a duração não é confirmada: a guarda retorna zero, não um intervalo enorme que libera inferência. Reflexão inválida não é escondida por coexistir com uma antiga válida; a iniciativa fica conservadoramente bloqueada nesse caso e o diagnóstico indica o problema, sem reparar/migrar a linha automaticamente. Listagem/inspeção continuam possíveis.

Novas linhas de `reflections` são UTC. Conclusões continuam `reflexao`, não fatos, mantendo suas evidências. Outros escritores mentais não foram convertidos em bloco.

### 4. Reflexão noturna respeita o dia local

Material anterior usava apenas `created_at >= YYYY-MM-DD`: incluía ontem em UTC e até eventos de amanhã. Agora episódios/estados emocionais têm limite inferior e superior do calendário local e teto no instante atual. JSONL relevante também filtra pelo instante; entradas de horário inválido ficam preservadas no arquivo, mas não são tratadas como evidência observada hoje.

Chave da noite e horário noturno usam fuso configurado. O marcador de conclusão usa o mesmo instante fornecido para a chave, gravado em UTC; antes combinava a chave de um instante com o horário real de outro. Solicitação e novas reflexões usam UTC. Não altera o significado de conclusão, origem ou tipo mental.

### 5. Tempo monotônico no ciclo existente

Guardas de fala, ação interna e visão não subtraem mais datas incompatíveis. Na mesma execução usam o par monotônico passado por `main`; zero é válido e relógio regredido/NaN não libera iniciativa. Guardas antigas sem marcador monotônico usam cálculo civil compatível, conservador em erro.

`main` conserva os horários observáveis e adiciona marcadores monotônicos somente em RAM. A fila **existente** `acoes_na_hora` passa a guardar instantes monotônicos, sem segunda fila/estado paralelo; entradas datetime antigas continuam legíveis. `deliberar` recebe esses marcadores. A prioridade de conversa recente sobre reflexão noturna também usa essa duração. Horário de silêncio continua uma política de calendário local, com a exceção urgente já existente preservada.

Esses marcadores não são persistidos nem comparados entre processos. Refratários duráveis de `drives` permanecem o mecanismo existente para restart; isso não cria uma nova persistência de cotas gerais.

## Arquivos deste incremento

Código: `app/core/history.py`, `bd.py`, `situation.py`, `kernel.py`, `autonomy.py`; `app/tools/agenda.py`; `app/mind/reflection.py`, `night_reflection.py`, `strategies.py`; `app/main.py`.

Testes: `testes/test_v20_iniciativa.py`, `test_integridade_memoria.py`, `test_reflexao_noturna.py`, `test_logica_cognitiva.py`. Nenhum grupo oficial novo.

Documento criado: este relatório. Nota de continuação adicionada a `TEMPO_CONTINUIDADE_20261009.md`, sem substituir evidências da rodada anterior.

## Validação

Baseline desta rodada: **74/74 grupos offline**, saída 0. Regressões foram executadas vermelhas antes da correção, incluindo recorrência zero com worker isolado e espera limitada, não um teste que trava CI indefinidamente.

**25 métodos novos** nos grupos existentes:

| Grupo | Novos métodos | Total do grupo |
|---|---:|---:|
| Iniciativa/agenda | 8 | 20 |
| Integridade/reflexão | 6 | 15 |
| Reflexão noturna | 6 | 6, mais smoke legado |
| Lógica/intervalos | 5 | 18, mais 13 verificações legadas |

Todos usam isolamento oficial, bancos/arquivos temporários, sem internet, microfone, entidades reais ou providers. Há execução real de SQLite, parser, rotinas de persistência e métodos do ciclo sem inferência. Não é evidência de sono físico, sentimento, personalidade real ou uso prolongado.

Falhas do desenvolvimento registradas, não ocultadas:

- Primeira bateria confirmou ordenação, retorno UTC ausente, erro de fuso, loop/recorrência, evidência futura e cooldown incorreto.
- Uma fixture nova usava o nome inexistente `HoshinoApp`; foi corrigida para a classe real `InterfaceHoshino`, não acrescentado alias ao produto para satisfazer o teste.
- Mock do relógio retornava UTC perto da meia-noite. Expôs normalização insuficiente do dia/arquivo local; corrigida conversão antes de extrair data.
- Fechamento explícito das conexões das fixtures removeu `ResourceWarning`. Isso não prova que todos os consumidores de SQLite do projeto estejam livres de leaks.
- Leitura da última reflexão ainda ignorava um registro temporalmente inválido quando coexistia com outro válido. Reproduzido em `reflexao-ambigua-antes.log`; agora bloqueia a guarda em vez de adivinhar ordem.

Resultado completo final: **74/74 grupos offline, saída 0**, em `suite-final.log`, após a correção da reflexão ambígua. As duas rodadas intermediárias também passaram 74/74. Os quatro grupos direcionados passaram 20/20, 15/15, 6/6 e 18/18 métodos, além das verificações legadas; todas as 25 regressões novas passaram. `git diff --check` sem erros. Isso não aprova cenários físicos ou funcionalidades das fases restantes.

## Evidências e preservação

Diretório privado ignorado pelo Git: `compartilhado/runtime/ensaios/20261009/agenda-revisao/`.

- `suite-antes.log`: baseline completo; logs `*.antes.log`, `*.bordas-antes.log`, `*.utc-escrita-antes.log` e `reflexao-ambigua-antes.log`: reproduções.
- `suite-depois.log`: primeira suíte verde após o conjunto inicial; `suite-verificada.log`: rodada intermediária; `suite-final.log`: código final e guarda de reflexão ambígua. Logs `*.final.log`: grupos direcionados.
- `pre-incremento/codigo.tgz`: snapshot do código/testes pertinentes. `strategies-head.tar` complementa o arquivo que estava limpo antes deste incremento; só a ordenação foi alterada.
- Três snapshots mentais feitos pela API de backup do SQLite em modo somente leitura, todos com `quick_check=ok`, fora do Git. Nenhum banco restaurado sobre o original.

Conteúdo lógico dos originais e snapshots comparado em leitura somente depois da primeira suíte completa e novamente após a final; mesmos hashes em ambas. `quick_check=ok` nos três originais:

| Banco | SHA-256 do dump lógico, igual no original e no snapshot |
|---|---|
| Hoshino | `f9164eba302fb5eb2884945877e390b8ae95a256698b2f2b4afd864c9edf8ae7` |
| Lilith | `aad72056ccb4a82567319f2d714118b80fea27f32d63d312194a8fb765498aec` |
| Alistair | `9212718395f40f66eadffd19d39450b299c816a60e31233a37fef6ba54120914` |

Os hashes binários de um backup SQLite podem diferir por cabeçalho; não confundir isso com mudança de conteúdo mental. Essa verificação não equivale a hashear todos os pesos/configurações/JSON do projeto.

## Limites e próximos pontos

1. Outros filtros/escritores mentais de datas textuais ainda precisam de auditoria coordenada. `bd.agora` permanece compatível; não declarar todo o projeto migrado para UTC.
2. Função SQLite de comparação não usa os índices textuais de data para ordenar instantes. Não foi comprovado desempenho com histórico enorme; medir antes de mudar esquema ou cache.
3. Suspensão, NTP físico, PC2 e utilização prolongada não foram testados. Monotônico do Python não é prova de horas físicas dormidas; nunca inferir duração entre processos desse marcador.
4. Material noturno ainda possui limites de linhas/caracteres do componente existente. Resumo semântico incremental diário, vínculo completo de evidências noturnas, diário voluntário/ACL, aprendizagem causal e oficina visual continuam pendentes.
5. Nenhuma nova validação de modelos, Discord, Minecraft, voz ou personalidade ocorreu nesta rodada.
6. Nem toda apresentação de data no material mental foi reformulada: há rótulos antigos compactados sem offset nos prompts. A comparação agora é por instante; revisão de apresentação/proveniência temporal nos demais prompts continua pendente. O marcador noturno usa o instante de referência fornecido pelo ciclo, não mede a duração real da inferência.

Para carregar o código novo será necessário restart cooperativo posterior; não foi executado automaticamente. Reversão deve retirar apenas este incremento de código, preservando o leitor compatível se registros UTC novos já tiverem sido gravados. Não restaurar bancos/identidades ou desfazer a árvore preexistente cegamente.
