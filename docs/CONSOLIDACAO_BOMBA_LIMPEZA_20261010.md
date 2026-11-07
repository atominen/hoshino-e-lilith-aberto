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
