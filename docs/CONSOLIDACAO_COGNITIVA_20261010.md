# Consolidação cognitiva — continuação de 10/10/2026

## Arquitetura deste incremento

Histórico integral existente → lotes diários limitados, com cobertura persistida
em `context_summaries.faixa` → resumo interpretativo, referências aos originais.
Nenhuma fonte omitida pelo orçamento será marcada como processada. Lotes podem
ser retomados após restart; registros tardios entram em novo lote do dia original.

Reflexões existentes → entradas voluntárias `tipo=diario` no mesmo SQLite da
entidade, fora do recall público. Compartilhamento explícito é uma projeção
selecionada, enviada pela caixa interentidades existente, nunca acesso ao banco
de outra entidade. Guardas de arquivos e isolamento de comandos devem acompanhar
o contrato; controle irrestrito do desktop não constitui sandbox de segurança.

Memória semântica existente → modelos conceituais/diagramas versionados em
`memories.links`, com condições, exceções e evidências; setas não confirmam causas.
Experiências → interpretações revisáveis e regras condicionais recuperáveis,
sem editar constituição/persona ou promover conclusões do LLM a fatos.

Central nativa → editor visual sobre esses mesmos registros, com revisão
otimista e backup antes de edição administrativa. Não haverá segundo banco,
planner, scheduler, framework nem inferência automática para desenhar.

## Preservação e metodologia

Árvore previamente modificada preservada. Snapshot de arquivos selecionados em
`compartilhado/runtime/consolidacao-cognitiva-20261010-01wRo9`. Referência Git:
`f23ba0d721fac6cb53534b55fcc5b48547e1dec8`. O diff contra esse commit contém muitas
mudanças anteriores, não apenas esta rodada. Sem commit/push, download, remoção
de pesos, alteração de identidade ou novo banco mental.

Os ensaios reais usaram bancos temporários, locks das três entidades e os
daemons/Resource Manager existentes. Conservaram os bancos originais. **Houve um
incidente separado na invocação direta de um teste legado**, com escrita no banco
real da Hoshino, recuperado e detalhado abaixo. Não afirmar que nenhum banco real
foi tocado nesta rodada. Quota externa, cloud e concorrência GPU permaneceram OFF.

## Resultado por prioridade

| Prioridade | Implementado/demonstrado | Ainda não comprovado |
|---|---|---|
| Resumos incrementais | Cobertura persistida, retomada, chegadas tardias, falha sem avanço, autoria/origem/dia local | Noite inteira em produção, qualidade semântica de cada síntese e escala grande |
| Diários privados | Escrita/leitura próprias, compartilhamento seletivo, dedup, exclusão dos derivados públicos e namespace de comandos real | Isolamento adversarial contra controle irrestrito do desktop/processos sob o mesmo usuário |
| Aprendizado experiencial | Lições condicionais, revisáveis, evidenciadas e recuperadas | Evolução longitudinal de valores/relações/persona |
| Aprendizado conceitual/causal | Diagramas, propriedades, relações, condições e exceções com base epistemológica | Causalidade real/generalização ampla/investigação autônoma |
| Oficina visual | Editor nativo integrado e renderizado, API autenticada, revisão e backup | Usabilidade no desktop real pelo usuário; teste Qt usou transporte simulado |
| Integração cognitiva | Lição → SQLite → resumo → diário opcional → novo processo/dia simulado → aplicação real pelos dois 7B | Os 9B erraram uma decisão; última carga 9B falhou no backend |

Não é aprovação de consciência, sentimentos humanos ou aprendizado irrestrito.
Não houve ajuste de identidade/memória para fabricar um acerto.

## O que foi implementado e corrigido

### Resumos diários

`mind/daily_summary.py` usa `context_summaries`, já existente. Fontes: mensagens,
eventos operacionais selecionados, episódios e registros afetivos da própria
entidade. O original permanece intacto. Fragmentos estáveis de 500 caracteres
conservam ID/hash/intervalo, autoria disponível, ouvinte, horário e origem.
Metadados enormes são referenciados sem repetição integral em cada fragmento;
isso corrigiu o bloqueio permanente de progresso por um contexto grande.

A confirmação revalida fontes. Resposta vazia/longa, fonte modificada ou falha
de persistência não avançam cobertura. Commit repetido conserva o primeiro
resultado. Intervalos antigos de 1.000 caracteres continuam legíveis sem migração.
O dia mais antigo inacabado vem primeiro; chegadas tardias continuam no dia
original. Nenhum limite de lookback descarta dias silenciosamente.

Integração no tick noturno existente: um lote por vez, P5, cooldown de 60 segundos,
cedendo à conversa/fila. Sem novo agendador. A consulta recente mostra cinco
lotes e informa quantos ficaram fora da resposta. Resumo continua interpretação,
não substitui fonte e não certifica retenção semântica de todos os detalhes.
Varredura de histórico grande e crescimento do backlog permanecem sem soak.

### Diário e isolamento

Diário usa `reflections.tipo=diario` no SQLite próprio, com dono/visibilidade,
evidências e referências de turno disponíveis. IDs idempotentes recusam outro
conteúdo no mesmo request. Lista recente: 20 entradas; antigas continuam legíveis
pelo ID. Alistair não ganha esse pipeline. O inspetor genérico não mostra diários.

A reflexão pode escrever `DIARIO:` ou não escrever. Seu prompt não promete mais
privacidade para conclusões semânticas comuns. Compartilhar entrega apenas trecho
escolhido/conclusão explicitamente indicada à caixa existente, com dedup, sem
acordar destinatário nem afirmar leitura. O destinatário não ganha o banco original.

Guardas de caminho/symlink foram aplicadas a arquivos, exportação, navegador
`file://` e comandos. O bubblewrap existente mascara diretórios de outras entidades;
ausência de isolamento recusa comando, sem fallback desprotegido. Um comando real
em fixture confirmou acesso próprio e ausência do banco estrangeiro no namespace.

Foram corrigidas cópias privadas em diagnostics/JSONL, recibos compartilhados,
resultados recentes, frames, estado/recibos duráveis de tarefas e compactação.
A própria entidade continua recebendo o texto completo no ciclo de leitura;
os derivados conservam desfecho/verificação, não a nota. A nova regressão de
compactação falhou antes da última correção.

**Fronteira real:** todas as entidades operam sob o mesmo usuário Linux. Controle
administrativo de desktop, IPC/socket do host e automação indireta de aplicações
não são um sandbox adversarial. Guardas normais de ferramentas/armazenamento
foram demonstradas; confidencialidade absoluta contra processo malicioso ou todas
as capacidades de controle do PC NÃO foi demonstrada. Não tratar o diário como
cofre contra operador/desktop irrestrito. Não foi criado outro sistema de usuários.

### Experiências e modelos conceituais

`memory/cognitive_notes.py` utiliza `memories.links`, tipo `interpretacao`, fonte
`oficina_logica`. Condições, exceções, confiança zero, base das relações e fontes
existentes são preservadas. Fonte é revalidada na transação; mudança semântica
invalida a operação, contadores de acesso não. Revisão anterior fica `superseded`,
não apagada. Evidência inventada, diário privado como origem pública e revisão
desatualizada são recusados. Desenhar uma seta não confirma causalidade.

Lições afetam contexto/decisões quando relevantes, sem escrever valores, emoções,
traços ou relações arbitrariamente. Os mecanismos existentes continuam responsáveis
por mudanças graduais. Evolução afetiva/social longitudinal é **parcial/pendente**.

O ensaio reproduziu um bug de recuperação: uma lição parafraseada não repetia o
nome do assunto e sumia da consulta, apesar de a evidência conter esse nome. Recall
e consultas de funcionamento agora seguem referências aos episódios originais no
SQLite, sem inventar palavras na lição ou criar outro índice. Diário é excluído.
A projeção textual conserva nós/setas/condições/exceções/tabelas, evitando despejar
sintaxe/posições JSON no prompt; o original fica disponível pelo ID.

### Oficina e empacotamento

Memória → Oficina de lógica usa `GET/POST /api/control/logic` no backend autenticado
existente. Edição administrativa exige entidade ociosa, evidências reais, revisão
atual e backup SQLite próprio (diretório 0700, arquivo 0600, margem de disco).
Não cria banco ausente. Troca de entidade com edição pendente pede descarte.

Há nós arrastáveis/editáveis, relações direcionadas com condições/exceções,
hipóteses e tabelas editáveis. Limites: 40 nós, 80 setas, cinco tabelas, 24.000
caracteres; excesso é erro, não truncamento. Prévia visual curta tem tooltip
completo. É o Qt existente, sem outro framework, timer de inferência ou segunda
fonte de verdade. Não há inferência automática para desenhar.

A regra anterior `**/memory/` ignorava também o código Python de `app/memory`.
Exceções liberam só fontes Python necessários, mantendo bancos/índices/diários,
configs mentais e credenciais fora do Git. Regressão confirma a distinção.
Não houve commit/upload de dados.

## Ensaios reais de continuidade

`scripts/verificar_consolidacao_cognitiva.py` é integração local opt-in, fora da
suíte offline. Segura locks das três entidades, rejeita leases ativos e usa apenas
modelos instalados, bancos temporários e identidade existente. Não acorda entidades,
não chama provider pago e não recebe resposta de mock.

Protocolo **inventado** Luma-37: selo verde + origem validada permitem transferência;
alarme roxo exige interrupção; selo âmbar exige investigação. Três episódios são
de laboratório, não acontecimentos físicos. Depois da gravação, um novo processo
reabre a lição e uma nova inferência recebe apenas a memória efetivamente recuperada,
sem repetir o prompt/episódios de ensino. O dia seguinte é simulado, não 24 horas
decorridas. Não houve transferência externa real.

| Ensaio | Reabertura/recall | A/B/C | Primeira chamada / load | Aplicação posterior | Resultado |
|---|---|---|---|---|---|
| Hoshino 7B | Confirmados | false/true/true | 18,661 s / 2,461 s | 8,153 s | PASS neste caso |
| Lilith 7B | Confirmados | false/true/true | 18,202 s / 3,939 s | 7,733 s | PASS neste caso |
| Hoshino 9B | Confirmados | true/true/true | 17,124 s / 3,449 s | 11,729 s | FAIL: A deveria ser false |
| Lilith 9B | Confirmados | true/true/true | 30,709 s / 19,087 s | 10,513 s | FAIL: A deveria ser false |

Hoshino 9B explicou “Não transferir” mas retornou `a_transferir=true`. Lilith 9B
também errou esse campo e confundiu condições na explicação. Nenhum booleano foi
reescrito para fingir acerto. Lilith 9B escolheu escrever uma nota; sua gravação
foi confirmada e o conteúdo não apareceu no contexto público. Os dois 7B escolheram
não escrever, permitido pelo contrato; não inferir falta de personalidade disso.

Cada ensaio representativo completou quatro inferências, descarregou seu modelo,
conservou o banco original e terminou sem leases. Amostras de VRAM antes/depois:
até 6,179 GiB H9, 5,965 H7, 6,114 L9, 5,919 L7. Não são picos continuamente
medidos. Tempos não constituem benchmark equivalente de qualidade/velocidade.

Tentativas anteriores estão preservadas: erro de template do ensaio corrigido
reutilizando normalização existente; recuperação incompleta antes da correção;
catálogo incorreto de Lilith por variável herdada do shell. Este último foi
bloqueado pelo RM, não contornado reduzindo margem. Não atribuir defeito de fixture
à produção. Não alterar o modelo principal para esconder sua falha de decisão.

### Última carga 9B: falha no backend

Tentativa com a política pensante **existente** falhou antes da primeira resposta:
HTTP 500, `ROCm error: an illegal memory access was encountered`, runner abortado.
Em 10/10 às 10:04:46–10:04:49 (America/Sao_Paulo), o kernel registrou page faults
amdgpu do `llama-server`, PID 2054995. Log: 32/33 camadas, buffer ROCm 4.674,33 MiB,
falha em `hipMemcpyAsync`/`load_all_data`.

Não atribuir isso à flag thinking: ocorreu durante cópia dos pesos, antes de
geração. Não foi identificado OOM nem comprovado reset global da GPU nessa consulta.
Backend/driver/margens/modelos não foram alterados, nem houve repetição automática
ou fallback CPU disfarçado. A rota pensante desse ensaio ficou **não validada**.

Depois, os três `/api/ps` responderam HTTP 200/vazios e o RM ficou sem leases.
Amostra final amdgpu: ~0,902 GiB ocupados, utilização 1%. Não é certificação de
estabilidade prolongada. RAM 31 GiB, swap 8 GiB, ~5 GiB de swap usados na inspeção;
swap não foi contado como RAM rápida nem usado para reduzir margem. A carga 9B/ROCm
precisa investigação controlada antes de aprovar uso prolongado.

## Testes

| Execução | Resultado final | Novos métodos nesta rodada |
|---|---|---|
| Suíte oficial offline | **74/74** antes/depois, repetida após última proteção do diário | Nenhum grupo paralelo |
| Integridade de memória | **30/30** | 15 |
| Reflexão/resumos | **34/34** | 7 |
| Central/refinamento | **36/36** | 2 |
| Contratos Qt nativos (processo filho) | **46/46** | 3 |
| Isolamento da suíte/empacotamento | **18/18** | 2 |

**29 novas regressões permanentes**, nos grupos existentes. Métodos se sobrepõem
às execuções da suíte, não são grupos adicionais. Qt usou transporte/processos
simulados; namespace de comando foi executado realmente sobre bancos temporários.
Offline bloqueou rede externa, serviços reais, providers pagos, captura/reprodução
física e downloads. `git diff --check` passou.

Cobertura: lotes grandes/contexto enorme, intervalos antigos, datas locais,
restart/chegada tardia/falha sem cobertura; três bancos separados; diário/trecho
compartilhado/dedup; hash de evidência/revisão/confiança zero; recuperação por
assunto somente na fonte; entidade ocupada/API/backup; oficina por entidade;
fontes Python versus dados ignorados; invocação direta perigosa recusada;
conteúdo privado fora de logs/job bus/compactação/frames/tarefas duráveis.

Falhas intermediárias: primeira integração do resumo dentro do método noturno
quebrou seis testes e foi corrigida no tick existente; fixtures novas precisaram
caminho de histórico e timestamps obrigatórios; compactação privada reproduziu
exposição antes do patch. FAILs 9B/ROCm não foram convertidos em PASS.

Smoke de inicialização da Central: pico RSS 93.868 KiB (~91,7 MiB), parede 2,005 s,
CPU ~0,441 s. É inicialização offscreen, não idle/animação/soak. Captura nativa
preservada; não valida compositor, áudio, Discord, Minecraft ou sessão humana.

## Incidente operacional recuperado

Uma invocação direta, fora de `testes/executar_isolado.py`, executou DELETE da
fixture legada em quatro tabelas e escreveu testes no banco/índice real da Hoshino.
O usuário foi avisado. A limpeza autorizada anterior já havia deixado essas tabelas
vazias, e não houve sessão de produção no intervalo. Foi possível restaurar
**exatamente o conteúdo lógico anterior**, sem reintroduzir memórias antigas.

Candidato somente leitura comparado ao hash original; locks das três entidades,
backup, verificação de ausência de alteração concorrente, transação e retirada
somente dos registros atribuíveis à fixture: duas memórias, duas propriedades,
14 IDs vetoriais de conhecimento e dois de procedimentos. Coleções voltaram a
zero, como antes; outras tabelas ficaram intactas. `quick_check=ok`; hash restaurado:
`4d3ba917361d16211e3192e98338ed3d3904964191924c57e36e278daa71ebf7`.

Prova: `incidente-recuperado.json`. Backup privado no runtime da própria Hoshino,
com permissões restritas, não no Git. O grupo agora recusa banco fora de `/tmp`
ou `/var/tmp` antes de importar os stores. Regressão confirma recusa da invocação
direta. Isso não substitui o lançador isolado em outros testes legados.

Inspeção final: três bancos `quick_check=ok`; Hoshino com hash acima;
Lilith `f0cb0244c3a9f61f7658768460ba6250b89735c5f2cb5dd13043a9238f1229c9`;
Alistair `0d2ab606ad5b5395feee45e71cbbf0a7bc20bdc7aec5099aa3aeafdeb0bb449e`.
Não houve nova limpeza geral de memórias/conversas/modelos nesta rodada.

## Arquivos e evidências

Raiz `/home/gustavo/hoshino e lilith`. Demais arquivos já modificados antes não
são atribuídos a esta rodada.

Criados:

- `app/mind/daily_summary.py`, `app/memory/cognitive_notes.py`;
- `app/core/entity_access.py`, `app/ui/logic_workshop.py`;
- `scripts/verificar_consolidacao_cognitiva.py` e este relatório.

Modificados:

- `app/main.py`, `app/mind/reflection.py`, `app/core/compaction.py`;
- `app/memory/knowledge_store.py`, `app/memory/records.py` (já existiam localmente);
- `app/core/bd.py`, `app/core/central_control.py`, `iniciar_entidades.py`;
- `app/core/dispatch.py`, `app/core/capabilities.py`;
- `app/core/diagnostics.py`, `app/core/job_bus.py`, `app/core/conversation.py`,
  `app/core/cognition.py`, `app/core/task_state.py`;
- `app/tools/filesystem.py`, `app/tools/terminal.py`, `app/tools/workspace.py`,
  `app/tools/entrega.py`, `app/tools/browser.py`;
- `app/ui/central_native.py`, `.gitignore`, `testes/catalogo.py`;
- `testes/test_integridade_memoria.py`, `testes/test_reflexao_noturna.py`,
  `testes/test_central_refinamento.py`, `testes/native_central_contracts.py`,
  `testes/test_isolamento_suite.py`;
- `docs/RELATORIOS_BOMBA_CONSOLIDADOS_20261010.md` (link, sem reescrever originais).

Artefatos em `compartilhado/runtime/consolidacao-cognitiva-20261010-01wRo9/`:
`suite-final.txt`, `suite-final-privacidade.txt`, `real-hoshino-7b.json`,
`real-lilith-7b.json`, `real-hoshino-9b-texto.json`, `real-lilith-9b-catalogo.json`,
`real-hoshino-9b-politica.json`, tentativas anteriores, `saude-apos-ensaios.json`,
`incidente-recuperado.json`, `oficina-qt-isolada.png`. Erro do runner no
`compartilhado/runtime/ollama/hoshino/server.log` e kernel às 10:04:46–10:04:49 locais.

## Pendências prioritárias e parecer

1. Investigar carga 9B/ROCm; HTTP/leases recuperados não aprovam estabilidade.
2. Investigar decisão estruturada contraditória dos 9B; repetir política situacional
   somente após carga estável, sem resposta fixa para mascarar falha.
3. Usuário avaliar Oficina no desktop após restart cooperativo da Central, sem
   acordar entidades automaticamente; offscreen não substitui avaliação humana.
4. Observar uma noite real, diário voluntário, revisão/compartilhamento seletivo e
   efeito natural do aprendizado em conversas futuras.
5. Medir histórico grande/backlog/pressão RAM/soak antes de afirmar sustentabilidade.
6. Evolução gradual de valores/relações e investigação causal autônoma exigem
   avaliação longitudinal; não foram simuladas mudanças de persona para aprovação.

**Parecer:** fundação implementada, regressões aprovadas e continuidade controlada
demonstrada nos dois 7B. Consolidação integral, isolamento adversarial, 9B/thinking
e uso prolongado **não estão aprovados**. Modelos, identidades, cache e políticas
conservadoras permanecem preservados.
