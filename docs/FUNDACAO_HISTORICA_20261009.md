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
