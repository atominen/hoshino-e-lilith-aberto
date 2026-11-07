# Áudio no aplicativo único — plano

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Central única com fontes de áudio isoladas e atenção individual, seguida do teste Minecraft autorizado.
**Architecture:** PipeWire owned routes + gerenciador dentro do AudioService; runners clientes do backend e painel Qt existente.
**Tech Stack:** Python, PipeWire/PulseAudio, Qt5, HTTP loopback autenticado, ASR/RM existentes.
**Spec:** `docs/superpowers/specs/2026-10-26-audio-unificado-design.md`.

## Global Constraints

- Mesma instalação/branch, sem outro ambiente, sem mover/apagar pesos ou dados.
- Uma captura/transcrição por fonte, até4 fontes,45s por trecho, uma pendência por fonte.
- Não mudar áudio padrão, reprodução original, permissões ou o backend ASR ativo.
- Identidades separadas, origem factual, sem mensagens fabricadas nem atribuir áudio de app ao humano.
- Só processos próprios; sem replay incerto; todos recursos pertencem à Central.

## Review Focus

- Object.serial/PID reutilizado nunca captura outro app (Task1).
- Fechar/ignorar/revogar autorização durante inferência não publica resultado tardio (Task2).
- Dois ouvintes da mesma fonte não duplicam captura/ASR (Task2).
- UI troca entidade enquanto resposta HTTP chega: não aplicar estado ao destinatário errado (Task3).
- Encerramento falho não dispara duplicata ou fallback privado (Tasks1–3).

### Task 1: Inventário e rotas próprias
**Files:** `app/core/audio_sources.py`, novo `app/core/audio_routes.py`, novo teste `testes/test_audio_listening.py`.
- [x] RED seleção factual e stream removido/reciclado; rota mantém links originais.
- [x] Implementar inventário enriquecido e loopback/captura de processos próprios, sem efeitos no import/GET.
- [x] GREEN; ensaio local sintético de isolamento/limpeza; commit.

### Task 2: Escuta compartilhada e integração dos runners
**Files:** novo `app/core/audio_listening.py`, novo cliente, `audio_service.py`, `social/escuta.py`, `iniciar_entidades.py`.
- [x] RED compartilhamento, origem desconhecida, atenção individual, revogação/término tardio e limites.
- [x] Reutilizar fila ASR/RM, observações voláteis e endpoints autenticados; ligação no supervisor/encerramento.
- [x] Ferramentas usam serviço real na execução supervisionada; sem ASR privado de fallback.
- [x] GREEN regressões focadas e commit.

### Task 3: Painel na Central existente
**Files:** novo `app/ui/native_listening.py`, `central_native.py`, contratos Qt/HTTP e documentação.
- [x] RED seleção por entidade, estado real, resposta obsoleta e controle de atenção.
- [x] Integrar aba Fontes e atenção, sem outro executável, mantendo modos Comando/Detecção.
- [x] GREEN, suíte inteira, passe RED→GREEN para Important; commit/aplicar. Revisão independente única foi parcial por limite do revisor, conforme relatório e ledger; não há aprovação independente integral.

### Task 4: Minecraft e validação conjunta
**Files:** ponte/ferramentas/contratos existentes e relatório novo do ensaio.
- [x] Verificar Minecraft1.16.5Fabric porta40601 (alvo atualizado pelo humano) e bancada/forno; corrigir lacunas mecânicas com RED→GREEN. Bancada/forno cobertos offline; prova de fabricação no mundo ainda pendente.
- [x] Reconciliar processos/jobs/leases, abrir mesma Central e despertar Lilith pelo supervisor.
- [ ] Objetivo progressivo e RP identificado como teste, decisões pelo LLM e evidências no mundo.
- [ ] Registrar inventário/equipamento/recibos, intervenções e impedimentos reais; não chamar parcial de aprovado.
