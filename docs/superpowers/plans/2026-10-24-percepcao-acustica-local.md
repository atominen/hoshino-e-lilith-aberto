# Percepção acústica local — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Perceber sons não verbais pelo microfone em Detecção sem depender de transcrição e sem inventar falas ou autoria.

**Architecture:** Preservar o ASR existente e acrescentar classificador acústico local em CPU. A captura envia janelas PCM curtas, sobrepostas e limitadas; um worker separado evita que uma transcrição demorada bloqueie a detecção. A Central e os canais de percepção existentes entregam eventos com fonte/horário, não mensagens humanas sintéticas.

**Tech Stack:** Python, PCM16/16kHz, QtWidgets/PulseAudio existentes, YAMNet oficial e runtime CPU isolado a verificar antes da instalação.

**Spec:** `docs/superpowers/specs/2026-10-24-percepcao-acustica-local-design.md`.

## Global Constraints

- Apenas Comando e Detecção; ativação explícita e permissão de ambiente existente.
- Sem cloud, GPU concorrente, alteração de LLM/Xbox, mensagens fictícias ou gravação permanente contínua.
- Sem atribuir sons ao usuário ou emoção sem evidência; score não é probabilidade calibrada.
- Sem download no import/runtime; origem/revisão/hash e licença exigidos para aquisição explícita.
- Sem recarga do app em uso que descarte rascunhos/áudio sem confirmação.

## Review Focus

- Risada abaixo do limiar do ASR precisa chegar ao classificador, sem falso texto humano: tarefas1/3.
- Sons curtos na borda das janelas precisam de sobreposição e deduplicação: tarefa2.
- Transcrição/TTS lentos não podem parar a captura nem criar fila ilimitada: tarefa3.
- Voz da própria aplicação não pode ser atribuída ao usuário: tarefa3.
- Revogação de permissão ou troca de entidade não pode entregar resultado antigo à nova destinatária: tarefa3.

### Task 1: Classificador offline e instalação isolada

**Files:** criar `app/core/acoustic_perception.py`, `scripts/preparar_percepcao_acustica.py`, `testes/test_percepcao_acustica.py`.
**Interfaces:** `classify_pcm(pcm: bytes, *, sample_rate: int = 16000) -> dict`; `status() -> dict`; aquisição somente pelo script explícito.

- [x] Escrever testes para ausência/corrupção de modelo, silêncio, PCM inválido e resultados sem texto/identidade inventada; reproduzir falha antes do código.
- [x] Verificar o artefato oficial YAMNet e compatibilidade do runtime CPU com o Python isolado; fixar origem/hash/versão e licença antes de instalar. Se incompatível, registrar impedimento, não instalar bibliotecas no ambiente principal para contorná-lo.
- [x] Implementar carga lazy, limite de threads/entrada e saída de classes/scores, sem rede no runtime.
- [x] Executar os testes isolados e documentar aquisição/recursos sem confundir fixtures com qualidade real.

### Task 2: Janelas contínuas e protocolo do worker

**Files:** criar `app/audio_perception_worker.py`; ampliar `app/ui/native_audio.py` e `testes/test_percepcao_acustica.py`.
**Interfaces:** `AcousticWindows.feed(pcm: bytes) -> list[bytes]`, com janela15600 amostras e avanço7680; worker recebe id/PCM e devolve id/eventos sem armazenar WAV.

- [x] Testar fragmentos ímpares, silêncio, som na borda, buffer limitado e fim/cancelamento; confirmar falhas antes da implementação.
- [x] Implementar janelas sobrepostas independentes do limiar de fala e protocolo com tamanho/timeout limitados.
- [x] Testar execução real do protocolo em fixture, sem microfone/rede, e de-duplicação de um evento presente em janelas adjacentes.

### Task 3: Captura, serviço e percepção nas entidades

**Files:** ampliar `app/core/audio_service.py`, `app/ui/central_native.py`, `iniciar_entidades.py`, `app/main.py`, `testes/test_audio_service.py`, `testes/native_central_contracts.py` e `testes/test_percepcao_acustica.py`.
**Interfaces:** `AudioService.submit_perception(entity, pcm, *, source, capture_id, sequence, playback_overlap) -> dict`; endpoint autenticado `/api/audio/perception`; resultado contém somente fonte/horário/classes/scores e dados de cancelamento. Adaptar o canal existente de percepção, não a entrada de fala humana.

- [x] Testar permissão revogada, resultado atrasado após trocar entidade/escopo, id duplicado, fila saturada e desligamento sem replay.
- [x] Testar captura contínua durante ASR/TTS e marcação de sobreposição da voz própria; não publicar autoria humana nem ordens a partir de eventos sonoros.
- [x] Integrar worker CPU separado, com fila limitada, status explícito e entrega pelo mecanismo existente de jobs/percepção, sem novo banco mental.
- [x] Acrescentar ao painel Áudio disponibilidade/escuta ativa/erros; não criar terceiro modo nem iniciar captura ao abrir o painel.
- [x] Executar testes das rotas, contratos Qt e percepção em fixtures antes de qualquer microfone real.

### Task 4: Calibração, documentação e entrega

**Files:** atualizar `testes/catalogo.py`, `docs/README.md`, `README.md` e relatório datado da percepção acústica.

- [x] Validar em arquivos de referência com origem/licença documentadas: fala, silêncio, risada curta/baixa, gargalhada, ruído e áudio misturado; medir latência, CPU/RAM e falsos positivos/negativos por classe.
- [x] Ajustar os limiares somente com evidência; scores não calibrados não aparecem como porcentagem de certeza.
- [x] Rodar `./rodar_testes.sh`, revisar mudanças e registrar limites, ativação e reversão. Não chamar o microfone real de aprovado sem teste físico consentido.
- [x] Solicitar confirmação antes de reabrir janela em uso ou realizar captura física; não enviar o teste como conversa humana.

## Estado

Plano aprovado pelo usuário em24/10, com execução direta e revisão independente
ao final. O usuário autorizou fechar a Central; trabalho na pasta atual, sem
duplicar pesos/dados. Progresso detalhado no ledger local deste plano. A correção
independente do atalho passou89/89 grupos offline e não depende do detector.

## Decisões de execução e custos

- Pasta atual após fechamento autorizado, não worktree novo: mudanças locais
  ficam nesta árvore; demais alterações anteriores foram preservadas separadas.
- YAMNet/LiteRT CPU isolado em vez de TensorFlow no ambiente principal: falha
  de compatibilidade interrompe o detector, não justifica alterar outros runtimes.
- Deduplicação movida da tarefa2 ao serviço da tarefa3: estado pertence à
  captura; se incorreto, poderia misturar fontes, coberto pelos contratos.
- Alistair recebe percepções no próximo turno normal, sem motor autônomo novo:
  pequeno custo adicional de contexto, sem despertar ou tarefa fabricada.
- Sobreposição com player é suprimida, não eco cancelado: pode perder áudio
  humano simultâneo; não prometer que essa situação foi resolvida.
- Limiar experimental de risada0,10 baseado no ensaio: pode falhar ou gerar
  falsos positivos em ambientes não amostrados; outras classes não recalibradas.
- Hardware deixado fora da revisão: usabilidade física permanece pendente,
  não inferir sucesso de desktop a partir de contratos Qt.
- Generalização deixada fora da aprovação: amostra pequena não garante
  reconhecimento em todo microfone/ruído; limitações publicadas no relatório.

## Revisão e correções

Revisor independente apontou sequência0 ausente da URL e cancelamento perdido
com8 requisições ocupadas. Corrigidos em um passe com RED→GREEN; preservação do
horário na descrição foi promovida a importante e também testada RED→GREEN.
Não houve segunda revisão/reexecução de inferências para esconder um resultado.
Teste físico de microfone/atalho/voz própria não realizado; nenhuma memória ou
modelo de conversa foi resetado ou substituído. Publicação/merge não autorizados
por esta tarefa. As evidências completas da suíte e o commit final acompanham
o relatório da entrega local.

Concluído em24/10:18 testes acústicos,42 testes de refinamento/112 contratos Qt,
42 testes do serviço de áudio; suíte final completa90/90 offline após o passe
de correção. Primeiro commit`f83a1ce`; preservadas alterações pré-existentes
do laboratório/6B sem incluí-las na entrega de áudio. Hardware real pendente.
