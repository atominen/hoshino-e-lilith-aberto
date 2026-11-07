# Professor e recuperação de executores — 13/10/2026

## Escopo e preservação

Rodada solicitada: testar primeiro o professor e recuperar executores ausentes
pelos últimos pesos estáveis aprovados, preservando o original separado. Não
implementa os demais itens da auditoria geral nem outro scheduler/banco/cérebro.
Plano e consumidores: `PROFESSOR_E_RECUPERACAO_PLANO_20261013.md`.

Antes: 74/74 grupos oficiais e 195 testes do laboratório passando. Backup do
código preexistente em `/tmp/hoshino-professor-recuperacao-8F2qEt/codigo-antes.tar.gz`.
O working tree já continha alterações de outras rodadas; foram preservadas.
Uma cópia durável do backup de código foi preservada no registro existente:
`laboratorio-local/controle-laboratorio/treinamento-unificado/backups/codigo-antes-professor-recuperacao-20261013.tar.gz`.
SHA-256 das duas cópias: `3dda21ef05fbd38f3993ed5c7cf34f07d33a33fca804db13f18b200ff04113d3`.
O arquivo contém código; não contém .env, pesos ou bancos mentais.
Nenhum download, treino, cloud, quota externa ou wake das entidades nestes ensaios.

## Professor: inferências reais, não mocks

Professor existente Qwen3.5-35B-A3B/Vulkan, RX 6650 XT, seed 42, mesmos perfis
e três situações controladas: peça de quebra-cabeça, entrega com timeout e
lembrança de livro sem título. Nenhuma referência autoral não aprovada entrou.
`brief` escreve o diálogo junto; `staged` escreve por prefixo, sem falas humanas
futuras. Ambos usam os críticos atuais. Isto compara métodos controlados, não
reconstitui exatamente um binário histórico anterior.

| Perfil gerado | Brief: gate técnico / tempo | Staged: gate técnico / tempo |
|---|---|---|
| Hoshino | 2/3 — 80,48 s | 2/3 — 63,72 s |
| Lilith | 3/3 — 48,97 s | 2/3 — 86,65 s |
| Alistair | 2/3 — 66,81 s | 2/3 — 62,28 s |

18 diálogos completos (36 respostas). Carga inicial: 29,04 / 8,02 / 8,45 s;
cache/ordem e amostra pequena impedem atribuir a diferença de latência apenas
ao método. Pico global observado de VRAM: 7.523.106.816 bytes. Não houve
interrupção pelos monitores de pressão. Swap esteve ocupado; disponibilidade
de RAM física foi medida separadamente, sem contar swap como RAM rápida.

Evidências preservadas em `laboratorio-local/professor-moe-35b/metricas/`:

- `geracao-controlada-hoshino-20261013-213421.json` (+ log).
- `geracao-controlada-lilith-20261013-213748.json` (+ log).
- `geracao-controlada-alistair-20261013-214046.json` (+ log).

### O que melhorou e o que ainda falhou

Melhoria demonstrável: escrita por prefixo não recebe revelações futuras;
o método conjunto vazou a peça sob a caixa e a pista do farol antes de serem
ditas. Não houve ganho consistente de naturalidade ou da avaliação do crítico.

Falhas reais: o professor aprovou "sem dado no banco, não existiu", negação de
acesso a histórico persistente, causa de entrega não confirmada, nome Alistair
atribuído ao interlocutor e respostas genéricas/poéticas fora de proporção.
O crítico também rejeitou figura de linguagem como se exigisse corpo físico.
Por isso PASS técnico **não é aprovação de personalidade**.

Após ajustar instruções e gates, um novo ensaio físico com Hoshino (`staged`)
gerou três diálogos em 83,86 s, carga 19,02 s, pico 7.439.364.096 bytes:
`geracao-controlada-hoshino-20261013-215815.json`. O crítico aprovou 3/3,
mas ainda deixou passar dois defeitos:

- "Não tenho registro de ter falado sobre nenhum livro ontem", sem consulta.
- "o problema foi na entrega", embora houvesse apenas timeout sem confirmação.

Esses textos reais viraram regressões. Gates `v1.12.3` os recusam: reaplicação
aos mesmos textos = 1/3 passa (quebra-cabeça), 2/3 bloqueados com motivo.
Essa reaplicação NÃO foi uma nova geração do 35B. O exemplo que passa ainda
é genérico e pede revisão humana; nenhum dos 21 diálogos foi aprovado como
dataset, exportado, usado em treino ou promovido.

Conclusão: melhor integridade de produção de dados, **professor ainda não
homologado para produzir personalidade autonomamente**. Curadoria por exemplo
continua obrigatória; rotina automática permanece desligada.

## Recuperação local: contrato implementado

Usa `treinos_unificados`/worker/registro/locks já existentes e os conversores
llama.cpp instalados. Suporta Qwen3.5 9B, Qwen2.5 7B, Yi 6B existente e Alistair
4B, nas entidades correspondentes; não reinstala candidatos removidos.

1. Modelo instalado é preservado; descarregado não significa ausente.
2. Última estável do registro da mesma entidade/base tem preferência. SHA,
   proveniência, avaliação física e assinatura da base precisam corresponder.
3. Se não houver estável aprovada, usa original local pinado. Estável corrompida
   bloqueia: não vira fallback silencioso.
4. Verifica espaço de staging/F16/Q4/importação, RAM física, permissões, hashes,
   arquitetura, template, tensores e contagem de camadas antes de publicar.
5. Importa em store próprio, sem pull. Original convertido separado; alias
   staging só é publicado após inferência real, verificação GPU e unload.
6. Quando a fonte é estável aprovada, a recuperação ativa essa versão, conforme
   escolha explícita do usuário. 9B usa o seletor Original/Neural existente.
7. 6B original experimental não é habilitado no selector apenas por converter.
8. Crash, cancelamento e publicação incerta bloqueiam replay automático.
   Recibo `publishing` nunca é executor verificado. Worker ainda liberando
   locks impede iniciar a próxima recuperação/entidade.

Ao acordar pela Central, entidade fica **acordando / recuperando executor**;
não é marcada acordada durante conversão. Sleep/shutdown cancela apenas seu
job. Falha permanece durável. Abrir UI/consultar preview não carrega pesos.
A inicialização individual relê o modo Neural após a recuperação.

Endpoints autenticados existentes do laboratório ampliados:
`POST /api/treinos/recovery-preview`, `POST /api/treinos/recovery-start`.
Seção **Treinamento → Recuperar executor ausente — pesos locais**; mesmo
progresso/log/parada dos jobs. Nenhum terminal ou comando arbitrário novo.

### Defeitos encontrados fisicamente

- Job `972de431cde04908`: projetor exportado como `model-f16.gguf`, não o nome
  presumido pelo helper. Corrigido com outfile explícito e regressão.
- Job `4d4e6eb3eac94416`: daemon Hoshino não conseguiu remover pasta manifests
  sem permissão. Usuário autorizou/executou `chmod g+w` nas duas pastas exatas.
  Preflight agora verifica permissões e daemon usa `OLLAMA_NOPRUNE=1` para
  não apagar automaticamente blobs preexistentes.
- Job `82cc3450e74f4705`: conversão anunciava 33 camadas, mas continha blocos
  0–31; Ollama recusou `blk.32.attn_norm.weight`. Causa era metadata MTP do
  conversor atual. `--no-mtp` oficial e validação de layout impedem importar
  novamente esse artefato. Contrato do cache versionado; originais intactos.
- Job `0d6aece0031142af`: inferência/unload passaram, mas `/api/copy` retornou
  HTTP 200 vazio e o helper tentou ler JSON. Corrigido apenas o contrato de
  copy; chat/streams continuam exigindo respostas completas. A publicação
  pendente foi confirmada por hashes/receipt, sem repetir copy nem inferência.
- Job `c4926c67b327431c`: o verificador antigo assumia registry/library e
  procurou o alias hf.co no lugar errado. Generalizado o helper existente
  após mapear consumidores, com regressão para nomes simples/namespace/hf.co.
  Novamente confirmação sem replay; erro anterior continua no job/log.

A conversão reprovada inicialmente reutilizada por SHA NÃO virou executor
válido: o probe detectou incompatibilidade. Artefatos/logs falhos preservados,
sem sobrescrever aliases ou fingir inferência bem-sucedida.

### Estado dos ensaios de recuperação

**Verificado fisicamente**, em sequência, a partir dos originais locais:

| Entidade/base | Job | Carga | Inferência | Lease | Pico global VRAM |
|---|---|---|---|---|---|
| Hoshino 9B | `c4926c67b327431c` | 3,740 s | 0,668 s | 5,676 s | 4.760.338.432 B |
| Lilith 9B | `0d6aece0031142af` | 4,049 s | 0,248 s | 5,800 s | 4.775.026.688 B |
| Hoshino 7B | `a420db57221c4e89` | 2,964 s | 0,118 s | 3,457 s | 5.999.190.016 B |
| Lilith 7B | `ce900537623c46bb` | 2,897 s | 0,326 s | 3,575 s | 5.898.354.688 B |
| Hoshino/Yi 6B experimental | `27207e019ef04a7a` | 2,259 s | 0,468 s | 3,001 s | 4.656.439.296 B |

Probe mínimo **"Responda somente: Olá."**: estes tempos NÃO representam conversa
normal, tarefas, raciocínio, personalidade ou qualidade de treino. Todos
confirmaram done, GPU via `/ps` e amdgpu, margem, ausência de pressão no monitor,
unload e saída do daemon owned. 9B usa offload conservador de 20 camadas e
16K de contexto; 7B auto offload com 8K; Yi 6B com 4K. Não alterou heurísticas
de camada nem habilitou concorrência. Vision aparece em `/show` dos 9B e o
projetor está pinado; não foi realizada inferência visual nesta rodada.

Hoshino/Lilith 7B foram recuperados pelo próprio `ensure`, sem iniciar entidade.
Repetir `ensure` depois devolveu `ready/needed=false`, sem converter de novo.
Hoshino e Lilith têm o mesmo hash de pesos mas arquivos/stores independentes:
9B em inodes `7609194` e `21366445` no device `66306`.

Yi 6B ficou `activated=false`; não houve alteração de `executores.json` nem
habilitação de terceiro executor. A fonte estável 6B também não cria um novo
executor: precisa já estar selecionado/aprovado no contrato conversacional.
Conversão do 6B na Lilith não foi repetida; isolamento/roteamento testados em
fixture, não uma segunda execução física do 6B.

Alistair 4B: preview e execução explícita confirmaram
`ready/needed=false/production_changed=false`; não reconverte nem troca
executor existente. Seu fallback CPU com métricas GPU indisponíveis e GPU
oportunista P5 foram cobertos em fixture, **não por nova inferência física 4B**.

Não há adaptador estável aprovado atualmente no registro:
preferência/isolamento de estáveis são contratos testados em fixture, não uma
implantação neural real comprovada.

Depois: leases/compute vazios, GPU voltou a cerca de 0,73 GiB de uso externo;
os nove hashes (constituição, self-model e SQLite das três entidades) iguais
ao início. Margem = 805.306.368 B; `concurrency_validated=false`; rotina noturna
`enabled=false`. Disco ainda possui cerca de 51 GiB livres (94% utilizado):
respeitar reserva e não iniciar download/treino longo sem novo preflight.
Busca no journal de kernel desde 21:30 não retornou os padrões de reset,
ring timeout ou GPU fault consultados; isso não equivale a soak prolongado.

## Validação e limites

Novas regressões cobrem fonte local, estável estrangeira/corrompida, SHA,
espaço, permissões, 4B/6B/7B/9B, no-op, crash/publicação incerta, cancelamento,
processo owned, MTP, nome do projetor, lease/unload e supervisor. Browser real
com transporte simulado passou; não prova hardware nem implantação neural.

Suíte oficial após primeira integração: **74/74 grupos**, zero falhas.
Execução do laboratório nessa revisão: **223/223 testes**. Regressões
acrescentadas depois serão contadas na execução final abaixo. Houve uma
invocação inicial incorreta do runner (nomes em vez de paths); ela foi recusada
antes de executar os testes e foi repetida corretamente, sem editar a suíte.

Outra rodada completa durante escrita/quantização pesada resultou **73/74**:
`test_gpu_cooperativo.test_priority_fifo_does_not_steal_running_compute`
excedeu `high.wait(1)`. Repetido sem conversão: **42/42** em 2,460 s. Nenhuma
heurística ou timeout de teste foi alterado para escondê-lo. A falha sob carga
está preservada como sensibilidade temporal pendente, não prova de prioridade
validada em todos os cenários. Último grupo de executores: **83/83**; fixture
agora isola também a raiz do projeto para não ler recibos GPU de produção.

**Execução final sem conversões/inferências reais simultâneas: 74/74 grupos
oficiais**, zero falhas. **234/234 testes do laboratório** em 13,767 s.
Baseline do laboratório era 195: **39 novos testes permanentes**, mais duas
regressões no grupo existente de executores (83 testes, grupos oficiais continuam
74). Browser Chromium com transporte simulado: PASS, zero erros, 28 chamadas
de fixture. Sintaxe Python exercitada pelas suítes; shell/JS e `git diff --check`
passaram. Nenhum teste de UI/fixture foi contado como prova física de modelo.

Verificação real de restauro concluída nos originais 9B/7B das duas entidades
e no 6B experimental Hoshino. Implantação da última **LoRA estável aprovada**
continua pendente de existir essa versão no registro e de ensaio do adaptador
no backend instalado. Seleção/isolamento/integridade dessa rota foram testados
em fixture; se importação/probe falhar, ela NÃO é ativada.

### Próximos pontos, sem expansão nesta rodada

1. Curadoria humana de bons exemplos de referência por entidade; professor
   ainda precisa melhorar naturalidade/persona sem perder honestidade.
2. Quando houver estável aprovada, ensaio físico do GGUF LoRA → importação →
   inferência → ativação, com original preservado; não fabricar aprovação agora.
3. Tratar a sensibilidade temporal do teste de prioridade sob I/O pesado em
   rodada própria, com medição; não alterar prioridades/margens especulativamente.
4. Uso humano/prolongado das entidades, qualidade e visão continuam distintos
   do smoke técnico de dois tokens. O restante da fila geral não foi implementado
   nesta rodada focalizada. Nenhum commit/push foi feito automaticamente.

Riscos: qualidade subjetiva do professor; LoRA GGUF de estável ainda não
exercitado fisicamente nesta rodada; uso prolongado; recuperação explícita de
publicação interrompida; daemon órfão após kill abrupto; restrições/latência de
conversão do hardware. Não habilita concorrência GPU nem muda margens/RM.

### Arquivos desta rodada

Criados: `laboratorio/recuperacao_modelos.py`, plano e este relatório.
Alterados: `laboratorio/trabalhador.py`, `treinos_unificados.py`, `professor_moe.py`,
`painel.py`, `web/app.js`, `web/index.html`; `iniciar_entidades.py`,
`iniciar_hoshino.sh`, `app/core/resource_manager.py`; testes existentes
`test_consolidacao.py`, `test_personalizacao_moe.py`, `test_noite_supervisor.py`,
`browser.cjs`, `testes/test_executores_leves.py` e documentação do laboratório.
Também `scripts/preparar_executores_leves.py`: caminho do manifesto existente
generalizado; continua o mesmo verificador/importador, não um sistema paralelo.
Outras diferenças no working tree são preexistentes, não novas capacidades
desta rodada. Pesos HF, identidades e bancos mentais são preservados.
