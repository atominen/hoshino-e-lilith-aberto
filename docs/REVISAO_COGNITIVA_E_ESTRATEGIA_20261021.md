# Revisão do sistema cognitivo e estratégia de refinamento — 21/10/2026

## Resultado e escopo

O projeto já tem os componentes necessários para experimentar convivência
persistente entre três entidades distintas. O investimento prioritário agora
é melhorar a qualidade da informação que chega aos modelos, a estabilidade das
atualizações mentais e a medição da experiência. Aumentar o número de componentes,
o contexto ou as horas de treino não resolve automaticamente esses problemas.

Esta entrega é **auditoria e proposta técnica**, com sondas reproduzíveis.
Não altera o comportamento da produção. Fontes: código da árvore local, decisões
recentes, planejamento histórico e pesquisas primárias consultadas nesta data.
HEAD `6441a7c275519af7dc00d004ca1b13334ab69e9f`, com alterações locais extensas
preservadas; HEAD sozinho não identifica o código analisado. A sonda registra
SHA-256 dos arquivos que executa parcialmente.

Não foram examinadas conversas pessoais para alimentar pesquisa externa. Não
houve inferência real, professor, treinamento, instalação, migração de banco,
mudança de identidade/configuração, restart, publicação ou leitura dos bancos
mentais reais nesta auditoria. Os testes existentes usam fixtures temporárias.
Latência de modelos, qualidade subjetiva e funcionamento físico não foram
medidos nesta rodada. A revisão cobre caminhos centrais, não todas as linhas
nem todos os serviços do repositório.

## 1. Objetivo que orienta as decisões

Interpretação das decisões registradas, priorizando as mais recentes:

- Hoshino e Lilith: companheiras locais com identidades próprias, lembranças
  persistentes, relações e preferências que evoluem com experiências atribuídas;
  conversam naturalmente e usam capacidades existentes quando pertinente.
- Alistair: organizador textual com continuidade e identidade próprias. Sua
  execução pode estar no Xbox, mantendo o estado canônico no PC. Não precisa
  duplicar todo o sistema psicológico das outras duas.
- Comunicação global visível e conversas diretas com autoria correta. Todas as
  entidades acordadas recebem o global; receber não exige três respostas iguais.
- Conhecimento editável, com origem e possibilidade de correção/esquecimento;
  iniciativa útil e silêncio válido, sem comportamento repetitivo.
- Infraestrutura compartilhada e mentes separadas. Interface simples, controle
  humano e uso eficiente do hardware existente.

Referências locais: `README.md`, `ESCOPO_CONGELADO.md`,
`docs/planejamento/11111_20261006_referencia.txt`,
`docs/CHAT_GLOBAL_CONHECIMENTO_AUDIO_20261020.md` e relatórios posteriores.
O planejamento antigo registra intenções e hipóteses, não comprova implementação.
Os estados chamados emoções/traços são mecanismos computacionais; seus nomes
não demonstram experiência subjetiva nem validam um modelo psicológico humano.

## 2. O que existe e deve ser aproveitado

| Camada | Evidência no código | Avaliação |
|---|---|---|
| Identidade e personalidade | `core/prompting.py`, `mind/personality.py`, identidade por entidade | Separação útil; a atualização de traços precisa de evidência melhor |
| Humor, emoções e estado médio | `mind/affect.py`, `emotions.py`, `psych_state.py` | Tempos distintos já existem; constantes e rótulos precisam de calibração comportamental |
| Histórico e episódios | `core/history.py`, `main.py:salvar_episodio`, tabelas próprias | Histórico com FTS5 e referências existentes; não criar outro histórico |
| Conhecimento | `memory/knowledge_store.py`, `records.py`, SQLite + Chroma opcional | Categorias, confiança, versões e fontes já existem; corrigir seleção e substituição |
| Reflexão, diário e modelos conceituais | `mind/reflection.py`, `daily_summary.py`, `memory/cognitive_notes.py` | Lições condicionais e referências são boas bases; reflexão continua interpretação |
| Contexto | `main.py:contexto_do_turno`, `core/compaction.py` | Orçamento, omissões explícitas e resumo por fio existem; medir a composição completa |
| Ação | `core/cognition.py`, `task_state.py`, `dispatch.py`, `capabilities.py` | Estado e recibos verificáveis são preferíveis a aceitar declarações de sucesso do LLM |
| Iniciativa | `core/kernel.py`, `autonomy.py`, `mind/drives.py` | Âncoras, silêncio, cooldowns e quotas já existem; não adicionar outro scheduler |
| Interações | `core/interentity.py` | Autoria, deduplicação, fanout e teto de seis saltos já existem |
| Alistair | `alistair_runner.py`, `core/alistair_continuity.py` | Caminho leve deliberado; busca e continuidade têm limites próprios |
| Permissões | `core/ui_policy.py`, `entity_access.py` | Política executável e guardas existentes; controle irrestrito de desktop não equivale a sandbox |
| Professor | `laboratorio/professor_schema.py`, `professor_moe.py` | Feedback humano separado de aprovação de treino; manter essa distinção |

O sistema já se parece mais com um agente persistente do que com um prompt
isolado. A quantidade de módulos não é medida de inteligência. A qualidade
depende do ciclo completo: origem → registro → recuperação → resposta → efeito
verificado → revisão.

## 3. Achados prioritários

### A. Memórias compatíveis podem se substituir — reproduzido

`knowledge_store.remember` considera conflito a mesma chave ou semelhança
lexical de pelo menos 0,75, após verificações de tipo/participante/entidades.
Semelhança lexical não determina contradição.

Sonda com funções reais e SQLite em RAM:

- “A pessoa gosta de café brasileiro forte sem açúcar pela manhã.”
- “A pessoa gosta de café brasileiro forte sem açúcar pela noite.”

Semelhança **0,8**; a primeira foi marcada `superseded`. As duas podem ser
verdadeiras. O texto anterior não foi apagado fisicamente, mas saiu da busca
ativa. Isso afeta o objetivo central de acumular experiências sem perder fatos.

**Refinamento:** semelhança gera candidato a comparação/deduplicação, não
substituição. Uma substituição exige mesmo sujeito, atributo, contexto/condição
e evidência de atualização. Preferências multivaloradas coexistem. Ambiguidades
ficam como versões concorrentes até resolução, sem chamar o professor por fato.
Correções explícitas mantêm a cadeia anterior e sua fonte.

### B. Recuperação aceita irrelevância e varre toda a memória — reproduzido/estático

`recall` lê todas as memórias e propriedades ativas, calcula scores em Python,
ordena tudo e atualiza contadores de acesso. A aceitação é `sim > 0.05 OR
score > 0.45`: recência, confiança e uso podem compensar falta de relevância.

Na sonda, “Qual a capital da Mongólia?” recuperou “A bicicleta é vermelha.”,
com distância vetorial sintética **100**, confiança 1 e dez acessos prévios.
Isso reproduz o limiar, não mede a distribuição real dos embeddings instalados.

**Refinamento:** primeiro filtrar elegibilidade e relevância, depois ranquear.
Buscar candidatos limitados por lexical/FTS e vetor, cruzar com o estado atual
do SQLite, combinar rankings e aplicar diversidade. “Nenhuma lembrança
pertinente” deve ser resultado válido. Uso frequente não constitui confirmação
nem deve criar um ciclo de autorreforço. Medir o custo das escritas de acesso.
O FTS de histórico já existe; eventual índice do conhecimento deve permanecer
no armazenamento existente e passar por migração em cópia.

### C. Recência trata datas equivalentes de forma diferente — reproduzido

`knowledge_store._recencia` subtrai `datetime.now()` sem fuso de uma data que
pode ter fuso. O `TypeError` retorna 0,5. A sonda deu aproximadamente **1,0**
para agora sem fuso e **0,5** para o mesmo instante UTC com fuso. O projeto já
tem utilitários temporais em `core/history.py`.

**Refinamento:** reutilizar esses utilitários; distinguir instante registrado,
período de validade e origem legada. Não converter datas antigas às cegas.
Testar limites de dia, fuso, correção tardia e pergunta “o que era verdade antes?”.

### D. Separação de histórico não garante separação da lembrança — lacuna estática

O global possui regras próprias de histórico. Entretanto,
`main.contexto_do_turno` recupera episódios e conhecimento sem argumento de
audiência; `scribe.origem_entrada` registra autor/canal, mas não transporta
explicitamente `chat_scope` como política de divulgação. Alistair filtra suas
citações de histórico público, mas `knowledge_editor.context` também não recebe
essa audiência. Diário privado possui proteções específicas e não deve ser
confundido com qualquer conversa direta.

**Risco:** informação aprendida no direto pode entrar no contexto de uma resposta
global. Não foi demonstrado vazamento ponta a ponta nem lida informação privada.

**Refinamento prioritário:** definir audiência na recuperação de episódios,
fatos, propriedades, resumos e ferramentas de consulta. Informação reservada
deve continuar reservada em seus derivados. Origem desconhecida não implica
permissão pública. Usar sentinelas sintéticas em testes direto/global/Discord;
interações entre entidades continuam visíveis conforme a decisão do usuário.
Não substituir controles por uma frase de privacidade no prompt.

### E. Evolução da personalidade mede sinais frágeis — reproduzido/estático

Em `scribe.evidencias_do_comportamento`, qualquer pergunta gera curiosidade;
expressões e comprimento geram calor, humor, franqueza e concisão. Exemplos
reproduzidos: “Não entendi. Pode repetir?” aumenta a evidência de curiosidade;
uma citação contendo “senti falta” conta como demonstração de afeto.
Uma crítica ao software é classificada como crítica e `pos_turno` a encaminha
ao estado afetivo sem determinar o alvo.

Além disso, `registrar_achados` transforma um gosto declarado pelo usuário em
gosto da própria entidade, com valência multiplicada por **0,4**, origem
`usuario` e categoria `herdado`. Isso favorece convergência das duas entidades
às preferências do usuário. É uma estratégia implementada, não uma lei de
aprendizado social demonstrada.

**Refinamento:** separar “sei que você gosta” de “eu gosto”; guardar observação
e influência social sem consolidar automaticamente preferência própria.
Traços devem considerar contexto, autoria, resultado e variedade de situações;
texto gerado serve como sinal fraco. Limitar contribuição por evento/sessão,
evitar contar a mesma experiência na resposta, resumo e reflexão, registrar
motivo revisável e permitir reversão. A emoção de curto prazo não deve
reescrever identidade. Não apagar gostos/traços existentes para aplicar isso.

### F. Importância visual ainda não é prioridade cognitiva — confirmado no código

Ferro/Ouro/Diamante/Platina ficam em `memory_card_settings`. A consulta normal
de conhecimento não lê essa tabela; `importance` também não entra na fórmula
atual de `recall`. O controle visual funciona como anotação, não como garantia
de que uma memória será lembrada antes.

**Refinamento:** importância humana pode desempatar lembranças relevantes e
reservar uma parcela limitada do contexto. Não deve sobrepor audiência,
validade ou relevância, nem aumentar confiança/veracidade. Platina não torna
um fato falso verdadeiro e não significa “colocar sempre no prompt”.

### G. Alistair tem um caminho de memória limitado — limite explícito, não paridade

`recall_history` consulta até 2.000 turnos do remetente + primeiro contato,
recupera até oito citações com orçamento de 3.600 caracteres e mantém quatro
turnos recentes. `knowledge_editor.context` examina os últimos 50 registros
por tabela antes de filtrar e seleciona três. Muitos registros inativos recentes
podem esconder registros ativos antigos dessa janela. O tratamento especial
de tipos usa `rule/relation`, enquanto o vocabulário canônico também usa
`regra/relacao`.

**Refinamento:** contrato comum de origem, validade e consulta paginada para os
três, mantendo o orçamento menor do 4B. Extrair o leitor da camada de edição
da UI quando houver um consumidor comum claro. Índice e busca no PC; enviar ao
Xbox somente contexto pertinente. Não confundir executor residente com contexto
ilimitado nem forçar todo o pipeline psicológico no Alistair.

### H. Custo de manutenção e de contexto — hipótese mensurável

H/L agendam extração de memória depois de cada turno não autônomo; a função
só elimina entradas ausentes ou menores que 12 caracteres, consultando conhecido
e pedindo inferência P5. Já há prioridade e orçamento no RM; falta demonstrar
quanto trabalho é redundante no uso real. Não afirmar que essas tarefas já
causaram starvation sem medir.

**Refinamento:** seleção conservadora de candidatos a extração, deduplicação
por IDs e lotes limitados no mecanismo existente, mantendo nomes/correções/
compromissos importantes imediatos. Nunca perder cobertura por cancelar lote.
Medir falhas de extração antes de reduzir chamadas.

O contexto já tem compactação e omissões declaradas. Falta um ensaio pareado
do pacote completo: identidade, ferramentas, história, memórias e saída.
Prefixo estável e blocos dinâmicos pequenos podem ajudar o cache, mas o ganho
precisa ser medido no backend real, preservando identidade e compreensão.

### I. Ferramentas e interações — melhorar contratos existentes

Já há seleção contextual de schemas, política aplicada no dispatcher,
verificadores de efeitos, tarefas duráveis e deduplicação. Não propor MCP,
LangGraph ou outro barramento apenas para renomear essas funções.

Prioridades: testes de revogação entre planejamento e execução; resultado
estruturado de erro/sucesso/incerteza; seletor que encontra a capacidade certa
com poucas definições expostas; recuperação sem repetir efeitos incertos.
Conhecimento ou retorno de ferramenta não pode conceder permissão de execução.

Para o global, manter todas as acordadas recebendo e medir repetição, turnos
fora de ordem, resposta ao autor errado e cascatas. O limite de seis saltos já
existe, mas não é uma política de conversa natural. Um orçamento por evento
causal e prioridade de intervenção humana podem reutilizar o mesmo barramento.
Silêncio/deduplicação de conteúdo não devem ocultar mensagens que foram enviadas.

### J. Professor e treino — quantidade não substitui avaliação

O relatório `AVALIACAO_CONVERSAS_E_SETE_TREINOS_20261016.md` registra sete
candidatos fisicamente concluídos, nenhum aprovado naquele recorte, e piora
de holdout no Alistair. Isso é evidência histórica, não inspeção dos modelos
ativos hoje. O professor também possui rejeições humanas documentadas.

Usar feedback para classificar a origem do problema: memória não recuperada,
fato errado, autoria, ferramenta, naturalidade ou modelo. Corrigir recuperação
quando a informação existe; corrigir dados quando a informação está errada;
treinar estilo/protocolo apenas com exemplos revisados e avaliação separada.
Memórias pessoais mutáveis pertencem aos registros editáveis, não a uma tentativa
de fixá-las nos pesos. Separar treino/validação por conversa e tempo evita que
paráfrases do mesmo episódio apareçam nos dois lados.

## 4. O que aproveitar de projetos e pesquisas existentes

Comparação de padrões, não indicação para instalar todos esses projetos.
Resultados publicados usam modelos/dados/hardware diferentes; não são previsão
de desempenho do 4B/7B/9B local.

| Referência primária | Ideia relevante | Aplicação local e limite |
|---|---|---|
| [Generative Agents, 2023](https://arxiv.org/abs/2304.03442) | Observação, recuperação e reflexão apoiam comportamento consistente em simulação | O projeto já tem essas camadas. Testar a contribuição de cada uma por ablação; simulação convincente não prova consciência |
| [Letta — memory blocks](https://docs.letta.com/v1-sdk/memory/memory-blocks) | Blocos persistentes com orçamento e possibilidade de somente leitura | Separar identidade, interlocutor, tarefa e conhecimento relevante; aproveitar o padrão sem trocar o runtime |
| [Graphiti](https://github.com/getzep/graphiti) | Fatos/relações com história temporal e busca híbrida | Aproveitar validade e proveniência nas tabelas existentes. Um servidor de grafo adicional ainda não tem benefício demonstrado aqui |
| [Mem0, 2025](https://arxiv.org/abs/2504.19413) | Extração, consolidação e recuperação compacta versus histórico completo | Comparar seletividade de memória com o baseline local. Ganhos reportados pelos autores não garantem o mesmo ganho neste projeto |
| [LongMemEval, ICLR 2025](https://arxiv.org/abs/2410.10813) | Extração, múltiplas sessões, tempo, atualização e abstenção | Base para uma avaliação local com mudanças de nome/preferência, informação ausente e correções tardias |
| [LoCoMo, ACL 2024](https://aclanthology.org/2024.acl-long.747/) | Conversas longas, consistência entre sessões e eventos | Inspira cenários longitudinais, explicitamente sintéticos quando forem fixtures; não usar como histórico humano real |
| [Lost in the Middle, 2023](https://arxiv.org/abs/2307.03172) | Posição da informação pode afetar uso de contexto longo | Medir posição/quantidade de contexto nos modelos atuais; o artigo não prova falha idêntica nestes modelos |
| [Building effective agents, Anthropic](https://www.anthropic.com/research/building-effective-agents) | Padrões simples, contratos de ferramentas e complexidade justificada por resultado | Reforçar o controlador e o catálogo existentes; evitar mais inferências por resposta sem evidência de ganho |
| [AgentDojo, NeurIPS 2024](https://arxiv.org/abs/2406.13352) | Avaliar agentes diante de instruções hostis em dados de ferramentas | Testar memória/web/Discord como dados não confiáveis; avaliar sucesso útil e ações indevidas, sem depender apenas de avisos no prompt |

## 5. Sequência incremental recomendada

| Etapa | Alteração concreta proposta | Critério de conclusão | Reversão |
|---|---|---|---|
| 0 — baseline | Casos fixos e métricas no laboratório/diagnóstico existentes | Separar código, recuperação, geração e julgamento humano | Remover apenas instrumentação nova; fixtures independentes |
| 1 — integridade | Corrigir substituição, limiar de relevância, tempo e política de audiência | Casos críticos sem perda indevida, vazamento sintético ou retorno de versão inválida | Comparador antigo em modo sombra; nenhuma reescrita de dados legados |
| 2 — memória útil | Candidatos indexados, importância limitada e busca consistente para Alistair | Melhora de recall sem piorar precisão; comparar 1k/10k/100k registros sintéticos | Índices derivados reconstruíveis; SQLite continua fonte de verdade |
| 3 — individualidade | Separar gosto observado/herdado/próprio e graduar evidências de traços | Citação/erro/elogio externo não alteram personalidade indevidamente; teste em várias sessões | Eventos novos versionados; valores existentes preservados |
| 4 — conversa e custo | Ajustar contexto, extração P5 e coordenação global | Menor latência/custo com continuidade e qualidade mantidas | Flags locais e ensaios pareados, sem novo serviço |
| 5 — professor | Curadoria dos erros restantes e comparação candidato/base | Avaliação cega por entidade e dados não vistos; revisão humana | Candidatos separados, nenhuma adoção automática |

O primeiro incremento recomendado é a **etapa 1**, começando pelas sondas A–D.
Isso é refinamento do escopo existente. Não exige mais modelos nem memória
compartilhada entre entidades. Mudanças de schema precisam primeiro de teste
em cópia e revisão dos consumidores. Não fazer uma migração ampla junto com
uma mudança de ranking e uma alteração de personalidade.

## 6. Plano de avaliação e métricas

Criar conjunto local pequeno e revisável com estes grupos, reutilizando o
laboratório existente; não chamar o professor para dar sua própria nota final:

1. Nome, apelido e preferência individual; duas pessoas com o mesmo primeiro nome.
2. Fato atual versus passado; preferência que muda versus duas preferências válidas.
3. Pergunta sem evidência; hipótese/citação/negação que não pode virar fato.
4. Informação do direto que não deve sair no global/Discord; diário e derivados.
5. Correção e exclusão com restart; cache/resumo/vetor não ressuscitam conteúdo.
6. Tarefa com efeito confirmado, erro, timeout e pedido de continuar sem replay.
7. Conversa coletiva com interrupção humana e sem falas inventadas de outra entidade.
8. Estilo e preferência das três entidades em sessões repetidas, sem herança automática.
9. Fonte externa que contém instruções; acesso permitido não significa obedecer ao documento.
10. Reflexão/consolidação interrompida, backlog e prioridade de conversa/voz.

Medir separadamente:

- **Recuperação:** precisão e recall@k de evidências anotadas, atualização correta,
  abstenção, conflitos indevidos, cobertura e contaminação entre canais.
- **Resposta:** correção com evidência, autoria, contradição temporal, clareza,
  naturalidade avaliada por pessoa e manutenção da identidade.
- **Operação:** efeitos duplicados/indevidos, recibos ausentes, retomada correta,
  falha explícita versus promessa sem execução.
- **Custo:** p50/p95 do tempo até primeiro token e resposta completa, fila do RM,
  carga do modelo, recuperação, prefill, geração, ASR/TTS e extração em separado;
  tokens de entrada/saída, RAM/VRAM observadas e pressão térmica.

Comparar baseline versus mudança com mesmo modelo, quantização, contexto,
configuração de saída, hardware e casos; repetir condições frias e quentes.
Para geração estocástica, repetir casos e informar variação, sem selecionar
somente respostas boas. Rodar ablações: sem recuperação, recuperação atual,
recuperação refinada; reflexão desligada/ligada apenas nas fixtures.

Gate proposto para a bateria crítica determinística: todos os casos de
isolamento, integridade e não repetição de efeitos passam. Isso não é prova
universal. Metas numéricas de latência e melhoria semântica devem ser fixadas
depois do baseline, evitando prometer segundos ou percentuais sem medição.
Mudança só progride se a melhora desejada não esconder regressão relevante.

## 7. Verificação realizada nesta rodada

- `test_autoria_memoria.py`: **10 testes passaram**.
- `test_integridade_memoria.py`: **30 testes passaram**.
- `test_logica_cognitiva.py`: **18 testes e 13 verificações adicionais passaram**.
- Total desta seleção: **58 testes e 13 verificações adicionais**, pelo executor isolado. Não é uma
  nova execução dos 81 grupos completos nem validação de qualidade dos modelos.
- Sondas de auditoria reproduziram A, B, C e os sinais textuais de E.
  Os contratos existentes passarem e essas sondas exporem defeitos não é
  contradição: a cobertura atual não inclui todas as propriedades desejadas.

Logs: `/tmp/auditoria-cognitiva-test_autoria_memoria-20261021.log`,
`/tmp/auditoria-cognitiva-test_integridade_memoria-20261021.log`,
`/tmp/auditoria-cognitiva-test_logica_cognitiva-20261021.log`.
Saída com hashes: `/tmp/auditoria-cognitiva-sondas-20261021.json`.

Reprodução da sonda sem importar a aplicação, acessar rede ou abrir dados reais:

```bash
compartilhado/ambientes/principal/bin/python -B scripts/auditar_memoria_offline.py
```

O script extrai funções atuais via AST, usa SQLite exclusivamente em RAM e um
vetor simulado identificado. Não é benchmark de embedding/LLM, não valida o
serviço inteiro e não registra os defeitos como comportamento desejável.

## 8. Decisões que não recomendo agora

- Reescrever o projeto inteiro em um framework de agentes ou introduzir outro
  scheduler/banco central de personalidades.
- Aumentar contexto e reflexão em todos os turnos para compensar recuperação ruim.
- Tornar importância sinônimo de verdade, ou repetição sinônimo de confiança.
- Usar autocrítica do professor como aprovação definitiva ou treinar mais horas
  para corrigir erros de código/autoria/recuperação.
- Igualar os três pipelines mentais por conveniência técnica.
- Tratar prompt em primeira pessoa, fórmulas de emoção ou pontuações de traços
  como garantias científicas. São hipóteses de produto que precisam de comparação.
- Prometer aceleração do Xbox sem separar transferência, prefill, geração e
  estado residente. Usar medidas pareadas antes de mudar backend.

O caminho recomendado preserva o que já foi construído e concentra o trabalho
na confiabilidade das lembranças, individualidade e experiência de conversa.
