# Auditoria de prontidão para o primeiro teste manual integrado

Data: 06/10/2026. Projeto: `/home/gustavo/hoshino e lilith`.

## Parecer

**NÃO, EXISTEM BLOQUEADORES para o roteiro completo solicitado, no estado atual.**

Não é necessário redesenhar o projeto. Há duas falhas concretas nos passos iniciais do roteiro:

1. Apresentações de Alistair/Lilith podem substituir o nome do usuário na memória de Hoshino/Lilith. A autoria se perde no aprendizado; episódios de Lilith ainda são escritos com o nome Hoshino.
2. A descoberta automática LAN ignora o formato de anúncio usado pelo Minecraft Java. Abrir um mundo para LAN não basta para a rota automática encontrá-lo.

Também recomendo corrigir antes da sessão: fluxo LLM incompleto aceito como concluído; recuperação de mensagens do Alistair diferente das demais entidades; desligamento de fala/ponte própria; isolamento dos callbacks de conexão Minecraft. Esses ajustes cabem nos componentes existentes.

Uma sessão curta exclusivamente textual pode servir como diagnóstico, mas **não seria aprovação do roteiro integrado nem deveria semear memórias reais antes de corrigir a autoria**.

Não alterei código, configuração, modelos ou bancos mentais nesta auditoria. Este relatório é o único arquivo de projeto acrescentado. Não iniciei entidades, modelos, Minecraft, microfone ou providers remotos. Não houve download, gasto de quota, nova integração, migração ou habilitação de cloud.

## Método e limites da evidência

Uso quatro qualificações: **código** = comportamento identificado na implementação; **reproduzido** = probe isolado exercitando código real com transporte/modelo simulado; **registro real anterior** = artefato existente, não repetido nesta auditoria; **pendente** = exige ensaio real.

Resultados desta rodada:

| Verificação | Resultado exato | O que comprova |
|---|---|---|
| Suíte oficial offline, `rodar_testes.sh` | **67/67 grupos; saída 0** | Contratos cobertos com isolamento. Não são 67 testes individuais. |
| Humano → Hoshino enquanto Alistair envia mensagem | **1/1 cenário passou** | Worker, envelope SQLite e respostas encaminhadas ao autor correto. |
| Hoshino → Lilith enquanto Lilith processa mensagem humana | **1/1 cenário passou** | A segunda entrada não desaparece; respostas mantêm destinatário e `reply_to`. |
| Apresentações Gustavo → Alistair → Lilith, no escriba real | **Defeito reproduzido** | As duas primeiras memórias tornam-se `superseded`; nome ativo do usuário passa a Lilith. |
| Episódio produzido com configuração Lilith | **Defeito reproduzido** | `what_happened` continua contendo `Hoshino:`. |
| Anúncio LAN Java padrão no parser real | **Defeito reproduzido** | Retorno `ok=true`, mas lista de mundos vazia. |
| Stream LLM com texto e EOF, sem `done=true` | **Defeito reproduzido** | Retorna mensagem de assistente como se concluída. |
| `PRAGMA quick_check`, somente leitura | **5/5 bancos retornaram `ok`** | Bancos mentais H/L/A, Resource Manager e mensageria estruturalmente legíveis agora. Não valida semântica nem recuperação após queda. |

Os dois cenários simultâneos terminaram sem falhas/erros, em aproximadamente 0,269 s. Usaram as fixtures dos testes de causalidade, LLM falso e aprendizado/contexto simulados. Portanto **não** validam três entidades completas, naturalidade ou memória — os probes do escriba encontraram justamente uma lacuna escondida por essa fixture.

Os probes adicionais foram executados em diretórios temporários sob as guardas do runner existente; não acrescentam testes persistentes nesta rodada. Devem virar regressões permanentes quando as correções forem autorizadas.

O [runner isolado](</home/gustavo/hoshino e lilith/testes/executar_isolado.py:113>) redireciona bancos/arquivos, remove credenciais, bloqueia serviços externos/captura/download e substitui métricas de GPU/RAM. A suíte verde **não** autoriza `concurrency_validated=true`.

### Máquina real observada

Snapshot, sem workload controlado:

| Medida | Estado |
|---|---|
| RAM física | 33.528.483.840 bytes, aproximadamente **31,2 GiB** |
| RAM disponível | Aproximadamente **23,5 GiB**; cache é recuperável |
| Swap | `/swapfile` ativo, aproximadamente **8 GiB**; cerca de **43,4 MiB** usados |
| GPU | AMD/amdgpu; sysfs informa **8.573.157.376 bytes**, aproximadamente **7,984 GiB** VRAM |
| VRAM ocupada | Aproximadamente **0,94 GiB**, `gpu_busy_percent=1` |
| Disco livre | Aproximadamente **82,1 GiB**, partição em **90%** |
| Pressão de memória | PSI médio observado em zero; isso não prevê pressão durante a sessão |
| Registro RM | Nenhum lease, pedido GPU ou modelo residente registrado no snapshot SQLite |
| PC2 | Configuração remota **desativada**; não contatei o Athlon |
| Política GPU | Margem **768 MiB**; concorrência validada **false**; stickiness **90 s**; folga RAM **2 GiB** |

O RM usa `MemAvailable`, não soma swap como RAM rápida. O limite nominal é 8 GiB e o orçamento usa o menor valor entre esse limite e o total físico observado. Não há dependência de CUDA nas métricas auditadas. Cloud de cognição segue desativada em [capacidades.json](</home/gustavo/hoshino e lilith/compartilhado/config/capacidades.json:17>).

## 1. Fluxo completo: transições e contratos

VERDE significa contrato defensivo existente e evidência delimitada; não significa validação humana. AMARELO significa incompleto/condicional ou real pendente. VERMELHO significa defeito ou falta relevante para o roteiro.

| Transição | Cor | Erro, prazo, cancelamento, retry/incerteza | Persistência, autoria, ordem, isolamento e observabilidade |
|---|---|---|---|
| Humano → admissão/envelope | VERDE | Central valida entrada e IDs; repetição com submission ID não cria outro efeito. Microfone vira rascunho, não envio automático. | Envelope SQLite durável, origem e timestamp; TUI direta não possui a mesma durabilidade de transporte. [Entrada](</home/gustavo/hoshino e lilith/iniciar_entidades.py:339>) / [worker](</home/gustavo/hoshino e lilith/app/main.py:581>). |
| Envelope → fila/turno | AMARELO | Desfechos H/L explícitos; falha/incerteza não é retry mutável automático. Debounce limitado. Não há limite total da fila conversacional. | FIFO por conversa; autores diferentes têm workers diferentes. Entrada aceita não garante processamento após crash sem reconciliação. Alistair diverge. [Fila](</home/gustavo/hoshino e lilith/app/main.py:706>) / [estados](</home/gustavo/hoshino e lilith/app/core/interentity.py:274>). |
| Fila → contexto | AMARELO | Snapshot impede incluir mensagem futura; correção invalida revisão anterior. Recuperação falha com aviso, não crash geral. | Histórico por chave/autor; observações Minecraft não são instruções. Sem ordem causal global. Cache de conversas/cursor de eventos vive em RAM. [Contexto](</home/gustavo/hoshino e lilith/app/main.py:429>) / [eventos](</home/gustavo/hoshino e lilith/app/main.py:505>). |
| Contexto → recuperação de memória | AMARELO | Banco antigo continua legível; exceções de persistência têm diagnóstico. Busca episódica depende do vetor; indisponibilidade pode empobrecer contexto. | Conhecimento retorna tipo/fonte/confiança/links; origem originalmente perdida não é reconstruída. [Recall](</home/gustavo/hoshino e lilith/app/memory/knowledge_store.py:537>). |
| Entrada/turno → aprendizado | VERMELHO | Erro não deve virar sucesso, mas extração LLM ainda tem retorno silencioso e trabalho em background. | Autoria não chega ao escriba; chave `nome_do_usuario` conflita entre participantes; episódio rotula Lilith como Hoshino. [Aprendizado](</home/gustavo/hoshino e lilith/app/main.py:3759>) / [regra](</home/gustavo/hoshino e lilith/app/mind/scribe.py:160>). |
| Contexto → executor 7B/9B | AMARELO | Escolha conservadora, contexto/tarefa complexa excluem leve; decisão fixada no ciclo. Custos previstos ainda majoritariamente heurísticos. | Identidade/memória externas; aliases leves separados. Registra modelo, tier e motivo. [Seleção](</home/gustavo/hoshino e lilith/app/core/resource_manager.py:139>). |
| Executor → RM → inferência | AMARELO | Fila priorizada, VRAM incerta serializa/nega; fallback CPU condicionado a RAM. Admissão tem prazo, stream não tem prazo total equivalente. | SQLite + flock impedem concorrência entre clientes cooperantes. Lease pertence ao cliente, não prova término do daemon. [Compute](</home/gustavo/hoshino e lilith/app/core/resource_manager.py:596>). |
| Backend → resposta/model tool calls | VERMELHO | EOF sem `done=true` é aceito. Timeout HTTP não é confirmação de conclusão nem garantia de cancelamento do backend. | Fragmentos parciais podem virar resposta persistida ou chamadas normalizadas sem confirmação final. [Stream](</home/gustavo/hoshino e lilith/app/main.py:1741>). |
| Plano → ferramenta mutável | AMARELO | Validação/política/lock, intenção durável antes do efeito; falha após envio vira incerteza. Não repete assinatura pendente automaticamente. | `job_bus` é o diário existente; thread mutável mantém serialização enquanto continua. Bridge Minecraft não oferece dedup próprio por request ID. [Execução](</home/gustavo/hoshino e lilith/app/core/dispatch.py:1739>). |
| Ferramenta → recibo → verificação | AMARELO | Separação accepted/verified/uncertain; conexão Minecraft exige consulta. STOP confirma pedido cooperativo, não cessação física imediata. | Marcadores fortes para arquivo/persistência/conexão; outras ações exigem estado externo. Spawn com erro ainda pode virar ready. [Contrato](</home/gustavo/hoshino e lilith/app/core/dispatch.py:1800>). |
| Resposta → envio | VERDE | IDs/dedup/desfechos de entrega; uma falha não autoriza repetir efeito externo incerto. | Resposta ao remetente, não ao último interlocutor global; `reply_to`, hops e histórico durável. [Saída](</home/gustavo/hoshino e lilith/app/main.py:3717>). |
| Resposta/frase estável → TTS | AMARELO | Frases estáveis, ordem, cancelamento e fallback; quota/rede/timeout remotos diagnosticados. Worker local pode demorar muito. | Entity/voice/provider/audio ID/stream ID; fala já ouvida não pode ser desfeita se geração posterior mudar. [Stream de fala](</home/gustavo/hoshino e lilith/app/core/speech_stream.py:12>). |
| TTS → reprodução | AMARELO | WAV validado e chunks ordenados; autoplay negado exige clique, não sucesso falso. Dormir não para automaticamente fala pendente/reprodução. | Interface tem serial de fala; síntese concluída não prova áudio ouvido. Falta ack durável de playout associado ao turno. [Player](</home/gustavo/hoshino e lilith/app/ui/central.html:55>). |
| Turno → persistência → restart | AMARELO | SQL commit/rollback e diagnóstico; nenhum commit atômico único abrange resposta, episódios, fatos e estado. Crash pode deixar aprendizado incompleto. | Bancos separados e legíveis; histórico curto reinicia vazio; Alistair só injeta quatro turnos por autor. Memória importante após restart precisa teste real. [SQLite](</home/gustavo/hoshino e lilith/app/core/bd.py:27>) / [Alistair](</home/gustavo/hoshino e lilith/app/alistair_runner.py:181>). |

### Semântica de repetição e recuperação em cada camada

- **Entrada durável:** retry com o mesmo submission ID representa o mesmo envio; novo ID representa nova mensagem, mesmo com texto igual. TUI direta não herda automaticamente esse contrato.
- **Fila/contexto:** recalcular contexto antes de efeito é seguro; depois de `processing`, crash não autoriza reiniciar o turno operacional indiscriminadamente. A ordem garantida é local, não causal global.
- **Memória:** chave/similaridade evitam parte das duplicações de conhecimento, mas não são transação idempotente do turno. Episódios têm ID aleatório; repetir aprendizado pode acrescentar episódio duplicado. Falta vínculo durável message ID → gravações automáticas para reconciliar esse caso.
- **Seleção/inferência:** escolher executor não altera estado mental e pode ser reavaliado no ciclo seguinte, nunca dentro da resposta. Repetir inferência sem efeito externo é diferente de repetir um ciclo que já executou ferramenta. Timeout do cliente não prova término do backend.
- **Ferramenta/recibo:** intenção persistida antes do efeito é pré-condição; se falhar, não executar. Recibo perdido após efeito exige resultado incerto e consulta externa, não retry automático. Dedup do diário Python não substitui idempotência de uma API/jogo.
- **Resposta/TTS/player:** dedup da mensagem não garante dedup de áudio ouvido. Cancelar job próprio é repetível; cancelar rede não desfaz cobrança, e cancelar player não desfaz frase ouvida. A confirmação de síntese/reprodução precisa continuar separada.
- **Persistência final:** SQL commit confirmado preserva aquela gravação. Não confirma que todos os callbacks posteriores de aprendizado terminaram. Falha de vetor pode deixar SQL correto mas recuperação semântica incompleta; restart precisa distinguir “não encontrado” de “serviço de memória indisponível”.

## 2. Acordar, dormir e ciclo de vida

### Comportamentos existentes

- **Acordar individualmente:** supervisor tem lock por entidade e o processo filho segura `entity.lock`. Uma entidade já ativa retorna estado correspondente; não deve ganhar segunda instância. Há janela entre verificação e spawn, mas o flock do filho é a proteção final. [Supervisor](</home/gustavo/hoshino e lilith/iniciar_entidades.py:45>) / [runner](</home/gustavo/hoshino e lilith/app/entity_runner.py:11>).
- **Prontidão:** `awake` de H/L pode indicar interface ativa mesmo se o modelo falhou na preparação. Não é prova de backend funcional. Uma confirmação de health/modelo existente deve acompanhar o gate.
- **Dormir H/L durante inferência/job:** para importar novas mensagens e drena workers, tarefas de background, locks mutáveis e leases. Não mata job externo desconhecido. Pode exceder 45 s; supervisor avisa em 10 s e diagnostica demora em 45 s, mantendo processo vivo. [Drenagem](</home/gustavo/hoshino e lilith/app/main.py:1568>).
- **Dormir Alistair:** termina a resposta corrente, depois descarrega e marca sleeping. Não preempta inferência inseguramente. Processo tem banco/identidade próprios; CPU continua fallback.
- **Mensagem pendente durante sono:** permanece no SQLite; acordar importa mensagens disponíveis. Mensagem já marcada processing em H/L fica retida como incerta após crash, não é reexecutada cegamente. Alistair não aplica o mesmo estado durável.
- **Shutdown central:** prazo global normal 30 s, aviso 10 s, limite diagnóstico 45 s; fecha áudio/monitor e solicita sono. Se algo bloqueia, mantém supervisor para mostrar o bloqueio, sem matar processo de terceiro. [Shutdown](</home/gustavo/hoshino e lilith/iniciar_entidades.py:134>) / [política](</home/gustavo/hoshino e lilith/app/core/shutdown.py:20>).
- **Modelos residentes:** compute liberado não descarrega automaticamente pesos. Sono tenta unload dos modelos da entidade, com confirmação. Daemon ocioso continuar vivo não é vazamento por si só.
- **Bancos:** as operações auditadas usam fechamento/finally/context manager; processo encerrado fecha descriptors restantes. Isso não garante conclusão de todo aprendizado em background ou flush vetorial coordenado.

### Lacunas antes do teste

1. `/api/sleep` só escreve solicitação de sono. Não chama `audio.interrupt_entity`; botão Dormir também não chama `stopSpeech`. TTS central da entidade pode segurar `cpu_audio` durante síntese/espera de frases, atrasando sono. Corrigir só a fala da entidade alvo, preservando outra entidade e ASR não relacionado. [Endpoint](</home/gustavo/hoshino e lilith/iniciar_entidades.py:339>) / [UI](</home/gustavo/hoshino e lilith/app/ui/central.html:166>).
2. `on_unmount` fecha voz/modelos, mas não usa o fechamento existente da ponte Mineflayer criada pela própria entidade. A ponte é iniciada como subprocesso em sessão própria. Não há confirmação de que dormir/encerrar deixe de jogar. Não proponho matar por nome/porta: usar ownership e handles já existentes. [Unmount](</home/gustavo/hoshino e lilith/app/main.py:396>) / [launcher](</home/gustavo/hoshino e lilith/app/tools/minecraft_launcher.py:137>).
3. `entity_runner` ignora o retorno de unload no finally e publica sleeping/offline; a presença pode esconder unload não confirmado. TUI registra falha, mas a semântica do estado central deve distinguir processo encerrado de pesos liberados. [Finally](</home/gustavo/hoshino e lilith/app/entity_runner.py:30>).
4. Leases têm limpeza por flock, porém cliente encerrado não comprova que o daemon independente terminou inferência. Recuperação precisa reconciliar backend antes de nova concessão sob pressão.

O estado mental de uma entidade não é copiado para outra. Já CPU, GPU, áudio e diário central são recursos compartilhados: podem atrasar outra entidade mesmo com isolamento de memória correto.

## 3. Memória do primeiro contato

### Defeito confirmado

No banco temporário, chamei as regras/registro reais para:

```text
Meu nome é Gustavo.
Eu sou Alistair.
Eu sou Lilith.
```

Resultado:

| Conteúdo gravado | Tipo / fonte / confiança | Chave | Estado final |
|---|---|---|---|
| A pessoa com quem falo se chama Gustavo | fato / escriba / 0,95 | nome_do_usuario | superseded |
| A pessoa com quem falo se chama Alistair | fato / escriba / 0,95 | nome_do_usuario | superseded |
| A pessoa com quem falo se chama Lilith | fato / escriba / 0,95 | nome_do_usuario | active |

Todas carregam a entidade semântica `usuário`, sem link de evidência. `main` chama `scribe.pos_turno` para conversas humanas e interentidade; o parâmetro nome não resolve a autoria da regra. A substituição é a regra normal de conflito por chave/entidade do [knowledge store](</home/gustavo/hoshino e lilith/app/memory/knowledge_store.py:185>), aplicada a um sujeito incorretamente identificado.

Não é contaminação automática de banco H → L: é **atribuição errada dentro do banco de quem ouviu**. Lilith continua sem saber fatos automaticamente; pode aprender pela mensagem recebida, mas não deve classificá-la como declaração do humano.

Além disso, [salvar_episodio](</home/gustavo/hoshino e lilith/app/main.py:111>) fixa os rótulos `Usuário` e `Hoshino`, mesmo em Lilith e em mensagem de Alistair. O probe com config Lilith confirmou esse resultado.

### Contrato mínimo recomendado, sem novo banco

Para “Gustavo diz que seu nome é Gustavo”, preservar no registro existente: sujeito Gustavo/participante humano; autoria usuário; entidade ouvinte Hoshino; tipo fato informado; confiança de que **ele informou isso**, não verificação civil; message ID/canal/timestamp como origem. Autodeclaração de Alistair deve mencionar Alistair como sujeito/fonte e nunca superseder `nome_do_usuario`.

Não virar fato automaticamente: pergunta, hipótese, texto citado, roleplay, instrução, fala do LLM, extração interpretativa ou reflexão. Uma entidade informar algo sobre outra pessoa é informação atribuída àquela entidade, não confirmação direta pelo humano.

Aspectos já bons: confiança zero e None são distintos; recall formata categoria/fonte/confiança/links; extração LLM rebaixa `fato` a interpretação; reflexão é armazenada como reflexão com links aos episódios. [Registros](</home/gustavo/hoshino e lilith/app/memory/knowledge_store.py:97>) / [extração](</home/gustavo/hoshino e lilith/app/mind/scribe.py:397>) / [reflexão](</home/gustavo/hoshino e lilith/app/tools/reflection.py:114>).

A persistência SQL é confirmada por recibo nas ferramentas de memória. Entretanto, o aprendizado automático não fornece um encadeamento completo mensagem → memória IDs → recuperação. A extração background pode falhar sem diagnóstico específico do turno; o ACK da mensagem não significa “todos os fatos já foram gravados”.

**Consumidores a preservar numa correção:** `main` pós-turno e extração, `scribe.pos_turno/extrair_por_regra/registrar_achados`, `core.compaction.salvar_fatos`, ferramentas de conhecimento e testes de persistência/integração. A compactação também chama as regras e precisa receber autoria; consertar apenas o pós-turno deixaria outra via de corrupção. [Compactação](</home/gustavo/hoshino e lilith/app/core/compaction.py:114>).

**Alistair:** `alistair_turns` persiste entradas/saídas e dedup por source ID, mas o prompt recupera só quatro turnos por remetente. Informação antiga fora dessa janela não é automaticamente recuperada como fato importante. Portanto a lembrança das informações básicas após sessão longa/restart **não está garantida pelo contrato atual**. Refinar recuperação da tabela existente, sem fingir que ele já usa todo o pipeline de memória H/L.

Os cinco `quick_check=ok` não aprovam isso: integridade estrutural e verdade/autoria são propriedades distintas. Não recomendo reclassificar ou reescrever cegamente memórias antigas.

## 4. Interação entre Hoshino, Lilith e Alistair

| Rota | Transporte/autoria/destinatário | Processamento/recuperação |
|---|---|---|
| Alistair → Hoshino | VERDE no envelope; banco durável, remetente Alistair | AMARELO worker; VERMELHO autoria ao aprender apresentação |
| Alistair → Lilith | Mesmo contrato | Mesmo defeito do escriba compartilhado |
| Hoshino → Lilith | VERDE no envelope | Cenário concorrente passou; aprendizado/episódio incorretos |
| Lilith → Hoshino | Mesmo contrato simétrico | Fonte não deve ser rebatizada usuário ao aprender |
| Usuário → H/L | Submission ID, envelope, FIFO por chave | Regra de nome funciona isoladamente, mas conflita com apresentação de outras entidades |
| Usuário/entidades → Alistair | Envelope correto | Não aplica `processing_outcome`; falha fica cooldown em RAM e mensagem pendente |

O [bus](</home/gustavo/hoshino e lilith/app/core/interentity.py:174>) valida participantes, persiste antes de retornar, deduplica submissões e respostas por parent/sender/recipient. Hops automáticos têm limite **6**, evitando conversa infinita. Isso é limite deliberado: não prometer que as três conversarão indefinidamente.

`delivered_at` indica retirada da caixa; `read_at` é confirmação posterior. Não confundir com resposta enviada, efeito executado ou aprendizado concluído. Mensagens para entidade dormindo permanecem duráveis e podem solicitar wake. Estado `processing`/`uncertain` retido de H/L exige inspeção, não replay automático de ação.

Os dois cenários simultâneos pedidos passaram com o worker/SQLite reais e LLM simulado. Eles verificaram destinatário, `reply_to`, duas saídas e limpeza de inflight. Não verificaram simultaneidade física de inferências, qualidade de apresentação ou memória real.

**Alistair precisa aderir ao estado durável existente:** seu [loop](</home/gustavo/hoshino e lilith/app/alistair_runner.py:292>) apenas imprime tipo de erro e guarda `failed_until` em RAM. Após crash, esse cooldown some. `_once` protege algumas ações e turnos gravados podem ser reutilizados, mas isso não equivale ao contrato completo de H/L. A primeira página de dez mensagens com falhas repetidas também pode atrasar entradas posteriores.

O contexto de Alistair inclui identidade própria, mas a mensagem atual é texto puro sem bloco explícito de autoria; o histórico é particionado por sender. As ferramentas fixam a autoria mecânica Alistair, porém o texto produzido ainda pode interpretar mal quem disse “eu”. Refinar o prompt existente com dados do envelope.

Dedup por parent/sender/recipient impede resposta duplicada, mas também limita a uma mensagem para o mesmo destinatário naquele parent. É preciso distinguir esse contrato de “enviar vários recados intencionais no mesmo turno”. Não mudar agora sem um caso real que exija isso.

Não há sala mental comum implícita. A interface central mostrar mensagens não faz o contexto privado das três conter tudo. Troca explícita de informações continua necessária e desejável.

## 5. Múltiplas mensagens, correção e causalidade

| Caso solicitado | Parecer | Limite importante |
|---|---|---|
| A, B, C comuns | VERDE no contrato central e regressões existentes | FIFO por chave/autor; TUI/voz podem agrupar fragmentos segundo contrato de lote. Não prometer três respostas em qualquer canal. |
| “vai para esquerda”; “não, direita” | VERDE para intenção ainda não executada | Revisão supersede a primeira. Efeito já iniciado não é desfeito magicamente; STOP suportado tenta cancelamento cooperativo. |
| “pegue madeira”; “depois faça uma bancada” | VERDE para não confundir dependência com correção | Execução efetiva de coleta/craft continua dependente do mundo e verificação Minecraft reais. |
| “continue”; “PARA” | AMARELO | STOP explícito ganha caminho de revisão/cancelamento próprio; não garante preempção instantânea do daemon LLM ou de qualquer ferramenta. |
| texto + ASR + interentidade + Minecraft | AMARELO | IDs de origem/timestamps preservados em partes do pipeline. Minecraft entra como observação, ASR é envio humano revisado. Não existe total order causal dessas fontes. |

Evidências: [classificação](</home/gustavo/hoshino e lilith/app/core/conversation.py>), [revisões](</home/gustavo/hoshino e lilith/app/main.py:664>), [worker/snapshot](</home/gustavo/hoshino e lilith/app/main.py:706>), [regressões](</home/gustavo/hoshino e lilith/testes/test_mensagens_causalidade.py>) e [auditoria anterior](</home/gustavo/hoshino e lilith/docs/CORRECOES_MENSAGENS_E_ELEVENLABS_20261006.md>).

Revalidei a suíte que contém essas regressões e os dois cenários novos; **não executei um cenário real completo com microfone + mundo Minecraft + três modelos nesta rodada**. O contexto sensorial usa janela limitada e cursor em RAM; ao restart começa no fim do log existente para não tratar eventos antigos como novos. Logs antigos permanecem, mas não são replay mental garantido.

## 6. Minecraft Java 1.16.5

### Bloqueio LAN reproduzido

O parser [descobrir_lan](</home/gustavo/hoshino e lilith/app/tools/minecraft.py:168>) espera `MOTD:` e separação NUL. Um pacote Java padrão:

```text
[MOTD]Mundo de Gustavo[/MOTD][AD]51234[/AD]
```

foi descartado pelo código real, com `mundos=[]`. A implementação pública [NeoForge LanServerPinger](https://github.com/neoforged/NeoForge/blob/26.2.x/src/main/java/net/neoforged/neoforge/server/dedicated/DedicatedLanServerPinger.java) confirma esse formato de anúncio; não estou tratando essa fonte moderna como ensaio executado no 1.16.5.

O caminho existente `minecraft_conectar(host, port)` pode contornar a descoberta com endereço/porta explicitamente fornecidos. Se esse contorno for aceito, **o bloqueio LAN específico deixa de bloquear a sessão**, mas a autoria de memória continua bloqueadora. Não adicionar outro bridge/discovery.

### Auditoria do protocolo real

| Área | Estado e evidência |
|---|---|
| Versão/ponte | Mineflayer, versão default **1.16.5**, HTTP local separado por entidade, protocolo bridge **3**. Health compatível é exigido antes de mutação. [Bridge](</home/gustavo/hoshino e lilith/compartilhado/servicos/minecraft/bridge.js:13>). |
| Conexão | Python exige resposta verificada e consulta posterior. Mas erro na preparação de `Movements` é capturado e ainda pode virar ready; falso positivo de capacidade operacional. [Spawn](</home/gustavo/hoshino e lilith/compartilhado/servicos/minecraft/bridge.js:164>). |
| Sessão/reconexão | `sessionId` existe. Listeners de bot antigo usam globais `bot/sessionId/connectionState`; `end` antigo pode alterar estado de conexão nova. Risco identificado no código, ainda sem probe específico. [Listeners](</home/gustavo/hoshino e lilith/compartilhado/servicos/minecraft/bridge.js:189>). |
| IDs | Python gera request ID e envia parent turn ID/entity ID. Bridge ecoa request ID, mas não usa parent/entity para validar/correlacionar sessão esperada. Recibo de outro ID é rejeitado; ausência de ID ainda tem compatibilidade legada. [RPC](</home/gustavo/hoshino e lilith/app/tools/minecraft.py:52>) / [HTTP](</home/gustavo/hoshino e lilith/compartilhado/servicos/minecraft/bridge.js:459>). |
| Timeout/incerteza | Timeout de mutação, JSON inválido, erro após envio ou recibo divergente → `RESULTADO_INCERTO`; consultar estado antes de repetir. Navegação no backend não tem deadline global próprio. |
| Dedup | Diário Python reserva assinatura antes de efeito. Bridge não possui ledger idempotente por request ID; reenviar HTTP diretamente pode repetir. Não afirmar exactly-once no jogo. |
| Serialização | Lock mutável no cliente; bridge aceita callbacks concorrentes sem fila/lock por operação. Depois de timeout, backend pode continuar e novo pedido diferente pode se sobrepor. |
| STOP | `pathfinder.stop()` é cooperativo. Retorno imediato “Navegação parada” não comprova parada física instantânea; precisa observar estado/goal. [STOP](</home/gustavo/hoshino e lilith/compartilhado/servicos/minecraft/bridge.js:280>). |
| Coleta/mutações | Coleta compara inventário antes/depois; erro após quebrar alguns blocos pode ser parcial. Craft/colocação/ataque/uso/chat precisam recibo e verificação compatível com efeito, não texto otimista. |
| Dano/morte | Health, death, respawn, kick/end/error têm eventos. Health não é diagnóstico completo de causa de dano; rótulos death/respawn ainda mencionam Hoshino literalmente. |
| Observação/contexto | JSONL com pid/seq/ts/session alimenta janela perceptiva como observação, não ordem. Cursor/rotação são locais; arquivo/log perdido não equivale a estado do mundo conhecido. [Consumidor](</home/gustavo/hoshino e lilith/app/main.py:505>). |
| Crash/log | Algumas falhas ao escrever log são engolidas; uncaught/unhandled exceptions são registradas e processo continua. Não prova consistência após exceção inesperada. |
| Desconexão | Detectada e registrada; não há reconnect automático garantido. Conexão explícita existente é a recuperação. Fechar ponte própria precisa integrar sono/shutdown. |

### O que está implementado versus validado

Implementados: conectar/desconectar; estado/inventário; chat; procurar bloco; navegar/parar/seguir; minerar/coletar; craft/equipar/atacar/colocar/usar item. São adaptadores reais, não apenas nomes de ferramentas. [Superfície](</home/gustavo/hoshino e lilith/app/tools/minecraft.py:135>) / [handlers](</home/gustavo/hoshino e lilith/app/core/dispatch.py:829>).

**Prontos para ensaio controlado após correções mínimas, não aprovados em jogo real:** começar por conexão manual/descoberta corrigida, estado, inventário, chat e navegação curta + STOP. Depois coleta de um bloco e craft com materiais previamente disponíveis.

**Não validados nesta auditoria:** servidor/world real 1.16.5, mods/autenticação, multicast da rede, reconexão física, dano/morte, inventário/craft efetivo, diálogo durante ação. Não encontrei evidência suficiente para certificar esses caminhos; históricos/mocks de protocolo não substituem isso.

## 7. Voz: ASR → contexto → resposta → TTS → reprodução

Contratos atuais:

- Central compartilha workers locais; entidades headless não abrem outro microfone/TTS. ASR usa faster-whisper CPU/int8, arquivos locais e request ID obrigatório. Entrada de microfone recebe papel usuário **por origem**, não biometria. [Áudio](</home/gustavo/hoshino e lilith/app/core/audio_service.py:169>) / [ASR](</home/gustavo/hoshino e lilith/app/core/audio_transcription.py:75>).
- Browser limita gravação; ASR retorna rascunho. É necessário revisar/enviar. `beginRecording` interrompe fala corrente; texto novo aceito cancela TTS antigo da entidade. Não prometer diálogo hands-free contínuo nessa UI. [Browser](</home/gustavo/hoshino e lilith/app/ui/central.html:111>).
- Frases estáveis, não tokens instáveis, alimentam TTS. Chunks têm índice, WAV validada, ordem e serial de reprodução. Frase já reproduzida não pode ser retirada se uma tool call aparecer depois.
- Azure é preferido quando configurado; ElevenLabs opcional no roteador existente; Qwen3-TTS fallback obrigatório; Kokoro preservado. Remote timeout total limitado e cooldown; cancelamento não inicia fallback de fala obsoleta. [Roteador](</home/gustavo/hoshino e lilith/app/core/tts_router.py:253>).
- Chaves vêm do ambiente, não do repositório/log; adapter registra códigos sanitizados, provider, voz e latência. Timeout/cancelamento local não garante ausência de cobrança remota já aceita.
- Na configuração observada: Qwen local, Serena/Vivian separadas; Azure enabled com vozes distintas; ElevenLabs disabled e IDs vazios. Não havia credenciais desses providers no processo de auditoria. Isso **não prova** ausência de credenciais no launcher do usuário.

### Evidência real anterior, com limites

O [probe de áudio existente](</home/gustavo/hoshino e lilith/docs/verificacao_audio_central_20261006.json>) usou workers/HTTP reais, bancos temporários e áudio sintético: Hoshino 6,96 s de WAV em **42,18 s**; Lilith 7,12 s em **38,159 s**; ASR do WAV sintético em **12,059 s**, processamento **11,204 s**. Captura física **false**, reprodução **false**. Portanto local funciona mecanicamente, mas **não é TTS em tempo real** nem aprovação de microfone/sotaque.

Azure real e ElevenLabs com conta real continuam **pendentes**. Testes mockados validam falha/timeout/quota/WAV/configuração, não endpoint real, licença/plano, qualidade ou latência primeira sentença.

### Riscos relevantes

Fila de áudio tem capacidade quatro e aging, mas um job ativo longo não é preemptado apenas porque ASR foi enfileirado. Qwen/ASR alternam descarregando workers para liberar RAM, podendo pagar reload repetido. TTS local tem timeout de até 600 s; áudio frio exige disponibilidade de 9 GiB + margem de 2 GiB, mas worker já quente não refaz a mesma admissão. Sem reserva agregada, a medição não garante memória futura.

Sono precisa cancelar fala da entidade e player, não aguardar texto/TTS velho. Autoplay negado exige clique e não é sucesso de reprodução. Não há ack durável de início/fim/cancelamento do player no histórico central. Voz de Alistair **não é capacidade atual**: ele está identificado como textual na UI; não acrescentar TTS para ele nesta rodada.

## 8. Qualidade do Resource Manager: notas A–S

Notas são julgamento de engenharia, não benchmark nem probabilidades. A evidência principal é [resource_manager.py](</home/gustavo/hoshino e lilith/app/core/resource_manager.py:39>), [gpu_resource.py](</home/gustavo/hoshino e lilith/app/core/gpu_resource.py:41>), [gpu_metrics.py](</home/gustavo/hoshino e lilith/app/core/gpu_metrics.py:9>) e os adaptadores de áudio/imagem. Cada nota considera as lacunas reais e falta de ensaio prolongado.

| Categoria | Nota /10 | Justificativa e obstáculo ao próximo nível |
|---|---:|---|
| A. Arquitetura | 6 | Um RM, banco/locks existentes, separação compute/residência. Ainda não reconcilia completamente cliente, daemon e memória física. |
| B. Segurança | 5 | Margem, flock, fail-closed de métricas, processo próprio. Falta confirmar término backend após perda do cliente. |
| C. Eficiência | 5 | Pesos quentes e fallback; custo previsto tem constantes, reload áudio recorrente e leituras síncronas. |
| D. Previsibilidade | 5 | Decisões/prazos explícitos, mas duração real não calibrada e prepare pode estender espera. |
| E. Ausência de starvation | 3 | GPU tem prioridade estrita sem aging; stream P0/P1 pode impedir P4/P5 indefinidamente. |
| F. Fairness | 4 | FIFO em empate; sem garantia de compartilhamento por entidade ou tempo máximo de espera. |
| G. Prioridade | 6 | P0–P5 muda admissão/ordem de verdade; não preempta LLM ativo e audio CPU usa outro lease. |
| H. Recuperação | 5 | Flock limpa cliente morto; registros stale removidos. Backend independente pode continuar; warm state pode estar desconhecido. |
| I. Telemetria | 6 | VRAM/busy/fila/lease/fallback/reload medido quando backend informa. Falta correlação completa, RAM/PSI/swap e playout. |
| J. Sob pressão | 3 | Não há reserva agregada RAM; imagem pula guarda RAM de staging; limites de backlog incompletos. |
| K. RAM | 4 | MemAvailable e margem corretos; worker TTS frio exige folga. Corridas e picos simultâneos sem contabilização conjunta. |
| L. VRAM | 6 | AMD real, hard cap e margem, serialização padrão. Estimativa workspace/contexto não cobre todos os picos. |
| M. CPU | 4 | CPU LLM serial e threads em workers; áudio pode competir, sem budget global de threads/carga. |
| N. GPU | 6 | Compute lease distinto de residência, concorrência desativada. GPU externa não participa do lock; TOCTOU permanece. |
| O. Modelos residentes | 6 | Observação `/api/ps`, TTL de conhecimento, stickiness. Não é inventário transacional real de RAM/VRAM. |
| P. 9B/7B | 5 | Não troca no meio do ciclo e mantém contexto/identidade. Ganho real e equivalência de estilo não demonstrados. |
| Q. Alistair oportunista | 6 | Não ganha GPU com prioridades H/L esperando; não expulsa modelos; CPU obrigatório. Job já iniciado pode atrasar chegada nova. |
| R. Qwen-Image | 4 | Job próprio, lease, valida saída, cede terminando subprocesso. RAM e coexistência com diálogo não calibradas. |
| S. TTS/ASR | 4 | Fila limitada, IDs, cancelamento e fallback. Latência local alta, reload alternado e contenda CPU/RAM. |

**Nota geral RM: 5/10 — experimental funcional, ainda não maduro para carga mista sustentada.** Não é média aritmética: pressão de RAM, recuperação backend e starvation impedem uma nota 6–7 mesmo com boas escolhas de VRAM.

## 9. Comparação de mecanismos com sistemas maduros

Não recomendo instalar nenhuma dessas infraestruturas. São referências de contratos, não uma lista de dependências. AIRI e Neuro SDK também não recebem certificado de robustez integral apenas por serem conhecidos.

| Nosso sistema | Mecanismo de referência | Diferença / risco real | Vale agora? Ajuste no sistema existente |
|---|---|---|---|
| Supervisor/Popen/flock, sono cooperativo | [Erlang/OTP supervision trees](https://www.erlang.org/docs/27/system/sup_princ.html): estratégias por filho, prazo e orçamento de restart | Ownership parcial; ponte não entra no fechamento; cooldown sem orçamento máximo explícito. Processo vivo/awake não é backend pronto. | **Sim:** fechar filho próprio, separar readiness e unload confirmado. Limitar retries de wake repetidamente falho; não adicionar supervisor paralelo. |
| Workers por conversa, locks e envelopes | [Akka delivery](https://doc.akka.io/libraries/akka-core/2.10.2/general/message-delivery-reliability.html) e [Orleans scheduling](https://learn.microsoft.com/en-us/dotnet/orleans/grains/request-scheduling): ordem delimitada e single-owner state | Não há ordem global entre autores; atributos globais da interface coexistem com workers. Aprendizado perde autoria apesar do envelope correto. | **Sim:** transportar autor/IDs até memória e contexto; auditar usos de estado global. Manter locks/processos atuais. |
| SQLite inbox + delivered/read + estados H/L | [RabbitMQ reliability](https://www.rabbitmq.com/docs/reliability): confirmação de publicação e ACK de consumo são coisas distintas | Commit do envio não comprova processamento; Alistair não segue desfechos duráveis. Crash pode repetir ou reter mensagem. | **Sim:** usar `processing_outcome` também em Alistair e documentar ACK. Usar SQLite, não instalar broker. |
| Dedup por ID/parent e retenção de incerteza | [NATS JetStream](https://docs.nats.io/concepts/jetstream): persistência, ACK e dedup com limites próprios | Dedup de mensagem não torna ação de jogo exactly-once; bridge não deduplica RPC. | **Sim:** propagar ID e estado incerto; vincular recibo a sessão. Não prometer exactly-once externo nem copiar JetStream. |
| Commit order no inbox e FIFO por chave | [Kafka design](https://kafka.apache.org/41/design/design/): ordenação em partição, offsets/replay delimitados | Relógios/processos/eventos não formam total order; cursor MC em RAM perde retomada automática. | **Agora documentar**, correlacionar parent IDs; replay seletivo de observações só se necessário, sem reexecutar mutações. |
| Pedidos VRAM/margem e limites backend | [Kubernetes resource requests/limits](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/) e [priority](https://kubernetes.io/docs/concepts/scheduling-eviction/pod-priority-preemption/) | Reserva/admissão não é limite físico garantido. RAM de múltiplos jobs não somada; prioridade não permite matar inferência arbitrariamente. | **Sim para RAM:** contabilizar reserva de staging nos leases existentes; manter serialização. Não Kubernetes. |
| GPU priority FIFO e stickiness | [Slurm multifactor priority](https://slurm.schedmd.com/priority_multifactor.html): idade/fair-share explícitos | Sem aging GPU, baixa prioridade pode nunca executar. Stickiness evita reload, mas pode reter espaço. | **Após medir espera:** aging limitado na fila atual, sem promover batch acima de interrupção; starvation diagnosticada agora. |
| Tokens lógicos GPU/CPU | [Ray logical resources](https://docs.ray.io/en/latest/ray-core/scheduling/resources.html): recursos de admissão não limitam threads/RSS automaticamente | `cpu_llm` não impede CPU audio usar núcleos nem limita RSS. Swap/PSI não entram no critério. | **Sim, pequeno:** medir host, limitar threads existentes e registrar pressão; reserva RAM agregada sem outro scheduler. |
| Pesos residentes separados de compute, keep_alive | [Ollama FAQ](https://docs.ollama.com/faq), [llama.cpp server](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md), [vLLM optimization](https://docs.vllm.ai/en/latest/configuration/optimization/) | Contexto/slots/KV têm custo além de pesos. Lease cliente não é slot backend. Custo textual 9B/7B não calibrado. | **Sim:** exigir término stream, observar modelo/slot depois de crash e medir cold/warm. Não introduzir vLLM/CUDA/batching novo. |
| Frases → job WAV → player serial | [WebRTC stats](https://www.w3.org/TR/webrtc-stats/): buffering e atraso de reprodução observáveis | Nosso caminho é clip HTTP/WAV, não RTP; não há jitter buffer WebRTC nem ack durável de playout. | **Sim:** registrar início/fim/stall/cancelamento no histórico existente. Não trocar o transporte por WebRTC. |
| WorkQueue Python de áudio, adaptada de AIRI | [AIRI load queue](https://raw.githubusercontent.com/moeru-ai/airi/main/packages/stage-ui/src/libs/inference/load-queue.ts): carga serial e AbortSignal; job ativo só para se o loader cooperar | Já aproveitamos o princípio. A fila local tem limite/aging; GPU usa outra política e áudio frio pode pagar reload. AIRI também mantém questões abertas de recursos. | **Manter:** consertar cancelamento/ownership e medir carga; não importar arquitetura inteira nem presumir que AIRI elimina esses riscos. |
| ActionWindow + validação + recibo/estado | [public Neuro SDK](https://github.com/VedalAI/neuro-sdk/blob/main/API/SPECIFICATION.md): action ID, resultado e sessão; contexto separado de ação | SDK público não revela mente/RM da Neuro. Seu ACK pode ser aceitação antes do efeito; isso não serve como prova externa de conclusão no nosso sistema. | **Sim:** separar accepted/executed/verified, IDs/sessão e eventos de término de fala. Não copiar recomendação de sucesso artificial para evitar retry. |

## 10. Aplicação simples, sem “enterprise cosplay”

Manter SQLite, locks, filas, processos e RM atuais. Nenhum problema encontrado exige Kafka, RabbitMQ, Redis, Ray, Kubernetes, microservices, service mesh, novo banco ou V2 paralela.

Princípios úteis: um dono por estado; IDs imutáveis; ACK com significado claro; confirmação antes de sucesso; limite/aging na fila existente; contabilização conjunta de recursos; prazo/cancelamento que não inventa término; reconciliação com processo/backend real; telemetria correlacionada.

## 11. As 25 perguntas do Resource Manager

As respostas abaixo referenciam principalmente [admissão/leases](</home/gustavo/hoshino e lilith/app/core/resource_manager.py:596>), [stale](</home/gustavo/hoshino e lilith/app/core/resource_manager.py:266>), [decisão GPU](</home/gustavo/hoshino e lilith/app/core/resource_manager.py:527>) e [residência](</home/gustavo/hoshino e lilith/app/core/gpu_resource.py:41>).

| Nº | Pergunta | Resposta individual |
|---:|---|---|
| 1 | Fonte única de verdade? | **Parcial.** Um RM e um registro SQLite, mas verdade de execução é flock/processo/backend e verdade de VRAM é sysfs. Não é um snapshot transacional único desses domínios. |
| 2 | RAM/SQLite/processo podem divergir? | **Sim.** Cache/contextvars/residência observada e daemon real têm ciclos distintos. Residência passa a unknown após observação envelhecer; não elimina todas as corridas. |
| 3 | Lease órfão? | **Registro sim, lock não após morte do dono.** SQLite pode guardar row stale; limpeza verifica flock. Backend independente pode continuar sem lease do cliente. |
| 4 | Crash deixa falsamente ocupado? | **Temporariamente sim** em registro até limpeza; flock impede expirar um job vivo só por TTL. Não há garantia de visualização imediata correta. |
| 5 | Crash libera recurso ainda usado? | **Pode, se o cliente morre e daemon continua.** Não foi provocado em GPU real; é lacuna de ownership/reconciliação identificada no código. |
| 6 | TOCTOU medir VRAM/iniciar? | **Sim.** SQLite/locks coordenam participantes locais, não aplicações externas nem todo pico de materialização; métricas são fotografias. |
| 7 | GPU externa? | **Parcial.** Uso/busy agregados entram; não pode reservar nem interromper Steam/browser/desktop. Uma aplicação pode crescer após medição. |
| 8 | Margem suficiente? | **768 MiB configurados, não comprovados sob carga.** É melhor que zero, mas KV/workspace/encoder/picos externos precisam medição; não chamar de suficiente universalmente. |
| 9 | Stickiness causa starvation? | **Pode contribuir.** P1 pode expulsar quente quando vantajoso; P2+ pode esperar stickiness renovada e fluxo interativo contínuo. |
| 10 | P0–P5 funciona? | **Sim na admissão e FIFO por prioridade; não só metadata.** Não preempta inferência ativa. ASR/TTS atuais são CPU com lease próprio, não GPU P0 real. |
| 11 | Aging? | **Não na fila GPU P0–P5. Sim na WorkQueue de áudio/PC2.** Não confundir as filas. |
| 12 | Baixa prioridade nunca executar? | **Sim, possível** com chegada contínua de prioridade maior. Deadline termina espera, mas timeout não é fairness. |
| 13 | Modelo residente bloqueia mais importante? | **Temporariamente sim.** Manutenção tenta unload seguro de peers quando preciso, considerando prioridade/custo; métricas incertas/unload lento atrasam. |
| 14 | Unload/reload medido? | **Parcial.** Timing backend `load_duration` grava reload quando disponível, com default heurístico. Não há baseline completo por workload/cold/warm e p95 da troca. |
| 15 | CPU fallback satura RAM? | **Pode.** Checa MemAvailable + modelo/folga e serializa CPU LLM, mas áudio/imagem/staging de outros jobs não têm reserva agregada suficiente. |
| 16 | Swap degrada sem perceber? | **Sim.** Não é contabilizado como RAM, corretamente; PSI/swapin/out/thrashing não influenciam a decisão. Swap ativo não equivale a desempenho normal. |
| 17 | ASR/TTS competem com Alistair? | **Sim em CPU/RAM.** Leases diferentes e threads limitadas individualmente não são budget global. GPU oportunista vê áudio, CPU fallback pode competir. |
| 18 | Alistair atrasa Hoshino? | **Pode se já admitido.** Pedido novo prioritário impede nova concessão oportunista, mas não cancela inferência Alistair no meio. CPU também pode disputar host. |
| 19 | Imagem atrasa fala? | **Pode.** Cede quando detecta espera prioritária/áudio a cada ~2 s, depois precisa encerrar subprocesso; RAM e tempo de unwind também afetam áudio. |
| 20 | Cancelamento imagem seguro? | **Razoável por ownership:** termina processo criado/guardião, não processo terceiro; não finge pause/resume. Segurança RADV/reset e liberação efetiva sob carga ainda não validadas. |
| 21 | Backpressure? | **Parcial.** Áudio limitado a 4, imagem a 2, PC2 a 2; conversas/banco e pedidos GPU não têm limite total explícito. |
| 22 | Fila possui limite? | **Depende da fila.** Os limites acima existem; `gpu_requests` e deques/históricos de conversas podem crescer. Paginação de inbox não é limite de admissão. |
| 23 | Overload diagnosticado? | **Parcial.** Full/timeout/falha de admissão e fila aparecem; não existe um diagnóstico agregado de overload/PSI/idade do backlog com objetivo de latência. |
| 24 | Degradação graciosa? | **Parcial e real.** Serialização/CPU/provider local preservados; RAM insuficiente falha sem sucesso fictício. Não há garantia de SLA durante pressão conjunta. |
| 25 | Recovery após crash? | **Parcial.** Stale por flock, presença e jobs com stamp, mensagens retidas H/L; falta reconciliação daemon e paridade Alistair. Recovery mental completo após restart não ensaiado. |

## 12. Pressão de memória e swaps

Não executei pressão artificial no PC real. O snapshot tem folga, mas o cenário somado não está admitido como seguro.

| Componente | Evidência/estimativa | Risco na soma |
|---|---|---|
| 9B residente | Probe anterior reportou ~6,0 GB `size_vram` por entidade | Dois 9B não cabem juntos em 8 GiB; contexto/workspace precisam folga |
| 7B carregando | Cada peso leve tem 4.683.073.952 bytes em disco | Tamanho de disco não é RSS nem pico de load; staging pode coexistir com 9B |
| Alistair 4B | Probe CPU anterior `size` ~3,18 GB; size_vram=0 | CPU libera VRAM, não elimina RAM/threads |
| Qwen TTS | Guarda existente exige 9 GiB + 2 GiB de folga para startup | Não reserva essa RAM globalmente; worker quente passa antes da guarda |
| ASR large-v3 int8 | CPU; modelo e buffers de áudio residentes | RSS conjunto não medido no cenário completo; alternância pode fazer reload |
| Qwen-Image + encoder + VAE | Arquivos somam ~11,66 GiB no disco | Não é medição de RSS; offload CPU/staging/picos precisam orçamento. Image pula guarda RAM de staging do RM |
| UI/sistema/desktop/apps | Aproximadamente 7,75 GiB usados no snapshot | GPU/RAM externos variam; Minecraft humano acrescenta carga CPU/RAM/GPU |

Evidências: [guarda TTS](</home/gustavo/hoshino e lilith/app/core/audio_service.py:70>), [staging](</home/gustavo/hoshino e lilith/app/core/resource_manager.py:668>), [imagem](</home/gustavo/hoshino e lilith/app/tools/image_gen.py:124>) e [probe modelos](</home/gustavo/hoshino e lilith/docs/verificacao_tres_modelos_20261006.json>).

**Conclusão:** alto risco de stalls/thrashing ou OOM no cenário combinado máximo, sem dados que permitam quantificar probabilidade. Não somar esses números como se todos fossem RSS exatos, mas também não presumir que offload resolve. 8 GiB swap é amortecedor, não 8 GiB adicionais rápidos. Margem livre instantânea pode ser consumida simultaneamente por vários admitidos.

Para a primeira sessão proposta, **não incluir imagem/batch**, que não constam do roteiro humano. Manter GPU serial, iniciar entidades sequencialmente, observar RAM disponível/swap/filas, limitar contexto existente de acordo com medições e impedir carga TTS se a guarda negar. Não baixar/trocar modelo para remediar latência.

## 13. Ensaios antes da sessão humana

Proposta; não executados como nova carga real nesta auditoria. Cada teste usa capacidades já existentes, artefatos temporários e critérios mecânicos. Evitar pressionar RAM até OOM, mundos importantes ou mutações externas irreversíveis.

| Ensaio | Local/isolamento | Critério de aprovação |
|---|---|---|
| 50 mensagens comuns rápidas | Workers reais, LLM falso, SQLite temporário | 50 entradas/50 desfechos, FIFO por chave, zero desaparecimento/duplicação, inflight limpo, limite/backpressure verificável |
| 500 envelopes, quatro autores/dormindo | Bus real em DB temporário | Authorship/recipient/reply_to íntegros, inbox paginado sem starvation, wake não duplica, commit order auditável |
| 100 correções/STOP/cancelamentos | Worker/modelo/tools simulados | Só intenção superseded não executa; dependência não some; thread mutável não é repetida se incerta |
| Crash worker antes/depois de efeito | Subprocesso próprio + efeito em arquivo temporário | Estado processing/uncertain durável; reinício não repete mutação; diagnóstico aponta pedido |
| Apresentações + restart de fixture | Três DBs temporários e autores reais do envelope | Gustavo permanece sujeito correto; Alistair/Lilith não substituem humano; tipos/fontes/evidências permanecem; conhecimento não atravessa DBs |
| Streams EOF, erro, lento, deadline, tool delta | HTTP fake/mock sem modelos | Nunca finalizar stream incompleto; não executar tool call parcial; parar speech stream correspondente |
| 7B/9B: 20 turnos fixos alternados | Depois das correções, um modelo por vez no PC principal | Mesma identidade/contexto, nenhum switch no ciclo; coletar cold/warm, p50/p95, load/infer/queue/RAM/VRAM, avaliar estilo em PT |
| Alistair CPU/GPU e áudio aguardando | Ensaio real controlado próprio | GPU negada quando H/L ou áudio aguardam; CPU funciona; medir quanto inferência já ativa atrasa novo humano |
| Imagem + chegada diálogo/áudio | Sessão separada, imagem descartável | Yield/terminação própria, sem pause/resume fictício; lease e VRAM liberam; prompt/resposta continuam corretos |
| TTS 10 frases + 20 cancelamentos | Mocks primeiro; depois local real sem capturar humano | Índices/voz/provider corretos; fala velha não reproduz; arquivo válido; nenhum worker/lease órfão |
| Falha/timeout/quota remota | Só mock na CI | Qwen fallback ou cancelamento correto; segredos ausentes; nenhum gasto real |
| Backlog P1 e P5 antigo | RM com relógio/métricas simulados | Evidenciar starvation atual; após eventual ajuste, limite de espera sem prejudicar P0 e sem OOM |
| Pressão de RAM simulada | Mock MemAvailable/PSI antes de real | Negar novas cargas quando incerto; reservas agregadas não excedem orçamento; swap não vira RAM rápida |
| Uso prolongado 60–120 min | Só após gates, carga pequena e controlada | Amostras periódicas RSS/VRAM/threads/FDs/filas; crescimento estabiliza; ausência de deadlock; shutdown/restart com fatos recuperáveis |

Ensaios GPU A–I continuam necessários: H9B, H7B, L9B, L7B, Alistair CPU, Alistair GPU, imagem, imagem+conversa, áudio+jobs. Não transformar probes de poucas palavras em calibração completa. Para comparação antes/depois, usar mesmo workload e medir CPU/GPU/RAM/VRAM/latência/resultado funcional. Verificar registros RADV/amdgpu acessíveis; falta de acesso a logs de kernel não prova ausência de reset.

## 14. Observabilidade: dá para reconstruir a sessão?

**Parcialmente, não de ponta a ponta sem lacunas.** O [diagnostics](</home/gustavo/hoshino e lilith/app/core/diagnostics.py:178>) usa ContextVar de turn ID e espelha eventos no histórico SQLite existente; threads via `to_thread` recebem contexto. Espelhamento pode falhar silenciosamente, enquanto JSONL permanece. Não criar outro coletor/banco.

| Elemento | Presente? | Lacuna/correção mínima |
|---|---|---|
| Turn ID | Sim H/L | Evento turn-start não inclui IDs das entradas selecionadas; Alistair não usa o mesmo contexto |
| Message ID / submission ID | Sim envelope/histórico | Message ID retornado pelo histórico não é encadeado explicitamente à criação do turno |
| Request ID / parent ID | Sim chamadas/RPC/bus | Tool receipt ID e MC RPC ID não são unidos explicitamente em todo caminho; bridge ignora parent/entity |
| Entidade / origem / timestamp | Sim na maior parte | Escriba/episódios perdem autor; evento físico e commit têm relógios distintos |
| Executor 7B/9B | Sim `executor.selected` | Correlacionado por turn onde contexto existe; timing incompleto quando stream termina sem done |
| Provider TTS / voz / latência | Sim router/job | Síntese não comprova playback; falta correlacionar ack do browser ao turno |
| Compute lease / fila / prioridade | Sim token e eventos | Turn ID herdado em H/L, mas não input IDs; fallback/recovery Alistair parcialmente fora desse vínculo |
| Tool call / receipt / incerto | Sim dispatch/job_bus | Sessão Minecraft/estado de mundo não plenamente ligados ao recibo; não existe dedup backend |
| Cancelamento | Sim eventos/jobs/revisões | Pedido cooperativo não equivale a término físico; player não persiste cancelamento completo |
| Memória gravada | IDs/recibos existem | Escriba descarta IDs como evidência de origem; não liga memória a mensagem/turno de forma suficiente |

Refinamento recomendado: acrescentar IDs de entrada no contexto de turno existente; anexar source IDs aos `links` existentes da memória; emitir IDs gravados após commit; passar tool ID → RPC parent/request/session no diagnóstico; usar eventos atuais de áudio/histórico para playout start/end/cancel/stall. Não registrar segredos e não confundir síntese/aceitação com execução/verificação.

## 15. Maturidade por componente

Escala solicitada: 0–2 protótipo frágil; 3–4 protótipo funcional; 5–6 experimental sólido; 7–8 maduro para uso pessoal; 9 produção muito robusta; 10 infraestrutura crítica.

| Componente | Nota /10 | Por que não merece o próximo nível |
|---|---:|---|
| Arquitetura | 6 | Separação entidade/executor boa; autoria não atravessa todos os consumidores e lifecycle de filhos incompleto |
| Mensageria | 6 | SQLite/ACK/dedup/revisões bons; recuperação Alistair e overload ainda divergentes |
| Persistência | 6 | Commit/rollback/diagnóstico e bancos legíveis; múltiplos commits de aprendizado sem confirmação final coordenada |
| Memória | 3 | Há categorias e confiança corretas, mas apresentações corrompem sujeito e episódios rotulam entidade errada |
| Resource Manager | 5 | Sem calibração conjunta RAM/CPU/GPU e sem aging/reconciliação completa |
| Lifecycle | 5 | Drenagem com prazo/ownership parcial; fala/ponte/unload não fecham contrato inteiro |
| Ferramentas | 6 | Diário antes/depois, verificação e incerteza; adaptadores textuais/bridge ainda não garantem término físico |
| Voz | 4 | Worker local real funciona, mas lento; microfone/playback/providers reais não aprovados integradamente |
| Minecraft | 3 | Adaptador implementado, descoberta LAN defeituosa e races de conexão; jogo real não validado |
| Observabilidade | 6 | Muito diagnóstico útil, ainda sem cadeia completa input → turno → efeito → memória → áudio ouvido |
| Testabilidade | 7 | Boa suíte isolada, histórico reconciliado, hardware separado; fixtures ocultam autoria real e faltam soak/crash completos |
| Recuperação de falhas | 5 | Locks/estado incerto úteis; cliente/daemon/Alistair e aprendizado não reconciliados integralmente |
| Uso prolongado | 3 | Não há ensaio longo que descarte leaks, starvation, thrashing e crescimento de histórico/fila |

Não há nota 8–9 porque não existe evidência de uso integrado sustentado que sustente essas notas. **A classificação global fica em protótipo funcional avançado/experimental**, limitada por memória e Minecraft, não pela média das tabelas.

### Validações reais anteriores e pendências

- [Três modelos](</home/gustavo/hoshino e lilith/docs/verificacao_tres_modelos_20261006.json>): H9B 5,5 s, L9B 5,65 s, Alistair CPU 10,84 s em respostas mínimas. Não são benchmark de primeira interação completa.
- [Executores leves](</home/gustavo/hoshino e lilith/docs/EXECUTORES_20261006.md>): probes GPU H/L7B e Alistair GPU/CPU registrados; não aprovam naturalidade ou ganho em conversa normal.
- [Imagem + standby](</home/gustavo/hoshino e lilith/docs/verificacao_imagem_standby_20261006.json>): imagem real 768×768/16 steps em 209,6 s, Alistair CPU respondeu enquanto imagem mantinha lease GPU. **Não prova** conversa GPU chegando/preempção, TTS simultâneo ou concorrência agressiva segura.
- [PC2](</home/gustavo/hoshino e lilith/docs/verificacao_pc2_20261006.json>): pacote/CPU foram testados no PC principal; documento declara **NOT Athlon**, real LAN/PC2 não testados. Modelo/identidade/banco continuam no dono da entidade; pacote não inclui mente privada. Athlon físico boot/HDD/RAM/LAN/auth/timeouts/restart/YouTube/soak continuam pendentes.
- Áudio local tem probe real sintético; **microfone e reprodução humanos pendentes**. ElevenLabs real pendente; Azure real não comprovado.
- Naturalidade H/L: sem avaliação repetível completa das situações emocionais/correções/memória/estilo entre 7B e 9B. Corrigir contexto/autoria antes de atribuir falhas à família de checkpoint.

Essas pendências reais não são, por si, bloqueadores: o primeiro teste humano existe para medi-las. Defeitos determinísticos já identificados é que devem sair do caminho antes.

## 16. Gate e prioridade

**PODEMOS INICIAR O TESTE MANUAL AGORA? NÃO, EXISTEM BLOQUEADORES.**

| Classe | Item | Justificativa |
|---|---|---|
| BLOQUEADOR | Autoria nas memórias + rótulos episódicos | Os passos 2–8 semeiam identidade/usuário incorretos; probe confirma substituição. Contamina a própria evidência do teste e do restart. |
| BLOQUEADOR para LAN automática | Parser do anúncio Java | O pacote padrão é descartado; passo 11–12 não conecta pela rota planejada. Contorno manual host/port reduz esse bloqueio, não resolve memória. |
| DEVE SER CORRIGIDO ANTES | EOF LLM sem done | Resposta incompleta vira concluída; pode poluir resposta/áudio/aprendizado e normalizar ferramentas parciais. |
| DEVE SER CORRIGIDO ANTES | Alistair: autoria explícita + estados de processamento | Primeiro interlocutor tem retry/recovery diferente; erro/crash não retém incerteza no contrato comum. |
| DEVE SER CORRIGIDO ANTES | Sono encerra fala e ponte própria; unload não confirmado visível | Roteiro inclui dormir e shutdown; entidade pode continuar falante/conectada ou parecer liberada sem confirmação. |
| DEVE SER CORRIGIDO ANTES | Bridge: setup failed ≠ ready; callbacks vinculados à própria sessão | Conexão falsa e evento antigo podem tornar o ensaio básico enganoso, sem exigir mundo real para encontrar o defeito. |
| DEVE SER CORRIGIDO ANTES | Proveniência/IDs mínimos do turno e memória | Sem isso, fica difícil explicar depois o que foi aprendido por qual mensagem. Usar telemetria/links existentes. |
| DEVE SER CORRIGIDO ANTES do critério “Alistair lembra” | Recuperação de informação antiga fora de quatro turnos | Persistir histórico não garante lembrar fatos importantes da sessão; contrato deve ser exercitado/reconciliado na tabela existente. |
| PODE SER OBSERVADO DURANTE | Voz local lenta, sotaque, autoplay, captura física; estilo 7B/9B | Limitações honestamente visíveis; não exigem novos providers/modelos. Texto permanece fallback. |
| PODE SER OBSERVADO DURANTE | Latência de troca, espera Alistair já ativo, memória após restart | Ensaiar sequencialmente com limites e diagnóstico; não habilitar GPU concorrente. |
| PODE SER OBSERVADO DURANTE | Ações curtas MC, inventário, dano/reconexão | Depois das correções, mundo de teste e efeitos pequenos; incerteza nunca vira retry automático. |
| PODE FICAR PARA DEPOIS da primeira sessão | Fair-share/aging calibrado, pressão máxima com imagem, soak longo, refatoração maior | Não necessário para sessão pequena sem imagem; não marcar pronto para carga sustentada. |
| PODE FICAR PARA DEPOIS se não fizer parte da sessão | Athlon físico e ElevenLabs/Azure reais | Não são requisito para Alistair local + texto/local fallback; seguem explicitamente não aprovados. |

## 17. Correções mínimas propostas, risco, arquivos e testes

**Aguardam aprovação. Nenhuma foi implementada aqui.** Não proponho alterações amplas nem novos módulos de capacidade.

| Rodada pequena | Correção | Arquivos/consumidores previstos | Risco de alteração | Regressões necessárias |
|---|---|---|---|---|
| R1 — prioridade máxima | Autor/sujeito/evidência no aprendizado; nome da entidade nos episódios; compactação preserva autoria | `app/main.py`, `app/mind/scribe.py`, `app/core/compaction.py`; `knowledge_store.py` somente se campos existentes exigirem compatibilidade. Consumidores pós-turno/extração/compactação/ferramentas/testes mapeados por busca. | **Médio:** aprendizado é transversal; manter API compatível, não migrar dados cegamente | Gustavo/Alistair/Lilith, citação/roleplay/pergunta; mesma chave por sujeitos diferentes; origem/0.0/None; reflexão; episódios de ambas; restart; três DBs independentes |
| R2 — independente | Parser LAN Java e anúncio inválido/duplicado | `app/tools/minecraft.py`; chamadas dispatcher/atalho UI já existentes | **Baixo:** parser isolado; manter erro explícito e host/port manual | Pacote padrão, Unicode, porta inválida, timeout, duplicado, múltiplos mundos; não validar com socket/mock não-Java |
| R3 — stream | Exigir término confirmado e diagnosticar erro/incompleto; invalidar speech stream correspondente | `app/main.py` streaming e consumidores `chamar_modelo`, speech stream; mesmas fixtures HTTP | **Baixo–médio:** afeta retorno do backend; não reexecutar ferramentas por falha | EOF parcial/erro/done, tool delta incompleto, deadline, chunks estáveis, nenhum sucesso/execução parcial |
| R4 — Alistair | Usar processing/outcome existente, autoria no prompt e recuperar informação relevante no histórico próprio | `app/alistair_runner.py`, consumidores `core/interentity.py` e banco/tabela `alistair_turns` existentes | **Médio:** não adicionar sistema mental; distinguir record/retrieve da qualidade LLM | Crash antes/depois de chat/send; mesma source ID; erro/incerto sem replay mutável; dez falhas não escondem nova mensagem; fato antigo após >4 turnos/restart |
| R5 — lifecycle | Cancelar fala própria ao dormir; fechar ponte somente se owned; expor unload não confirmado | `iniciar_entidades.py`, `app/ui/central.html`, `app/main.py`, `app/entity_runner.py`; métodos atuais `audio_service`/`minecraft_launcher` | **Médio:** shared áudio, não afetar outra entidade; não matar por nome | H dorme/L fala; ASR separado; job mutável lento/incerto; ponte própria versus externa; unload false; drain/restart sem leases falsos |
| R6 — bridge | Setup failure não vira ready; callbacks/estado pertencem ao bot/sessão correto; correlacionar IDs existentes | `compartilhado/servicos/minecraft/bridge.js`, RPC Python se exigir contrato compatível | **Médio:** mudanças pequenas no estado de conexão, sem reescrever bridge | Fake bot antigo termina após novo spawn; setup falha; request/parent/entity/session corretos; timeout/stop incerto; não confiar em recibo estrangeiro |
| R7 — rastreabilidade | Input IDs → turn context → tool/RPC → memória/áudio, usando history/diagnostics/links atuais | `app/main.py`, `app/core/diagnostics.py`, `app/mind/scribe.py`, consumidores anteriores; UI se acrescentar eventos de playout | **Baixo–médio:** schema de evento pode afetar leitores | Reconstrução automática de um turno misto; IDs íntegros após restart; sem segredos; síntese ≠ playback |

Após R1–R7: rodar suíte oficial novamente, adicionar regressões aos grupos existentes, executar cargas offline pequenas e uma pré-verificação real **não humana** controlada dos backends/ponte. Então revisar gate para **SIM, com limitações explícitas**; a sessão humana mede voz, naturalidade, Minecraft e continuidade que não podem ser fingidos por mocks.

Separadamente, sem bloquear por perfeccionismo, refinamentos RM recomendados depois de dados: admissão RAM agregada/staging incluindo imagem, reconciliação pós-crash de daemon, limite de backlog com recusa explícita sem descartar FIFO, diagnósticos de idade/starvation/PSI/swap e aging restrito. Arquivos atuais: `resource_manager.py`, `gpu_resource.py`, `gpu_metrics.py`, `audio_service.py`, `image_gen.py`, testes correspondentes. Risco **médio**, porque mudam admissões/fallback/latência; não calibrar por palpite.

### Alterações e comportamentos nesta rodada

- Arquivo acrescentado: este relatório.
- Implementação/configurações/modelos/bancos: **nenhuma alteração intencional**.
- Bugs corrigidos nesta rodada: **nenhum**; são diagnóstico e propostas, conforme solicitado.
- Testes permanentes novos: **nenhum**; dois cenários e quatro probes adicionais foram temporários/isolados.
- Comportamento antigo alterado: **nenhum**.
- Regressões/defeitos encontrados: autoria aprendida, rótulo episódico, LAN e EOF reproduzidos; lifecycle/bridge/Alistair/recursos têm lacunas de código descritas com nível de evidência.
- Próxima prioridade dentro do escopo congelado: **R1 autoria e R2 LAN**, seguidas de stream/lifecycle/Alistair/bridge e correlação mínima. Nenhum novo modelo/capacidade/cloud é necessário.

O projeto tem uma base útil e várias proteções reais. Ainda não está pronto para chamar o primeiro encontro integrado de aprovado: o problema principal não é quantidade de recursos, e sim preservar quem disse o quê, saber quando algo realmente terminou e conseguir recuperar isso depois.
