# Da “bomba” até agora — relatórios reunidos

Data de compilação: 10/10/2026. Projeto: Hoshino, Lilith e Alistair.

Continuação posterior: [Consolidação cognitiva — implementação e ensaios reais](</home/gustavo/hoshino e lilith/docs/CONSOLIDACAO_COGNITIVA_20261010.md>).
Essa rodada não reescreve os resultados históricos reproduzidos abaixo. Inclui
resumos incrementais, diários, lições e oficina, com falhas 9B/ROCm e incidente
de fixture recuperado explicitamente documentados; não é aprovação integral.

Este documento reúne **oito relatórios completos**: os sete produzidos desde o material “CODEX — CONSOLIDAÇÃO DA ARQUITETURA COGNITIVA, MEMÓRIA HÍBRIDA, APRENDIZADO…” até a validação física do cache em RAM, mais a continuação/limpeza desta rodada. Os originais permanecem preservados. Os relatórios anteriores de consolidação/ensaio são antecedentes, não novos resultados desta etapa.

## Leitura rápida: o que realmente avançou

| Rodada | Entrega principal | Validação registrada |
|---|---|---|
| Auditoria cognitiva | Inventário dos mecanismos existentes, lacunas e correção da atribuição do backend físico | Auditoria do código, métricas e logs; não aprovação integral |
| Fundação histórica | Autoria, destinatário, timestamps e consultas cronológicas sem atribuir registros legados cegamente | 23 novos métodos de teste; suíte final 74/74 |
| Sessões diárias | Catálogo diário no armazenamento existente, histórico arquivado e vínculo correto de respostas tardias | 16 novos métodos; suíte final 74/74 |
| Tempo e continuidade | UTC/tempo monotônico, retomada após restart e ausência tratada como hipótese | 19 novos métodos; suíte final 74/74 |
| Agenda e reflexão | Recorrência, limites temporais da reflexão e cooldown conservador | 25 novos métodos; suíte final 74/74 |
| Reflexão com evidências | Material selecionado inteiro, referências de origem, omissões explícitas e reflexão distinta de fato | 14 novos métodos; suíte final 74/74 |
| Cache em RAM | Orçamento agregado limitado; daemons reiniciados cooperativamente; recuperação real de prefixos | 12 + 3 novos métodos; suíte 74/74 antes/depois; inferências físicas controladas |
| Recovery e limpeza | Reconciliação da reflexão salva; retirada de pesos não aprovados; memórias/conversas de teste removidas sem replay | 7 + 1 novas regressões; suíte final 74/74; operações administrativas reais verificadas |

Os números de métodos são os registrados por rodada, **não grupos adicionais da suíte**. O total oficial continua sendo 74 grupos. Falhas intermediárias e limitações aparecem nos relatórios originais abaixo; não foram apagadas para apresentar uma história artificialmente verde.

## RAM, VRAM e recuperação: o que está implementado

- **SQLite/índice existente:** memória durável e busca de informações, com sujeito, autoria, tipo, confiança e evidência. A lembrança selecionada entra no contexto textual.
- **RAM:** cache de estados de prompt já calculados, limitado a 8 GiB agregados (3,5 GiB Hoshino; 3,5 GiB Lilith; 1 GiB Alistair). Não é um novo banco mental nem uma reserva integral antecipada de RAM.
- **VRAM:** pesos/camadas e estados ativos de inferência quando admitidos pelo Resource Manager. É a área rápida, sujeita ao teto físico de 8 GiB e à margem de segurança existente.
- RAM também pode conter mmap/staging de pesos e camadas processadas na CPU no offload parcial. O backend atual não permite prometer RAM exclusivamente para cache e nenhum peso nela.
- Um prefixo reutilizável pode evitar novo processamento. **Memória semântica relevante e prefixo KV reutilizável são coisas diferentes:** alterar texto, ordem, executor ou configuração pode invalidar a reutilização.
- Não há prova de “VRAM expandida pela RAM” nem de GPU calculando automaticamente sobre todo cache host. O que foi observado foi cache host recuperado pelo backend e inferência admitida conforme os recursos.
- Alistair conserva GPU oportunista e CPU como fallback. A execução física confirmou ambos; a GPU não é concedida apenas porque ele está sozinho.
- ROCm foi o backend selecionado nos logs físicos recentes, apesar de Vulkan habilitado no ambiente. A errata permanece junto aos resultados originais.

### Amostra física do cache (não benchmark geral)

| Executor | Chamada fria* | Retorno ao prefixo A | Prefill frio → retorno |
|---|---:|---:|---:|
| Hoshino Qwen2.5 7B | 6,290 s | 0,416 s | 2,904 → 0,034 s |
| Hoshino Qwen3.5 9B | 6,904 s | 0,709 s | 2,906 → 0,112 s |
| Lilith Qwen2.5 7B | 7,846 s | 0,409 s | 2,913 → 0,033 s |
| Alistair Qwen3.5 4B / CPU | 45,607 s | 0,815 s | 41,039 → 0,194 s |
| Alistair Qwen3.5 4B / GPU | 4,104 s | 0,679 s | 1,611 → 0,089 s |

*Fria significa runner descarregado; o cache de disco do sistema não foi esvaziado. São prompts curtos sintéticos A/B/A, não conversas reais longas. O relatório detalhado inclui RSS corrigido, logs de recuperação, tentativas não aprovadas, condições e limitações. Não atribuir redução do tempo de carregamento dos pesos exclusivamente ao cache de prompt.

## O que ainda não está concluído

- A “bomba” inteira **não está implementada/aprovada**: diário com controles de acesso e edição voluntária, resumos diários incrementais, aprendizado experiencial completo e oficina visual ainda têm lacunas.
- A persistência da reflexão e o marcador de conclusão noturna continuam dois destinos distintos. Nesta rodada novos lotes recebem reconciliação/idempotência após commit; lotes legados sem metadados e crash físico ainda não têm aprovação integral.
- Não há certificação de retenção em conversas muito longas, eviction sob pressão, soak prolongado, ausência de vazamentos ou convivência pesada com jogo/voz/imagem.
- Resource Manager ainda tem riscos documentados de starvation, RAM agregada futura, pressão/swap, TOCTOU de métricas e daemon sobrevivente ao cliente.
- Os ensaios de cache não aprovam Discord/Minecraft físicos completos, PC2 real nem providers externos.
- Nenhum terceiro executor ~6B foi aprovado. Não preencher esse lugar habilitando um candidato defeituoso.

## Atualização desta rodada

A pedido explícito do usuário, esta rodada reuniu os relatórios e retirou pesos não aprovados, sem criar outro scheduler/banco nem baixar modelos:

- Jan, Esper3 e Hunyuan removidos de Hoshino/Lilith; GGUF duplicado do Esper3 removido. Espaço livre aumentou **28,358 GiB** durante a limpeza.
- Mantidos **9B + Qwen2.5 7B** por Hoshino/Lilith e **Qwen3.5 4B** por Alistair. Terceiro executor ~6B continua sem aprovação; nenhum substituto foi instalado.
- Limpas **194 memórias SQL + 168 entradas vetoriais** da Hoshino e **10 turnos lembrados** do Alistair. Lilith já estava vazia. Integridade dos três bancos: **ok**.
- Após confirmação do usuário, removidas **158 mensagens** do histórico bruto/FTS e o conteúdo de **170 envelopes** de conversa. As consultas reais de fila/conversa retornam vazias.
- Conservados IDs/autoria/desfechos mínimos, **78 recibos de resposta**, **91 chaves de dedup** e **16 resultados incertos**, sem fingir execução ou repetir efeitos. Cinco objetivos antigos foram cancelados, não completados.
- Preservados identidade, personalidade, relações/traços/estado psicológico, modelos ativos, configurações, recibos, relatórios e evidências. Há backups de manutenção pequenos; isto não é apagamento seguro de todas as cópias nem reset mental total.
- Corrigida a duplicação de reflexão após falha do marcador: **27/27** métodos de reflexão; mensagens/causalidade **41/41**; suíte completa final **74/74**.

O relatório 8 detalha arquivos, testes, falhas intermediárias, procedimento de limpeza e limitações. Concorrência GPU permanece desativada; Alistair mantém GPU oportunista/CPU fallback; não houve quota externa nesta rodada.

Os estados “instalado”, “preservado” ou “pendente” dos documentos originais descrevem **a data de cada documento**. Uma decisão posterior de limpeza não reescreve esses resultados históricos.

## Índice dos originais

1. [AUDITORIA_COGNITIVA_MEMORIA_HIBRIDA_20261009.md](</home/gustavo/hoshino e lilith/docs/AUDITORIA_COGNITIVA_MEMORIA_HIBRIDA_20261009.md>)
2. [FUNDACAO_HISTORICA_20261009.md](</home/gustavo/hoshino e lilith/docs/FUNDACAO_HISTORICA_20261009.md>)
3. [SESSOES_DIARIAS_20261009.md](</home/gustavo/hoshino e lilith/docs/SESSOES_DIARIAS_20261009.md>)
4. [TEMPO_CONTINUIDADE_20261009.md](</home/gustavo/hoshino e lilith/docs/TEMPO_CONTINUIDADE_20261009.md>)
5. [AGENDA_REFLEXAO_TEMPO_20261009.md](</home/gustavo/hoshino e lilith/docs/AGENDA_REFLEXAO_TEMPO_20261009.md>)
6. [REFLEXAO_EVIDENCIAS_RAM_20261009.md](</home/gustavo/hoshino e lilith/docs/REFLEXAO_EVIDENCIAS_RAM_20261009.md>)
7. [CACHE_RAM_20261010.md](</home/gustavo/hoshino e lilith/docs/CACHE_RAM_20261010.md>)
8. [CONSOLIDACAO_BOMBA_LIMPEZA_20261010.md](</home/gustavo/hoshino e lilith/docs/CONSOLIDACAO_BOMBA_LIMPEZA_20261010.md>)

As seções seguintes reproduzem integralmente o conteúdo dos originais no momento da compilação.


---

## Original 1 — AUDITORIA_COGNITIVA_MEMORIA_HIBRIDA_20261009.md

# Fundação cognitiva e memória híbrida — auditoria de 09/10/2026

## Escopo e preservação

Lido integralmente o material enviado (1.823 linhas). Esta é a **Fase 1**, antes da implementação incremental da fundação temporal. Não representa aprovação das oito fases. O pedido autoriza funcionalidades novas delimitadas — diário, oficina visual e sessões diárias — mas não autoriza substituição indiscriminada dos componentes existentes.

Referência do código: `f23ba0d721fac6cb53534b55fcc5b48547e1dec8`, com árvore previamente modificada. O estado atual não corresponde somente a esse commit. Nenhuma alteração anterior foi revertida. Nesta auditoria: sem inferências novas, downloads, drivers, chamadas pagas, migração de bancos, limpeza de pesos ou ativação de concorrência.

O resultado de **74/74 grupos** é o baseline da rodada anterior, não uma nova execução. Os resultados reais anteriores de modelos/programação continuam em `CONSOLIDACAO_FINAL_20261009.md`, inclusive falhas; não foram substituídos por expectativas desta especificação.

## 1. Descoberta importante: backend efetivamente usado

**Correção de proveniência:** os relatórios anteriores atribuíram a execução a Vulkan sem confirmar a seleção do runner. Os logs das últimas inferências mostram **ROCm**. A presença de `OLLAMA_VULKAN=1` não prova qual backend executou cada chamada.

Evidências locais em `compartilhado/runtime/ollama/`:

- `hoshino/server.log:81648`: seleção `library=ROCm`, 16:23 de 09/10. Linhas 81807–81809: 32/33 camadas offloaded, CPU_Mapped 683,55 MiB e ROCm0 4.674,33 MiB. KV ROCm0 256 MiB em 8K; tipos f16. Reserva de compute adicional registrada.
- `lilith/server.log:20611`: `library=ROCm`, 16:26. Linhas 20771 e 20792: buffers ROCm0 de pesos e KV.
- `alistair/server.log:15463`: `library=ROCm`, 13:59. Linhas 15636 e 15657: pesos ROCm0 2.603,50 MiB e KV 256 MiB.
- Ambientes dos três servidores incluem `HSA_OVERRIDE_GFX_VERSION=10.3.0` e `OLLAMA_VULKAN=1`; portas 11435/11436/11437 e armazenamentos separados. Ollama reporta versão 0.32.6.

Isso preserva a evidência de GPU real dos ensaios anteriores, mas **corrige o nome da rota**. Não comprova certificação oficial da GPU, execução nativa sem override, nem superioridade ROCm/Vulkan. Não foram reiniciados os servidores para forçar outra seleção.

## 2. Hardware e limites observados

| Item | Observação nesta auditoria |
|---|---|
| CPU | Ryzen 5 5500, 6 núcleos/12 threads |
| GPU | RX 6650 XT, Navi23/gfx1032, amdgpu, 8 GiB físicos |
| Vulkan | RADV disponível, Mesa 25.2.8; disponibilidade não equivale a execução do LLM por Vulkan |
| Kernel | 7.0.0-38-generic |
| RAM | Aproximadamente 31 GiB, 25 GiB disponíveis no snapshot |
| Swap | 8 GiB ativos, aproximadamente 3,5 GiB usados; não contar como RAM rápida |
| Disco | Aproximadamente 46 GiB livres, 95% utilizado |
| Relógio | America/Sao_Paulo; NTP sincronizado |
| Residência | `/api/ps` vazio nos três daemons no momento da consulta |

O Vulkan anuncia heap host-visible/coherent não local de aproximadamente 15,61 GiB e heap device-local de 7,98 GiB. **Isso não prova que a GPU esteja processando pesos do LLM nessa RAM**, nem elimina tráfego PCIe. O dispositivo CPU llvmpipe não foi contado como memória da Radeon. `CPU_Mapped` nos logs também não prova zero-copy GPU.

`rocminfo`/`hipcc` não estavam no PATH, mas o runner empacotado usa ROCm; ausência desses executáveis não significa ausência de runtime. HMM, XNACK, registro/pinning, zero-copy e prefetch permanecem **não comprovados**.

A tabela pública atual do [TheRock](https://github.com/ROCm/TheRock/blob/main/SUPPORTED_GPUS.md) marca gfx1032 como build/sanity/release ready no projeto; não é certificação do Ollama local ou da versão distribuída do ROCm. O [build completo recomendado pelo TheRock](https://github.com/ROCm/TheRock) pede cerca de 200 GB livres: não cabe no disco atual com folga segura. Nada foi instalado.

## 3. Cache: há mecanismo existente, mas ainda falta orçamento e benchmark

Os próprios runners já possuem prompt cache em RAM:

- `lilith/server.log:20861`: limite 8.192 MiB; slots ociosos podem ser salvos.
- `hoshino/server.log:79733`, 79783 e 79836: estados de cache com 311,789 / 671,921 / 1.037,212 MiB.
- `hoshino/server.log:79747`: checkpoint restaurado, **187 tokens**, 50,251 MiB; não é apenas uma flag de configuração.

**8 GiB é limite, não alocação atual.** Três limites independentes poderiam criar pressão agregada, mas não se observou alocação simultânea de 24 GiB; neste snapshot não havia runners residentes. `graphs reused` mede reutilização de grafo computacional, não necessariamente hit do prefixo/KV entre pedidos.

A documentação do [llama-server](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md) descreve `--cache-ram`/`LLAMA_ARG_CACHE_RAM`. Isso não garante que o Ollama deste projeto propague esse ambiente ao runner; testar antes de configurar. A [documentação do Ollama](https://docs.ollama.com/faq) descreve Flash Attention e quantização KV; configurações não equivalem a qualidade/ganho medido.

Plano: primeiro medir cache existente frio/quente com mesmo prefixo, contexto, saída e backend; observar tokens reaproveitados, duração, RAM e VRAM; só depois limitar orçamento no caminho atual. Testar perda de cache no unload/restart e isolamento de entidades. Não criar daemon de cache, cache mental paralelo nem persistir KV na memória autobiográfica.

## 4. Mapa dos componentes e lacunas

| Área | Componente atual / evidência | Estado diante do novo pedido |
|---|---|---|
| Resource Manager | `app/core/resource_manager.py`, `gpu_resource.py`, leases/residência/filas/estimativas | Existente. Margem baseline 768 MiB VRAM, 2 GiB RAM, concorrência não validada. Orçamento agregado de cache, starvation e longa duração precisam de evidência adicional |
| Modelos | Daemons/aliases independentes; 9B, Qwen2.5 7B, Hunyuan, Jan, Esper; Alistair 4B | Preservados. Esper/Jan não aprovados; nenhum novo leve selecionado |
| Contexto | `prompting.py`, `compaction.py`, `resource_manager.inference_options` | Dinâmico e buckets existentes. Prefixo determinístico e medição de cache ainda não demonstrados; não reduzir identidade para produzir hit |
| Histórico | `core/history.py`, mensagens/FTS/eventos por entidade | Persistente e pesquisável; horários novos sem fuso, exportação/consulta com rótulos fixos, busca diária ainda ausente |
| Diagnóstico | `core/diagnostics.py`, JSONL e espelho SQLite | Correlação existente. `SESSION_ID` é sessão de diagnóstico/processo, **não sessão diária de conversa** |
| Central | `central_control.py`, `central_native.py`, `native_panels.py` | Inspetores/atividade atuais; sessões diárias e leitura de dias anteriores ainda não implementadas |
| Memória | `memory/knowledge_store.py`, `records.py`, `mind/scribe.py` | Tipo/autoria/ouvinte/origem/confiança/evidência e revisões presentes. Não há aprendizado causal completo demonstrado |
| Reflexão | `mind/reflection.py`, `night_reflection.py` | Reflexões distintas de fatos; revisão noturna já existe. Material pode ser cortado e nem toda conclusão liga IDs da evidência |
| Personalidade | `mind/personality.py`, afetos/relações atuais | Aprendizado gradual por evidências existe; motivos atuais não são trilha imutável completa de todas as mudanças |
| Iniciativa | `core/kernel.py`, `mind/drives.py`, permissões do dispatcher | Motivos/saliência/cooldowns/sono existentes, não somente frases sorteadas. Autonomia ampla do novo pedido não está fisicamente validada |
| Diário privado | Reflexões atuais não têm contrato de diário voluntário com compartilhamento seletivo | Funcionalidade nova delimitada; integrar armazenamento existente, sem confundir com histórico ou cadeia de pensamento |
| Oficina visual | Oficina de arquivos existente | Não existe contrato completo de grafo editável/versionado/ACL/evidência; funcionalidade nova, não trocar a arquitetura inteira |
| Tempo | `datetime.now()` em histórico/diagnóstico/memória; monotônico já usado em leases/turnos | Mistura de contratos. Corrigir incrementalmente; não converter registros antigos cegamente |

### Autoria: defeito estático confirmado

`app/tools/historico.py` exibe “Hoshino” para qualquer mensagem de saída, mesmo executando na Lilith, e “Você” para qualquer entrada, mesmo de outra entidade. `history.export_txt` faz o mesmo e usa nome de arquivo fixo. Os registros têm `person_name`/role/direction; a falha é na apresentação. Corrigir sem reescrever mensagens antigas.

### Isolamento: diário não pode ser protegido só pelo prompt

`tools/filesystem.py` permite zonas amplas (home e raiz do projeto). Um diário de Lilith dentro dessas zonas não fica privado de Hoshino por ganhar uma pasta própria. Ferramentas de arquivos, shell/sandbox, anexos, exportação e oficina precisam do mesmo contrato de acesso. Não foi feito teste de vazamento com dados reais.

O operador/admin local continua podendo acessar os arquivos; não prometer sigilo absoluto. A privacidade exigida é entre entidades/ferramentas e participantes autorizados, não criptografia contra o dono do PC. A inspeção administrativa da Central deve ser distinguida de acesso concedido à outra entidade.

## 5. Modelos leves: candidatos, não decisão

As fichas oficiais de [SmolLM3-3B](https://huggingface.co/HuggingFaceTB/SmolLM3-3B) e [Qwen3-4B](https://huggingface.co/Qwen/Qwen3-4B) documentam modos de raciocínio; SmolLM3 declara português entre idiomas nativos. Isso somente sustenta a possibilidade de um ensaio posterior. Não prova naturalidade das entidades, protocolo no backend instalado ou economia de 10–15% sob o mesmo workload.

Não houve download ou troca de executor. Primeiro resolver fundação histórica/prefixos e medir os modelos instalados. Os dois 7B continuam disponíveis; nem Esper nem novo leve devem ser habilitados só para completar uma lista.

## 6. Primeiro incremento: fundação temporal/histórica (Fase 2 parcial)

Sequência pequena e reversível, sem novo banco:

1. Regressões reproduzindo rótulos incorretos e horários ambíguos em bancos temporários.
2. Configuração de fuso local validada, padrão America/Sao_Paulo; novos registros do histórico/diagnóstico em UTC. Legado intacto, com interpretação explicitamente marcada, sem inventar timezone antigo.
3. Consultas por data local e canal/participante no `history.sqlite3` atual, conservando IDs, conteúdo, ordem local e metadados. Busca antiga continua compatível.
4. Apresentação respeitando autor/entidade, sem fabricar autoria ausente.
5. Ordenação/filtros da timeline reconhecendo timestamps antigos e novos; sem alegar ordem causal global.
6. Duração da inferência pelo relógio monotônico existente.

Consumidores localizados antes de alterar: `main.py` (entrada/saída/interentidade), `tools/historico.py`, dispatcher/capabilities, `diagnostics.py` (espelho/exportação por sessão), `central_control.activity`, manutenção/reset, scripts de migração e testes de histórico/diagnóstico/central/turno. As tabelas `events` do world_state são outro contrato; não alterá-las por semelhança do nome.

**Fora desse primeiro incremento:** migração de todos os relógios mentais/agenda, interface de sessões diárias, vínculo de resposta tardia à sessão original, resumo incremental diário, diário/ACL, oficina visual, tuning de RM/cache e modelos. Esses itens continuam pendentes, não serão declarados concluídos por passar regressões de consulta.

Antes de alterar um banco real: snapshot consistente pelo mecanismo SQLite, backup privado de configs/código pertinente, identificação de processos e conexões, compatibilidade testada em cópia. Nesta fase os testes devem abrir exclusivamente bancos temporários. Não mudar DDL nem conectar a banco real para testar a migração.

## 7. Aprovação e riscos

- **Verificado fisicamente, leitura apenas:** GPU/driver/Vulkan disponíveis, RAM/swap/disco, timezone/NTP, versão/residência Ollama; logs reais anteriores do backend/cache.
- **Verificado estaticamente:** mapa de consumidores, rótulos errados, UTC ausente, lacunas de diário/ACL/oficina/sessão diária.
- **Pendente:** benefício real de zero-copy/RAM mapeada, cache pareado/orçamento agregado, modelos leves aprovados, aprendizado causal e diários, oficina usada pela entidade, continuidade diária completa, diálogo prolongado e integrações físicas.

Nenhum desses ensaios pendentes deve ser chamado de aprovado. O próximo passo é a fundação histórica, não outra rodada de troca de modelos ou de drivers.

## 8. Continuação desta rodada

O primeiro incremento da Fase 2 foi implementado após esta auditoria, com baseline e bancos temporários. Resultados, arquivos, regressões encontradas e limites estão em `FUNDACAO_HISTORICA_20261009.md`. Esta continuação não transforma o mapa estático acima em validação integral de diário, oficina, cache ou autonomia.


---

## Original 2 — FUNDACAO_HISTORICA_20261009.md

# Fundação histórica — primeiro incremento, 09/10/2026

## Resultado e limite da entrega

**Fase 1 concluída como auditoria; Fase 2 iniciada, não concluída.** Consulte `AUDITORIA_COGNITIVA_MEMORIA_HIBRIDA_20261009.md` para o mapa completo e as evidências de hardware/backend/cache.

Este incremento entrega autoria correta nas consultas/exportações, novos horários do histórico e diagnóstico em UTC, busca por data local no SQLite existente e compatibilidade explícita com registros antigos. Não entrega ainda sessões diárias da Central, diário privado, oficina visual ou novos experimentos de modelos/cache.

Nenhuma entidade acordada, inferência nova, chamada paga, download, alteração de driver, migração mental, descarte de pesos ou concorrência GPU. Não foi modificado o Resource Manager. Personalidades e identidades não foram editadas.

## Correções e contratos

1. **Autoria exibida:** ferramentas de histórico e exportador deixaram de escrever “Hoshino” em respostas da Lilith. Entradas identificadas de Alistair mostram Alistair, não “Você”. Autor ausente aparece como “Autor não registrado”, sem inventar interlocutor.
2. **Destinatário não é autor:** o contrato antigo `person_id/person_name` em mensagens de saída representa o destinatário. Ele foi preservado. Metadados novos registram separadamente `author_id`, `author_name`, `observer_entity` e destinatário; evidências, source IDs, turn IDs e diagnostic session IDs existentes são mantidos.
3. **Relógio persistente:** novos registros de mensagens/eventos e JSONL usam UTC com offset explícito. Eventos com timestamp fornecido exigem fuso e são normalizados para UTC. Fuso local configurável por `HOSHINO_TIMEZONE`, padrão `America/Sao_Paulo`; configuração inválida é recusada, não adivinhada. `get_system_time` informa horário local, dia e fuso reais.
4. **Legado:** não há DDL novo, atualização em massa ou conversão dos horários antigos. Sem offset, a data literal é mantida e a consulta sinaliza `timezone_known=false`, `utc=null`. Ordenação visual assume o fuso configurado somente como aproximação, explicitamente indicada; não certifica UTC histórico ou causalidade global.
5. **Consulta diária:** `daily_records` lê mensagens/eventos paginados em conexão read-only no mesmo `history.sqlite3`. Retorna conteúdo, IDs, autoria/destinatário, metadados e correlação; filtros de canal, destino e participante não misturam conversas. Registros com offset são agrupados na data local, inclusive perto de meia-noite. Eventos sem canal/autoria correspondente não entram em uma consulta de conversa filtrada.
6. **Ferramentas existentes:** `historico_chat` e `buscar_historico_chat` receberam filtros opcionais por data/canal/participante/destino; nenhuma ferramenta nova. Argumentos inválidos não viram busca genérica “bem-sucedida”. Consultas antigas sem data continuam com assinatura e tuplas compatíveis. Em busca diária, o limite é 1–500; mais registros são sinalizados, não chamados de inexistentes.
7. **Timeline:** ordenação/filtros passam a comparar instantes, não strings de UTC e hora local misturadas. Campos de origem desconhecidos continuam sinalizados. Não foi alegada ordem causal global entre processos.
8. **Duração:** a medição de inferência em `main.py` usa monotônico, sem sofrer saltos do relógio de parede. Não há segundo relógio/scheduler. Outros relógios de memória/agenda/afeto ainda precisam de revisão incremental.

## Arquivos desta rodada

Código modificado:

- `app/config.py`: fuso local configurável, sem editar configs reais.
- `app/core/history.py`: interpretação temporal, autoria, metadados, consulta diária read-only e exportação.
- `app/core/diagnostics.py`: UTC e mesmo timestamp no JSONL/espelho; bootstrap continua tardio.
- `app/core/central_control.py`: timeline com ordenação temporal compatível e indicação de legado.
- `app/core/dispatch.py`: parâmetros opcionais das duas ferramentas existentes, com limites preservados para validação.
- `app/tools/historico.py`: autoria correta e apresentação da busca diária com IDs.
- `app/tools/terminal.py`: fuso no relógio existente.
- `app/main.py`: monotônico para duração de inferência.

Testes modificados, sem novo grupo paralelo:

- `testes/test_historico_integral.py`.
- `testes/test_central_control.py`.
- `testes/test_v23_diagnostico.py`.
- `testes/test_prontidao_r1_r7.py`.

Documentação criada: esta entrega e `AUDITORIA_COGNITIVA_MEMORIA_HIBRIDA_20261009.md`. Acrescentadas erratas em `CONSOLIDACAO_FINAL_20261009.md` e `CORRECOES_ENSAIO_20261009.md`; conteúdo/evidências originais preservados. Os logs confirmam ROCm nas inferências recentes, não a atribuição anterior a Vulkan. Isso é correção de proveniência, não mudança de backend.

A árvore já estava modificada. O diff total contra HEAD contém mudanças anteriores; não corresponde ao tamanho deste incremento.

## Testes e falhas encontradas

Antes de alterar código: **74/74 grupos offline**. Reproduções no histórico original: 13 casos, um contrato anterior passando, cinco falhas de autoria/horário e sete erros por contratos novos ainda ausentes. Ausência de nova API não foi classificada como regressão da arquitetura antiga.

Após implementar, **23 verificações novas** nos grupos atuais:

- Histórico: **20/20**, sendo 19 novas mais o contrato integral anterior. Abrangem autoria/destinatário/ausência de autor, fontes/confiança zero/evidência, UTC/offset/legado, datas inválidas, filtros, paginação, reabertura, três bancos separados, read-only, banco ausente, parâmetros do dispatcher e relógio real.
- Central: **40/40**, duas novas verificando ordenação/filtros mistos e recusa de filtro temporal inválido.
- Diagnóstico: **5/5**, uma nova verificando igualdade do timestamp/correlação JSONL↔SQLite.
- R1–R7: **111/111**, uma nova verificando monotônico no caminho de inferência enquanto o relógio de parede é inutilizado pela fixture.
- Turno E2E existente: **27/27 verificações**.

Suíte completa final, após todos os ajustes: **74/74 grupos offline**, saída 0. Inventário permanece com os mesmos 74 grupos; as novas verificações foram acrescentadas aos grupos existentes. `git diff --check` sem erros. As execuções são isoladas, sem internet, modelos/voz/servidores externos ou escrita nos bancos reais.

Regressões detectadas e corrigidas durante o desenvolvimento:

- Primeiro ajuste de diagnóstico causou referência local antes da importação; corrigido e coberto pelos testes de emit/espelho/central.
- Primeira suíte pós-alteração: **73/74**, falha em `test_v23_diagnostico_pacote`. A importação antecipada fixava o banco antes da seleção do runtime da fixture. Restaurada inicialização tardia; teste original não enfraquecido nem editado. O grupo voltou a passar.
- Avisos de conexão SQLite não fechada na nova consulta: corrigidos com fechamento explícito, inclusive nos testes. Não descartados por filtros de warnings.

## Preservação e evidências

Backups consistentes dos três históricos por SQLite backup, `quick_check=ok` nas três cópias; cópia dos arquivos tocados antes das alterações. Arquivos privados em:

`compartilhado/runtime/ensaios/20261009/fundacao-historica/pre-incremento/`

Históricos reais e snapshots apresentaram hashes iguais dos dumps lógicos após os testes:

| Entidade | SHA-256 do dump lógico (original = snapshot) |
|---|---|
| Hoshino | `ab925e35effdf2e51d0cdeffe61a5cd9decee8667fd98d307485a076145c9a7d` |
| Lilith | `94865263faf52973fbcce28f9d386a34561d3a0ed7a4bde8dc7bd0770a3d5fcb` |
| Alistair | `7387f9218fc543323cdd3bd130c1cb80bdcfc25d1d4ab94b616acb85cfa8ea98` |

É comparação lógica dos históricos, não hash de todos os bancos/modelos do projeto. Nenhum banco mental real foi aberto para escrita nesta rodada. Backups/logs privados permanecem ignorados pelo Git; não houve commit/push em bloco.

Evidências anteriores/vermelhas/verdes preservadas no diretório privado acima, inclusive reprodução e suíte 73/74. Não são validação física de voz, Discord, Minecraft, reflexão ou personalidade.

Log final: `hoshino-fundacao-historica-verificada-20261009.log`. Baseline: `hoshino-fundacao-historica-antes-20261009.log`. Primeira suíte vermelha: `hoshino-fundacao-historica-depois-20261009.log`. Registros de execução local desta rodada não contêm chamadas pagas nem inferência real.

Reversão: comparar os arquivos atuais com o snapshot e reverter somente este incremento, preservando alterações posteriores. Não restaurar bancos cegamente nem apagar novas conversas. Não existe migração de schema para desfazer; versões anteriores ainda conseguem ler as mesmas tabelas e campos básicos.

## Pendências e próximo passo

Atualização posterior: o incremento de sessões diárias está documentado em
`SESSOES_DIARIAS_20261009.md`. A lista abaixo registra o estado ao encerrar a
fundação histórica, não significa que todos esses itens permaneçam sem código.

O incremento temporal de JSON/atividade/presença está documentado em
`TEMPO_CONTINUIDADE_20261009.md`. Não é conversão global da agenda/bancos nem
validação física de suspensão ou sincronização com PC2.

1. Concluir Fase 2: sessões diárias na Central, identificadores duráveis distintos da sessão diagnóstica, arquivamento somente leitura, resposta tardia ligada ao turno original e continuidade após meia-noite/restart. Testar antes de aplicar em histórico real.
2. Revisar consumers de datas mentais/agenda/afeto antes de converter seus relógios. O fuso configurado aqui não substitui automaticamente todos os usos antigos de `datetime.now()` no projeto.
3. A consulta de compatibilidade pode percorrer muitos registros para interpretar offsets antigos; falta medir em históricos grandes. Paginação por offset não é snapshot imutável durante escritas concorrentes. Não confundir essa primeira consulta com contrato completo de sessões concorrentes.
4. Registros com timestamp inválido permanecem recuperáveis pela busca textual antiga; não podem ser atribuídos com certeza a um dia. UI diária deverá mostrar essa limitação e não afirmar que a ausência em uma data prova inexistência.
5. Diário privado requer controle transversal de ferramentas/arquivos/sandbox, não só uma pasta ou prompt. Oficina visual requer estrutura editável e evidências, não somente caixas desenhadas. Ainda não implementados.
6. Cache em RAM já existe nos runners, mas faltam orçamento agregado e ensaio pareado. RAM host-visible não prova zero-copy GPU. Não alteradas margens, drivers ou backends.
7. Nenhum novo modelo aprovado/baixado; Esper continua não aprovado, Jan preservado e os dois 7B disponíveis. Não declarar conversa prolongada/autonomia certificadas a partir desta suíte.

**Parecer:** incremento de fundação validado de forma isolada; projeto inteiro e nova especificação continuam parcialmente pendentes. A avaliação humana prolongada permanece necessária.


---

## Original 3 — SESSOES_DIARIAS_20261009.md

# Sessões diárias — decisão de implementação

Incremento da fase 2. Baseline antes: 74/74 grupos offline, em
`/tmp/hoshino-sessoes-diarias-antes-20261009.log`.

## Fonte de verdade e consumidores

Central nativa e Central web → `/api/state` e `/api/send` → Supervisor →
`core.interentity` → `entity_messages.metadata`, no SQLite compartilhado existente.
Hoshino/Lilith → `main.receber_de_pessoa`/`publicar`; Alistair → runner e histórico
próprios. Áudio consulta envelopes e jobs existentes; o overlay continua usando a
consulta legada. O histórico mental não é a caixa postal da Central.

Não criar banco, tabela de sessões, scheduler ou nova fila. Sessões são metadados
de organização da conversa principal do participante local `usuario`; Discord,
Minecraft e mensagens privadas conservam canais, autoria e filas atuais.

## Contrato

- Uma identificação determinística por entidade, data local e fuso. Atribuída
  pelo backend no aceite, nunca pelo LLM ou pelo relógio da interface.
- Envio com sessão arquivada recusado. Dedupe ocorre antes dessa validação:
  repetir o mesmo submission já aceito antes da meia-noite confirma o mesmo
  envelope, sem criar outra mensagem nem novo wake.
- Resposta herda a sessão do envelope humano que está sendo processado, mesmo
  após meia-noite. A sessão antiga continua somente leitura para novos envios.
- Dia novo é uma vista vazia quando não há mensagens; não reinicia identidade,
  contexto mental, objetivos, promessas, tarefas, inbox ou processamento.
- Legado interpretado em leitura, com origem derivada explícita; nunca reescrever
  o histórico em massa. Datas sem fuso continuam marcadas como não confirmadas.
- Consulta atual opt-in (`daily=1`), preservando a API all-time de outros
  consumidores. Páginas com teto de rowid e cursor, sem alegar ordem causal global.
- Resumos serão contagens verificáveis de registros, não narrativas inventadas
  ou novas inferências. Resumo semântico permanece indisponível nesta rodada.
- Interface observa a sessão retornada: bloqueia composer/captura de conversa
  arquivada; testes isolados de áudio permanecem disponíveis. Leitura histórica
  não dispara TTS automático. Rascunhos e respostas HTTP atrasadas não se apagam
  mutuamente. Streams conservam a referência à sessão de origem.

## Preservação e validação

Código prévio e snapshots SQLite consistentes estão em
`compartilhado/runtime/ensaios/20261009/sessoes-diarias/pre-incremento/` (privado,
fora do Git). Nenhuma migração mental, inferência real, quota TTS, alteração de
modelo, wake automático ou concorrência GPU autorizada neste incremento.

Regressões nos grupos existentes: data/fuso, restart, herança de respostas,
dedupe em virada de dia, legado, isolamento, paginação, HTTP, Qt e navegador com
transporte simulado. Testes de UI não comprovam hardware, áudio ouvido ou uso
prolongado. Custo da leitura de legado deve ser medido e documentado.

## Resultado do incremento

Implementado na Central nativa e no cliente web preservado:

- Seletor de dias, Hoje, busca por data/assunto e páginas de 100 envelopes.
  Catálogo de 60 sessões recentes; datas anteriores consultáveis pelo campo de
  data. Não renderizar todo o histórico de uma vez.
- Metadado `conversation_session` no envelope novo, separado do `session_id`
  diagnóstico. IDs incluem entidade, dia e digest do participante/fuso.
- Backend recusa sessão arquivada/estrangeira para novos envios. Submission
  já aceito continua idempotente depois da meia-noite. API all-time preservada.
- Resposta herda a sessão da entrada humana persistida, verificando autoria e
  destinatário; resposta tardia não reabre o arquivo para novos envios.
- Legado derivado sem alterar linhas; `session_origin` e `time` distinguem dados
  registrados/derivados e fuso original desconhecido. Datas inválidas são
  contabilizadas e continuam acessíveis pela API all-time, sem data fictícia.
- Paginação com teto de rowid/cursor e transação de leitura. Não é snapshot
  permanente dos estados de processamento nem ordem causal global.
- Rascunhos preservados ao mudar dia/entidade. HTTP atrasado não limpa rascunho
  novo nem substitui a vista selecionada. Anexo atrasado conserva o destino.
- Composer/anexos/captura de conversa bloqueados no arquivo; teste descartável
  de mic permanece disponível, sem envio automático à entidade.
- Arquivo, busca e páginas antigas não disparam TTS automático. Streams levam
  a sessão de origem, evitando começar fala de ontem na vista de hoje. A virada
  do relógio não cancela o turno nem uma reprodução que já começou.
- Histórico de entrada/saída, origem do escriba, jobs/eventos de áudio conservam
  a referência diária. Memória mental, relações, tarefas, filas e chaves de
  conversa não são particionadas/resetadas pelo dia.
- Bug Qt adicional reproduzido: conversa privada filtra pela entidade
  selecionada, não pela variável da última entidade do dashboard.

### Arquivos desta rodada

| Área | Arquivos alterados |
|---|---|
| Sessões/API | `app/core/interentity.py`, `iniciar_entidades.py` |
| Central | `app/ui/central_native.py`, `app/ui/central.html`, `app/ui/control.js` |
| Rastreabilidade | `app/main.py`, `app/mind/scribe.py`, `app/core/speech_stream.py`, `app/core/audio_service.py`, `app/core/diagnostics.py` |
| Testes | `testes/test_central_entidades.py`, `testes/native_central_contracts.py`, `testes/test_central_refinamento.py`, `testes/central_browser.cjs`, `testes/test_mensagens_causalidade.py`, `testes/test_prontidao_r1_r7.py` |

Este documento foi criado. O diff total do Git inclui alterações anteriores
muito maiores: não atribuir tudo a esta rodada. Elas foram preservadas.

### Testes/evidências

16 novos métodos permanentes: 9 Central/caixa postal, 6 Qt, 1 turnos/causalidade.
Fortalecidas as duas simulações simultâneas existentes, o turno completo R7 e
assertivas do navegador.

| Execução | Resultado |
|---|---|
| Baseline oficial | 74/74 grupos offline |
| Central/caixa postal, processo novo e HTTP efêmero autenticado | 28/28 |
| Turnos/causalidade, duas simulações simultâneas e meia-noite durante resposta | 40/40 |
| R1–R7, mensagem → memória → TTS → playback correlacionados | 111/111 |
| Refinamento Central | 34/34, incluindo subprocesso Qt com 42/42 contratos |
| Chromium headless, APIs simuladas, arquivo/read-only/Hoje | 1/1 teste de navegador |
| Suíte oficial final | **74/74 grupos offline** |
| `git diff --check` | sem erros |

Integração isolada: SQLite temporário real, processo novo lendo o mesmo arquivo,
HTTP local em porta efêmera, Qt offscreen e Chromium headless. LLM, Minecraft
RPC, áudio e transporte da UI são simulados; isso não comprova personalidade,
voz ou hardware real.

Medição: 2.000 envelopes temporários com metadados registrados; 100 retornos em
**0,024407 s**. Catálogo/compatibilidade examina metadados do histórico: custo
cresce com o número de envelopes. Não afirmar calibração para milhões de mensagens.

Smoke Qt offscreen, ~2 s de **inicialização e polling**: RSS máximo 92.924 KiB
(~90,7 MiB), CPU 0,417 s (~20,76% de um núcleo nesse intervalo). Não é medição de
idle, desktop real, ganho de desempenho ou soak. Nenhum shutdown do backend enviado.

### Falhas da validação, sem ocultação

1. Cinco testes de sessão falharam antes da implementação por ausência dos
   contratos novos; reprodução preservada.
2. Import local introduzido em `publicar` sombreou `interentity` e bloqueou
   respostas locais/privadas. A suíte expôs a regressão; removido o import
   redundante, sem relaxar fixtures para aceitar ausência de resposta.
3. Fixture nova de stream não fornecia sentença seguinte/terminação confirmada.
   Corrigida para sentença estável e finalização explícita; gate do produto mantido.
4. Assertiva nova de áudio buscava `details` na API pública reduzida. Corrigida
   para job persistido existente, também exigindo ID diário no evento playback.
   Whitelist de diagnóstico ampliada para esse ID, não para texto/segredos.
5. Teste de navegador esperava bloqueio provisório de carregamento, não arquivo
   confirmado. Agora espera a data retornada, read-only, ausência de envio e Hoje.
6. Pai dos testes Qt exigia literalmente 36 métodos; atualizado para 42 devido
   aos seis novos, preservando exigência de saída zero.

Primeira suíte pós-alteração: **69/74**, não aprovação. Falhas e resultados finais
conservados nos logs privados.

### Preservação

Dumps lógicos dos três históricos reais coincidem com seus snapshots. Caixa
postal também permaneceu igual, SHA-256 lógico
`220480b9108e283db450be54d3dd7d6e00a2635a55f667c3ed8e10011c683cb6`.
Isso não é hash de todos os bancos/modelos. Testes com o isolador existente;
nenhum banco mental real disponibilizado para escrita. Sem migração, delete,
wake, restart real, download, quota ou inferência real.

Evidências privadas em `compartilhado/runtime/ensaios/20261009/sessoes-diarias/`:
baseline, reprodução inicial, primeira suíte vermelha, suíte final e testes
específicos. Não versionar logs/snapshots/conversas no Git. Reversão retira somente
o incremento; não restaurar banco antigo por cima de novas conversas.

## Pendências/próximo passo

- Central já aberta precisa de restart cooperativo do backend/cliente para usar
  o código novo. **Não feito**; não interromper sessão humana em andamento.
- Teste manual no desktop, virada real de dia, áudio, uso prolongado e arquivos
  grandes pendentes. Somente os mecanismos foram validados em isolamento.
- Resumo narrativo do dia anterior não produzido. Contagens não cumprem esse
  requisito semântico. Continuidade de objetivos/promessas não foi resetada,
  mas ainda exige ensaio prolongado.
- Esta UI diária é da conversa principal do participante local `usuario`;
  pessoas/canais externos continuam separados. Não prova identificação biométrica.
- Fase 2 ainda exige auditoria dos consumidores mentais de tempo/duração.
  Diários privados, aprendizagem, oficina visual e experimentos de cache/modelos
  das fases seguintes **não foram implementados aqui**.

Conclusão: incremento de sessões diárias validado em ambiente isolado, suíte
verde. A especificação cognitiva completa permanece em andamento.


---

## Original 4 — TEMPO_CONTINUIDADE_20261009.md

# Tempo e continuidade observada — 09/10/2026

## Limite desta rodada

Incremento da Fase 2 do plano cognitivo, depois da fundação histórica e das sessões diárias. Não é conclusão do plano inteiro nem validação física prolongada.

Sem novos modelos, bancos, schedulers, sistemas mentais, providers ou capacidades externas. Sem alteração de identidade, personalidade, catálogos afetivos, margens GPU, concorrência ou cloud. Nenhuma entidade acordada, nenhum serviço reiniciado, nenhuma chamada paga, inferência ou download nesta rodada.

## Mapa auditado antes das alterações

- `core/history.py`: relógio local configurável e horários UTC do histórico/diagnóstico. Reutilizado para compatibilidade dos cálculos, sem novo serviço de relógio.
- `mind/affect.py`, `psych_state.py`, `drives.py`, `emotions.py`: estados JSON existentes, leitores de decaimento, satisfação/refratário e projeção visual consumida pela Central/orbes. Eventos afetivos e coeficientes permanecem os mesmos.
- `core/situation.py`: consumido pelo batimento de `main.py`, pelo dispatcher de situação e pelas ferramentas existentes `tempo_em`/`resumo_do_dia`. Usa `estado_mente.situacao` e a tabela existente `activity_sessions`.
- `tools/agenda.py` e `core/kernel.py`: consomem presença para diretivas e contato espontâneo; ausência exige `False`, desconhecido é `None`. Auditados, não substituídos nem editados nesta rodada.
- `bd.agora`, episódios, reflexão, agenda, objetivos e histórico emocional ainda têm consumidores SQL de datas textuais. Não converter esses bancos globalmente para UTC antes de revisar todos os filtros/ordenações.

## Defeitos reproduzidos e correções

### 1. Mistura entre datas com/sem fuso

Antes, humor/estado psicológico/emoções subtraíam datas incompatíveis, lançando `TypeError`. A projeção visual engolia a mesma falha e ficava neutra apesar de existir emoção válida. O refratário dos impulsos devolvia `1.0` ao falhar, permitindo iniciativa imediatamente.

Agora `history.local_datetime` e `elapsed_seconds` normalizam cálculos para instantes UTC. Legado ingênuo usa **somente como aproximação de cálculo** `HOSHINO_TIMEZONE`, padrão `America/Sao_Paulo`. `timestamp_details` continua dizendo que seu fuso original é desconhecido. Nada é migrado ou reescrito por uma leitura.

Novos marcadores JSON afetivos/psicológicos/refratários usam UTC explícito com milissegundos. Zero decorrido é válido. Timestamp inválido, ausente ou futuro retorna duração desconhecida, não sucesso. Nesse caso o refratário bloqueia iniciativa; humor e estado psicológico não são apagados por falha do relógio; emoções de origem temporal inválida não são projetadas como confirmadas.

`clock.unreliable` usa o diagnóstico existente, com operação, entidade observadora e motivo. Não registra o texto do timestamp inválido. Cache limitado a 64 combinações operação/motivo evita um aviso repetido a cada tick; não é coletor nem banco paralelo.

### 2. Inatividade não comprova ausência

Antes, X11 ocioso por 900s produzia `usuario_presente=False`, inclusive quando a pessoa acabara de conversar por voz. Isso podia ativar diretivas `enquanto=ausente` sem prova de ausência.

Agora interação humana recente prevalece. Sem interação recente, teclado/mouse ociosos geram `None`, com base `inatividade_de_entrada`. O evento é observacional (`inatividade_entrada`), não `sumiu`/rejeição/abandono. Atividade do desktop não dispara mais um retorno humano presumido (`voltou`) nem conclui diretivas de ausência por esse caminho. Não foram alterados traços ou intensidades emocionais para esconder o problema.

O teste histórico `test_input_inactivity_is_only_a_private_inference` ainda esperava `False`; foi atualizado para o contrato explícito atual, verificando também que uma diretiva de ausência não é ativada. Não se enfraqueceu a guarda da agenda: `False` explícito continua sendo tratado como ausência pelos consumidores existentes.

### 3. Horas de sono não são atividade observada

Antes, manter a mesma janela após restart preservava o início antigo e atribuía o intervalo inteiro à atividade. Uma troca de janela depois de suspensão também podia ser descrita como evento observado em tempo real.

O mesmo JSON de situação agora guarda ID da sessão, época de execução, último retrato UTC, último instante monotônico e duração observada acumulada. Relógio monotônico nunca é reutilizado entre processos. Reinício, lacuna ou regressão reabre uma linha de base; encerra a sessão anterior no último retrato conhecido, sem contar o intervalo não observado nem inventar novidade/música ocorrida enquanto dormia.

Uma lacuna maior que `max(60s, 3 × HEARTBEAT_SEGUNDOS)` interrompe continuidade. Esse teto é conservador: também segmenta um tick muito atrasado. A duração continua aproximada entre observações, não comprova que alguém usou o aplicativo durante cada segundo. O nome público da API e seus argumentos anteriores são preservados; o instante monotônico opcional serve aos testes determinísticos.

A sessão legada aberta sem marcador confiável de última observação não é retropreenchida com horas adivinhadas. Registros históricos já fechados permanecem intactos. A tabela existente continua com datas locais textuais para seus consumidores SQL; os novos marcadores JSON são UTC. O resumo de atividade ainda agrupa por data de início, não divide uma sessão que atravessa meia-noite.

### 4. Fechamento durável sem duplicação

Na revisão, um ensaio com SQLite temporário reproduziu duas linhas ao fechar duas vezes a mesma sessão, simulando queda entre INSERT e atualização do JSON.

Agora o ID é persistido na sessão; há chave determinística de compatibilidade quando necessário. O INSERT usa a chave primária existente, `ON CONFLICT(id) DO NOTHING`, e a leitura posterior confirma o registro. Falha de banco é propagada, não tratada como sessão gravada. O estado pendente não é esquecido. Duração divergente para um ID já gravado preserva a primeira evidência e emite `activity.close_conflict`, sem sobrescrever ou somar duas vezes.

## Arquivos desta rodada

Código: `app/config.py`, `app/core/history.py`, `app/core/situation.py`, `app/mind/affect.py`, `app/mind/psych_state.py`, `app/mind/drives.py`, `app/mind/emotions.py`.

Testes: `testes/test_historico_integral.py`, `testes/test_logica_cognitiva.py`, `testes/test_world_state.py`, `testes/test_v20_iniciativa.py`.

Documentação: este relatório e nota de andamento em `FUNDACAO_HISTORICA_20261009.md`.

## Testes e evidências

Baseline real desta rodada: **73/74 grupos**, não 74/74. `test_v20_iniciativa` falhou porque um timestamp truncado em segundos permitia erro de quase 1s numa comparação com tolerância de 0,9s. Novos marcadores usam milissegundos; a fixture usa instante fixo e exige zero exato. Não aumentamos a tolerância.

Regressões vermelhas preservadas: `test_logica_cognitiva-antes.log`, `test_historico_integral-antes.log`, `test_world_state-antes.log`, `test_v20_iniciativa-antes.log`, `atividade-dedup-antes.log`.

**19 métodos novos** nos grupos existentes:

- Lógica cognitiva: 7 novos, grupo **13/13**, mais 13 verificações legadas.
- Histórico integral: 3 novos, grupo **23/23**.
- World state: 9 novos, grupo **40/40**; inclui SQLite real temporário para duração, confirmação e deduplicação.
- Iniciativa: fixture determinística atualizada, grupo **12/12**.

Primeira suíte após o conjunto inicial: **74/74**, saída 0. Suíte final após idempotência e todas as regressões: **74/74**, saída 0. `git diff --check` sem erros. O catálogo permanece com os mesmos 74 grupos; não foram criados grupos paralelos para inflar o baseline.

Os testes executam no isolamento existente: runtimes/SQLite temporários, credenciais removidas, rede/captura/hardware/download e escrita em bancos reais bloqueados. Testes de UTC, suspensão e restart são **controlados**, não prova de suspensão física, relógios PC2 alinhados ou comportamento real de sentimentos.

Arquivos privados, ignorados pelo Git:

`compartilhado/runtime/ensaios/20261009/tempo/`

Snapshot pré-alteração de código/testes: `pre-incremento/codigo.tgz`. Baseline completo em `suite-antes.log`; rodada intermediária `suite-depois.log`; final `suite-verificada.log`. Nenhum backup mental ou credencial foi colocado no Git.

## Preservação e limites restantes

Históricos reais consultados somente em modo read-only: dumps lógicos continuam iguais aos snapshots da fundação histórica (Hoshino `ab925e35…`, Lilith `94865263…`, Alistair `7387f921…`). Isso não é hash de todos os modelos/dados do projeto. Não houve migração mental nesta rodada.

Os hashes SHA-256 dos três bancos mentais e dos cinco JSON mentais/psicológicos disponíveis foram iguais nas verificações antes/depois da suíte final. O hash do banco Hoshino e dos cinco JSON também coincide com a leitura feita durante a suíte intermediária. Isso reforça as guardas de isolamento; não equivale a ter medido cada arquivo/peso ou feito snapshot byte a byte antes de toda a rodada. Backups de código e evidências dos ensaios anteriores foram preservados.

Ainda pendentes:

1. Conversão coordenada dos consumidores SQL mentais/agenda/reflexão, sem misturar ingenuamente formatos de datas.
2. Cooldowns gerais de `main/kernel` ainda usam datetimes; duração monotônica foi aplicada aqui ao acompanhamento de atividade, não prometida para todos os caminhos.
3. Suspensão/restart físicos e relógios entre processos/PC2. Os testes controlados não substituem essa evidência.
4. Diário privado, aprendizagem/identidade, oficina visual, experiências de cache/modelos e autonomia social do plano maior continuam para incrementos posteriores.
5. Validação humana prolongada de naturalidade, emoções, iniciativa e integração com ambientes reais.

Para carregar este Python novo, é necessário reinício cooperativo do backend/entidades. Não foi feito automaticamente. Reversão deve comparar o snapshot e retirar apenas este incremento de código; não restaurar bancos ou estados reais cegamente nem desfazer mudanças preexistentes. Se o novo código já tiver gravado marcadores JSON UTC, manter o leitor compatível de datas ao reverter consumidores: a versão antiga, sem esse leitor, não sabia misturar timestamps com/sem offset.

## Continuação — agenda, reflexão e intervalos

O incremento seguinte revisou os consumidores de agenda/reflexão e os intervalos gerais de iniciativa, sem converter os bancos em bloco. Evidências, regressões e limites estão em `AGENDA_REFLEXAO_TEMPO_20261009.md`. A lista acima registra o encerramento desta rodada anterior; não representa conclusão automática de diário, aprendizagem, oficina, cache ou teste humano.


---

## Original 5 — AGENDA_REFLEXAO_TEMPO_20261009.md

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


---

## Original 6 — REFLEXAO_EVIDENCIAS_RAM_20261009.md

# Revisão noturna e RAM compartilhada — 09–10/10/2026

## Arquitetura e escopo do incremento

Continuação limitada da Fase 2 do plano cognitivo. O histórico bruto, as
identidades e os bancos existentes permanecem preservados. Não implementar
outro cache, scheduler, backend ou diário nesta rodada.

Fluxo implementado: `night_reflection.preparar_material` lê os registros atuais
com limites explícitos → `prompt` usa esse mesmo recorte → inferência existente
P5 → `salvar` guarda a referência ao recorte no campo `reflections.evidencias`.
`main.talvez_refletir_noturno` conserva o material entre a consulta e a gravação;
não consulta novamente o banco para inventar a evidência depois da resposta.

Reutilizar `bd`, SQLite mental, diagnósticos e recuperação de `reflection`.
Material composto de registros inteiros, sem cortar conclusões/episódios no meio.
Exclusões por orçamento e limites de linhas ficam explícitas. Registro grande
demais pode ficar de fora; isso não equivale a prova de ausência nem a revisão
completa. Falha de leitura ou resposta sem conclusões válidas não marca sucesso.

O vínculo é com o **contexto fornecido**, não certificação de que cada conclusão
do LLM é verdadeira ou foi sustentada por todas as fontes. Categoria permanece
`reflexao`. APIs antigas de material/prompt e gravação sem evidência estruturada
continuam legíveis; nenhuma migração de evidências antigas.

Consumidores mapeados antes das alterações: `main` chama prompt/salvar;
`reflection.ultimas` e `bloco_para_prompt` recuperam `evidencias` pelo formatador
existente; Central inspeciona as linhas; manutenção usa IDs. Testes de reflexão,
integridade, persistência, capacidades e reset usam esses contratos. O escritor
JSONL não fornece ID em todos os eventos: usar arquivo/linha/hash real, não criar
message ID fictício. Não há afirmação de snapshot causal global entre SQLite,
JSONL e outros processos.

## RAM — opinião e evidências iniciais

RAM é útil para cache, staging e offload parcial. Não se deve somar sua capacidade
à VRAM como se tivessem a mesma velocidade. [HIP/AMD](https://rocm.docs.amd.com/projects/HIP/en/latest/how-to/hip_runtime_api/memory_management/unified_memory.html)
documenta acesso compartilhado/mapeado, dependências de suporte e transferência
de dados. [Khronos](https://docs.vulkan.org/guide/latest/memory_allocation.html)
descreve a memória dedicada e o custo do caminho PCIe nas GPUs discretas.

Leitura física inicial: aproximadamente 31 GiB RAM, 25 GiB disponíveis; swap
8 GiB, 3,4 GiB ocupados. Nos dois intervalos curtos de observação não houve
swap-in/out; isso não comprova estabilidade prolongada. O driver expõe cerca de
7,98 GiB VRAM e 15,61 GiB de orçamento GTT, dos quais cerca de 0,16 GiB estavam
ocupados. **GTT não é VRAM física extra e não comprova inferência sobre pesos
remotos.** A coluna `shared` de `free` tampouco é essa reserva de GPU.

Logs reais anteriores do runner Hoshino mostram ROCm, buffer CPU_Mapped de
683,55 MiB, buffer ROCm0 de 4.674,33 MiB, KV 256 MiB e compute 111,39 MiB.
Confirmam buffers distribuídos, não GPU calculando diretamente sobre todos os
pesos mantidos em RAM. Cache configurado em 8.192 MiB é limite, não alocação
atual. Não executar inferência nem alterar perfis nesta rodada.

Antes de adotar zero-copy no runner real: comparar o mesmo modelo/prompt/saída
com offload atual, medindo primeiro token, tokens/s, RAM/VRAM, swap e falhas.
Mantenho VRAM 8 GiB, margens existentes e concorrência desativada. RAM aumenta
possibilidades, mas não há ganho de latência demonstrado nesta rodada.

## Validação

Baseline: 74/74 grupos offline, saída 0. Novas regressões executadas antes da
correção: 16 métodos, 6 antigos verdes e 10 novos vermelhos (5 falhas, 5 erros
pela ausência do contrato de preparação). Logs privados em
`compartilhado/runtime/ensaios/20261009/reflexao-evidencias/`.

Resultado final: **74/74 grupos offline**, sem grupo em falha, registrado em
`suite-final.log`, depois da guarda de isolamento do recorte. A rodada completa
intermediária também passou 74/74 (`suite-depois.log`), mas não é o baseline final.
O diretório/nome deste relatório mantém a data de início da rodada; fechamento
em 10/10/2026.

## Correções implementadas

1. Episódios agora fornecem ID, horário integral, resultado, sucesso/falha,
   fonte e contexto/autoria existente. Antes o resultado era consultado, mas
   não enviado; ID/contexto sumiam e o offset era retirado da apresentação.
   Não presumir autor quando o legado não o registrou.
2. Categorias disputam o mesmo orçamento em rodadas, por registros inteiros.
   Nenhuma fonte toma silenciosamente o espaço de todas as outras. O teto de
   caracteres permanece o configurado, com mínimo legado de 1.000; ele limita
   **material**, não o prompt de identidade nem tokens. Limites de linhas são
   sinalizados, com contagem de exclusões conhecidas pelo orçamento; não é
   contagem exata de todo o histórico fora dos limites de consulta.
3. Consultas mentais passam a falhar explicitamente; JSONL ilegível também.
   A noite não é marcada como vazia/concluída nessas falhas. Leitura de eventos
   mantém só a janela existente de 300 linhas em RAM, embora ainda percorra o
   arquivo diário. Hash do evento é dos bytes da linha, excluindo terminador,
   mesmo quando a exibição precisou substituir UTF-8 inválido.
4. O recorte que chegou à inferência acompanha a gravação. Registro novo que
   aparece enquanto o modelo responde não é anexado retrospectivamente como
   evidência. Envelope contém entidade, dia, instante de referência, fontes
   selecionadas, seus metadados disponíveis, hashes e limites, mais o motivo.
   Referência de outra entidade é recusada no prompt e na gravação.
5. `reflections.evidencias` preserva o envelope no próprio banco existente.
   Recuperação automática apresenta até oito referências resumidas, explicita
   as demais e fornece o ID para inspeção do registro integral. A recuperação
   não reinjeta todos os contextos antigos. Tipo continua reflexão, confiança
   ausente continua explicitamente ausente/default, não confirmação factual.
6. Nenhuma conclusão válida → não marcar conclusão da noite. Conclusão maior
   que os 700 caracteres já previstos é recusada inteira, não cortada e
   salva como se estivesse completa. Exclusões por tamanho/limite de 12 são
   diagnosticadas sem texto do conteúdo; conclusões válidas restantes podem
   ser salvas. Isso é processamento parcial, não prova de que todo material
   foi aprendido.
7. Ordenação de memórias, procedimentos e contatos usa os comparadores de
   instantes já existentes, com ID como desempate, sem reescrever legado.
   Material diário de episódios/emoções/eventos mantém os limites do dia e
   teto temporal da rodada anterior.

O envelope registra **origem do contexto**. Não contém a íntegra imutável de
todos os registros consultados, nem vínculo semanticamente comprovado de cada
conclusão com uma fonte. Hash ajuda a detectar alteração posterior da versão
representada, não recupera sozinho um registro modificado. Não persiste cadeia
de raciocínio ou cache de execução como memória autobiográfica.

## Arquivos desta rodada

- [night_reflection.py](</home/gustavo/hoshino e lilith/app/mind/night_reflection.py>): preparação/limites/proveniência/compatibilidade.
- [main.py](</home/gustavo/hoshino e lilith/app/main.py>): conservar recorte e não declarar sucesso em falhas.
- [reflection.py](</home/gustavo/hoshino e lilith/app/mind/reflection.py>): prévia explícita da evidência na recuperação.
- [test_reflexao_noturna.py](</home/gustavo/hoshino e lilith/testes/test_reflexao_noturna.py>): 14 métodos novos; fixture compartilhada pelos testes antigos sem duplicar sua execução.
- Este relatório é o único documento novo. Nenhum grupo oficial novo.

## Regressões e preservação

**20/20 métodos** do grupo noturno, sendo 6 anteriores e **14 regressões novas**,
mais o smoke legado. Integridade: **15/15**. Persistência: **17/17**. Todos em
isolamento oficial, SQLite e arquivos temporários, inferência simulada.

Cobertura nova: ID/autoria/resultado/offset; orçamento e fonte gigante; tipo e
confiança zero; recorte estável durante resposta; fonte JSONL verificável;
falha de tabela/leitura; limite de linhas; material que não cabe; resposta
inválida; recuperação compacta; UTF-8 inválido; conclusão longa; origem de outra
entidade recusada. Strings de evidência antigas continuam legíveis sem migração.

Falhas de desenvolvimento não ocultadas:

- Primeira execução: 5 falhas determinísticas e 5 erros da API nova ausente.
- A própria ampliação inicial expôs reinjeção excessiva: 16.630 caracteres em
  uma reflexão do ensaio isolado; adicionada regressão e corrigido o leitor.
- Hash calculado após decodificação não correspondia a bytes UTF-8 inválidos;
  reprodução e correção para leitura binária sem reescrita do arquivo.
- Conclusão longa era cortada/salva; regressão vermelha antes da recusa inteira.
- Novo envelope não recusava contexto de outra entidade; guarda adicionada após
  regressão vermelha. Não houve vazamento de banco real nesse teste.
- Persistência ainda emite `ResourceWarning` de conexões SQLite não fechadas
  durante seus testes. Não foram suprimidos nem corrigidos neste incremento;
  suíte verde não demonstra ausência de leaks em todos os consumidores.

Snapshots consistentes dos três bancos pela API de backup SQLite, fonte aberta
somente para leitura, e arquivos de código pré-incremento estão no diretório
privado ignorado pelo Git. Comparação dos dumps lógicos após alterações: originais
e snapshots idênticos, `quick_check=ok` nos seis arquivos:

| Entidade | SHA-256 lógico |
|---|---|
| Hoshino | `f9164eba302fb5eb2884945877e390b8ae95a256698b2f2b4afd864c9edf8ae7` |
| Lilith | `aad72056ccb4a82567319f2d714118b80fea27f32d63d312194a8fb765498aec` |
| Alistair | `9212718395f40f66eadffd19d39450b299c816a60e31233a37fef6ba54120914` |

Nenhum modelo removido/trocado, banco migrado, personalidade editada, entidade
acordada, serviço reiniciado ou provider pago chamado. Alterações anteriores da
árvore suja foram preservadas. `git diff --check` sem erros.

## Limites e próximos pontos

- Ainda é revisão limitada, não resumo semântico incremental que garanta visita
  posterior a todos os registros omitidos. Esse processamento restante, diário
  voluntário/ACL, aprendizagem causal e oficina visual seguem pendentes.
- Registros grandes demais ficam fora; quando nenhum cabe, há falha explícita,
  não sucesso vazio. Não foi medido volume enorme de registros/JSONL; teto de
  contexto não equivale a limite rígido de RAM das consultas.
- SQLite e marcador JSON de noite concluída não formam uma transação única.
  Persistência de reflexão seguida de falha do marcador ainda precisa de
  auditoria de idempotência/recovery; não prometer exactly-once.
- Falhas deixam a revisão pendente; backoff e contenção de tentativas continuam
  sujeitos ao ciclo existente. Não afirmar orçamento de inferência prolongada
  ou iniciativa diária validado por mocks.
- Não há teste novo de personalidade, consciência/sentimento, Discord,
  Minecraft, GPU, providers ou convivência física prolongada nesta rodada.
- A segunda leitura física encontrou cerca de 24 GiB disponíveis, VRAM usada
  0,89 GiB e GPU busy 0%; swap ocupada continua 3,4 GiB sem entrada/saída nos dois
  intervalos. É snapshot curto enquanto rodavam testes offline, não benchmark
  de LLM, cache ou acesso GPU direto à RAM.
- Memória de execução compartilhada não autoriza compartilhar memórias mentais
  de entidades. Pesos/cache, histórico e contexto/estado de cada entidade têm
  contratos diferentes. Nenhuma deduplicação de pesos/cache foi implementada.

Para carregar o código novo, restart cooperativo posterior; não executado aqui.
Reversão deve retirar somente este incremento, sem restaurar bancos por cima dos
originais ou reverter alterações anteriores. O leitor legado continua disponível.


---

## Original 7 — CACHE_RAM_20261010.md

# Cache de prompts em RAM — incremento de 10/10/2026

## Decisão e limites

O Resource Manager existente calcula um teto agregado para o cache de prompts/KV
do backend já instalado. Não há outro scheduler, banco, serviço de cache ou pool
de pesos em RAM. Os caches continuam privados a cada executor/entidade; orçamento
compartilhado não significa conteúdo compartilhado.

Política inicial no `compartilhado/config/gpu.json`: 8 GiB combinados, repartidos
em 3,5 GiB para Hoshino, 3,5 GiB para Lilith e 1 GiB para Alistair. É um teto,
não uma alocação antecipada. RAM pequena, insuficiente ou desconhecida reduz/desliga
o cache no próximo boot gerenciado. Swap nunca amplia o orçamento. Mantemos a
margem RAM existente mais 4 GiB de folga operacional e limitamos a soma a um terço
da RAM física. Configuração inválida desliga o cache, sem invalidar o fallback.

Fluxo: configuração existente → Resource Manager → ambiente do daemon próprio
no lifecycle existente → cache do llama-server. O endpoint Recursos e as duas
interfaces apenas mostram a política prevista; uso real permanece desconhecido.
Um daemon próprio fica limitado a um modelo carregado e uma geração paralela,
evitando multiplicar o teto por vários runners residentes nesse daemon.

Não mudamos offload, seleção de executor, janelas de contexto, margem VRAM,
concorrência GPU ou fallback CPU. CPU/mmap/staging e cache de arquivos do sistema
operacional ainda podem usar RAM para pesos: não é possível prometer zero bytes
de modelo em RAM. O cache de prompts não substitui memória autobiográfica nem
torna maior a janela de contexto. Não se promete sobrevivência a unload/restart.

## Evidência e ativação

Ollama local/API: 0.32.6. O `llama-server --help` instalado reconhece
`--cache-ram` / `LLAMA_ARG_CACHE_RAM`, em MiB, com padrão 8192 por runner.
O [código desta versão do Ollama](https://github.com/ollama/ollama/blob/v0.32.6/llm/llama_server.go)
transmite o ambiente do daemon ao runner. A [documentação do llama.cpp](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
descreve o cache de prompts em RAM.

Isso confirma a rota por inspeção, não o teto efetivo em uma inferência real.
Não reiniciamos daemons existentes, não carregamos modelos, não acordamos
entidades e não usamos quota. A política só será transmitida ao iniciar um
daemon novo pelo lifecycle gerenciado. Porta ocupada não causa restart/takeover.
Daemons externos, já vivos, PC2 portátil e sobreposição transitória de runners
durante unload/reload não têm um limite global de RSS comprovado por este patch.
O inicializador legado dos scripts de preparação/verificação de modelos também
não foi alterado: esta política se aplica ao lifecycle normal das entidades.
Não executar esses scripts supondo que esse teto foi imposto ao seu daemon.

Validação física pendente: boot cooperativo autorizado; observar teto no log do
runner; workload repetido com o mesmo contexto; medir cache hit/restore, primeira
resposta, RAM/RSS, swap, VRAM e unload. Não há ganho de latência medido nesta rodada.

## Resultados

### Correções e regressões

- O padrão do backend podia permitir até 8 GiB por runner. O boot normal passa
  agora a transmitir uma cota pública por entidade calculada pelo Resource
  Manager. Um limite menor definido pelo operador é preservado, inclusive zero;
  valores herdados ilimitados/maiores são limitados à cota. Nunca retornamos o
  ambiente completo para a Central/diagnóstico.
- Um JSON GPU válido sintaticamente, mas não objeto (`[]`, `null`, `true`), causava
  `AttributeError` em `gpu_policy`. Reproduzimos os três casos; agora o RM mantém
  a política conservadora, e o plano de cache fica desativado/inválido.
- A primeira varredura deu **73/74 grupos**: duas verificações de iniciativa
  falhavam porque a execução ocorreu de madrugada. O log mostrou a revisão
  noturna consumindo a resposta simulada da conversa antes da deliberação.
  Classificação: **fixture incompleta**, não regressão da personalidade. Apenas
  nessa fixture de conversa isolamos o gatilho noturno, mantivemos as verificações
  de fala/motivo e acrescentamos a exigência de uma única chamada ao modelo.
  Nenhuma regra de iniciativa/reflexão real foi desativada.
- Na validação da UI, o teste envoltório ainda esperava 42 contratos Qt; o novo
  teste de projeção do cache elevou o conjunto para 43. Atualizamos a contagem
  explícita, mantendo retorno zero e sem relaxar as verificações.

Antes da implementação, as novas regressões acusaram 14 erros no grupo GPU
(funções de orçamento ainda ausentes) e três falhas no boot Hoshino/Lilith/Alistair
(limite ilimitado herdado). O teste de porta ocupada já passava e protege esse
contrato contra takeover/restart. Depois, as três formas inválidas do JSON foram
reproduzidas separadamente antes da correção de `gpu_policy`.

**12 novos métodos de regressão:** oito de cache/sondas no grupo GPU, dois de
lifecycle, um de Recursos/segredos e um de projeção Qt. Também expandimos os
asserts de navegação do navegador e da fixture de integração existente.

| Execução isolada | Resultado |
|---|---|
| `test_gpu_cooperativo` | 39/39 |
| `test_ollama_lifecycle` | 15/15 |
| `test_central_control` | 41/41 |
| `test_central_browser` | 1/1; 12 cenários de navegação com API simulada |
| `test_central_refinamento` | 34/34; inclui 43/43 contratos Qt offscreen |
| `test_integracao` | 44 verificações, zero falhas |
| `test_reflexao_noturna` | 20/20; contrato real de horário/estado testado isoladamente |
| Suíte oficial após primeiro patch | 74/74 grupos offline |
| Suíte oficial repetida após guarda final do JSON | 74/74 grupos offline |

Testes offline bloqueiam serviços/provedores/hardware reais. UI simulada e Qt
offscreen não provam a aplicação da variável no runner real, captação/fala física,
Minecraft ou desempenho prolongado. `git diff --check` passou nos arquivos
versionados tocados nesta rodada.

### Arquivos deste incremento

Produção/configuração (alterados, sem substituir mudanças preexistentes):

- [resource_manager.py](</home/gustavo/hoshino e lilith/app/core/resource_manager.py>): cálculo puro, validação e opções de ambiente públicas; guarda do documento GPU.
- [gpu_metrics.py](</home/gustavo/hoshino e lilith/app/core/gpu_metrics.py>): sonda somente leitura de RAM física.
- [ollama_lifecycle.py](</home/gustavo/hoshino e lilith/app/core/ollama_lifecycle.py>): ambiente limitado no boot próprio; diagnóstico de preparação, não confirmação.
- [gpu.json](</home/gustavo/hoshino e lilith/compartilhado/config/gpu.json>): seção de cache; demais parâmetros preservados.
- [central_control.py](</home/gustavo/hoshino e lilith/app/core/central_control.py>): campo `ram_prompt_cache` no endpoint Recursos existente.
- [native_panels.py](</home/gustavo/hoshino e lilith/app/ui/native_panels.py>) e [control.js](</home/gustavo/hoshino e lilith/app/ui/control.js>): teto previsto separado de utilização real; aviso de configuração inválida. Nenhum timer novo.

Testes alterados:

- [test_gpu_cooperativo.py](</home/gustavo/hoshino e lilith/testes/test_gpu_cooperativo.py>)
- [test_ollama_lifecycle.py](</home/gustavo/hoshino e lilith/testes/test_ollama_lifecycle.py>)
- [test_central_control.py](</home/gustavo/hoshino e lilith/testes/test_central_control.py>)
- [native_central_contracts.py](</home/gustavo/hoshino e lilith/testes/native_central_contracts.py>)
- [test_central_refinamento.py](</home/gustavo/hoshino e lilith/testes/test_central_refinamento.py>)
- [central_browser.cjs](</home/gustavo/hoshino e lilith/testes/central_browser.cjs>)
- [test_integracao.py](</home/gustavo/hoshino e lilith/testes/test_integracao.py>)

Criado: este relatório. Nenhum modelo, identidade, banco, histórico ou evidência
anterior foi removido. Nenhum novo backend ou scheduler.

### Preservação e evidências

Snapshot anterior do código/config pertinente, privado e ignorado pelo Git:
`/home/gustavo/hoshino e lilith/compartilhado/runtime/ensaios/20261010/cache-ram/pre-incremento/codigo.tgz`.
Logs de testes no mesmo diretório `cache-ram`, incluindo RED e as suítes antes/depois.
Não copiamos bancos mentais para Git, nem gravamos credenciais.

Os três bancos reais foram consultados somente em modo read-only; `quick_check`
retornou `ok`, e os hashes lógicos continuam iguais ao incremento anterior:

| Banco | SHA256 lógico |
|---|---|
| Hoshino | `f9164eba302fb5eb2884945877e390b8ae95a256698b2f2b4afd864c9edf8ae7` |
| Lilith | `aad72056ccb4a82567319f2d714118b80fea27f32d63d312194a8fb765498aec` |
| Alistair | `9212718395f40f66eadffd19d39450b299c816a60e31233a37fef6ba54120914` |

Leitura real durante a rodada: aproximadamente 31,2 GiB RAM física, 22,8 GiB
disponíveis na consulta do plano; AMD/sysfs conhecido/estável, GPU busy 0% e
cerca de 0,91 GiB VRAM usada. Isso não é benchmark de inferência/cache.

### Riscos restantes / próximo passo

O teto é de cache do runner, **não limite de RSS de todo o projeto**. Pressão de
RAM surgida depois do boot não reduz automaticamente esse cache; mudanças na
configuração também não são reaplicadas a processos existentes. Daemons com
políticas de versões diferentes e processos externos impedem alegar um teto
global efetivamente imposto. O isolamento testado é de cotas/instâncias; não
realizamos nesta rodada ensaio físico de recuperação cruzada de KV.

Próxima prioridade: ensaio frio/quente pareado no backend real, após boot
cooperativo controlado, confirmar o teto no log e medir latência/uso/pressão.
Só então avaliar se aumentar ou redistribuir cache oferece vantagem. Não
declaramos cache calibrado, ganho de velocidade ou projeto inteiro concluído.

## Continuação — aplicação e ensaio físico, 10/10/2026

As seções anteriores registram o primeiro incremento, antes do restart. Nesta
continuação aplicamos e medimos a política no hardware real, sem acordar entidades.
Não mudamos os tetos de cache, modelos, offload, prioridades, contexto de produção
ou concorrência. Não usamos providers externos nem abrimos bancos mentais para escrita.

### Duas correções pequenas

1. `scripts/preparar_tres_modelos.py`: o boot legado usado pela preparação e pelo
   verificador não passava as cotas. Agora reutiliza
   `resource_manager.ram_prompt_cache_environment`. Um daemon saudável continua
   intocado. Combinações entidade/porta fora dos três endpoints dedicados são
   recusadas antes da sondagem; nenhum consumidor encontrado utiliza outra combinação.
2. `app/core/resource_manager.py`: um fallback CPU durante a janela de proteção
   interativa podia registrar `allowed=true, reason=fits`. Havia espaço físico,
   mas a política não concedia GPU. Agora esse caso informa
   `allowed=false, reason=interactive_grace` (ou proteção de áudio, quando aplicável).
   A decisão CPU/GPU, a janela de três segundos, o fallback e a prioridade são
   **os mesmos**; corrigimos a explicação, não recalibramos a admissão.

Regressões em `test_gpu_cooperativo.py`: dois novos métodos para boot/cota e
endpoint vivo/estrangeiro; um para fallback durante a janela interativa e GPU
após a janela. Primeiro reproduzimos quatro falhas de asserts nos dois métodos
de boot e uma falha no método de diagnóstico. Após as correções: **42/42 testes**.
As métricas de RAM das fixtures são simuladas, sem depender do hardware do CI.

### Restart e preservação

Os três daemons antigos estavam ociosos, com `/api/ps` vazio. Mantivemos os locks
existentes das três entidades e o lease de manutenção GPU. Conferimos UID,
executável, argumentos, host, diretório de pesos e destino do log antes de enviar
SIGTERM ao PID exato, com pidfd; nenhum kill por nome/porta ou SIGKILL.
Iniciamos os substitutos pelo lifecycle existente. APIs saudáveis, catálogos e
digests iguais antes/depois; nenhuma entidade acordada.

O ambiente dos três daemons e os logs dos modelos confirmaram:

| Entidade | Teto observado | Modelos ensaiados nesta continuação |
|---|---:|---|
| Hoshino | 3584 MiB | Qwen2.5 7B, Qwen3.5 9B |
| Lilith | 3584 MiB | Qwen2.5 7B |
| Alistair | 1024 MiB | Qwen3.5 4B em CPU e pela rota GPU oportunista |

Teto não é RSS nem alocação antecipada. Não testamos Lilith 9B ou os candidatos
6B nesta rodada, nem prometemos sobrevivência do cache após descarregar o modelo.

### Workload e resultados

Sequência A → B → A → A, com dois contextos sintéticos diferentes, hashes
registrados, 4096 tokens de janela, saída máxima de 64 tokens, temperatura zero
e seed 42. Respostas numéricas 42/43, término `done=true` e `done_reason=stop`.
Nenhuma ferramenta foi executada. Para Hoshino/Lilith usamos o lease existente;
para a validação GPU de Alistair usamos **o método de produção `Alistair.infer`**,
sem `chat`, apresentação, histórico ou pipeline mental. Isso não valida sua persona.

"Frio" abaixo significa runner descarregado; não limpamos o cache de arquivos
do sistema operacional. As repetições não permitem atribuir a melhora de load
ao cache de prompts. `A_return` compara o mesmo prompt A depois de outro B;
o log `found better prompt` confirma seleção do estado salvo, além de checkpoints
nos modelos Qwen3.5. `A_repeat` mede reutilização do contexto ativo e não é prova
independente de recuperação do pool em RAM.

| Execução real | Load frio | Total A frio | Total A recuperado | Processamento A frio → recuperado | Cache salvo máximo observado |
|---|---:|---:|---:|---:|---:|
| Hoshino 7B, GPU, repetição com RSS corrigido | 3,258 s | 6,290 s | 0,416 s | 2,904 → 0,034 s | 121,487 MiB |
| Hoshino 9B, 32 camadas GPU, repetição | 3,862 s | 6,904 s | 0,709 s | 2,906 → 0,112 s | 303,097 MiB |
| Lilith 7B, GPU, primeiro ensaio | 4,762 s | 7,846 s | 0,409 s | 2,913 → 0,033 s | 121,487 MiB |
| Alistair 4B, CPU real, primeiro ensaio | 4,374 s | 45,607 s | 0,815 s | 41,039 → 0,194 s | 303,097 MiB |
| Alistair 4B, GPU real, método de produção | 2,380 s | 4,104 s | 0,679 s | 1,611 → 0,089 s | 303,097 MiB |

São medições pontuais de prompts sintéticos, não percentis, benchmark de diálogo
ou prova de ganho igual em qualquer mensagem. As diferenças de tokenização entre
famílias também impedem uma comparação de qualidade/velocidade entre modelos.

### Medição corrigida e um ensaio reprovado preservado

No primeiro ensaio, a coleta de filhos olhava somente a thread principal do
daemon; o runner nasce em outra thread. **Seu campo de RSS não mede o modelo e
não deve ser utilizado como RSS agregado.** Repetimos Hoshino 7B/9B incluindo os
filhos de todas as threads. Alistair recebeu a coleta corrigida no ensaio GPU final.

No caminho genérico do primeiro ensaio de Alistair, os leases posteriores diziam
GPU, mas `/api/ps` manteve `size_vram=0`: o runner CPU foi reutilizado. Os quatro
casos dessa sequência são classificados como **CPU real**, nunca GPU aprovada.
Esse ensaio não usou a troca própria CPU→GPU existente em `Alistair.infer`.

A primeira repetição pelo método de produção foi **reprovada na exigência GPU**:
começou logo após Hoshino, durante a janela interativa; caiu corretamente em CPU.
Não relaxamos a janela. Fora dela, repetimos quatro casos pelo mesmo método:
`size_vram > 0` confirmado em cada resposta, sem acordar entidade ou forçar GPU.
Não apagamos o ensaio reprovado nem o tratamos como validação GPU.

| Coleta incluindo daemon + runners | Pico RSS | Pico VRAM total da máquina | Menor RAM disponível |
|---|---:|---:|---:|
| Hoshino 7B | 4,620 GiB | 5,541 GiB | 23,193 GiB |
| Hoshino 9B | 5,564 GiB | 5,947 GiB | 21,651 GiB |
| Alistair 4B GPU | 2,856 GiB | 3,995 GiB | 22,582 GiB |

RSS inclui pesos mapeados, staging, runtime e cache, não apenas prompts; somar
RSS também não deduplica páginas compartilhadas. Mesmo com GPU, existe uso RAM
para pesos. Não é correto prometer "RAM somente para cache". Não criamos um
pool de modelos residentes em RAM. O uso observado de cache ficou muito abaixo
das cotas: **não há evidência para aumentá-las agora**.

VRAM permaneceu abaixo do limite real e da margem de 768 MiB. As consultas de
swap global registraram atividade pequena, incluindo aproximadamente 49 MiB de
page-out na primeira sequência 9B; há navegador/Steam externos ativos. Não
podemos atribuir essas páginas exclusivamente ao modelo. Sem teste de pressão
controlada/soak, não afirmamos ausência de swap thrashing em uso prolongado.

Todos os unloads foram confirmados pela API, sem leases restantes. A liberação
VRAM no driver não foi instantânea após algumas confirmações: a próxima medição
fria aguardou estabilização, sem alterar o scheduler ou matar processos. Memórias
dos três bancos: `quick_check=ok`, dumps lógicos antes/depois idênticos nesta
continuação. Memória autobiográfica, personalidades e configurações de executor
não foram alteradas. Oportunismo do Alistair preservado, CPU obrigatório preservado.

### Evidências e escopo restante

Artefatos privados, fora do Git, em
`compartilhado/runtime/ensaios/20261010/cache-ram/`:

- `restart-controlado.json`: propriedade dos processos, ambiente público,
  catálogos/digests e hashes lógicos iniciais.
- `ensaio-real.json`: 16 respostas confirmadas; primeira coleta RSS limitada e
  Alistair classificado pelo backend real, não pela permissão solicitada.
- `ensaio-real-rss-corrigido.json`: oito respostas GPU Hoshino; registra a
  reprovação GPU de Alistair durante a janela interativa.
- `alistair-cache-gpu-real.json`: quatro respostas GPU Alistair pelo caminho
  de produção, coleta corrigida, hashes mentais finais iguais e leases vazios.
- `diagnostics-ensaio/`: diagnóstico existente redirecionado para o ensaio,
  sem acrescentar conversas ao histórico real.
- `pre-validacao-real/`: snapshots reversíveis dos arquivos tocados.
- `suite-ensaio-antes.log` / `suite-ensaio-depois.log`: suíte oficial antes/depois.

Resultado final: **74/74 grupos offline antes e 74/74 depois**; grupo GPU
**42/42**, três métodos novos de regressão. `git diff --check` passou nos
arquivos versionados tocados. `verificacao-final.json` confirmou as três APIs
saudáveis, zero modelos residentes, zero leases/pedidos pendentes, catálogos
inalterados e os três bancos mentais íntegros/inalterados. Nenhuma regressão
restante apareceu na suíte; isso não substitui as validações prolongadas abaixo.

Código-base Git registrado: `f23ba0d721fac6cb53534b55fcc5b48547e1dec8`.
A árvore já tinha numerosas alterações; elas foram preservadas, não revertidas
ou incluídas num commit automático. Arquivos alterados nesta continuação:
`scripts/preparar_tres_modelos.py`, `app/core/resource_manager.py`,
`testes/test_gpu_cooperativo.py` e este relatório. Nenhum arquivo de modelo,
identidade, personalidade ou banco mental editado.

Pendentes: soak, saturação/evicção do cache, pressão agregada/swap, recuperação
entre muitas alternâncias, ensaio físico Lilith 9B nesta configuração e isolamento
cruzado de conteúdo KV. A UI continua distinguindo plano de uso real: estas
medições não viraram um contador vivo de RSS/cache na Central. Não há motivo
medido para mudar heurísticas, habilitar concorrência ou prometer cache calibrado.

---

## Original 8 — CONSOLIDACAO_BOMBA_LIMPEZA_20261010.md

# Continuação da “bomba”: recovery e limpeza — 10/10/2026

## Resultado

**Rodada concluída no escopo descrito abaixo; a consolidação cognitiva inteira não está concluída.**

- Reunidos sete relatórios anteriores completos, mais este relatório, em [Relatórios da bomba](</home/gustavo/hoshino e lilith/docs/RELATORIOS_BOMBA_CONSOLIDADOS_20261010.md>). Os originais permanecem intactos.
- Corrigida a repetição de reflexão noturna quando o SQLite confirma a gravação, mas o marcador JSON falha.
- Removidos somente os pesos dos candidatos não aprovados: Jan, Esper3 e Hunyuan de Hoshino/Lilith, mais o GGUF fonte duplicado do Esper3.
- Liberados **28.358 GiB** de espaço entre os snapshots da limpeza. É uma diferença física de espaço livre, não um valor universal de tamanho lógico por alias.
- Mantidos modelos ativos, configurações de recursos e fallbacks. Limpas memórias de teste pelo mecanismo existente, sem eliminar identidades, traços, relações, recibos, diagnósticos ou evidências.
- **74/74 grupos offline antes e depois**, inclusive após o refinamento de descarte de conversas. Reflexão noturna: **27/27 métodos**, incluindo **sete regressões novas**. Mensagens/causalidade: **41/41**, com mais uma regressão permanente para conteúdo apagado e dedup preservado.

Não acordamos entidades, não fizemos nova inferência física nesta rodada, não gastamos quota externa, não baixamos modelo, não ligamos cloud nem concorrência GPU. Ensaios físicos de cache/GPU são os descritos no relatório anterior, não testes novos desta limpeza.

## 1. Defeito reproduzido e corrigido

### Reprodução antes da correção

O teste novo grava uma reflexão, simula falha de `marcar_concluida` e executa o ciclo novamente com uma nova instância de teste:

```text
Ran 21 tests
FAILED (failures=1)
test_committed_reflection_marker_failure_does_not_regenerate_on_restart
AssertionError: Expected mock to not have been awaited. Awaited 1 times.
```

O código anterior não reconciliava o commit do SQLite. IDs aleatórios permitiam outra chamada ao modelo e outro registro da mesma noite. Esta é uma **regressão reproduzida em ambiente isolado**, não um crash provocado na entidade real.

### Correção mínima

Consumidores encontrados: ciclo noturno em `app/main.py`, funções de reflexão noturna, recuperação de reflexões, inspetor/manutenção da Central e testes de persistência/reflexão.

- Novos commits noturnos usam IDs determinísticos por **entidade + chave da noite + índice** dentro da tabela `reflections` existente.
- O campo `evidencias` conserva as referências anteriores e acrescenta metadados do lote: noite, quantidade, índice e hash das conclusões.
- O lote inteiro é salvo na transação SQLite existente. Uma falha de uma linha reverte o lote.
- Antes de inferir novamente, o ciclo consulta e valida o lote já salvo. Se ele existe inteiro, tenta apenas finalizar o marcador JSON.
- Outra tentativa de salvar não substitui as conclusões/evidências já confirmadas, mesmo que a nova saída seja diferente.
- Lote parcial, modificado, incompatível ou banco indisponível provoca diagnóstico e bloqueia replay automático. Não marca uma revisão corrupta como concluída.
- Categoria continua `reflexao`, nunca fato. Não há DDL, migração, nova tabela/banco, gerador de memória ou scheduler.
- A assinatura antiga de `salvar` continua válida. A recuperação idempotente vale para novos ciclos com o parâmetro `agora`; registros legados não recebem autoria/noite presumidas.

**Limite:** SQLite e o JSON continuam dois destinos distintos. A reconciliação fecha a janela posterior ao commit de novos lotes; não promete exactly-once global, nem recuperação automática de lotes legados sem metadados. O teste de restart usa estado persistente isolado e nova instância; não é um reboot físico ou um crash real do daemon.

## 2. Limpeza dos modelos

A autorização atual para remover modelos não aprovados substitui a decisão histórica de preservar candidatos. “Instalado/preservado” nos relatórios antigos descreve aquele momento, não o inventário atual.

| Entidade | Mantido ativo | Retirado |
|---|---|---|
| Hoshino | Qwen3.5 9B + Qwen2.5 7B | Jan ~6B, Esper3 ~6B, Hunyuan 7B |
| Lilith | Qwen3.5 9B + Qwen2.5 7B | Jan ~6B, Esper3 ~6B, Hunyuan 7B |
| Alistair | Qwen3.5 4B | Nada |

Não existe terceiro executor ~6B aprovado após a limpeza. Não instalamos outro apenas para preencher o número de executores.

- Esper3: falha casual por orçamento esgotado/repetição e admissão seguinte bloqueada, documentadas no ensaio anterior.
- Jan: predecessor não aprovado como executor automático.
- Hunyuan: candidato com problemas observados de português/identidade; não houve aprovação definitiva nem um vencedor geral entre os 7B. Sua retirada é decisão de limpeza autorizada, não fabricação de resultado de benchmark.
- Modelos de imagem, visão, ASR, Qwen3-TTS/Kokoro e pesos do Alistair foram preservados.
- Aliases fonte compartilhados com os modelos ativos foram mantidos: removê-los não pouparia novamente o mesmo blob e atrapalharia os caminhos de preparação/reversão existentes.
- Rotinas e regressões que descrevem protocolos/candidatos antigos foram preservadas como compatibilidade/teste. Nenhum arquivo ativo ainda referencia o companion removido.

Operação realizada sob os locks das três entidades e manutenção GPU existentes, com presença/jobs/leases ociosos e `/api/ps` vazio. Cada alvo teve digest conferido antes; remoção passou pela API local do Ollama, seguida de consulta de confirmação. Os manifestos retidos e tamanho/inode dos arquivos mantidos foram comparados. Isso comprova preservação durante a limpeza, não uma nova leitura criptográfica integral de todos os pesos antigos.

O GGUF duplicado do Esper3 foi removido só depois de verificar tamanho e SHA-256 `c6e8b85ffd17184ec44103c2ee2348203fd5f8ccb63fc87750173c71ca873d72` e confirmar que os blobs retidos não mudaram. O README de origem e as evidências foram preservados.

### Espaço

- Stores Ollama: **51.410.616.320 → 25.201.827.840 bytes alocados**.
- Livre no filesystem: **56.194.256.896 → 86.643.544.064 bytes** durante a operação.
- Diretório de modelos observado depois: cerca de **41 GiB**, contra aproximadamente 70 GiB antes. Filesystem: aproximadamente **90% ocupado**, 81 GiB disponíveis no snapshot posterior.
- Não apagamos testes, relatórios ou ensaios para poupar alguns MiB enquanto existiam dezenas de GiB de pesos não utilizados.

**Recuperabilidade:** pesos removidos não foram duplicados em outro backup. Para voltar a eles seria necessário baixar/importar novamente as fontes fixadas nos registros preservados. Configs anteriores têm uma cópia privada pequena. Nenhum download de reversão foi executado.

## 3. Limpeza das memórias de teste

Foi usada a seleção explícita da manutenção já existente, por entidade, sob `entity.lock`. Não utilizamos o reset total que poderia apagar personalidade/relações.

| Entidade | Registros SQL removidos | Registros vetoriais removidos | Remanescentes nas categorias selecionadas | Integridade |
|---|---:|---:|---:|---|
| hoshino | 194 | 168 | 0 | ok |
| lilith | 0 | 0 | 0 | ok |
| alistair | 10 | 0 | 0 | ok |

Categorias: fatos/conhecimentos, propriedades, episódios, reflexões, procedimentos, resumos e histórico recuperável próprio `alistair_turns`, quando existem naquele banco.

Identidades e o conteúdo lógico das outras tabelas foram comparados antes/depois e preservados durante a primeira exclusão. Não houve VACUUM destrutivo, exclusão do arquivo SQLite nem migração.

**Atualização após resposta do usuário:** autorizada também a remoção das conversas de teste. Operação separada, com as três entidades paradas:
- Removidas **158 mensagens** do histórico bruto da Hoshino e do índice FTS. Lilith/Alistair já tinham zero mensagens nessa tabela. Os eventos técnicos foram preservados e comparados por conteúdo lógico.
- Retirados texto e metadados de conteúdo de **170 envelopes** da caixa postal. Permanecem tombstones sem texto, com IDs/autoria/tempo/desfecho e correlação operacional mínima. Isso evita perder a deduplicação e executar uma resposta antiga novamente.
- Preservados **78 recibos de resposta**, **91 chaves de dedup** e os **16 desfechos incertos** exatamente como estavam. Apagar o conteúdo não transforma incerteza em sucesso.
- Filas, consulta entre entidades, conversa do usuário, histórico privado e catálogo diário excluem tombstones. Teste isolado valida essas rotas e a repetição com o mesmo ID/chave não cria outra mensagem.
- Tipo `deleted` é reservado à manutenção: envio normal não pode esconder uma mensagem nova com esse tipo.
- **Cinco tarefas antigas active/paused foram canceladas**, preservando todos os outros campos, passos e recibos. Nenhuma ação passada foi declarada desfeita/completada. Não há objetivo de teste retomável.
- Ao final, consultas reais de conversa e fila retornam vazias; contagem de mensagens/FTS é zero nos três históricos. Nenhum pedido de wake estava pendente.
- A exclusão de conversas passou pela função de limpeza de mensagens existente; não foi usado o reset que apaga eventos técnicos.

**Importante:** isto ainda não é um “reset mental total” nem apagamento seguro de toda cópia histórica. Relações/traços/estado psicológico e evidências/recibos técnicos permanecem conforme o contrato de preservação. Esses registros podem conter referências a testes; não declarar inexistência de toda informação antiga em todas as fontes. Cada banco teve uma cópia recuperável de manutenção pequena; o histórico foi acrescentado à mesma pasta de backup, sem duplicar pesos ou criar outro ramo/instância de teste. Backups/logs preservados não são automaticamente reimportados como conversa.

Backups de esta operação:
- hoshino: `/home/gustavo/hoshino e lilith/entidades/hoshino/runtime/memory-backups/manual-a865731625944c9e8cf5d9fa0a6b790f`
- lilith: `/home/gustavo/hoshino e lilith/entidades/lilith/runtime/memory-backups/manual-fdda30f9a9e94018b7396fe4dca45d35`
- alistair: `/home/gustavo/hoshino e lilith/entidades/alistair/runtime/memory-backups/manual-6fe78d63eb60422ba6292cbd254f07a6`

## 4. RAM / VRAM / Alistair

O objetivo do usuário foi preservado **sem prometer que RAM se torna VRAM**:

1. Estados de inferência ativos/pesos offloaded ficam em VRAM quando o RM consegue conceder compute com margem.
2. Estados de prompt reutilizáveis podem ficar no cache RAM existente para poupar prefill; o runner real já demonstrou restauração.
3. Memória semântica durável fica nos bancos/índices existentes e é selecionada por relevância/autoria.
4. Cache depende de executor, prefixo, contexto e configuração. Não é garantia de eliminar todos os recálculos nem de guardar todas as lembranças.
5. RAM ainda pode conter mmap/staging e camadas processadas na CPU no offload parcial. O backend atual não permite prometer “RAM exclusivamente para cache, zero pesos nela”.

Política preservada: limite físico 8 GiB; margem VRAM 768 MiB; margem RAM 2 GiB; cache RAM agregado 8 GiB (H/L 3,5 GiB cada; A 1 GiB); `concurrency_validated=false`; stickiness e prioridade existentes.

Alistair continua com GPU oportunista quando houver memória, compute e vantagem, sem trabalho prioritário aguardando. CPU/RAM continua fallback. GPU/RAM não foi inventado como um terceiro backend: offload e memória host dependem do backend existente. A rodada física anterior confirmou geração CPU e GPU; esta rodada só preservou/inspecionou o contrato.

## 5. Arquivos desta rodada

Produção:
- `app/mind/night_reflection.py`: commit/recovery por noite no SQLite existente.
- `app/main.py`: reconciliar antes de gerar; salvar com a chave da noite original.
- `app/core/interentity.py`: excluir conteúdo apagado das rotas de fila/contexto/UI, conservando o ledger existente de IDs/dedup; impedir envio normal com tipo reservado.
- `entidades/hoshino/config/executores.json` e `entidades/lilith/config/executores.json`: remoção do companion desativado referente a peso não aprovado.

Testes:
- `testes/test_reflexao_noturna.py`: sete métodos novos, sem duplicar grupos nem mexer em memória real.
- `testes/test_mensagens_causalidade.py`: uma regressão para limpeza sem replay, invisibilidade em todas as rotas de contexto/fila e preservação da incerteza.

Documentação:
- Este relatório e `docs/RELATORIOS_BOMBA_CONSOLIDADOS_20261010.md`, com cópias completas dos sete originais.
- Originais conferidos contra o conteúdo atual: **7/7 cópias exatas**, sem editar resultados anteriores.

Artefatos privados de execução em `compartilhado/runtime/ensaios/20261010/limpeza/`:
- `resultado.json`: inventário, digests, alvos, remoções e espaço.
- `memorias-resultado.json`: seleção/counts, confirmação, backup e integridade por entidade.
- `suite-depois.log`: saída completa da suíte final.
- `suite-final-conversas.log`: 74/74 após o refinamento adicional autorizado de conversas.
- `conversas-resultado.json`: exclusão de mensagens/FTS, cancelamento de objetivos de teste, conteúdo postal descartado e preservação dos desfechos/dedup.
- Três rotinas administrativas desta execução para reproduzir/verificar o procedimento; não são serviços, novos testes paralelos ou ferramentas da entidade.

A árvore já estava modificada. Não atribuímos todo o diff a esta rodada, não revertimos nada e não fizemos commit/push indiscriminado.

## 6. Testes e classificação da evidência

- Baseline atual, antes da mudança: `bash rodar_testes.sh`: **74/74**, retorno 0.
- Reprodução anterior ao patch: grupo de reflexão **20/21**, uma falha reproduzida (nova regressão).
- Após correção inicial: **21/21**.
- Após acrescentar demais regressões: **27/27**.
- Suíte completa depois: **74/74**, retorno 0.
- Após autorização adicional de apagar conversas: mensagens/causalidade **41/41**; suíte completa final **74/74**, retorno 0.
- Durante o desenvolvimento da fixture adicional houve um erro: ela enviava `reply_to` como argumento inexistente em `send`. Corrigida a fixture para usar o contexto de processamento real existente. Não se alterou a assinatura de produção para satisfazê-la nem se classificou isso como regressão do projeto.
- `git diff --check`: sem erro.
- Operações reais verificadas: remoção local de pesos, consultas de inventário/arquivos, exclusão administrativa de memórias/vetores, `quick_check=ok` nos três bancos.
- Ambiente isolado: falha do marcador, recuperação sem LLM, preservação do primeiro lote, rollback integral, corrupção/lote parcial sem replay, isolamento entidade/noite, compatibilidade legada, falha ao consumir pendência e falha de leitura SQL.
- Não testado fisicamente nesta rodada: crash/reboot durante reflexão, inferência/persona longa, PC2, Discord/Minecraft completos, TTS externo, competição jogo/imagem/voz ou GPU/RAM zero-copy.

## 7. Próximos problemas prioritários

- Conversas/fatos/episódios de teste foram retirados do fluxo ativo. Relações/traços, recibos e evidências não foram zerados: qualquer reset adicional desses estados precisaria de uma decisão específica, não de apagar o banco inteiro.
- Ensaiar contexto/cache em conversação longa real e observar pressão/eviction. Não alterar margens/concorrência para aparentar ganho.
- Prosseguir nos pontos da “bomba” ainda pendentes: resumos incrementais diários, diário com ACL e oficina/aprendizado experiencial conforme auditoria. Não declarar pronta uma função só porque existe um prompt.
- Validar integrações e autonomia em uso humano real, com evidências e limites já definidos.

