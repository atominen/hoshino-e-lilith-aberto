# Refinamento — rodada 1, 06/10/2026

Escopo congelado. Esta rodada reconcilia a auditoria histórica e endurece a
execução offline. Não conclui a fase inteira de refinamento.

Não foram acrescentados modelos, capacidades, bancos de produção, backends,
schedulers ou sistemas mentais. Cloud e configurações de GPU/voz não foram
alteradas. Os pesos, bancos e identidades existentes foram preservados.
`compartilhado/config/gpu.json` continua com `concurrency_validated: false`.

## Antes das alterações

- Suíte oficial anterior: **40/40 grupos**, saída de processo 0.
- Reproduzidos os **nove arquivos históricos que falhavam**. A auditoria
  anterior registrava 15/25 passando, nove falhando e um manual.
- A reprodução de `test_ollama_lifecycle` bloqueou `subprocess.Popen` real
  adicionalmente: a fixture antiga não mockava a criação de daemon próprio.
  Não seria aceitável reiniciar/criar serviço real para reproduzir um mock.
- `test_microfone_continuo_v33` não foi executado em hardware nesta rodada.

## Classificação de todas as falhas conhecidas

A = regressão real; B = teste obsoleto; C = fixture/discovery incorreta;
D = manual/inadequado para CI; E = comportamento removido intencionalmente.
Um arquivo pode conter problemas de mais de uma categoria.

| Arquivo histórico | Expectativa antiga / falha reproduzida | Classificação e evidência atual | Correção / contrato substituto |
| --- | --- | --- | --- |
| `test_capacidade_operacional` | `write_file` público; no máximo 12 ferramentas em conversa; verificação por `read_file` separado | **B**. `dispatch.esquemas`, `NUCLEO` e `LEGADOS_ARQUIVOS` expõem `workspace` e 13 consultas no núcleo atual. A intenção e adaptadores antigos continuam internos. | Mesmo arquivo: núcleo exato, ausência de APIs legadas na superfície pública; gravação real temporária, hash/recibo, conteúdo e leitura reais. Contrato legado de verificador continua coberto. |
| `test_execucao_paralela` | Resultado ainda denominado `write_file`; erro como string | **B**. `InterfaceHoshino._executar_chamadas_da_etapa` converte o adaptador para `workspace` antes do dispatcher e devolve erro estruturado. | Mesmo arquivo: consultas em paralelo, mutações seriais, ordem, suboperação `salvar`, `verified=false` no mock de agendamento e erro JSON estruturado. Não afirma que o mock gravou arquivo. |
| `test_v17_arquitetura` | `write_file` exposto ao LLM | **B**. Contrato público unificado de `dispatch.esquemas`. | `test_routing`: exige `workspace`, comando subsequente e ausência de todas as APIs legadas. Filtros de ferramentas próprias, erros mecânicos e IDs de abas preservados. |
| `test_v18_continuidade` | Etapas `write_file/execute_command/read_file`; falha com status `failed` | **B** para nomes/status. Em `task_state.registrar_ferramenta`, erro mantém a operação pendente, registra o erro e não marca execução/conclusão. **A adicional**: recibo síncrono dispensava verificação em dispatch/cognição, mas a tarefa persistida ainda acrescentava `ver_comando` impossível para comando sem job. **C adicional**: UI comparava strings com listas e nunca detectaria binding removido. | Mesmo arquivo: sequência real de escrita/comando/leitura temporários; encaminhamento do recibo existente; erro registrado sem sucesso; verificação conservadora sem recibo ou com recibo divergente; comparação correta das chaves de bindings. |
| `test_v19_continuidade` | Roteador ainda expõe nomes antigos; repetição não duplica; reset preserva pessoas | **B** para nomes. **A**: `_compativel_com_pendente` comparava intenção `write_file/read_file` com etapa `workspace`, criando outra tarefa. **E** para preservar pessoas: `memory_admin.wipe_persistent_memory` documenta reset total, já coberto por `test_reset_full_v28`. **A adicional**: formatos antigos de operações/executadas não preservavam corretamente categoria/IDs após canonicalização. | Mesmo arquivo: retomada e barreira de etapas via workspace; repetição mantém ID/etapas; leitura/anexação não substituem escrita; reset remove estado dinâmico e preserva arquivo de identidade; compatibilidade em leitura sem regravar JSON antigo ou perder escrita já registrada como executada. |
| `test_ollama_lifecycle` | Recuperação das entidades via restart genérico do systemd | **B/C**. `recuperar` não reinicia serviço genérico nas portas próprias 11435/11436. Fixture trocava URL para 11434, mas deixava HOST em 11435. Havia `unittest.main()` antes da classe assíncrona, portanto seu teste nunca rodava. | HOST/URL coerentes; criação própria sempre mockada; testes Hoshino/Lilith proíbem restart genérico; modelo ausente não inicia/baixa; teste assíncrono reativado cobre recuperação uma vez, executor inalterado e segunda queda sem loop. Lifecycle de produção não foi alterado. |
| `test_v20_iniciativa` | `kernel.deliberar` falha com `no such table: goals` | **C**. `init_db.SCHEMA` já cria `goals` e migra seus campos. `agenda` importa `DB_PATH` ao carregar, mas a fixture só trocava `config.DB_PATH`/`init_db.DB_PATH`. Outros testes atuais de agenda vinculam explicitamente esse alias ao banco temporário. | Fixture patcha/restaura `agenda.DB_PATH`; consulta `goals` confirma tabela legítima vazia antes da deliberação. Não foi criada tabela/banco novo na aplicação. |
| `test_v32_multimodal` | Animagine XL 4 | **B**. `config` e `_executar_sd` usam Qwen-Image 2.1 Q6_K, GGUF de difusão, encoder e VAE separados, CPU/Vulkan e limite de VRAM. | Mesmo arquivo: identifica os três componentes atuais, localização/configuração, parâmetros em CPU e margem dos 8 GiB. Preserva verificações de ASR/Kokoro e acrescenta rota local sem Azure/fallback Qwen. Não carrega modelo nem gera imagem. |
| `test_v35_hardening` | Worker fake retorna `ok` sem request ID/WAV; anuncia prontidão como resultado de síntese | **C**. `voice._sintetizar_pedido`, `audio_service.Worker` e `voice_worker` exigem ID correspondente. O worker real não publica resultado de síntese sem pedido. | Fixture devolve ID recebido e produz WAV PCM temporária válida; aviso não-resultado continua ignorado; faltando ID ou com ID antigo deve falhar. Testa transporte simulado, não qualidade de TTS real. |
| `test_microfone_continuo_v33` | Captura 60 segundos e espera fala humana durante a suíte | **D**. O próprio arquivo descreve teste manual de hardware. | Catalogado fora da CI; runner rejeita antes de inicializar. Import/discovery é inerte; execução com flag offline/CI é recusada. Execução manual continua capturando microfone real, sem mock e sem download incidental. **Hardware continua pendente.** |

Os 15 históricos que já passavam também foram incorporados à suíte, sem remoção
de verificações. Os nove arquivos reconciliados mantêm seus nomes; a mudança de
nome de caso individual é:

- `test_reset_memoria_preserva_cadastro_de_pessoas` →
  `test_reset_total_remove_pessoas_preserva_identidade_estatica`, também
  apoiado pelo contrato existente em `test_reset_full_v28`.
- `test_recuperacao_aciona_restart_quando_api_cai` →
  `test_recuperacao_dedicada_nao_reinicia_servico_generico`.

## Bugs reais corrigidos e consumidores localizados

### 1. Repetição de operação pendente

Localizados `iniciar_ou_continuar`, `_compativel_com_pendente`, normalização de
operações, `proxima_operacao`, roteamento e consumidores de tarefa em `main`.
Agora a comparação usa a próxima operação atômica não executada e a capacidade
pública atual. Em workspace também compara suboperação/modo. Repetir leitura ou
escrita conserva a tarefa; ler/substituir/anexar não são confundidos.

Os testes de repetição de escrita e leitura falharam antes da correção,
mostrando IDs de tarefas diferentes. Não foi restaurada a arquitetura antiga.

### 2. Recibo perdido ao persistir progresso

Localizados os dois consumidores de `task_state.registrar_ferramenta` em `main`,
chamadas legadas nos testes, metadados de capabilities, recibos de dispatch e
consumo pela cognição. O consumidor de ferramentas agora passa o **mesmo recibo**
já produzido, sem um segundo sistema de contratos.

O argumento novo é opcional e somente nome/status/output correspondentes e
`requires_verification` booleano podem dispensar a verificação adicional.
Chamadas antigas, recibos incompletos ou de outra operação mantêm o caminho
conservador. Resultado incerto mantém a política existente de pausa.

### 3. Compatibilidade de tarefas antigas

Localizados o carregador `_carregar_row`, `_normalizar_operacoes`, mapa de IDs
executados, planejador, roteador e controlador. Listas de nomes e operações
antigas em dicionários são adaptadas em memória para workspace, preservando
IDs, suboperação e modo. Nome antigo de operação executada é associado à
suboperação correspondente, não apenas ao nome genérico `workspace`.

Isso evita perder a marca de uma escrita já executada ou usar a marca de
leitura para concluir uma escrita. Não migra/regrava os bancos antigos
automaticamente. Os três primeiros casos adicionais de compatibilidade
falharam antes da correção; o caso da lista com escrita executada complementa
a proteção contra repetição.

## Organização e isolamento da suíte

O runner existente continua sendo `rodar_testes.sh`, usando
`testes/executar_isolado.py`. Não há runner V2 paralelo.

| Categoria principal do arquivo | Grupos | Execução padrão |
| --- | ---: | --- |
| Unitário | 10 | Sim |
| Regressão | 21 | Sim |
| Integração offline | 34 | Sim |
| Hardware/manual | 1 | Não |
| Integração local com serviços/modelos | 7 scripts existentes inventariados | Não |

Grupos mistos mantêm suas asserções unitárias; a categoria identifica sua
responsabilidade predominante. `test_manual_diretivas` é automatizado apesar
do nome histórico: testa agenda/diretivas com banco temporário, não hardware.

O inventário único em `testes/catalogo.py` verifica duplicatas, arquivos
ausentes e testes não classificados. Não usa um glob para executar testes.

```bash
cd "/home/gustavo/hoshino e lilith"
bash rodar_testes.sh
bash rodar_testes.sh --tipo unitario
bash rodar_testes.sh --tipo regressao
bash rodar_testes.sh --tipo integracao_offline
```

Guardas adicionais no processo isolado:

- Estado, identidades de teste e bancos temporários; SQLite real recusado antes
  de abrir, inclusive URI SQLite. Escritas/alterações fora de área temporária
  recusadas; `/dev/null` é permitido para descarte.
- Credenciais Azure reais removidas do ambiente de teste; casos Azure usam
  sentinelas e transporte mockado. Zero chamadas Azure reais/quota nesta rodada.
- Download Hugging Face offline; conexão Python externa ou com daemons reais
  recusada. HTTP de integração só em portas efêmeras de loopback abertas pela
  própria fixture, com backend fake explícito.
- Inicialização/restart real de serviços/modelos/captura recusados; microfone
  bloqueado por stub que **lança erro**, nunca por áudio/sucesso fictício.
- Captura manual não é importada/executada; sua descoberta não carrega ASR.
- PyAutoGUI fica indisponível e DISPLAY/WAYLAND_DISPLAY são retirados do
  processo isolado. Sua importação antes disso havia aberto sockets X11 e
  emitido ResourceWarning; não foi suprimido o warning para fingir correção.
- GPU/RAM da suíte simuladas explicitamente; as guardas não afirmam validação
  de concorrência, GPU real, sintetizador real ou microfone real.

Essas guardas previnem efeitos acidentais da suíte conhecida. **Não constituem
um sandbox para código arbitrário/não confiável**, nem pretendem controlar
toda chamada nativa de um subprocesso. Ensaios existentes de oficina/laboratório
usam seus mecanismos atuais de isolamento e código temporário conhecido.

## Testes novos e resultados

Além dos casos substituídos, foram adicionados **31 casos novos e um caso
assíncrono antigo reativado**:

- V18: três casos de recibo ausente, incompatível e incompleto/divergente.
- V19: sete casos de leitura repetida, distinção leitura/escrita/anexação,
  dicionário legado sem migração e marcas antigas de execução.
- Lifecycle: Lilith não reinicia serviço genérico, modelo ausente não inicia,
  segunda queda não recupera em loop; reativado o primeiro caso assíncrono.
- V35: ID ausente e ID antigo rejeitados, sem eliminar o caso válido.
- Isolamento: 16 casos cobrindo inventário, exclusão/importação manual, rede,
  portas de daemons, HTTP efêmero, bancos temporários/reais/URI, escrita,
  restart, microfone, links relativos e limpeza de venv/dir_fd.

Resultados já obtidos durante o desenvolvimento; fechamento integral abaixo:

- Nove arquivos históricos reconciliados: todos passaram.
- V18: **19/19** casos. V19: **17/17**. Lifecycle: **8/8**.
- V35: **5/5**. V32: **20/20** verificações de contrato/configuração.
- Duas execuções integrais ampliadas: **65/65 grupos**, saída 0.
- Bateria anterior de executores leves: **47/47**, preservada dentro da suíte.
- Recusa explícita do manual pelo runner: saída não-zero esperada, antes de
  importar ASR/captura. Não conta como validação de microfone real.
- `bash -n rodar_testes.sh`: passou.

**Fechamento após a última alteração de código:** `bash rodar_testes.sh`
concluiu com **65/65 grupos**, saída **0**, incluindo os 24 históricos
automatizáveis e o novo grupo de isolamento. Execuções direcionadas confirmaram
**47/47** executores leves, **8/8** lifecycle e **16/16** isolamento. Nenhum
processo de teste/manual/worker fake permaneceu na inspeção final.

| Verificação | Antes | Depois |
| --- | --- | --- |
| Suíte oficial | 40/40 grupos | 65/65 grupos |
| Nove históricos problemáticos | 9 arquivos falhando | 9 arquivos passando, com classificação documentada |
| Caso assíncrono de recuperação | não descoberto | executado e aprovado |
| Microfone contínuo | manual fora do contrato offline | explicitamente separado, importação inerte e execução offline recusada |

Isto não é comparação de desempenho: o workload da suíte cresceu e não foi
usado para afirmar redução de latência em produção.

Falhas intermediárias **não omitidas**: a primeira versão das guardas tentou
importar PortAudio, indisponível nesta máquina (**0/65** nessa execução).
Passou a usar stub de recusa sem carregar PortAudio. A execução seguinte
ficou em **62/65**: URI SQLite temporária e links/limpeza de venv foram
indevidamente recusados. As guardas foram corrigidas e os casos de regressão
foram acrescentados. Nenhuma dessas falhas virou sucesso fictício.

## Arquivos alterados/criados

Produção — apenas:

- `app/core/task_state.py`
- `app/main.py`

Testes históricos atualizados:

- `testes/test_capacidade_operacional.py`
- `testes/test_execucao_paralela.py`
- `testes/test_v17_arquitetura.py`
- `testes/test_v18_continuidade.py`
- `testes/test_v19_continuidade.py`
- `testes/test_ollama_lifecycle.py`
- `testes/test_v20_iniciativa.py`
- `testes/test_v32_multimodal.py`
- `testes/test_v35_hardening.py`
- `testes/test_microfone_continuo_v33.py`

Infraestrutura existente/documentação:

- `testes/executar_isolado.py`
- `rodar_testes.sh`
- `README.md`

Arquivos novos, somente teste/inventário/relatório:

- `testes/catalogo.py`
- `testes/test_isolamento_suite.py`
- `docs/REFINAMENTO_20261006.md`

Backups reversíveis anteriores às respectivas alterações em
`arquivo/refinamento-20261006/`: `codigo_antes.tar.gz`, `main_antes.tar.gz`,
`manual_readme_antes.tar.gz`. Não restaurar tudo indiscriminadamente sobre
alterações posteriores; comparar/restaurar os arquivos desejados.

## Comportamentos alterados / preservados

- Repetição compatível de operação mantém tarefa, em vez de pausar/criar outra.
- Operações antigas são adaptadas em leitura, preservando marcas de execução.
- Comando com recibo síncrono completo não ganha verificador de job inexistente.
- A suíte padrão passou de 40 para 65 grupos e falha para teste não classificado.
- Descoberta do teste manual tornou-se inerte; captura exige execução manual
  explícita, fora da CI, com ASR local disponível.
- Reset total **não mudou**; apenas seu teste obsoleto foi substituído.
- Lifecycle **não mudou**; restart genérico não foi reintroduzido.
- Escolha 7B/9B, pesos quentes, filas/prioridades, Alistair CPU/GPU, Azure/Qwen/
  Kokoro e cloud **não mudaram**. Não houve otimização sem benchmark comparável.
- Entidades/daemons reais não foram reiniciados; a aplicação incorpora as
  mudanças de código na próxima inicialização normal do processo correspondente.

## Medição real somente observacional

Uma leitura de telemetria às 19:02:57 BRT encontrou `amdgpu/sysfs`, VRAM total
8.573.157.376 bytes, usada 1.175.044.096 bytes, GPU busy 0%, RAM disponível
25.202.855.936 bytes. Disco: aproximadamente 84 GiB livres, 90% de uso.
É **um snapshot sem workload**, não prova latência, desempenho ou estabilidade.

Os processos principais observados mantinham sua inicialização anterior:
central/Alistair/daemon desde 13:45; daemons Hoshino/Lilith desde 06:52.
Nenhum restart foi usado para tornar um teste verde.

## Riscos restantes e próximos problemas prioritários

Auditoria histórica: **100% das nove falhas conhecidas e do manual classificadas**.
Os testes corrigidos não demonstram por si só funcionamento prolongado.

Próxima rodada: preparar/realizar ensaios controlados com os executores/modelos
atuais, usando o Resource Manager existente. Primeiro serializados; não alterar
heurísticas ou `concurrency_validated` com base em mocks ou neste snapshot.

Permanecem pendentes:

1. Séries A–I de GPU AMD real: H/L 9B/7B, Alistair CPU/GPU, imagem sozinha,
   conversa durante imagem e áudio durante jobs; medir carga, filas, leases,
   RAM/VRAM, load/unload/reload, latência, RADV/reset/timeouts e outra aplicação.
2. Calibração conservadora de 7B/9B com dados pareados e ausência de starvation;
   nenhuma conclusão de ganho baseada apenas no tamanho dos modelos.
3. Avaliação repetível de naturalidade/continuidade de identidade entre
   executores, incerteza e isolamento de memória nas situações solicitadas.
4. Azure **real**, quando credenciais estiverem disponíveis. A disponibilidade
   real de credenciais não foi validada nesta rodada. Mocks não aprovam Azure.
5. PC2 **Athlon físico**: boot/HDD/RAM/latência/LAN/autenticação/perda/reinício/
   fallback e uso prolongado. Loopback com fake engine não substitui esse teste.
6. Microfone/saída/autoplay/interrupção em hardware real, fora da CI.
7. Sessões prolongadas e reinício real controlado: leaks, deadlocks, crescimento
   de RAM e preservação de memória/estado. Testes temporários não equivalem a
   reiniciar e validar os bancos reais existentes.

Portanto: rodada de contratos históricos/offline concluída; **refinamento do
sistema em uso real ainda não concluído**.
