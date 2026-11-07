# Voz progressiva básica — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Reproduzir frases antes do fim da resposta, ouvir durante a fala com fones e dar às entidades percepção factual e controle da própria reprodução.

**Architecture:** Reutilizar SpeechStream, jobs, player nativo e ferramentas de voz. Filas limitadas e leases existentes continuam governando os workers, mas esperar novas frases não pode impedir ASR. A reprodução é um estado distinto da síntese, renovado por recibos do player e consultado sem expor conversas privadas de outra entidade.

**Tech Stack:** Python, SQLite, PyQt5, parec/paplay, workers e provedores já instalados.

**Spec:** docs/superpowers/specs/2026-10-25-voz-progressiva-basica-design.md

## Global Constraints

- Na instalação atual; sem outro ambiente, dependências, modelos ou cancelamento de eco.
- Preservar dados e mudanças preexistentes; não usar quota de voz nos testes.
- Texto novo não cancela fala automaticamente; pedidos de parada e decisão contextual continuam possíveis.
- Áudio sintetizado não conta como áudio reproduzido nem prova de audição.
- ASR e síntese precisam avançar sem um bloquear o outro, respeitando os recursos e limites existentes.
- Sem inferência extra por palavra, novo scheduler ou GPU concorrente.

## Review Focus

- Global com Alistair selecionado deve escolher o autor correto, sem expor streams diretos.
- Primeiro stream já encerrado na consulta não pode causar repetição da resposta final.
- Reconexão/callback atrasado não pode reabrir voz nem registrar um estado de reprodução falso.
- Falta de recibo recente e morte do player tornam o estado desconhecido, não speaking permanente.
- Microfone em Comando e Detecção durante reprodução não pode cortar o player ou perder a fala captada.

## Task 1: Frases públicas e encaminhamento nativo

Files: app/core/speech_stream.py, app/ui/central_native.py, testes/test_voz_streaming.py, testes/native_central_contracts.py.
Interfaces: SpeechStream publica chat_scope/room_day/reply_to a partir de processing_envelope; seleção de streams respeita sala e sessão, usa entity real.

- [x] Escrever regressões de global/direto, autor correto e deduplicação.
- [x] Executar e observar falha antes da correção.
- [x] Implementar seleção comum e priorizar stream correspondente à resposta final ainda não falada.
- [x] Verificar grupos de voz e Qt; commit somente dos arquivos deste trabalho.

## Task 2: Percepção e controle da reprodução

Files: app/core/audio_playback.py (novo), app/core/audio_service.py, app/tools/voice.py, app/core/dispatch.py, app/main.py, iniciar_entidades.py, testes/test_voz_basica.py (novo).
Interfaces: audio_playback.snapshot(entity, now=None) projeta frases próprias e somente estado de outros autores; request_stop(entity) anota cancelamento da voz própria; context(entity) fornece resumo ao turno atual. Player informa chunk + evento + progresso limitado, com prazo de validade.

- [x] Regressões de recibos ordenados/idempotentes, estado vencido, falha e privacidade.
- [x] Regressão HTTP: mensagem comum não cancela, pedido explícito cancela somente destinos autorizados.
- [x] Observar falhas; implementar validação/transições, projeção e controles existentes estado_voz/parar_voz.
- [x] Incluir resumo factual no contexto da conversa e manter ferramentas disponíveis nessa conversa.
- [x] Verificar grupos relevantes e commit.

## Task 3: Microfone e processamento sem bloqueio da geração

Files: app/core/work_queue.py, app/core/audio_service.py, app/ui/central_native.py, testes/test_voz_basica.py, testes/native_central_contracts.py.
Interfaces: WorkQueue.get_matching(predicate, timeout) mantém capacidade/contabilidade/prioridade; dois consumidores fixos por tipo compartilham a mesma fila. Leases cpu_audio cobrem chamadas de motor, não espera pelo próximo texto. Áudio captado com fones não é descartado por playback_overlap.

- [x] Regressão ASR conclui enquanto stream aguarda novas frases; limites/cancelamento/close mantidos.
- [x] Regressões Qt: abrir Comando/Detecção não corta voz; fala sobreposta chega ao ASR.
- [x] Observar falhas e implementar o mínimo, preservando limites e liberação de RAM ociosa.
- [x] Verificar grupos relevantes e suíte completa; commit.

## Finalização

- [x] Uma revisão independente final, conforme executing-plans; corrigir problemas importantes com regressões.
- [x] Atualizar relatório e índice com resultados e limites físicos não testados.
- [x] Conferir processos/jobs/leases e reabrir a mesma Central, sem despertar entidades nem gerar voz paga.

Autorização: o usuário aprovou o desenho e pediu execução direta de tudo necessário. A revisão deste plano ocorre durante a execução; não haverá nova rodada de perguntas para escolhas já resolvidas. Sem worktree por decisão humana.
