# Tempo e continuidade observada — 09/10/2026

## Limite desta rodada

Incremento da Fase 2 do plano cognitivo, depois da fundação histórica e das sessões diárias. Não é conclusão do plano inteiro nem validação física prolongada.

Sem novos modelos, bancos, schedulers, sistemas mentais, providers ou capacidades externas. Sem alteração de identidade, personalidade, catálogos afetivos, margens GPU, concorrência ou cloud. Nenhuma entidade acordada, nenhum serviço reiniciado, nenhuma chamada paga, inferência ou download nesta rodada.

## Mapa auditado antes das alterações

- `core/history.py`: relógio local configurável e horários UTC do histórico/diagnóstico. Reutilizado para compatibilidade dos cálculos, sem novo serviço de relógio.
- `mind/affect.py`, `psych_state.py`, `drives.py`, `emotions.py`: estados JSON existentes, leitores de decaimento, satisfação/refratário e projeção visual consumida pela Central/orbes. Eventos afetivos e coeficientes permanecem os mesmos.
- `core/situation.py`: consumido pelo batimento de `main.py`, pelo dispatcher de situação e pelas ferramentas existentes `tempo_em`/`resumo_do_dia`. Usa `estado_mente.situacao` e a tabela existente `activity_sessions`.
- `tools/agenda.py` e `core/kernel.py`: consomem presença para diretivas e contato espontâneo; ausência exige `False`, desconhecido é `None`. Auditados, não substituídos nem editados nesta rodada.
- `bd.agora`, episódios, reflexão, agenda, objetivos e histórico emocional ainda têm consumidores SQL de datas textuais. Não converter esses bancos globalmente para UTC antes de revisar todos os filtros/ordenações.

## Defeitos reproduzidos e correções

### 1. Mistura entre datas com/sem fuso

Antes, humor/estado psicológico/emoções subtraíam datas incompatíveis, lançando `TypeError`. A projeção visual engolia a mesma falha e ficava neutra apesar de existir emoção válida. O refratário dos impulsos devolvia `1.0` ao falhar, permitindo iniciativa imediatamente.

Agora `history.local_datetime` e `elapsed_seconds` normalizam cálculos para instantes UTC. Legado ingênuo usa **somente como aproximação de cálculo** `HOSHINO_TIMEZONE`, padrão `America/Sao_Paulo`. `timestamp_details` continua dizendo que seu fuso original é desconhecido. Nada é migrado ou reescrito por uma leitura.

Novos marcadores JSON afetivos/psicológicos/refratários usam UTC explícito com milissegundos. Zero decorrido é válido. Timestamp inválido, ausente ou futuro retorna duração desconhecida, não sucesso. Nesse caso o refratário bloqueia iniciativa; humor e estado psicológico não são apagados por falha do relógio; emoções de origem temporal inválida não são projetadas como confirmadas.

`clock.unreliable` usa o diagnóstico existente, com operação, entidade observadora e motivo. Não registra o texto do timestamp inválido. Cache limitado a 64 combinações operação/motivo evita um aviso repetido a cada tick; não é coletor nem banco paralelo.

### 2. Inatividade não comprova ausência

Antes, X11 ocioso por 900s produzia `usuario_presente=False`, inclusive quando a pessoa acabara de conversar por voz. Isso podia ativar diretivas `enquanto=ausente` sem prova de ausência.

Agora interação humana recente prevalece. Sem interação recente, teclado/mouse ociosos geram `None`, com base `inatividade_de_entrada`. O evento é observacional (`inatividade_entrada`), não `sumiu`/rejeição/abandono. Atividade do desktop não dispara mais um retorno humano presumido (`voltou`) nem conclui diretivas de ausência por esse caminho. Não foram alterados traços ou intensidades emocionais para esconder o problema.

O teste histórico `test_input_inactivity_is_only_a_private_inference` ainda esperava `False`; foi atualizado para o contrato explícito atual, verificando também que uma diretiva de ausência não é ativada. Não se enfraqueceu a guarda da agenda: `False` explícito continua sendo tratado como ausência pelos consumidores existentes.

### 3. Horas de sono não são atividade observada

Antes, manter a mesma janela após restart preservava o início antigo e atribuía o intervalo inteiro à atividade. Uma troca de janela depois de suspensão também podia ser descrita como evento observado em tempo real.

O mesmo JSON de situação agora guarda ID da sessão, época de execução, último retrato UTC, último instante monotônico e duração observada acumulada. Relógio monotônico nunca é reutilizado entre processos. Reinício, lacuna ou regressão reabre uma linha de base; encerra a sessão anterior no último retrato conhecido, sem contar o intervalo não observado nem inventar novidade/música ocorrida enquanto dormia.

Uma lacuna maior que `max(60s, 3 × HEARTBEAT_SEGUNDOS)` interrompe continuidade. Esse teto é conservador: também segmenta um tick muito atrasado. A duração continua aproximada entre observações, não comprova que alguém usou o aplicativo durante cada segundo. O nome público da API e seus argumentos anteriores são preservados; o instante monotônico opcional serve aos testes determinísticos.

A sessão legada aberta sem marcador confiável de última observação não é retropreenchida com horas adivinhadas. Registros históricos já fechados permanecem intactos. A tabela existente continua com datas locais textuais para seus consumidores SQL; os novos marcadores JSON são UTC. O resumo de atividade ainda agrupa por data de início, não divide uma sessão que atravessa meia-noite.

### 4. Fechamento durável sem duplicação

Na revisão, um ensaio com SQLite temporário reproduziu duas linhas ao fechar duas vezes a mesma sessão, simulando queda entre INSERT e atualização do JSON.

Agora o ID é persistido na sessão; há chave determinística de compatibilidade quando necessário. O INSERT usa a chave primária existente, `ON CONFLICT(id) DO NOTHING`, e a leitura posterior confirma o registro. Falha de banco é propagada, não tratada como sessão gravada. O estado pendente não é esquecido. Duração divergente para um ID já gravado preserva a primeira evidência e emite `activity.close_conflict`, sem sobrescrever ou somar duas vezes.

## Arquivos desta rodada

Código: `app/config.py`, `app/core/history.py`, `app/core/situation.py`, `app/mind/affect.py`, `app/mind/psych_state.py`, `app/mind/drives.py`, `app/mind/emotions.py`.

Testes: `testes/test_historico_integral.py`, `testes/test_logica_cognitiva.py`, `testes/test_world_state.py`, `testes/test_v20_iniciativa.py`.

Documentação: este relatório e nota de andamento em `FUNDACAO_HISTORICA_20261009.md`.

## Testes e evidências

Baseline real desta rodada: **73/74 grupos**, não 74/74. `test_v20_iniciativa` falhou porque um timestamp truncado em segundos permitia erro de quase 1s numa comparação com tolerância de 0,9s. Novos marcadores usam milissegundos; a fixture usa instante fixo e exige zero exato. Não aumentamos a tolerância.

Regressões vermelhas preservadas: `test_logica_cognitiva-antes.log`, `test_historico_integral-antes.log`, `test_world_state-antes.log`, `test_v20_iniciativa-antes.log`, `atividade-dedup-antes.log`.

**19 métodos novos** nos grupos existentes:

- Lógica cognitiva: 7 novos, grupo **13/13**, mais 13 verificações legadas.
- Histórico integral: 3 novos, grupo **23/23**.
- World state: 9 novos, grupo **40/40**; inclui SQLite real temporário para duração, confirmação e deduplicação.
- Iniciativa: fixture determinística atualizada, grupo **12/12**.

Primeira suíte após o conjunto inicial: **74/74**, saída 0. Suíte final após idempotência e todas as regressões: **74/74**, saída 0. `git diff --check` sem erros. O catálogo permanece com os mesmos 74 grupos; não foram criados grupos paralelos para inflar o baseline.

Os testes executam no isolamento existente: runtimes/SQLite temporários, credenciais removidas, rede/captura/hardware/download e escrita em bancos reais bloqueados. Testes de UTC, suspensão e restart são **controlados**, não prova de suspensão física, relógios PC2 alinhados ou comportamento real de sentimentos.

Arquivos privados, ignorados pelo Git:

`compartilhado/runtime/ensaios/20261009/tempo/`

Snapshot pré-alteração de código/testes: `pre-incremento/codigo.tgz`. Baseline completo em `suite-antes.log`; rodada intermediária `suite-depois.log`; final `suite-verificada.log`. Nenhum backup mental ou credencial foi colocado no Git.

## Preservação e limites restantes

Históricos reais consultados somente em modo read-only: dumps lógicos continuam iguais aos snapshots da fundação histórica (Hoshino `ab925e35…`, Lilith `94865263…`, Alistair `7387f921…`). Isso não é hash de todos os modelos/dados do projeto. Não houve migração mental nesta rodada.

Os hashes SHA-256 dos três bancos mentais e dos cinco JSON mentais/psicológicos disponíveis foram iguais nas verificações antes/depois da suíte final. O hash do banco Hoshino e dos cinco JSON também coincide com a leitura feita durante a suíte intermediária. Isso reforça as guardas de isolamento; não equivale a ter medido cada arquivo/peso ou feito snapshot byte a byte antes de toda a rodada. Backups de código e evidências dos ensaios anteriores foram preservados.

Ainda pendentes:

1. Conversão coordenada dos consumidores SQL mentais/agenda/reflexão, sem misturar ingenuamente formatos de datas.
2. Cooldowns gerais de `main/kernel` ainda usam datetimes; duração monotônica foi aplicada aqui ao acompanhamento de atividade, não prometida para todos os caminhos.
3. Suspensão/restart físicos e relógios entre processos/PC2. Os testes controlados não substituem essa evidência.
4. Diário privado, aprendizagem/identidade, oficina visual, experiências de cache/modelos e autonomia social do plano maior continuam para incrementos posteriores.
5. Validação humana prolongada de naturalidade, emoções, iniciativa e integração com ambientes reais.

Para carregar este Python novo, é necessário reinício cooperativo do backend/entidades. Não foi feito automaticamente. Reversão deve comparar o snapshot e retirar apenas este incremento de código; não restaurar bancos ou estados reais cegamente nem desfazer mudanças preexistentes. Se o novo código já tiver gravado marcadores JSON UTC, manter o leitor compatível de datas ao reverter consumidores: a versão antiga, sem esse leitor, não sabia misturar timestamps com/sem offset.

## Continuação — agenda, reflexão e intervalos

O incremento seguinte revisou os consumidores de agenda/reflexão e os intervalos gerais de iniciativa, sem converter os bancos em bloco. Evidências, regressões e limites estão em `AGENDA_REFLEXAO_TEMPO_20261009.md`. A lista acima registra o encerramento desta rodada anterior; não representa conclusão automática de diário, aprendizagem, oficina, cache ou teste humano.
