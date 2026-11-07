# Texto contínuo no chat — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mostrar a resposta de Hoshino/Lilith enquanto é gerada, numa única bolha, preservando a posição de leitura.

**Architecture:** Aproveitar o callback cumulativo já existente do Ollama para publicar uma prévia limitada no diário de jobs existente. Uma consulta HTTP compacta e autenticada leva apenas prévias do destinatário/sala/sessão corretos à Central nativa; o envelope final continua pelo caminho atual e substitui a prévia.

**Tech Stack:** Python 3.13 do projeto, SQLite existente, HTTP autenticado existente e PyQt5 no Python 3.12 do sistema. Sem dependências novas.

**Spec:** `docs/superpowers/specs/2026-10-24-texto-continuo-chat-design.md`

## Global Constraints

- Texto surgindo continuamente, não por frases completas.
- Manter a posição da leitura quando ele rolar para mensagens antigas.
- Não simular digitação de uma resposta já pronta.
- Não alterar modelos, pesos, personalidades, memórias, permissões, treino ou configurações de áudio.
- Não criar uma segunda geração para produzir a prévia; não mudar TTS/ASR nem o app Xbox.
- Preservar mudanças preexistentes, incluindo os trechos já modificados em `testes/catalogo.py`.
- Código carregado não será editado no checkout vivo: reconciliar processos e trabalhar isoladamente na execução; carregar mudanças somente após fechamento cooperativo e ausência de jobs/leases incertos.

## Review Focus

- Troca de entidade, sala ou sessão durante uma consulta: uma resposta antiga não deve reaparecer no novo chat (tarefas 2/3).
- Tags internas divididas entre fragmentos e HTML: não vazar raciocínio nem interpretar texto como marcação ativa (tarefas 1/3).
- Final alterado pelo verificador, retry existente ou publicação falha: não duplicar bolhas nem declarar conclusão prematuramente (tarefas 1/2/3).
- Sala global com Hoshino/Lilith gerando ao mesmo tempo e sessões individuais diferentes: mostrar ambas somente no dia/sala corretos (tarefas 1/2/3).
- Fila ocupada e usuário lendo/copiando texto antigo: manter atualização limitada, seleção/rascunho/foco e posição de leitura, sem multiplicar requisições (tarefas 1/3).

---

## Arquivos e responsabilidades

- Criar `app/core/text_stream.py`: estado incremental, limites, filtragem e projeção de prévias.
- Alterar `app/core/interentity.py`: referência segura ao envelope físico em processamento.
- Alterar `app/core/job_bus.py`: filtro opcional de tipo em `status`, sem quebrar chamadas atuais.
- Alterar `app/main.py`: fan-out do callback, cancelamento e vínculo com publicação final.
- Alterar `iniciar_entidades.py`: consulta compacta autenticada, sem inferência.
- Criar `app/ui/native_chat_stream.py`: mesclar prévias e atualizar a leitura sem alterar áudio.
- Alterar `app/ui/central_native.py`: consultar e renderizar prévias no chat atual.
- Criar `testes/test_texto_streaming.py`; ampliar `testes/native_central_contracts.py` e registrar o novo grupo em `testes/catalogo.py`.

### Task 1: Prévia limitada, com origem física e sem conteúdo interno

**Interfaces:**
- `interentity.processing_envelope(entity: str) -> dict | None`: ler o envelope físico apontado por `processing_message`; retornar somente `message_id`, remetente/destinatário, `chat_scope`, `conversation_session_id` e `room_day`. Recusar origem inexistente, privada ou incompatível; não confiar em metadados fornecidos pelo modelo.
- `job_bus.status(active_only=False, limit=50, *, kind=None) -> list[dict]`: filtro SQL parametrizado por tipo antes do limite, preservando a reconciliação atual.
- `TextStream(entity, channel, *, validator, cancelled, request_id='')`: aceitar apenas Hoshino/Lilith em conversa humana localhub com envelope verificado.
- Métodos `push(text: str) -> None`, `finish(text: str) -> None`, `commit(message_id: str) -> None`, `stop(reason: str, *, discard_text=False) -> None`.
- `text_stream.snapshot(entity: str, session_id: str, chat_scope: str) -> dict`: retornar `streams`, com no máximo 8 prévias, filtradas antes da projeção.

- [ ] **Step 1: Criar testes vermelhos em `testes/test_texto_streaming.py`.** Usar diretórios temporários e patches dos caminhos de bus/jobs; rede/inferência reais proibidas. Caso mínimo:

```python
def test_prefix_is_available_before_sentence_and_completion(self):
    stream = self.stream_for_physical_input('hoshino')
    stream.push('Olá, estou')
    row = job_bus.get(stream.id, 'hoshino')
    self.assertEqual(row['status'], 'running')
    self.assertEqual(row['details']['text'], 'Olá, estou')
    self.assertFalse(row['details']['final'])
```

Adicionar casos com relógio simulado: primeiro prefixo imediato; no máximo uma escrita a cada 100 ms depois dele; flush em `finish`; texto limitado a 12000 caracteres; `finish` não conclui sem recibo; terminal não reabre; cancelamento não pede retry; reescrita de prefixo invalida; chamadas de ferramenta não viram conteúdo.

Testar tags `<think>`, `<analysis>` e marcadores internos divididos em vários fragmentos: reter sufixos que possam iniciar marcador, descartar prévia contaminada e nunca publicar o conteúdo interno. O `validator` existente precisa aprovar cada prefixo efetivamente exibido; falha conserva o fluxo final existente, não relaxa o gate.

Testar origem forjada/ausente, sessão estrangeira, chat direto versus global, dois produtores globais com sessões individuais diferentes, sala de outro dia e mais de 200 jobs de outros tipos. `snapshot` não pode carregar histórico mental nem consolidar prévias como memória.

- [ ] **Step 2: Rodar e conferir falha por interface ausente.**
  `PYTHONPATH=app:testes compartilhado/ambientes/principal/bin/python -B -m unittest test_texto_streaming -v`
- [ ] **Step 3: Implementar as interfaces acima.** Usar `kind='llm_text'`, uma linha atualizada por stream, revisão inteira crescente e envelope imutável. Campos projetados: `id`, `entity`, `status`, `text`, `revision`, `turn_id`, `input_ids`, `reply_to`, `chat_scope`, `conversation_session_id`, `room_day`, `final_message_id`, `reason`. Nunca copiar `thinking`, prompts ou argumentos. Estado de geração deve ser distinto de publicação confirmada.
- [ ] **Step 4: Rodar o mesmo grupo e conferir todas as asserções verdes.**
- [ ] **Step 5: Commit apenas deste entregável e dos testes/registro adicionados.** Não incluir mudanças preexistentes do catálogo no commit.

### Task 2: Ligar o turno real à consulta compacta

**Interfaces:**
- Consumir `TextStream` e `snapshot` da tarefa 1.
- `Supervisor.chat_streams(entity, session_id, chat_scope) -> dict` e GET autenticado `/api/chat/streams?entity=...&conversation_session_id=...&chat_scope=direct|global`.
- Acrescentar `text_streams` aos metadados do envelope final localhub, contendo os IDs das prévias substituídas, sem mudar `speech_streams`.

- [ ] **Step 1: Acrescentar testes vermelhos ao grupo novo.** Fragmentos de transporte simulados devem aparecer antes do frame `done`; campos `thinking` e frames de ferramenta nunca entram no callback público. Voz desabilitada não impede texto. Um turno usa exatamente a chamada já existente; não há inferência adicional.
- [ ] **Step 2: Rodar o grupo e verificar a falha esperada da integração.**
- [ ] **Step 3: Integrar em `app/main.py`.** Usar o contexto de turno atual para manter `text_streams` separado de `streams` de voz. Fazer fan-out do callback cumulativo para os consumidores elegíveis. Invalidar prévias antigas em correção, erro, ferramenta, mudança de resposta ou encerramento. `publicar` continua dono do envio durável; só após `interentity.send` retornar recibo a prévia recebe `commit(message_id)`. Finalizador encerra qualquer prévia que ficou sem recibo.
- [ ] **Step 4: Acrescentar testes HTTP vermelhos.** Sem autenticação: 403; entidade/escopo/sessão inválidos: 400; sessão/sala válida: só sua projeção. Final diferente substitui a prévia por ID; publicação falha nunca vira `done`. Dois pedidos/salas concorrentes não se misturam. Não retornar o texto de `llm_text` na listagem genérica e não filtrada de jobs da UI.
- [ ] **Step 5: Implementar `Supervisor.chat_streams` e a rota em `iniciar_entidades.py`.** Não carregar modelos, consultar memórias ou disparar trabalhos pela leitura. Preservar as demais rotas e seus formatos.
- [ ] **Step 6: Rodar `test_texto_streaming`, `test_voz_streaming` e `test_chat_global`; conferir todos verdes.** Reutilizar as fixtures HTTP isoladas de `test_audio_service`/`test_central_control`.
- [ ] **Step 7: Commit somente do fluxo integrado e seus testes.**

### Task 3: Uma bolha contínua, com rolagem preservada

**Interfaces:**
- `merge_previews(conversation, streams, *, entity, session, scope, read_only=False, query='', before=0) -> list[dict]` em `app/ui/native_chat_stream.py`.
- `update_chat_document(browser, rendered: str) -> None`: conservar leitura/seleção quando fora do fim, seguir crescimento quando no fim; não mudar foco ou rascunho.
- Consumir exclusivamente a projeção da tarefa 2; o renderer existente continua escapando texto como texto, não HTML ativo.

- [ ] **Step 1: Criar testes vermelhos de mesclagem.** Mesma stream/revisão não duplica; revisão anterior não faz texto regredir; envelope final com `metadata.text_streams` remove sua prévia na mesma atualização. Falha/interrupção visível fica marcada como incompleta; conteúdo invalidado por privacidade é removido. Busca, página antiga, arquivo ou sessão/entidade/sala incompatível não recebe prévias. No global, mostrar os dois autores permitidos sem depender da entidade selecionada.
- [ ] **Step 2: Criar testes Qt vermelhos em `testes/native_central_contracts.py`.** Antes do fim da geração já existe texto visível; um único balão passa a final; texto com HTML é escapado. Ao receber mais texto, verificar posição e seleção de leitura antiga intactas, rascunho e foco intactos; no fim, a barra acompanha. Troca de chat invalida callbacks anteriores.
- [ ] **Step 3: Implementar os helpers e integrar à Central.** Timer de UI de 250 ms, somente na página Conversa e sessão corrente sem filtros; no máximo uma consulta de prévias em voo. Não chamar o pesado `/api/state` nessa frequência. Preservar o timer existente de 2 s e o fluxo de TTS. Cache local limitado aos 8 streams projetados, com ordenação por revisão e guarda `chat_generation`; limpar ao trocar de sessão/backend ou encerrar. Nenhuma animação de digitação.
- [ ] **Step 4: Testar indisponibilidade e fila ocupada.** Uma consulta pendente não cria outra; erro não repete envio, não desperta entidades nem sintetiza áudio; resposta antiga de `/api/state` não remove prévia mais nova. Encerramento cancela somente consultas próprias e não mata jobs de entidades.
- [ ] **Step 5: Rodar os grupos `test_texto_streaming` e `test_central_refinamento`.** O segundo executa os contratos Qt reais com transporte/processos simulados. Conferir o total e falhas, sem chamar isso de teste do desktop real.
- [ ] **Step 6: Commit da interface e seus testes.**

### Task 4: Verificação conjunta e entrega delimitada

- [ ] **Step 1: Rodar os grupos focados completos.**
  `PYTHONPATH=app:testes compartilhado/ambientes/principal/bin/python -B -m unittest test_texto_streaming test_voz_streaming test_chat_global test_central_refinamento -v`
- [ ] **Step 2: Conferir registro e imports.**
  `compartilhado/ambientes/principal/bin/python -B testes/catalogo.py`
- [ ] **Step 3: Conferir diff e preservação.** `git diff --check`, diffs por arquivo e inventário de mudanças: sem alterações de áudio/modelos/treino/dados reais; mudanças preexistentes não incluídas.
- [ ] **Step 4: Atualizar relatório local `docs/TEXTO_CONTINUO_CHAT_20261024.md`.** Registrar comandos e resultados efetivos, limites e distinção entre ensaio Qt isolado e uso real. Atualizar o estado deste plano com evidências, sem inventar verificações pendentes.
- [ ] **Step 5: Revisão final, de acordo com o método escolhido pelo usuário.** Resolver falhas encontradas e repetir os testes afetados antes de declarar entrega.
- [ ] **Step 6: Carregamento real somente com estado seguro.** Reconciliar Central/processos/treinos/leases atuais. Se houver trabalho incerto, não reiniciar; entregar o código e explicar o impedimento. Fechamento cooperativo e reabertura, quando cabíveis, não devem acordar entidades automaticamente. Não consumir voz/quota nem enviar pergunta artificial às entidades sem decisão de teste correspondente.

## Autorrevisão do plano

As duas escolhas humanas estão cobertas na tarefa 3. Origem/privacidade e limites
ficam na tarefa 1; publicação confirmada, filtros e falhas na tarefa 2; os cinco
casos do Review Focus têm testes designados. Não há mudança do app Xbox, TTS,
ASR, agrupamento de mensagens ou dados mentais. Identificadores técnicos e
intervalos de 100/250 ms são escolhas propostas do assistente, não requisitos
atribuídos ao usuário.

Estado em 25/10/2026: execução nativa aprovada pelo usuário; implementação,
testes e revisão independente realizados em área isolada. Os quatro achados
importantes da revisão foram corrigidos com regressões RED→GREEN e repetição
da suíte completa (90/91 grupos no worktree; somente a falha antiga do atalho
aceita pelo humano). Após a escolha humana de aplicar localmente, integração
por fast-forward e carregamento real realizados: 91/91 grupos aprovados na
instalação, endpoint novo respondendo e entidades dormindo.

- [x] Tarefa 1 — prévia limitada e origem física.
- [x] Tarefa 2 — geração, publicação e consulta autenticada.
- [x] Tarefa 3 — interface, leitura e seleção preservadas.
- [x] Tarefa 4 — verificação, revisão, correções e relatório.
- [x] Decisão humana de integração e carregamento seguro na instalação real.

Resultados, decisões e limitações: `docs/TEXTO_CONTINUO_CHAT_20261024.md`.
