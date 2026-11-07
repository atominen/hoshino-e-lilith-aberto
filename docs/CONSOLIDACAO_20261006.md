# Consolidação Hoshino / Lilith / Alistair — 06/10/2026

## Resumo e limites da entrega

Esta etapa reforçou código existente, sem adicionar ferramentas, capacidades ou funções psicológicas. A suíte original passou antes das mudanças: **30 grupos, nenhuma falha**. Na execução final, depois das correções: **36 grupos, nenhuma falha**, incluindo **63 novos casos de regressão** distribuídos em cinco arquivos. O grupo existente de reflexão noturna também foi incorporado ao executor geral.

Cloud permaneceu desativado: `cloud.enabled=false` e os dois backends cloud estão desabilitados na configuração existente. Não foram baixados/apagados modelos, nem feita migração em massa dos bancos. As identidades e memórias reais não foram disponibilizadas para escrita nos testes. Nenhum serviço real foi reiniciado por esta etapa; processos já abertos precisam de um encerramento normal e nova inicialização para carregar o código alterado.

Avaliação sincera: a base ficou mais conservadora e observável, principalmente quanto à diferença entre uma tentativa, uma gravação e um resultado comprovado. Isto **não é uma certificação de funcionamento integral em produção**. Há limites conhecidos descritos ao final; não considero todos os contratos de todas as ferramentas completamente consolidados.

## 1. Bugs corrigidos

### Integridade da memória — prioridade 1

- Confiança `0.0` deixou de ser substituída pelos padrões `0.5`/`0.8`. Agora somente ausência/`None` recebe o padrão apropriado. Escrita, leitura, propriedades e ranking de procedimentos preservam zero.
- Confianças não numéricas, NaN e infinitas são rejeitadas, em vez de serem interpretadas como certeza.
- Reflexões produzidas pelo modelo são gravadas como **reflexão**, não como fato. O registro traz os identificadores dos episódios de origem quando disponíveis.
- O extrator preserva hipótese, interpretação, reflexão e inferência. Um suposto "fato" extraído apenas pelo LLM passa a interpretação; categoria desconhecida não é promovida automaticamente a fato.
- Recuperação de conhecimento, propriedades, consultas diretas, material noturno e contexto do modelo preservam categoria, fonte, confiança, identificação/data de origem e evidência disponível. Reflexões e hipóteses não recebem um cabeçalho que as declare fatos confirmados.
- A classificação participa da resolução de conflitos: uma reflexão antiga não substitui silenciosamente um fato apenas por compartilhar a mesma chave.
- Compatibilidade sem migração cega: registros antigos `fato` cuja fonte é explicitamente `reflexao`/`reflexao_noturna` são apresentados como reflexão **na leitura**. O tipo original, a confiança original e os campos legados continuam preservados no banco e no registro estruturado. Dados sem fonte permanecem legíveis, com ausência/default indicada; não foi inventada proveniência.
- Episódios que mencionam ferramentas não recebem mais `is_success=1` simplesmente porque o texto de resposta foi salvo.

### Auditoria de zero fora da memória

A revisão estática cobriu os arquivos Python ativos de aplicação, inicialização e scripts, incluindo fallbacks com constantes e com variáveis. Não houve substituição indiscriminada de `or`: strings/listas vazias, booleanos e limites onde zero é inválido mantiveram suas regras.

Foram corrigidos zeros válidos em intervalo de sorteio, deslocamento do navegador, espera do desktop, distância de Minecraft nas camadas Python e JavaScript, rating de xadrez, índice de dispositivo de áudio e relógio de progresso. Em xadrez, o antigo zero usado como sentinela de "não exigir rating" virou `None` explicitamente, preservando os desbloqueios anteriores. A correção do índice de áudio é de tratamento de valor; não adiciona voz ou captura nova.

### Persistência — prioridade 2

- Falhas nos caminhos de memória/reflexão, relações, traços e estado passaram a usar o diagnóstico estruturado existente: operação, entidade, arquivo/banco, erro/tipo, timestamp, possibilidade de repetição segura e indicação de efeito já confirmado/parcial quando conhecida.
- Falhar ao criar a pasta de diagnóstico não derruba o aprendizado; existe fallback estruturado para a saída de erro. Se também esse destino falhar, não há garantia de conservação do diagnóstico.
- Atualizações de traços, relações e seus eventos, curiosidades e progresso de tarefa usam transações delimitadas. Uma segunda escrita que falha reverte a primeira; falha de curiosidade não devolve um ID fantasma. Atualizações concorrentes de evidências de traços não perdem incrementos.
- Reflexão e a memória correspondente são confirmadas na mesma transação SQLite. Falha não entra na contagem de reflexões aprendidas. O lote noturno também não parece concluído quando a gravação falha.
- JSONs existentes usam gravação temporária, sincronização e substituição atômica, com trava de arquivo. As partições e campos desconhecidos são preservados; JSON corrompido é diagnosticado e não é sobrescrito com um estado vazio. Leitura aceita o BOM de arquivos antigos.
- A atualização do estado psicológico é calculada dentro da trava. Escritas de humor, emoções, impulsos, situação e self-model sinalizam falhas. Um evento afetivo parcialmente persistido não retorna `persisted=true` se a gravação das emoções falhar.
- Falha do índice vetorial não apaga uma memória confirmada em SQLite nem provoca nova inserção automática. A resposta informa que a persistência foi somente SQLite.
- Se o arquivo de self-model foi salvo mas o índice de versões falhou, a resposta é explicitamente parcial e não recomenda repetir o aprendizado.

### Sono e encerramento — prioridade 3

Política da central: aviso após **10 segundos**, prazo normal de **30 segundos**, teto global de observação/drenagem de **45 segundos**. Os trabalhos, processos, recursos, fechamentos de serviços e erros de observação aparecem no diagnóstico de bloqueio. Até uma consulta de diagnóstico ou observação travada não ganha prazo ilimitado.

- O pedido inicial continua cooperativo; no prazo normal há nova solicitação cooperativa e cancelamento de jobs de áudio que o serviço consegue identificar como próprios.
- Se não houver prova de que uma escalada é segura, não há morte forçada de entidades. Ao atingir o teto com pendências, o resultado é `blocked` e a central permanece disponível para diagnóstico, recusando novas operações mutáveis. **O teto limita a espera de drenagem; não promete matar qualquer processo em 45 segundos.**
- Sono individual também recebe aviso/diagnóstico de demora, sem matar trabalhos incertos.
- Cancelamento explícito de comando verifica entidade, raiz, marca de criação do processo, token colocado em seu ambiente e grupo próprio. PID reutilizado, metadados legados sem prova ou processo alheio não recebem sinal.
- Enviar TERM/KILL não basta para afirmar que o job terminou. Sem observar o término, a saída é incerta, o job continua marcado como rodando/bloqueador e não há repetição automática. Mesmo quando o término é comprovado, os efeitos do comando original continuam incertos.

### Ação → recibo → verificação — prioridade 4

Foi ampliado o **mesmo contrato estruturado e o mesmo diário de jobs existentes**, sem introduzir outro banco ou sistema paralelo de recibos.

- Uma ferramenta mutável reserva o recibo antes do efeito. Sem conseguir registrar essa intenção, não executa.
- Exceção depois do início do efeito, ou perda do recibo final, produz resultado incerto. Uma intenção pendente/incerta com a mesma assinatura bloqueia repetição automática, inclusive em tentativas concorrentes.
- O ciclo e a tarefa param diante de resultado incerto ou job pendente. Não avançam a etapa nem repetem o lote para tentar obter uma resposta bonita.
- Arquivos são reabertos após a escrita e comparados por conteúdo/tamanho/hash esperado. Pastas são verificadas pela existência real. Memórias/propriedades/procedimentos têm confirmação por consulta SQLite após o commit.
- `EDIT_FALHOU` não é mais sucesso. Texto arbitrário de arquivo/log não pode forjar verificação de Minecraft ou código de saída do shell.
- Um job em execução é pendente; um job terminado sem código conhecido é incerto, não sucesso.
- Mensagem colocada na saída do Discord é **enfileirada**, não entregue. A mera chamada de instalação/download também não prova sucesso quando a ferramenta falhou.
- Verificar o término de um processo não é verificar os efeitos de seu comando. Esses dois resultados não são confundidos.

## 2. Consumidores localizados antes das alterações

O mapa de referências do código atual foi usado para manter APIs e formatos legados:

- Conhecimento: montagem de contexto e ciclos em `main`, scribe, reflexão normal/noturna, consultas diretas, esquemas/handlers do dispatch, prompting e testes de integração/turno.
- SQLite/transações: módulos mentais, relações sociais, progresso de tarefa, reflexão e curiosidades; os leitores tolerantes legados continuam compatíveis, com diagnóstico.
- JSON de estado: estado psicológico, humor, emoções, impulsos, situação, conclusão noturna, self-model e referências da administração de memória. Nenhum reset real foi executado.
- Encerramento: Supervisor, API e laço da central, sono/presença entre entidades, ciclos locais, jobs, gerenciador de recursos, serviço de áudio, monitor do mundo e registros de comandos de terminal.
- Contratos: dispatch, execução em lotes, cognição, verificadores, trava de afirmação de sucesso e estado persistido das etapas.
- Outros zeros: handlers e adaptadores do navegador/desktop; Minecraft Python e bridge JavaScript; níveis de xadrez; construção/captura da fonte de áudio; snapshots e consumidores do progresso.

Isso é um mapa estático do código presente, não uma garantia sobre consumidores externos que não estejam no projeto.

## 3. Arquivos modificados e adicionados

São **30 arquivos existentes modificados**, **2 auxiliares internos novos**, **5 arquivos novos de regressão** e este relatório. Os caminhos dos links são os da raiz canônica; a pasta de compatibilidade não foi reorganizada nesta etapa.

### Existentes modificados

- Memória: [knowledge_store.py](</home/gustavo/hoshino e lilith/app/memory/knowledge_store.py>), [chroma_store.py](</home/gustavo/hoshino e lilith/app/memory/vector/chroma_store.py>).
- Aprendizado/reflexão: [scribe.py](</home/gustavo/hoshino e lilith/app/mind/scribe.py>), [reflection.py da mente](</home/gustavo/hoshino e lilith/app/mind/reflection.py>), [night_reflection.py](</home/gustavo/hoshino e lilith/app/mind/night_reflection.py>), [personality.py](</home/gustavo/hoshino e lilith/app/mind/personality.py>).
- Estado existente: [psych_state.py](</home/gustavo/hoshino e lilith/app/mind/psych_state.py>), [affect.py](</home/gustavo/hoshino e lilith/app/mind/affect.py>), [emotions.py](</home/gustavo/hoshino e lilith/app/mind/emotions.py>), [drives.py](</home/gustavo/hoshino e lilith/app/mind/drives.py>), [situation.py](</home/gustavo/hoshino e lilith/app/core/situation.py>).
- Persistência/diagnóstico: [bd.py](</home/gustavo/hoshino e lilith/app/core/bd.py>), [diagnostics.py](</home/gustavo/hoshino e lilith/app/core/diagnostics.py>), [people.py](</home/gustavo/hoshino e lilith/app/social/people.py>), [reflection.py das ferramentas](</home/gustavo/hoshino e lilith/app/tools/reflection.py>).
- Ciclo e recibos: [job_bus.py](</home/gustavo/hoshino e lilith/app/core/job_bus.py>), [dispatch.py](</home/gustavo/hoshino e lilith/app/core/dispatch.py>), [task_state.py](</home/gustavo/hoshino e lilith/app/core/task_state.py>), [cognition.py](</home/gustavo/hoshino e lilith/app/core/cognition.py>), [prompting.py](</home/gustavo/hoshino e lilith/app/core/prompting.py>), [progress.py](</home/gustavo/hoshino e lilith/app/core/progress.py>), [main.py](</home/gustavo/hoshino e lilith/app/main.py>).
- Adaptadores existentes: [filesystem.py](</home/gustavo/hoshino e lilith/app/tools/filesystem.py>), [terminal.py](</home/gustavo/hoshino e lilith/app/tools/terminal.py>), [desktop.py](</home/gustavo/hoshino e lilith/app/tools/desktop.py>), [transcricao.py](</home/gustavo/hoshino e lilith/app/tools/transcricao.py>), [session.py do xadrez](</home/gustavo/hoshino e lilith/app/play/chess/session.py>), [bridge.js do Minecraft](</home/gustavo/hoshino e lilith/compartilhado/servicos/minecraft/bridge.js>).
- Inicialização e testes: [iniciar_entidades.py](</home/gustavo/hoshino e lilith/iniciar_entidades.py>), [rodar_testes.sh](</home/gustavo/hoshino e lilith/rodar_testes.sh>).

### Auxiliares internos novos

- [state_file.py](</home/gustavo/hoshino e lilith/app/core/state_file.py>): escrita segura dos JSONs existentes. Não é uma ferramenta exposta ao modelo.
- [shutdown.py](</home/gustavo/hoshino e lilith/app/core/shutdown.py>): política de drenagem dos trabalhos existentes. Não cria capacidade nova.

## 4. Testes novos e resultados — prioridade 5

| Grupo novo | Casos | Cobertura principal |
| --- | ---: | --- |
| [Integridade de memória](</home/gustavo/hoshino e lilith/testes/test_integridade_memoria.py>) | 9 | Zero/None, seis categorias, fonte/evidência, reflexão, extração, dados legados sem alteração, confiança inválida, ranking e prompt |
| [Persistência](</home/gustavo/hoshino e lilith/testes/test_persistencia_consolidacao.py>) | 17 | Rollback, contadores concorrentes, corrupção/BOM, replace falho, partições JSON, diagnóstico, índice parcial, conclusão noturna, episódio, curiosidade, self-model e emoção parcial |
| [Encerramento](</home/gustavo/hoshino e lilith/testes/test_encerramento_consolidacao.py>) | 11 | Normal/lento/travado, limite com observação/logger travados, supervisor conservador, PID legado/reutilizado/alheio, cancelamento próprio confirmado ou incerto |
| [Contratos e recibos](</home/gustavo/hoshino e lilith/testes/test_contratos_consolidacao.py>) | 19 | Edição falha, prova forjada, recibo ausente/perdido, concorrência, SQL/arquivo verificados, append incerto, pausa de lote/tarefa, Discord enfileirado, jobs/códigos e erro pós-início de comando |
| [Defaults com zero](</home/gustavo/hoshino e lilith/testes/test_zero_defaults.py>) | 7 | Sorteio, pixels, distância, rating, espera, dispositivo de áudio e relógio |
| **Total novo** | **63** | Todos aprovados na execução final |

Resultados:

- Antes das mudanças: executor completo, **30/30 grupos aprovados**, saída 0.
- Depois das mudanças finais: mesmo executor, ampliado, **36/36 grupos aprovados**, saída 0.
- Verificação de sintaxe JavaScript da bridge de Minecraft: aprovada no Node existente, saída 0.
- Os testes são isolados: identidade copiada para pasta temporária; bancos, estado e runtime redirecionados; inicialização automática de embeddings e troca de residência dos modelos reais desabilitadas no executor existente.
- Foram usados mocks onde necessário. Não houve envio real ao Discord, sessão real de Minecraft, uso de microfone físico, chamada a LLM/cloud ou operação mutável real de ferramenta para validar estes casos.

## 5. Comportamentos antigos que precisaram mudar

1. Uma reflexão/extração do LLM não ganha automaticamente a autoridade de um fato. Isso altera classificação, cabeçalhos de contexto e a confiança aparente de algumas respostas antigas, sem reescrever as memórias legadas.
2. Gravação falha, parcial, somente SQLite e efeito incerto têm respostas diferentes. O sistema pode deixar de contar um aprendizado que antes aparentava sucesso.
3. JSON corrompido agora impede a escrita sobre ele. Ele precisa ser reparado conscientemente; não é substituído silenciosamente pelo padrão.
4. Resultado mutável incerto ou job pendente pausa o ciclo/tarefa. Não há avanço automático da etapa nem repetição da ação para tentar descobrir se funcionou.
5. Ao exceder o teto de encerramento com trabalho incerto, a central fica em estado de fechamento/diagnóstico; não some afirmando que tudo encerrou.
6. Comandos legados sem prova de posse não são mortos pelo cancelamento novo. Sinal enviado sem término observado também não é anunciado como processo encerrado.
7. Enfileirar mensagem não equivale a enviar/entregar. Executar shell com código 0 comprova o término do comando, mas não necessariamente toda a intenção descrita pelo usuário.

## 6. Riscos restantes e próximos trabalhos de consolidação

- **Memória antiga sem evidência:** fatos legados com fonte desconhecida não foram certificados nem reclassificados por adivinhação. Categoria e confiança não são prova de verdade. A compatibilidade identifica somente a origem de reflexão que está explicitamente registrada.
- **Índice vetorial:** SQLite confirmado pode estar sem indexação vetorial. Reflexão gravada numa transação compartilhada não atualiza automaticamente esse índice. A recuperação SQL continua disponível; não foi feito rebuild/migração.
- **Concorrência dentro de humor/emoções:** o arquivo e suas partições são preservados atomicamente, mas alguns cálculos de humor/emoção ainda leem antes de adquirir a trava de escrita. Eventos simultâneos na mesma partição ainda podem disputar o último valor. O estado psicológico e os contadores de traços já têm cálculo/incremento transacional protegido.
- **Persistência entre destinos:** arquivo de humor/emoções, estado psicológico, histórico SQL e índice de versões não formam uma única transação global. Falhas parciais são diagnosticadas, mas não há rollback global de todos esses destinos.
- **Diário de diagnóstico:** o espelho secundário em SQLite ainda é best-effort; a trilha principal JSON/log e o fallback não transformam falha do espelho em sucesso de aprendizado. Fallbacks de leitura de contexto/componentes opcionais também continuam existindo; não foi removido todo `except` do projeto. Diagnósticos assíncronos do encerramento não têm garantia absoluta de flush se o processo for encerrado externamente.
- **Jobs sem código de saída:** o mecanismo legado de jobs em segundo plano não conserva sempre o código final. Nesses casos, o novo contrato retorna incerto em vez de inventar sucesso. Não foi adicionado um monitor novo para certificar esses resultados.
- **Repetição após resultado confirmado:** o bloqueio desta etapa cobre intenção pendente/incerta por assinatura. Ainda não existe um identificador de operação ponta a ponta para garantir execução exatamente uma vez de todo efeito Hoshino/Lilith já confirmado caso falhe a gravação posterior do progresso. A proteção durável específica já existente no Alistair foi preservada.
- **Verificadores heterogêneos:** algumas ferramentas ainda usam consultas de saúde/listagem, em vez de uma pós-condição completa do pedido. Não foi certificada a semântica de todas as ferramentas. Os casos fortes desta etapa são persistência SQL, conteúdo de arquivo/pasta, conexão Minecraft estruturada, estados de job e término observado de processo próprio. Entrega real do Discord continua distinta de fila.
- **Encerramento conservador:** um job realmente travado pode exigir análise/intervenção; não há autorização implícita para matar processo alheio ou abandonar silenciosamente efeitos incertos. A central pode permanecer aberta para diagnóstico.
- **Uso real e distribuição:** os processos atuais não foram reiniciados; o pacote já exportado para PC2 não foi reconstruído nesta etapa. Testes de voz/Discord/Minecraft existentes passaram offline, mas isso não certifica dispositivos, conectividade ou entrega reais. Cloud, Discord voz e novas capacidades ficaram fora do escopo.

## Reversibilidade

Antes de alterar o código, foram preservadas cópias locais:

- [Código anterior](</home/gustavo/hoshino e lilith/arquivo/consolidacao-20261006/codigo_antes.tar.gz>): aplicação, inicializador e testes/executor anteriores.
- [Bridge anterior](</home/gustavo/hoshino e lilith/arquivo/consolidacao-20261006/minecraft_bridge_antes.tar.gz>): JavaScript de Minecraft antes da alteração.

São backups de **código**, não substitutos de backup de memórias/modelos. Ambos têm acesso restrito ao proprietário. Para desfazer, comparar e restaurar apenas os arquivos desta etapa, com processos encerrados normalmente; não extrair indiscriminadamente sobre alterações posteriores. Os dois auxiliares e os cinco testes novos não existiam no snapshot inicial. Nenhuma restauração ou remoção foi executada.
