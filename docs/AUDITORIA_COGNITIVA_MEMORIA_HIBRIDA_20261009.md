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
