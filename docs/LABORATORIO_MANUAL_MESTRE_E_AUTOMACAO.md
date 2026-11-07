# Laboratório Neural — manual mestre, estado validado e plano de automação

## Orientação atual — 14/10/2026

**Professor mantido: Qwen3.5-35B-A3B Q3_K_M.** Para operar, começar pelo
[guia atual do laboratório](../laboratorio/README.md); para encontrar evidências,
usar o [índice por assunto](README.md) e o [mapa do projeto](ESTRUTURA_ATUAL.md).
O [reteste](PROFESSOR_RETESTE_RESULTADOS_20261014.md) e o
[A/B 9B/35B](PROFESSOR_9B_VS_35B_20261014.md) registram defeitos ainda presentes.
Não substituir modelos nem habilitar noite automática por passar um filtro.

As seções 1–13 abaixo preservam a captura inicial e o plano até v1.6.2; a
seção 14 registra consolidação posterior. Inventário, OOMs, PIDs, números de
testes e situação do GitHub desses trechos são **históricos**, não estado vivo.
Não refazer itens já implementados com base neles. A documentação organizada
não sobrescreve contratos, dados reais ou as correções de 13–14/10.

## Captura e continuidade anteriores

**Atualizado:** 12/10/2026 · **Projeto:** Hoshino / Lilith / Alistair · **Status:** referência de transferência para Codex.

**Continuação v1.8 nesta máquina:** leia primeiro o
[relatório de qualidade do professor e preparação de 12h](LABORATORIO_V18_QUALIDADE_E_12H_20261012.md).
Preparar o plano não autoriza sua execução; não há treino de 12h automático.

**Consolidação v1.7 preservada:** leia o
[relatório atual com resultados, falhas e limitações](LABORATORIO_CONSOLIDACAO_20261012.md)
e a seção 14 antes de operar. As referências v1.2/v1.6.2, OOMs e timers abaixo
registram o estado de entrada e histórico, não instruções para reinstalar ZIPs
ou restaurar código antigo.

> Registro histórico de transferência: evidências de execução no computador estão separadas de capacidades previstas e pendências. Na captura descrita abaixo, o GitHub na branch `laboratorio-v11-organizacao-20261012` continha a base sincronizada v1.2 e documentação posterior; o computador havia recebido patches até v1.6.2. **Antes de implementar, conferir os arquivos locais; não restaurar versões remotas antigas sobre versões novas.**

## 1. Objetivo do laboratório

Ambiente local, reproduzível, para adaptar, comparar, avaliar e eventualmente integrar LLMs às entidades **Hoshino, Lilith e Alistair**, preservando as identidades e memórias originais. A personalidade deve surgir de exemplos e avaliação de comportamento, não de um simples roteiro fixo. A personalidade aprendida no LoRA não substitui memória persistente, identidade versionada, políticas nem o orquestrador da entidade.

Fluxo-alvo: **inventário → preparação/curadoria → diagnóstico da arquitetura → calibração de presets → treino isolado → checkpoints → avaliação independente → candidato → promoção estável → integração opcional na Central → monitoramento/rollback**. O professor 35B propõe dados; não treina diretamente outros modelos nem substitui a aprovação dos dados.

### Princípios de organização adotados

- Um único menu **Treinamento** para diagnóstico, treinos cronometrados, presets, escolha da entidade, modelo-base, conjunto de dados e artefatos; não criar menus paralelos para "10 minutos".
- **Modelo original imutável**, LoRAs por entidade/execução em diretórios próprios e checkpoints intermediários; um resultado `completed` é **candidato**, não versão estável automática.
- Alistair é associado ao Qwen3.5-4B; Hoshino e Lilith têm execução original no Qwen3.5-9B. O 0.8B só serviu para testes de pipeline, não deve ser promovido como substituto.
- Yi-1.5-6B, Hunyuan-7B e Qwen2.5-7B HF são bases independentes para pesquisa; treinar uma arquitetura experimental não altera as entidades originais.
- O professor Qwen3.5-35B-A3B GGUF (Vulkan) é usado **somente para curadoria/inferência**, separado de LoRA e do runtime principal.
- A execução noturna deve depender de autorização explícita e de estado seguro do supervisor; nunca inferir que o usuário dorme apenas porque chegou um horário.
- Reivindicações de qualidade exigem avaliação comportamental/holdout; baixar pesos, carregar, completar dois updates ou diminuir loss de uma amostra pequena não prova estabilidade.

## 2. Máquina e limites observados

- Linux Mint; Ryzen 5 5500, 32 GiB de RAM, AMD Radeon **RX 6650 XT de 8 GiB** (gfx1032), SSD NVMe.
- Ambiente Python isolado `~/laboratorio-lora/.venv-rocm`; nos logs: ROCm `7.17.26405` e PyTorch `2.16.0a0+rocm10.2.0a20261010`. Alguns módulos `bitsandbytes` usam fallback, `causal_conv1d` e `flash-linear-attention` não estavam instalados.
- Professor GGUF com `llama-server`/Vulkan, no laboratório; taxa real observada ~**4,3–5,4 tokens de geração/s**. Modelos maiores frequentemente dependem de GTT/RAM compartilhada e PCIe Gen3 x8. Potência ~50 W durante geração não prova que não houve trabalho na GPU; o gargalo pode ser banda, latência ou kernels.
- A GPU registrou clocks de memória **675 MHz** via sysfs (e 1.350 MHz no LACT, convenção de exibição), política DPM `high`, máximo OD de núcleo 3.010 MHz e memória 1.150 MHz. Não usar clocks/overclock como solução de OOM. Para comparações confiáveis, medir com ajuste conhecido e telemetria real durante a carga.
- O treinamento precisa respeitar o orçamento real de ~8 GiB: Qwen2.5-7B e Qwen3.5-9B produziram erros de memória. Nenhuma homologação dessas duas arquiteturas para sessão longa foi obtida.

## 3. Estrutura física e Git

```text
~/hoshino e lilith/                 # checkout do projeto
  app/                              # executores e Central originais
  entidades/                        # identidades, memórias e configs originais
  iniciar_entidades.py              # supervisor original das três entidades
  laboratorio/                      # código versionável: painel, professor, treino, testes
  docs/                             # documentação versionável
  laboratorio-local/                # privado, IGNORADO PELO GIT
    .venv-rocm/
    modelos/                        # HF 9B, Qwen2.5-7B HF e 0.8B de teste
    modelos-extras/                 # Alistair 4B, Yi 6B, Hunyuan 7B
    professor-moe-35b/              # GGUF, logs, propostas e trabalhos
    pacotes/datasets/historicos...  # nomes reais devem ser inventariados
    controle-laboratorio/           # runs, checkpoints, adaptadores e relatórios
    backups/
    logs/

~/laboratorio-lora -> ~/hoshino e lilith/laboratorio-local/
```

A migração foi efetivada por rename no mesmo filesystem; `migrar_laboratorio.py verify` confirmou o symlink, os diretórios e `gitignore_rule=true`. O diretório de dados preserva os caminhos legados. **Não subir `laboratorio-local/`, pesos, LoRAs, datasets, históricos privados, caches, `.env`, venv, memórias ou tokens ao GitHub**. O repositório é privado, mas isso não torna apropriado versionar conteúdo sensível.

GitHub: `atominen/hoshino-e-lilith`; PR de revisão **#1**, branch `laboratorio-v11-organizacao-20261012`; `main` não recebeu os patches do laboratório. O commit `2c0cae0` sincronizou 44 arquivos em 12/10/2026. Posteriormente houve commits apenas de documentação; o código no PC avançou pelas versões **v1.3, v1.3.1, v1.4, v1.5.1, v1.6 e v1.6.2**, sem sincronização integral comprovada desses patches. A v1.5 falhou por hash incompatível e **não** foi instalada; a v1.5.1 corrigiu isso.

O `laboratorio/README.md` antigo da v0.3 ficou obsoleto e foi substituído por um índice para este manual. Outros changelogs e históricos antigos são documentação de contexto, não instruções atuais para habilitar agendamento anterior.

## 4. Inventário de modelos — conservar o que foi decidido

| Modelo/arquivo | Uso | Estado confirmado em 12/10/2026 |
|---|---|---|
| `Qwen3.5-4B` (HF, Alistair, ~8,68 GiB) | Base exclusiva de Alistair | Smoke de 2 updates aprovado; sessão de **5 min, 110 passos** concluída. Checkpoint precisa de teste independente de recarga. |
| `Yi-1.5-6B` (HF, ~11,29 GiB) | Base de pesquisa 6B | Smoke de 2 updates aprovado. |
| `Hunyuan-7B` (HF, ~13,98 GiB) | Primeira base de pesquisa 7B | Smoke de 2 updates aprovado; ainda há avisos de RoPE a investigar. |
| `Qwen2.5-7B HF` (~14,19 GiB) | Segunda base de pesquisa 7B, **diferente** do Hunyuan | Pesos preservados; smoke falhou por OOM. |
| `Qwen3.5-9B-Uncensored HF` (~17,53 GiB) | Base original treinável pretendida para Hoshino/Lilith | Pesos completos com SHA-256 `95117c3faed067c2a48dd3ddebf16209c4c6b60d1714ef5dd32cf784e2e053fc` previamente confirmado; LoRA longo bloqueado por OOM. |
| `Qwen3.5-0.8B` (~1,63 GiB) | Ferramenta temporária de teste | Mini-LoRAs Hoshino/Lilith treinados e recarregados; não é o modelo principal. |
| `Qwen3.5-35B-A3B Q3_K_M GGUF` (~16,36 GB decimais) | Professor de curadoria em Vulkan | Inferência funcionando; geração de dados ainda não homologada em qualidade/tempo. |
| `professor-27b` | Legado a eliminar | Exclusão **não comprovada** nesta conversa: primeiro verificar disco, serviços e referências. |

**Limpeza efetivamente confirmada:**
- Parcial antigo `.incomplete` de 1.024.000.000 bytes do 9B foi eliminado depois da validação SHA do arquivo final.
- `~/laboratorio-lora/modelos/qwen2.5-7b-local/modelo.gguf` (cópia compacta de ~4,4 GiB) foi removido pelo operador. Permanecem **dois LLMs 7B diferentes para treinamento**: Hunyuan HF e Qwen2.5 HF. O menu não deve exibir o GGUF apagado como instalado.
- Não eliminar Hunyuan ou Qwen2.5 HF para "deduplicar": arquiteturas diferentes. Não remover assets do projeto principal nem checkpoints aprovados.
- Checar eventual professor 27B, arquivos de teste 0.8B e caches apenas depois de inventário de dependências, sem exclusão baseada unicamente no nome.

### Modelos originais de produção

Na versão de `app/config.py` e `app/core/central_control.py` publicada:
- Hoshino: alias original `hf.co/ccharnkij/Qwen3.5-9B-Uncensored-GGUF:Q4_K_M`, serviço Ollama na porta 11435.
- Lilith: `lilith-qwen3.5-9b:latest`, porta 11436.
- Alistair: `alistair-qwen3.5-4b:latest`, porta 11437.

Não presumir equivalência automática entre a revisão dos pesos HF e a revisão dos GGUF/Ollama. Um LoRA HF treinado não está automaticamente pronto para `ollama create` nem para visão; confirmar revision, tokenizer, conversão e qualidade antes de deploy.

## 5. Dados e isolamento por entidade

Corpora originais:
- Hoshino: `pacote_neural_v3/hoshino_train.jsonl`, `hoshino_validation.jsonl`, `hoshino_test.jsonl`; **722 / 131 / 104** registros.
- Lilith: os correspondentes `lilith_*`; **722 / 131 / 104** registros.
- Alistair: `datasets-alistair-seed/alistair_train.jsonl` e `alistair_validation.jsonl` (corpus piloto sintético, distinto dos corpora v3).
- Existem opções históricas `pacote_neural_v2` e variações `*_delta`; preservá-las para rastreabilidade, mas **o menu principal deve mostrar um corpus recomendado por entidade**. Opções avançadas de outras versões só quando explicitamente necessárias e rotuladas.

No inventário v0.9, as divisões Hoshino/Lilith tinham zero duplicatas exatas e zero interseções exatas entre train/validation/test; isso não comprova ausência de quase-duplicação ou vazamento semântico. Medição da tokenização do train: Hoshino mediana 58, p95 115, máximo 124; Lilith mediana 57, p95 112, máximo 121. O limite 128 cobre o train medido, mas checar validação/teste e templating antes de reduzir contexto automaticamente.

Regras semânticas: a entidade só consome seu próprio corpus; históricos privados entram somente via snapshots autorizados. **Train** pode receber exemplos aprovados do professor em dataset derivado; **validation/test/holdout originais continuam imutáveis**. Identidade e memória continuam sob `entidades/<id>/identity` e `memory`, fora dos datasets exportados por padrão.

## 6. Treinamento: resultados realmente observados

| Experimento | Comprovação | Loss/memória |
|---|---|---|
| 0.8B Hoshino, rank 8, ~3 min | 541 passos, LoRA gravado, 228 tensores, recarregamento/inferência aprovados | validação amostrada **3,7556 → 2,5189**, pico 2,53 GiB |
| 0.8B Lilith, rank 8, ~3 min | 543 passos, LoRA gravado, 228 tensores, recarregamento/inferência aprovados | validação amostrada **3,8197 → 2,2263**, pico 2,51 GiB |
| Alistair 4B, 5 min | 110 updates e job `completed` | validação amostrada **3,9460 → 2,6808**, pico 5,54 GiB |
| 4B, smoke inicial | 2 updates ROCm concluídos | loss de treino 3,4668 → 3,3206, pico 5,58 GiB |
| Yi-1.5-6B | 2 updates ROCm concluídos | loss de treino 3,4248 → 3,2807, pico 5,36 GiB |
| Hunyuan-7B | 2 updates ROCm concluídos | loss de treino 5,1685 → 5,1497, pico 6,58 GiB |
| Qwen2.5-7B HF | modelo carregou, smoke falhou | OOM ao solicitar 2,03 GiB com ~430 MiB livres; **sem 2 updates aprovados** |
| Qwen3.5-9B HF | v0.9.4 fez 1 update real, mas tentativa de 12 updates e treino longo falharam | pico ~7,38–7,47 GiB; problema de movimentação de embedding de **1,89 GiB** CPU→GPU |

A avaliação dos LoRAs 0.8B revelou respostas mais específicas, mas falhas em apresentação pessoal: Hoshino respondeu "Olho, sorriso, pergunta aberta."; Lilith não informou seu nome. Portanto, **não homologar identidade** com apenas quatro perguntas e seis exemplos fixos de validação.

O trainer 9B usou NF4/LoRA, offload visual, embeddings na CPU e saved-tensor hooks. O offload v0.9.5 voltou a transferir embeddings grandes na GPU via hooks do Accelerate e OOM. A correção exige **arquitetura de memória diferente**, não só diminuir `max_length` ou aumentar clock. O professor 35B não é fonte obrigatória de treino nem substitui estes modelos.

### Modos no menu

- **Diagnóstico: 2 atualizações LoRA** = smoke de compatibilidade, verifica forward, backward e otimizador; não equivale a checkpoint final estável.
- **Treinar LoRA com checkpoint** = treino cronometrado, avaliação amostrada e saída separada. Duração é teto; antes de declarar concluído, confirmar arquivos e reload.
- Presets devem ser medidos **por modelo, entidade, corpus, arquitetura, driver e hardware**; rank 8 no 0.8B não implica rank 8 ideal para 4B/6B/7B/9B.
- Evitar diversos iniciadores paralelos, duplicação de código e reabertura automática do antigo agendador 9B.

## 7. Checkpoints, candidatos e versões estáveis

A v1.6.2 foi **instalada localmente em 12/10/2026**; seis testes passaram. Seu `treino_nf4_curto.py` foi modificado para salvar checkpoints LoRA a cada **25 updates**, com estado de otimizador, e `versionamento_lora.py` foi adicionado. Instalador registrado com backup `laboratorio-local/backups/lab-versionamento-v162-20261012-165110-79532112`.

Contrato pretendido:
1. `base/original`: só leitura; checksum/revisão conhecida.
2. `runs/<id>/checkpoints/passo-N`: LoRA + optimizer + estado necessário para posterior retomada, gravados atomicamente.
3. `runs/<id>/candidate`: adaptador final e provenance, completo porém **não estável**.
4. `stable/<entity>/<model>`: referência versionada promovida após reload e avaliação independente; rollback para o estável anterior sem reescrever a base.

**Limites comprovados:** a suíte local simulou escrita/restauração de estrutura, mas **não foi executado um novo treino real Hunyuan com checkpoints v1.6.2**; a verificação posterior respondeu `Nenhum treinamento Hunyuan encontrado`. Retomada exata de optimizer/scheduler, promoção para estável, comparador e rollback em produção **ainda não estão homologados**. Codex deve provar isso em execução real e verificar que os nomes reais de campos/caminhos correspondem ao código local.

## 8. Professor MoE 35B — pipeline, falhas e qualidade

Arquitetura: `professor_moe.py` + `professor_schema.py` + `professor_auditoria.py` + `llama-server` Vulkan, isolados da Central. Etapas:
1. Selecionar corpus **train** ou histórico previamente autorizado; criar snapshot JSONL com entidade e hash SHA-256.
2. Preparar trabalho sem carregar GPU; quando autorizado, ligar professor Vulkan.
3. Gerar **cenários novos**, não copiar perguntas/respostas originais nem inventar fatos pessoais; preservar o vínculo com o `source_id`.
4. Checar esquema, evidência, finish reason, repetição, cópia literal/semântica e política da entidade; salvar progresso por lote.
5. Apresentar propostas ainda não aprovadas e permitir revisão/exclusão de itens, mantendo trilha de auditoria.
6. Somente exemplos explicitamente aprovados podem formar dataset **derivado de treino**. Nunca mudar conjuntos originais de validação/teste. Não aplicar automaticamente a um LLM da Central.

Evidência real:
- Trabalho Hoshino `f2c50100a69a48c1`: 12 evidências de v3 train; professor standard gerou **6 exemplos**; **todos os seis** foram detectados como cópias de respostas do train; estado `needs_revision`; nenhuma exportação aprovada.
- Lote Alistair de 40 exemplos no modo anterior: abortou em `1.800 max_tokens` após vários minutos.
- v1.5.1 modo de qualidade máxima dinâmico, 40 casos Lilith: lotes de 4, `reasoning_on=True`, até 3.584 tokens de saída; execução ultrapassou **80 min**; o log mostra no lote 3/10 tentativa 2 `max_tokens/finish_reason`, geração ~4,5 tokens/s; repetir o lote longo consumiu tempo sem resolver a truncagem.
- v1.6 instalado posteriormente: modo máximo único no menu; ideia de 2 evidências por lote, teto de 2.048 tokens, uma tentativa inviável interrompida, janela 60 min e preservação de lotes anteriores **para diagnóstico, não para exportação**. A execução real bem-sucedida deste novo fluxo **não foi comprovada**. Não chamar "qualidade máxima" de garantia de bom resultado.

### Otimização exigida

Medir sucesso por **exemplos aceitos e inéditos por minuto**, não somente tokens/s. Priorizar pedidos pequenos, JSON conciso, finish reason explícito e interrupção quando a saída estiver sendo consumida por raciocínio/repetição. Decidir empiricamente quando thinking on/off melhora a aceitação; contexto dinâmico significa ajustar ao material necessário, **não** aumentar tudo para 10k sempre. Persistir sucesso de cada lote antes de tentar o seguinte; retries devem mudar a causa (prompt, saída, formato) em vez de repetir cegamente. Sem exportar respostas copiadas ou JSON truncado.

Acesso ao histórico: snapshots previamente curados e autorizados, **não** leitura automática de bancos de memória da produção. Os exemplos descartados podem ser removidos da proposta ativa; nunca apagar treino original nem destruir auditoria para "aproveitar" um trabalho.

## 9. Interface e estado dos patches

Porta local do painel de laboratório: tipicamente `http://127.0.0.1:8788` (painel legado usava 8787). Interface baseada em `laboratorio/painel.py`, `laboratorio/web/index.html`, `app.js` e `style.css`; servidor usa validação de origem e confirmação para ações. **Testar no Firefox após mudanças**, não somente compilar JS.

Histórico relevante:
- v1.0: auditoria e presets; quatro tentativas 0.8B inicialmente rejeitadas porque runner barrava `vision_config`.
- v1.2: runner 0.8B multimodal corrigido, professor mais restrito por entidade, probes 4B/6B/7B.
- v1.3/v1.3.1: menus de "treino 10 min" e professor 27B legados; experiência ruim e redundante.
- v1.4: catálogo real de pesos, um único Treinamento, treino cronometrado 4B/6B/Hunyuan 7B, status explícito OOM 7B/9B. Houve erro JS `textContent` ao atualizar elemento HTML não existente.
- v1.5: instalador rejeitado devido a SHA de `professor_moe.py` divergente; não instalado.
- v1.5.1: compatibilidade corrigida, curadoria dinâmica e controles de proposta, instalada conforme capturas.
- v1.6: legados retirados da interface, Qwen2.5-7B HF/GGUF reunidos em cartão, escolha de curadoria inferior removida, corpus principal por entidade; instalação local concluída. **Suíte do pacote: 8 testes passaram, 2 deram erro por fixture da v1.5.1 ausente**; isso precisa ser corrigido sem reverter os arquivos instalados.
- v1.6.2: checkpoint a cada 25 updates instalado; **não muda a interface**, seis testes locais aprovados.

Pontos de UX ainda relevantes para Codex: deixar um único fluxo operacional por objetivo, esconder legados em documentação; catálogo distinguir presente/removido/test-only; não exibir Qwen2.5 GGUF removido; operação atual deve casar com entidade/modelo selecionados; professor única qualidade de produção, status de lotes e exclusão de propostas; erros de backend claramente visíveis sem falsos "completed".

## 10. Integração com a Central principal

Código-base: `iniciar_entidades.py` com supervisor e serviços por entidade; `app/config.py` com configuração por identidade; `app/core/central_control.py` e `app/ui/central_native.py`/`app/ui/control.js` para operação e modelo. No GitHub remoto essa parte está defasada em relação à instalação local de modos Original/Neural 9B: **inspecionar o checkout atual antes de modificar**.

Objetivo:
- Laboratório na Central como **acesso ao mesmo painel/unidade lógica**, não uma segunda implementação com estados concorrentes.
- Catálogo completo de modelos locais, modelos não homologados visíveis com razão; 4B = Alistair, 9B = Hoshino/Lilith; 6B/7B bases experimentais.
- Alternar **Original** / **Adaptado estável** por entidade, somente após homologação e momento seguro de sono/desligamento; manter identidades, memórias, workspaces, configurações originais e opções de rollback.
- Evitar que um LoRA HF seja confundido com GGUF Ollama. Homologar loader/adapters/conversão, config de visão e tokenizer por arquitetura/revisão.
- Nenhum treino pode promover automaticamente um adaptador a executor principal; todo candidato precisa passar avaliação separada.

## 11. Ideia de automação do laboratório e sessão noturna

### Papel do seletor de presets

O sistema deve descobrir a configuração que funciona **naquele modelo + máquina**, guardar resultados de probes reais (tempo, VRAM, memória reservada, falhas, loss em holdout, estabilidade após vários updates, checkpoint/reload), comparar alternativas e recomendar um preset reproduzível. Não confundir ranking do benchmark de quatro passos com qualidade de personalidade. Se nenhuma configuração couber, registrar bloqueio e sugerir opção de hardware/offload mensurável; não inventar sucesso.

### Sessão "vou dormir", explicitamente autorizada

O usuário define uma **janela de início/fim** e autoriza somente quando disser que ficará dormindo. O orquestrador usa os controles existentes do supervisor, não mata indiscriminadamente processos:

1. Inventariar GPU, CPU, RAM, VRAM/GTT, disco, serviços e jobs; se houver atividade de terceiros/jogos ou outro treino, não iniciar.
2. Solicitar parada cooperativa de Hoshino, Lilith e Alistair, aguardar persistência de memória/estado e confirmar que as entidades ficaram inativas. Guardar quais estavam rodando.
3. Priorizar a ação autorizada: auditar dados e resultados, gerar material novo pelo professor, revisar automaticamente apenas defeitos objetivos e preparar propostas **não aprovadas**, ou treinar **somente** se houver corpus já aprovado e preset homologado para a arquitetura.
4. Executar um modelo por vez; aplicar tempo-orçamento realista (professor 35B ~4,3–5,4 tok/s); registrar progresso, decisões, VRAM e motivos de parada; parar na hora prevista e persistir.
5. Encerrar professor/treinador com saída limpa; restaurar somente entidades previamente ativas, sem modificar seus modelos originais; entregar relatório de resultado/erros na Central.

Separar **agenda** de **permissão**: agendar a janela não inicia ação destrutiva por si; o consentimento contextual "vou dormir" autoriza a sessão solicitada. Notificações e plano podem ser configuráveis. Não afirmar que essa automação já está implementada: até a v1.6.2 o modo noturno integrado ao supervisor **permanece ideia/pendência**. O antigo orquestrador noturno 9B está suspenso/obsoleto e não deve ser reativado automaticamente.

### Quando treinar?

A decisão deve considerar corpus realmente novo e aprovado, desempenho/regressão do adaptador estável anterior, orçamento de GPU/tempo, ganhos esperados e teste de qualidade. Curadoria que só copia exemplos não justifica novo treinamento. Pode ser correto **não treinar** numa sessão noturna.

## 12. Plano de trabalho para Codex: executar e comprovar

**P0 — sincronizar e estabilizar**: inspecionar arquivos locais e branch GitHub antes de sincronizar; preservar patches instalados; consertar os 2 testes da v1.6 que dependem de fixture externa; mapear módulos, processos e caminhos; confirmar v1.6.2, artefatos e jobs reais; atualizar documentação baseada no código e publicar na branch de revisão.

**P1 — fechamento da UI/professor**: catálogo sem duplicatas e sem legado, uma aba Treinamento; corpus principal por entidade; qualidade máxima de curadoria sem modos redundantes; professor por lotes com progresso, stop, orçamento de tokens e salvamento parcial seguro. Testar geração pequena real e verificar novidade, esquema, tempo e aprovação, inclusive falhas, antes de 40 casos.

**P2 — treino e estabilidade**: validar 4B com checkpoint/reload; Yi 6B e Hunyuan 7B com treino de minutos/checkpoints (confirmar RoPE Hunyuan); resolver o OOM do Qwen2.5-7B e Qwen3.5-9B por engenharia de memória/arquitetura, com múltiplos updates e validação antes de treino longo. Se inviável com 8 GiB, demonstrar o limite e deixar execução original intacta.

**P3 — versionamento e Central**: base imutável, checkpoints recuperáveis com optimizer/scheduler, candidato isolado, avaliação completa e promoção/rollback de estável; integrar painel/estado à Central sem duplicar runners; opção de execução Original / Estável só depois de comprovar compatibilidade.

**P4 — automação supervisionada**: implementar primeiro simulação seca e testes de coesão do supervisor; depois janela noturna explicitamente autorizada, preflight de recursos, sono/restauração cooperativos, seleção medida de presets, professor, treino condicional, relatórios e término na janela.

**P5 — higiene e publicação**: inventário final, eliminar somente sobras confirmadas (incluindo verificar professor 27B e referências), revalidar Git ignore/segredos, atualizar README e manual, rodar regressões e testes de integração; submeter código atualizado na branch/PR, sem introduzir pesos e dados privados.

### Critérios objetivos de conclusão

- Treino/reload/checkpoint para 4B/6B/Hunyuan-7B realmente testados; 7B Qwen2.5 e 9B homologados ou limitação técnica documentada com evidência, sem mascarar falhas.
- Propostas inéditas do professor, auditáveis e potencialmente aprováveis; exportação somente após revisão.
- Um menu de treinamento confiável, documentação única, sem inconsistência entre estado de disco, jobs e UI.
- Presets baseados em resultados reais; execução noturna supervisionada testada com simulação e hardware ocioso, sem perturbar processos de terceiros.
- Pesos/identidades originais preservados e separação rastreável entre base, checkpoints, candidato e estável.
- Código/docs sincronizados com o GitHub após validação; registrar o commit e as pendências restantes.

## 13. Orientação rápida para o operador

- Para consultar o painel: `cd "$HOME/hoshino e lilith" && python3 -m laboratorio.labctl serve --port 8788`, somente se não houver instância ativa.
- Para inspecionar o professor sem GPU: `python3 -m laboratorio.professor_moe status`.
- Para inventário de modelos sem GPU: `python3 -m laboratorio.probes_arquiteturas plan`.
- Para medir presets 0.8B, os relatórios já estão em `laboratorio-local/controle-laboratorio/presets-auto/`; isso não obriga novos treinos.
- Para o Codex: **não partir do README antigo nem reinstalar ZIPs em sequência**. Auditoria do estado **local primeiro**, depois editar o código final diretamente, testar, documentar e sincronizar.

## 14. Consolidação v1.7 — execução Codex em 12/10/2026

Código local preservado, versionado e reconciliado com a branch remota sem
substituir os patches v1.6.2. Um runner NF4/QLoRA e uma seção Treinamento;
professor 35B com pipeline único de lotes, fit e novidade. Runners/timer antigos
não iniciam novas cargas; documentos e evidências históricas continuam legíveis.

Os cinco modelos completaram treino curto real na RX 6650 XT. O OOM do perfil
anterior não foi "corrigido" alterando testes: houve updates/validação/save na
AMD. Recargas completas de 4B, Yi6B, Hunyuan7B, Qwen2.5-7B e 9B foram executadas;
respostas truncadas/extração de thinking mantêm a homologação bloqueada. O 9B
exigiu correções de SDMA, recarga LoRA e gestão de cache: avaliação completa
131/104 e duas respostas terminadas, pico físico 7,007 GiB, margem preservada.
Lilith também treinou separadamente no 7B, sem mistura de corpus/adaptador.
Falhas anteriores permanecem no relatório, sem esconder interrupções por VRAM.

Retomada Alistair 2→4 foi comparada com treino contínuo 0→4: os 496 tensores
LoRA foram exatamente iguais. Stop pela API real terminou como
`cancelled_checkpointed`, após o update em curso. Checkpoints contêm RNG,
otimizador, posição, hashes e corpus/base/preset vinculados.

Professor 35B gerou dois pares inéditos completos, ~22,3 tokens/s neste workload,
sem autorização de treino. Um lote maior foi recusado por cópia e seus parciais
foram preservados. Cortes de campos por gramática foram corrigidos e dois pilotos
novos completaram 2/2. O último servidor foi autenticado com chave efêmera só
em memória/ambiente; acesso sem chave recebeu 401. Filtro técnico não aprova
personalidade nem curadoria humana. Lote final de dez depois dos ajustes terminou
5/5 batches e 10/10 pares completos em 165,79s, mas foi reprovado por categoria
única; ficou `needs_revision`, sem exportação/treino. Naturalidade segue pendente.

Sessão noturna integrada ao supervisor, com autorização contextual, janela,
sono/drenagem cooperativos e restauração seletiva. Validada em testes isolados;
uma noite real com entidades de produção **ainda não foi homologada**. Recarregar
a Central cooperativamente antes do primeiro uso do supervisor atualizado.

Nenhum modelo foi baixado/apagado ou aplicado à produção, nenhum banco mental
foi migrado ou limpo, nenhum dado novo do professor foi treinado sem aprovação.
GPU concorrente/cloud continuam desativados. Resultados de minutos não aprovam
treino prolongado. Artefatos privados permanecem fora do Git; detalhes e contagens
finais estão no relatório de consolidação.
