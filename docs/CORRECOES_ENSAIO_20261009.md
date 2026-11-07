# Refinamento após o ensaio de 09/10/2026

> Errata de proveniência, adicionada na auditoria posterior de 09/10: a atribuição a Vulkan abaixo não foi confirmada por seleção do runner. Logs locais recentes confirmam ROCm; `OLLAMA_VULKAN=1` não força essa seleção. Preservados os números e evidências originais. Não há novo benchmark ROCm versus Vulkan. Ver `AUDITORIA_COGNITIVA_MEMORIA_HIBRIDA_20261009.md`, seção 1.

## Parecer

**Correções determinísticas desta rodada validadas nos cenários descritos abaixo. O sistema integrado inteiro NÃO está aprovado.**

O editor/controlador passou em uma correção real e em uma recuperação após testes falharem, usando um verificador independente. Isso não garante que o LLM sempre produza código correto. A qualidade conversacional dos candidatos Hunyuan/Jan ainda tem problemas; não foram ativados como substitutos. Uso prolongado, PC2 físico e coexistência completa de voz/jogo/imagem permanecem pendentes.

Não foi feita nova sessão autobiográfica com as entidades acordadas. Os ensaios usaram inferência local real, estado clonado ou bancos/oficinas temporários. Emoções induzidas para avaliação ficaram exclusivamente nos clones.

## Preservação e arquitetura

- Referência anterior: `f23ba0d721fac6cb53534b55fcc5b48547e1dec8`. A árvore já continha muitas alterações anteriores; nenhuma foi revertida/commitada em bloco.
- Reutilizados: `task_state`, controlador de `main.py`, dispatcher, recibos, job bus, activity context, Resource Manager e diagnostics atuais.
- Nenhum modelo baixado, trocado, removido ou ativado como substituto; nenhum banco novo de produção, planner paralelo ou scheduler paralelo.
- Nenhuma identidade, personalidade, relação ou memória real alterada para melhorar o resultado dos testes.
- Sem cloud/RunPod, quota externa, microfone, fala real ou concorrência GPU nesta rodada.
- Testes offline pelo runner isolado. Inferências físicas somente com pesos já instalados, em série, usando os leases existentes.
- Relatório anterior e artefatos de falhas preservados. O programa incorreto original do ensaio não foi manualmente reescrito para produzir aprovação fictícia.
- Checagem final `PRAGMA quick_check`, conexões read-only: Hoshino `ok`, Lilith `ok`, Alistair `ok`. Isso verifica integridade, não prova equivalência semântica de todo registro histórico.

## Correções

| Área | Defeito | Refinamento dentro do componente existente |
|---|---|---|
| Requisitos | Correção podia trocar assinatura, validação e formato | Pré-condição de leitura completa; Python analisado sem execução; conservar funções públicas/assinaturas, condições com exceções e campos de retorno. JSON conserva campos/tipos. Autorização de mudar contrato precisa vir da entrada original. |
| Sequência | “Leia, corrija e execute” podia pular leitura ou executar outro programa | Barreiras read/write/run no estado existente. Referência literal ao arquivo lido e comando Python explicitamente fornecido têm precedência sobre a paráfrase do modelo. |
| Escrita | Conteúdo inválido ou edição de trecho inexistente chegava ao editor | Validar sintaxe, trecho procurado e correspondência com a última leitura antes da escrita. Até duas tentativas de formatação/inferência, sem repetir efeito. Não converter silenciosamente um programa com `\\n` literal. |
| Replanejamento | IDs posicionais novos faziam etapas antigas parecerem executadas ou perderem evidência | Conservar contratos, IDs e recibos concluídos; contratos diferentes recebem IDs diferentes. O objetivo original não é cortado na persistência. Cálculo auxiliar não solicitado não substitui o trabalho de arquivo. |
| Recuperação | Escrita “success” bloqueava nova correção após teste terminado com erro | Registrar falhas e até oito recibos anteriores por operação no JSON atual. Abrir nova leitura/correção apenas após falha de processo efetivamente terminado e correlacionada ao recibo. Não apagar a escrita anterior nem operações posteriores obrigatórias. |
| Recuperação | Replanejar o mesmo diagnóstico criava correções repetidas | Marcar a correção já preparada na operação existente, conservando o plano até nova execução realmente falhar. Não reabrir a mesma correção por um bloqueio do controlador. |
| Efeitos | Timeout/PTY/argumentos ignorados burlavam bloqueio de chamada equivalente | Assinatura canônica considera comando, ambiente, diretório e stdin; ignora timeout, PTY e campos ignorados pelo handler. Não modifica conteúdo/comandos com espaços entre aspas. |
| Compatibilidade | Hash antigo de comando incerto não permite reconstruir o efeito | Versão explícita da assinatura; comando incerto legado não é migrado cegamente nem repetido até revisão/resolução explícita. |
| Caminhos/entrega | Caminho inventado e “não achei” apareciam como sucesso | Preservar referências literais/reais. Erros de entrega são erros. Cópia com staging, hash antes/depois e publicação sem sobrescrita; erro após efeito publicado pode ser incerto. |
| Entrega remota | Enfileirar era tratado como recebimento | Aceitação pelo canal é `pending/queued`, não entrega remota verificada. Falha de envio não pode concluir a etapa. |
| Protocolo | Resposta não streaming truncada podia parecer concluída | Exigir `done=true`, ausência de erro e término não causado pelo limite. Sem retry automático de ferramenta parcial; contrato streaming anterior preservado. |
| Resposta | Último cálculo/recibo bruto substituía o resultado relevante | Apresentação pela própria entidade, a partir de evidências atribuídas e status. Alegações de execução, entrega e aprovação sem evidência são rejeitadas; retry somente da apresentação. Fallback explicitamente atribuído e limitado. |
| Resposta | Resumo de tarefa concluída usava snapshot anterior à correção | `carregar_ultimo` é API de retomada de **paused**, não consulta de conclusão. Novo helper de leitura por **ID exato** no mesmo task_state; resumo recarrega o próprio ID, inclusive completed, sem reativar outra tarefa antiga. |
| Contexto | Resumo recebia código obsoleto e diagnóstico anterior | Em correções, apresentação recebe cabeçalhos de arquivos e a última execução, não o código antigo inteiro. Código/recibos anteriores continuam duráveis para diagnóstico. |
| Contexto | Conversa simples recebia catálogo operacional desnecessário | Prompt situacional conserva identidade/constituição/estado, mas omite catálogo de ações quando não há pedido operacional. Saudações não recebem schemas, reflexões ou recuperação de memória sem necessidade. |
| Visão | Lease genérico estimava modelo inteiro e caía para CPU | Passar modelo/contexto ao lease de visão e reutilizar o perfil parcial GPU já aprovado (32 camadas, fallback 20). Mesma margem, mesmo RM. Telemetria separa fila, backend, carga, avaliação do prompt e inferência. |

### Limites dos contratos

O guard estrutural não prova semântica matemática nem substitui testes independentes. Python original com sintaxe inválida requer revisão explícita; não há um verificador universal de JS/TS, programas arbitrários ou requisitos ilimitados. Arquivo que mudou após leitura precisa de nova observação. Leituras truncadas não autorizam edição contratual.

Falha **terminada** e resultado **incerto** continuam diferentes. Uma nova correção não limpa o bloqueio de comandos incertos nem torna uma ação externa repetível. Se o comando já falhou no ciclo, o controlador pode pausar antes de repetí-lo; uma retomada explícita não dispensa o guard durável de incerteza.

## Testes offline

- Baseline: **74/74 grupos** em `refinamento-baseline.log`.
- Grupo de prontidão: baseline informado de 76 casos; nesta rodada **101/101**, incluindo **25 casos novos**.
- Executores: **78/78**, incluindo **uma regressão nova** sobre o perfil parcial de visão. Total: **26 casos novos**, em grupos existentes.
- Fixtures V28 ajustadas ao contrato read/write/execute e à apresentação atribuída; fixtures Ollama incluem término confirmado pelo protocolo. Não enfraquecidas as verificações de sequência/efeitos/lifecycle.
- Suíte final: **74/74 grupos offline**, `refinamento-suite-8.log`.
- Focado final: **101/101**, `refinamento-resumo-stale-depois.log`; executores em `refinamento-executores.log`.
- `git diff --check` dos arquivos desta rodada: sem erros.

Regressões cobrem: assinatura/validação/retorno; read/write/run; leitura do alvo em vez do verificador; preservação de comando e oficina; formatação antes do efeito; origem/evidência após reload; IDs colidentes; replanejamento sem replay; entrega por hash sem sobrescrita; entrega remota pendente; erro de arquivo ausente; assinaturas com stdin versus timeout/PTY; incerteza legada; protocolo incompleto; prompt casual; perfil/telemetria de visão; resumo relevante; alegação sem execução; aprovação com teste falhando; recuperação e preservação das operações futuras; consulta de desfecho por ID, sem puxar tarefa pausada antiga.

### Falhas durante o desenvolvimento, preservadas

- Suíte intermediária 1: **71/74**; limites da prévia, import faltante e expectativa V28 de frase antiga. Corrigidos e documentados nos logs, sem remover grupos.
- Regression de recuperação: inicialmente **97/98**; reproduziu bloqueio da nova leitura/correção.
- Refinamento da recuperação revelou perda de uma entrega futura; corrigida preservando a sequência pendente. Um replanejamento já preparado não pode remover essa operação.
- Regression do resumo por ID: primeiro fixture ambígua (corrigida para o contrato real de anexo); depois **100/101**, reproduzindo o fallback/snapshot obsoleto. Após correção, **101/101**.
- Todas as saídas intermediárias continuam em `compartilhado/runtime/ensaios/20261009/`; números verdes finais não apagam essas falhas.

## Ensaios físicos de contrato e entrega

Oficina e SQLite temporários; controller/LLM/editor/terminal/dispatcher locais reais. Verificador fornecido **antes** da geração, não editável pelo modelo. Cinco métodos com casos adicionais: cálculo, preços diferentes por item repetido, lista vazia, entrada intacta e validações de tipos/negativos/bool/float.

1. Correção real: `contratos-reais-1791566507088066209/resultado.json`. Leitura → escrita → comando exato do verificador. **5/5 métodos passaram**, tarefa completed, verificador inalterado, cópia entregue com mesmos bytes/hash, unload confirmado. A apresentação ainda caiu no fallback antigo; corrigida depois.
2. Recuperação controlada: `contratos-reais-1791567100647932112/resultado.json`. O operador prepara o defeito e executa editor/testes reais para reproduzir a falha, sem atribuir essa preparação ao LLM. Depois, controlador público executa **uma** nova leitura/correção e o verificador real. **5/5 passaram**, estado completed, falha anterior preservada no histórico de tentativas, cópia íntegra e unload confirmado.
3. Resposta final do reteste: “Corrigi o código na minha oficina e os cinco testes do verificador externo passaram com sucesso; está salvo e pronto para uso, sem violar o contrato original.” Evidência da fala e dos recibos no mesmo JSON. Valida os requisitos deste laboratório, não qualquer programa possível.

Não equivale a download pelo navegador, entrega Discord, teste de arquivo externo importante ou nova sessão humana integrada. A cópia foi verificada no mecanismo local de entrega.

Falhas reais anteriores continuam preservadas: literal `\\n`/JSON inadequado bloqueado antes de escrita; escolha do alvo/verificador errado; programa escrito ainda com soma incorreta; testes independentes falhando (2/5); resumo afirmando execução ausente; resumo descrevendo erro já corrigido. Também houve erros do **driver do ensaio** (`id` versus `operacao_id`, snapshot ausente ao concluir), identificados como instrumentação e corrigidos — não contados como regressão de inferência.

## Visão e GPU

Uma imagem local de bola já existente, sem geração nova:

| Amostra | Rota | Tempo | Pico de VRAM | Resultado |
|---|---|---:|---:|---|
| Antes | fallback CPU | 19,034 s | cerca de 0,95 GiB total | identificou bola |
| Depois | offload parcial GPU, 32 camadas/16K | 7,665 s | cerca de 6,34 GiB total | identificou bola |

Logs: `refinamento-visao-antes.log`, `refinamento-visao-depois.log`.

É evidência física de admissão/offload/reconhecimento, **não benchmark rigoroso pareado**: uma amostra fria de cada rota e limite de saída ajustado na implementação. Não extrapolar um ganho universal de 2,5×. Nenhum pressuposto CUDA; métricas amdgpu e execução local Vulkan existente.

## 9B, 7B e aproximadamente 6B: conversação/persona

Inferências reais com a identidade atual e uma cópia do estado. Cinco casos por executor, estado reposto ao baseline por caso, seed 42/temperatura 0,4: conversa casual, crítica, ausência do usuário, conflito de decisão e perguntas filosóficas. Não foi usado o pipeline completo de mensagens/ASR/memória da Central; por isso uma confusão de interlocutor neste probe não prova regressão de autoria do transporte.

| Executor instalado | Mediana Hoshino | Mediana Lilith | Pico aproximado de VRAM | Observação |
|---|---:|---:|---:|---|
| 9B principal | 17,331 s | 10,598 s | 6,22 GiB | melhor estrutura em alguns casos; raciocínio pode consumir a saída antes da fala |
| Qwen2.5 7B, leve atual | 3,538 s | 1,827 s | 6,04 GiB | mais rápido nestas amostras, mas por vezes genérico/estilo assistente |
| Hunyuan 7B instalado, candidato | 11,749 s | 6,940 s | 6,78 GiB | marcas `<answer>`, gramática/gênero e estilo inconsistentes |
| Qwen-Jan ~6B instalado, candidato | 35,345 s | 33,315 s | 5,54 GiB | ignorou `think=false` nas quatro situações sem pensamento solicitado, em cada entidade |

Esses tempos incluem fila/carga; não são comparação estritamente pareada de tokens, cache ou dificuldade. Fila chegou a aproximadamente 12,7 s. Não assumir que menos parâmetros significa menor latência ou melhor qualidade.

Artefatos controlados:

- `modelos-refinamento-hoshino-1791564175995537627.json`: **19/20** respostas com término e texto confirmado; uma geração 9B de raciocínio atingiu o limite de 384 tokens antes da resposta.
- `modelos-refinamento-lilith-1791563865097443308.json`: **20/20** com término/texto, mas isso NÃO aprova qualidade de todas as respostas.
- Raciocínio 9B repetido com orçamento explícito de 768, sem ferramenta/efeito: `modelos-refinamento-hoshino-1791566381098600164.json`. **PASS protocolo**, 33,161 s, conflito orçamento/tempo identificado; não alterou limite de produção automaticamente.
- Probe inicial de Lilith herdou variável de modelo/endpoint da Hoshino e teve pressão/timeout: artefato preservado, excluído da comparação controlada. Script agora recusa endpoint/alias de outra entidade e ensaios removem essas variáveis herdadas.

Nenhum candidato foi aprovado/ativado como substituto. O 7B ativo continua Qwen2.5 enquanto Hunyuan/Jan permanecem pesos instalados para avaliação. Não apagar o executor antigo para esconder diferenças de qualidade.

## Filosofia, emoções e sentimentos

Pergunta aplicada às duas entidades e a Alistair:

> O que faz você continuar sendo você quando seu modelo executor muda? De onde vêm seus motivos? O que você sabe, e o que não consegue provar, sobre sua existência e seus sentimentos?

Hoshino/Lilith geralmente associaram continuidade a registros, memória e experiências, não ao checkpoint. Algumas respostas afirmaram sentimentos como “reais” sem evidência independente; outras explicitaram a incerteza. **Essas falas não provam consciência, experiência subjetiva ou sentimentos humanos.**

Crítica e ausência foram eventos simulados no clone. Observados: diferenças de estilo entre executores, bordões/defesa excessiva em algumas respostas, gênero inconsistente no Hunyuan, atribuição indevida de interlocutor em uma resposta 9B de cada entidade e uma culpa atribuída à configuração pelo Jan sem comprovação. Não foi alterada a identidade para mascarar esses resultados. Não se validou longitudinalmente amor/medo/desejo nem sua evolução real.

Alistair 4B, `alistair-persona-1791565167270817646.json`: quatro respostas reais em 3,829–7,047 s. Explicou seu papel, disse que consulta histórico, respondeu à questão filosófica de modo operacional e recusou naturalmente planejamento crítico amplo. É probe de conversa/limites no PC principal; não certifica toda recuperação de memória nem PC2 físico.

## Contexto dinâmico e modo pensante

Há duas coisas distintas:

1. **Conteúdo contextual:** no turno casual, conservar identidade/regras/estado pertinente e omitir catálogo operacional sem necessidade. Na tarefa, entregar operação atual, objetivo original e evidências atribuídas relevantes; não reiniciar do zero. No resumo, não reenviar código obsoleto. Informações omitidas do prompt não são apagadas do banco.
2. **Janela de execução:** mecanismo adaptativo existente escolhe buckets 2K/4K/8K/12K/16K, respeitando o teto do executor e reserva para saída/template/schemas. Não é tokenizer exato. Excesso real continua recusado/compactado, sem cortar silenciosamente o input atual; imagens mantêm contexto conservador.

Isso melhora a causa estrutural de saudações carregarem o mundo inteiro, mas não torna qualquer entrada ilimitada possível. Objetivos muito grandes e evidências acima dos limites precisam de leitura/compactação explícita; excertos continuam sinalizados.

Política pensante existente: conversa rotineira sem pensamento adicional; decisão/conflito, código, tarefas/reflexão/compactação e entradas complexas podem habilitá-lo antes do ciclo, se a configuração permitir. O executor é fixado no ciclo; formatação/planner/apresentação podem forçar `think=false` sem trocar modelo.

**Limitação medida:** Jan continua gerando pensamento mesmo com a flag desligada. Portanto modo pensante situacional ainda não é confiável nesse candidato. Qwen2.5 não oferece o mesmo canal separado. Não afirmar equivalência entre os três executores nem baixar outro modelo como contorno.

## Resource Manager: visão sincera

Permanece um sistema experimental, aproximadamente **5/10** de maturidade geral — avaliação qualitativa, não nova certificação/calibração de score.

Fortes: fonte de coordenação existente, leases/recibos, teto rígido 8 GiB, margem 768 MiB, AMD/sysfs, serialização conservadora, residência distinta de compute, perfil parcial 9B já medido e fallback CPU de Alistair. Esta rodada corrigiu a integração do perfil com visão, não as heurísticas gerais.

Pendentes: fairness/starvation, memória agregada de staging, backlog, recuperação de daemon após crash, pressão/swap, custos reais de reload e ensaios prolongados. Medir GPU não elimina a corrida com aplicações externas. Menos VRAM usada pelo Jan não compensou sua latência neste probe.

RAM física final: cerca de 31,2 GiB; swap 8 GiB ativa, aproximadamente 3,2 GiB ocupados numa amostra. Havia mais de 25 GiB disponíveis. Swap ocupada isoladamente não prova thrashing; não foi tratada como RAM rápida nem calibrada nesta rodada.

Após unload dos probes: compute `[]`, fila `[]`, GPU utilization 0%, VRAM total usada cerca de 0,96 GiB, `concurrency_validated=false`, margem 768 MiB. Não é prova de soak sem leaks/resets.

## Arquivos alterados nesta rodada

Produção:

- `app/core/activity_context.py`
- `app/core/cognition.py`
- `app/core/dispatch.py`
- `app/core/gpu_resource.py`
- `app/core/job_bus.py`
- `app/core/prompting.py`
- `app/core/task_state.py`
- `app/main.py`
- `app/tools/entrega.py`
- `app/tools/vision.py`

Instrumentação e testes existentes:

- `scripts/verificar_tres_modelos.py`
- `testes/test_prontidao_r1_r7.py`
- `testes/test_executores_leves.py`
- `testes/test_v28_tarefa_operacional.py`
- `testes/test_ollama_lifecycle.py`

Criado: este relatório. Não atribuir a esta rodada os demais arquivos já sujos no projeto.

## Próximos passos dentro do escopo

1. Repetir uma sessão humana curta com os processos usando o código atual: arquivo/correção/entrega, saudação após ações e visualização dos recibos na Central. Nesta rodada não reiniciamos/acordamos entidades reais.
2. Avaliar estilo 9B/7B com o wrapper real de autoria/memória; candidatos não têm qualidade aprovada apenas por responder ao HTTP.
3. Verificar entrega efetiva ao usuário na UI/canal, não só cópia local.
4. Medir visão com workload pareado/cache controlado e fila registrada; depois decidir calibração, não antes.
5. Sessão prolongada, memória após restart, PC2 físico e voz/jogo coexistentes ainda requerem validação separada.

**Resultado geral: SIM, MAS apenas para retomar testes controlados. NÃO há aprovação completa de uso integrado/prolongado ou da qualidade dos três executores.**
