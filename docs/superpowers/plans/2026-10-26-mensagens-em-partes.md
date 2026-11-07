# Mensagens em partes — plano

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Um turno por sequência de mensagens digitadas, após2s de silêncio, com cada envio preservado.
**Architecture:** Quietude conferida no barramento persistente; batching no worker já existente. Sem outro scheduler/fila.
**Tech Stack:** Python, asyncio, SQLite, barramento existente.
**Spec:** `docs/superpowers/specs/2026-10-26-mensagens-em-partes-design.md`.

## Global Constraints

- Janela2s confirmada; até20 fragmentos por lote, sem truncar/excluir excedentes.
- Somente mensagens digitadas do usuário no localhub, mesma entidade/escopo/sessão.
- Voz, Discord, entidades, interrupções reais e efeitos incertos preservam seus caminhos.
- Instalação/branch atuais por preferência humana; dados e alterações alheias preservados.

## Review Focus

- Último fragmento fora da página de20 também prolonga a espera (Task1).
- Voz/salas/sessões/entidades distintas nunca se fundem (Tasks1/2).
- Envelope ainda aguardando não pode ser marcado entregue/lido (Task1).
- Corrigir intenção antes do turno conserva recibos sem executar pedido superado (Task2).
- Fragmentos chegados durante inferência aguardam novo turno e preservam objetivo ativo (Task2).

### Task 1: Quietude no barramento

**Files:** novo `app/core/conversation_bursts.py`, `app/core/interentity.py`, novo `testes/test_mensagens_partes.py`, catálogo.
**Interfaces:** `typed_key(message)` e `stable(message,latest_at,now,seconds)`; `inbox(...,settle_text_seconds=0,now=None)` retorna `_text_burst_ready` somente para envelopes que cumpriram quietude.

- [ ] Testar limite de2s, retomada, último fora de20, entrega pendente, voz e isolamento com SQLite real temporário; observar RED.
- [ ] Implementar consultas sobre o barramento existente e pure helpers sem I/O no import.
- [ ] Rodar grupo novo, obter GREEN e commit.

### Task 2: Turno agrupado e entrega

**Files:** `app/main.py`, `testes/test_mensagens_causalidade.py`, documentação.
**Interfaces:** leitor pede quietude2s; worker consome consecutivos com a mesma `typed_key`, até20, sem segunda espera. Snapshot e recibos continuam por IDs reais.

- [ ] Testes RED de um turno/uma resposta com todos IDs, fronteiras de escopo/modalidade/sessão, correção e mensagens durante inferência.
- [ ] Integrar e rodar regressões focadas; revisão independente do intervalo.
- [ ] Corrigir Important com RED→GREEN, rodar suíte integral, documentar e aplicar localmente quando apropriado, sem despertar entidades por esta etapa.
- [ ] Commit e remover somente workspace desta etapa depois de preservar evidências.
