# Transcrição ao vivo — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Prévia real durante a fala e um único envio depois de 2000 ms de silêncio ou liberação do comando.

**Architecture:** O cliente mantém uma fala identificada e uma fila limitada de instantâneos/trechos definitivos; a fila de áudio e o ASR persistente existentes reconhecem os arquivos. O servidor valida a origem composta antes do envio final. Prévias nunca são mensagens de conversa.

**Tech Stack:** Python, QtWidgets, PCM mono 16 kHz, faster-whisper existente, WorkQueue/RM existentes.

**Spec:** `docs/superpowers/specs/2026-10-25-transcricao-ao-vivo-design.md` (aprovada pelo usuário).

## Global Constraints

- Instalação atual e branch atual, por preferência humana; preservar alterações alheias.
- Sem novos pesos, dependências, processos de inferência paralelos, cloud, quota de voz ou AEC.
- Silêncio de 2000 ms; instantâneos no máximo a cada 1 s; 45 s por trecho físico.
- Uma solicitação em processamento; uma prévia recente; até quatro trechos definitivos em espera.
- Envio automático somente com a opção existente habilitada; um envio final por fala.
- Erro/aceite incerto não autoriza retry; descarte e troca de contexto invalidam callbacks.

## Review Focus

- Silêncio cruzando 45 s e liberação exatamente no limite não enviam fala incompleta (Task 1/3).
- Aceite HTTP atrasado após descarte/troca de contexto não envia à conversa errada (Task 3).
- Prévias e trechos de outra fala/sessão não podem compor uma origem final (Task 2).
- Edição humana e seleção sobrevivem a prévias/resultados finais (Task 3).
- Contenção, erro de prévia e saturação preservam recursos e bloqueiam somente envio incompleto (Tasks 1–3).

### Task 1: Captura e estado de uma fala

**Files:** `app/ui/native_audio.py`, novo `app/ui/native_asr.py`, novo `testes/test_asr_live.py`.

**Interfaces:** Segmenter conserva `feed()->(level,segments)` e expõe eventos com PCM e fim real; `LiveTranscript(entity,session_id,scope,mode,auto_send)` oferece `preview(pcm)`, `seal(pcm,ended)`, `end()`, `take()`, `complete(packet,job_id,result,error)`, `discard()`, `ready()` e `text()`.

- [x] Escrever regressões de silêncio de 2 s, retomada antes dele, corte de 45 s, liberação sem residual, ordem/fila/última prévia, revisão e falha.
- [x] Executar `PYTHONPATH=app:app/ui:testes python -B -m unittest test_asr_live` e observar RED por recurso ausente.
- [x] Implementar segmentação com fim real separado do corte e controlador sem I/O/modelo.
- [x] Reexecutar o grupo até GREEN e registrar no catálogo oficial sem remover entradas alheias.
- [x] Commit da captura/controlador e testes.

### Task 2: Contrato autenticado de prévias e origem composta

**Files:** `app/core/audio_service.py`, novo `app/core/asr_provenance.py`, `iniciar_entidades.py`, `testes/test_asr_live.py`, `testes/test_audio_service.py`.

**Interfaces:** `submit_transcription(...,utterance=None)` valida metadados `{id,part,revision,preview,session_id,scope}`; `get()` devolve esses metadados. O endpoint aceita JSON limitado no parâmetro `utterance`. `audio_origin()` aceita `audio_job_ids` ordenados e valida todas as origens definitivas, preservando `audio_job_id` para revisão semântica existente.

- [x] Testar recusa de prévia como origem, troca de entidade/fala/sessão/escopo, duplicação/lacuna/ordem, legado e agregação de sinais acústicos; observar RED.
- [x] Implementar validação fechada, metadados duráveis e prioridade inferior das prévias na fila existente.
- [x] Testar HTTP real em fixture, origem composta e regressões ASR/TTS; obter GREEN.
- [x] Commit do transporte/origem e testes.

### Task 3: Cliente Qt e envio único

**Files:** `app/ui/central_native.py`, `app/core/central_control.py`, `testes/native_central_contracts.py`, `testes/test_asr_live.py`.

**Interfaces:** cliente captura guarda `LiveTranscript`; os jobs referenciam controlador e packet. Área readonly mostra hipótese; confirmação usa `audio_job_ids`. Testes de microfone continuam no caminho legado sem prévias/envio. Preferência de silêncio atualizada para 2000 ms pelo caminho existente.

- [x] Escrever RED Qt para prévia antes de parar, correção sem append, um envio final, descarte/aceite tardio, troca de sala/dia/entidade, rascunho/seleção, erro definitivo e limite físico sem envio.
- [x] Integrar controlador à captura, dar precedência aos definitivos e impedir envio de resultados obsoletos. Preservar fluxo legado de teste e opção de envio automático.
- [x] Executar contratos Qt e grupos focados de áudio/chat/percepção; obter GREEN.
- [x] Commit da integração Qt e testes.

### Task 4: Revisão, regressões e entrega local

**Files:** documentação de entrega e índice existente.

- [x] Executar `bash rodar_testes.sh`, conferir desfecho completo e registrar falhas sem suprimir grupos.
- [x] Revisão independente do intervalo desta implementação; corrigir problemas importantes com RED→GREEN e regressões.
- [x] Atualizar documentação, aplicar preferência de 2 s, reabrir somente após encerramento reconciliado; não acordar entidades que dormiam.
- [x] Verificar health, estado e UI. Registrar limites: testes offline não medem ASR físico/latência.
- [x] Commit da entrega e arquivar/remover somente o workspace desta etapa.
