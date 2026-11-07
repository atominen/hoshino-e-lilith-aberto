# Central de controle e interface viva — rodada de 07/10/2026

## Parecer

**A CENTRAL ESTÁ PRONTA PARA O TESTE MANUAL? SIM, MAS…**

Está preparada para iniciar a sessão básica controlada: acordar/dormir,
conversar, acompanhar erros/jobs/recursos, inspecionar memória e configurar
os executores/providers suportados. Não é certificação de toda a UX avançada
nem de hardware/providers reais. Primeiro confirme captura/saída de áudio e
arraste/topmost dos orbes no desktop Mint. Se a saída não for selecionável no
navegador, a UI informa a limitação: use o painel de som do Linux, sem terminal.

Não iniciamos entidades reais para produzir screenshots. Não houve inferência,
consumo ElevenLabs/Azure, captura física, conexão Minecraft/Discord ou download
de modelos nesta validação. Screenshots estão marcados **SIMULAÇÃO OFFLINE**.

## Arquitetura encontrada e decisões

O launcher Python já era servidor HTTP loopback autenticado, Supervisor,
interentity, AudioService, job bus e Resource Manager. O HTML já tinha chat,
microfone/rascunho ASR, reprodução sequencial e caixas postais duráveis.

Preservamos essa aplicação. `central.css`/`control.js` acrescentam navegação e
painéis aos elementos/contratos existentes. `core/central_control.py` é um
adaptador no MESMO servidor, não outro backend/coletor/registro de execução.
SQLite/diagnostics/history/job_bus/RM continuam fontes de verdade. Não há
novo banco, scheduler, modelo ou mecanismo mental. Qt5, já instalado, serve
apenas para três janelas opcionais de orbes, em processo separado e sem
WebEngine/OpenGL/inferência. Fechar a aba/overlay não manda encerrar entidades.

Mapa prévio: [ARQUITETURA_CENTRAL_20261007.md](</home/gustavo/hoshino e lilith/docs/ARQUITETURA_CENTRAL_20261007.md>).

## Etapas implementadas

| Etapa | Entrega nesta rodada |
|---|---|
| A | Sidebar, 11 áreas, layout escuro 1080p/responsivo, foco acessível, detalhes recolhíveis. |
| B | Três cards independentes; wake/sleep/chat/memória/atividade/stop voz; autoria/desfechos do chat preservados; frases estáveis existentes, não tokens privados; anexos na entrada existente. |
| C | Catálogo local por entidade; contexto/saída validados; persistência com revisão/backup e gate de sono; router de voz configurável, Voice IDs, key somente CONFIGURADA/NÃO CONFIGURADA; testes explícitos de TTS e tom local. |
| D | CPU/RAM/swap/AMD VRAM, fila/leases/residência separados; contratos agrupados da entidade sem importar dispatch; timeline/filter/correlação; comandos observados; memória READ-ONLY. |
| E | Inventário de pesos; upload GGUF em chunks de 2 MiB, staging, reserva 4 GiB, verificação de fragmentos/hash; exportação local com hash de cópia; progresso no job bus e cancelamento próprio. Sem apagar/substituir pesos. |
| F | Overlay opcional, três orbes próprios, transparência, arraste/persistência e topmost opcional. Processo separado; desligado por padrão. |
| G | Menu com conversa/wake/sleep/stop voz/carinho; carinho entregue como mensagem social do usuário, sem alterar emoção diretamente. Balões limitados, cooldown 20s por entidade, duração configurável, silencioso; clique abre central. Foco só por relatos explícitos. |
| H mínima | Metadados/assets-placeholder separados Hoshino/Lilith/Alistair, cores próprias e estados operacionais. Não geramos figurinha/personagem final nem inventamos emoções. Variantes cute/chip/toy e controles finos de representação permanecem para refinamento visual. |

## Configurações e comportamento

- Modelo principal: apenas instalado e previamente aprovado para a entidade.
  Um GGUF importado é um ARQUIVO, não um executor automaticamente compatível.
  H/L principal continua 9B, leve 7B independente; Alistair continua 4B.
- Contexto principal: inteiro 2048–16384 H/L; 2048–8192 Alistair. Saída:
  inteiro 128–8192 e não pode exceder contexto. Referência no formulário:
  H/L 16384/4096, Alistair 4096/768. Aplicação exige sono confirmado; não troca
  executor no meio da resposta. Contexto leve 8192 permanece READ-ONLY.
- Env preserva comentários/linhas desconhecidas; JSON preserva campos
  desconhecidos. Escrita atômica, backup 0600 desde criação e revisão otimista.
  O gate compartilha lock do Supervisor e `entity.lock`, verifica presença,
  processo, jobs e leases. Não há editor arbitrário de config/comandos.
- ElevenLabs pode ser habilitado e preferido pela UI; habilitar sozinho não
  sintetiza áudio. Chave exclusivamente no ambiente. Hoshino:
  `jotBQRDYDizrWQAbv9VO`; Lilith: `m151rjrbWXbBqyq56tly`.
  **Config real preservada: ElevenLabs enabled=false; preferred_provider=azure;
  Azure enabled=true.** Configurado não equivale a conectado/testado.
- Qwen3-TTS obrigatório como fallback; Kokoro preservado. Troca de worker
  Kokoro não implementada como hot swap: exige configuração/restart local.
  Chaves/valores secretos são redigidos antes de resposta JSON/log observado.
- Microfone/ASR usam captura existente, com nível durante gravação e rascunho
  revisado. Saída usa `setSinkId` somente quando suportado; volume da aba e
  tom de teste explícito. Permissão/lista de dispositivos não comprovam som.
- Shutdown global agora tem botão explícito, confirmação e resposta accepted,
  NÃO verified; solicita a mesma drenagem cooperativa existente. Fechar aba
  continua não desligando entidades. Jobs bloqueados não são mortos à força.
- Cada mensagem tem detalhes operacionais recolhíveis com IDs, autoria,
  destinatário, origem e metadados disponíveis. São registros do contrato,
  não cadeia de pensamento nem promessa de ordem causal global.
- RM não foi recalibrado: 8 GiB rígidos, margem 768 MiB, serialização
  conservadora, concurrency_validated=false; nenhuma dependência CUDA.
- RunPod/cloud não implementados/habilitados. Minecraft/Discord continuam
  pelos controladores da entidade; painel não chama funções globais como se
  fossem pertencentes a outra entidade. Sem sondagem, estado é desconhecido.

## READ-ONLY e limites explícitos

Memória não é editada/migrada. O inspetor não chama recall nem inicializa Chroma:
formatação pura foi extraída, mantendo reexports e categorias/confiança/origem.
Busca atual examina até 300 registros recentes POR categoria; resultado até
150. Isso é indicado na UI: ausência nessa janela não prova inexistência.
Alistair apresenta histórico próprio, não recebe mente Hoshino/Lilith.

Timeline lê até 300 eventos por arquivo SQLite e últimas janelas de 512 KiB
de dois JSONL por entidade; até 200 resultados. Logs centrais são filtrados
pela autoria `data.entity`, não pelo diretório do logger. Novos eventos
JSONL/SQLite compartilham diagnostic_id, evitando contar espelho duas vezes.
Eventos antigos sem esse identificador não são fundidos por heurística cega.
Ordem mostrada é cronológica/local; não é causalidade global garantida.

Comandos existentes unem stdout/stderr: exibimos saída COMBINADA limitada a
32 KiB, não uma separação fictícia. Exit code ausente aparece indisponível.
Cancelamento de comando segue pedido pelo chat/controlador já existente; não
criamos terminal irrestrito nem matamos PID arbitrário pela central.

ASR/VAD, heurísticas do RM, integrações e compatibilidades desconhecidas são
somente leitura quando não existe contrato seguro de edição. Não existe
download externo novo, delete de modelos nem hot swap de checkpoints locais.
Exportar significa cópia verificada em Entregas/saída; não reter gigabytes no
Blob do navegador. Transferência interrompida/crash não é retomada/repetida
automaticamente; staging inconclusivo é preservado para inspeção.

## Endpoints novos no servidor existente

Todos os endpoints de dados/controle continuam autenticados por Bearer local,
com Host/Origin estritos. Somente HTML/CSS/JS estáticos não têm estado secreto.

| Rotas | Método / contrato |
|---|---|
| `/api/control/models` | GET catálogo/config; POST validação/persistência com sono. |
| `/api/control/audio` | GET configuração pública; POST provider/vozes entre jobs. |
| `/api/control/memory`, `/activity`, `/commands` | GET leitura limitada/redigida/filtros. |
| `/api/control/resources`, `/capabilities`, `/entities` | GET projeção do sistema/RM/catálogo/observações. |
| `/api/control/interface` | GET/POST preferências visuais validadas. |
| `/api/control/files` | GET inventário autorizado de pesos locais. |
| `/api/control/import`, `/upload`, `/import/finish` | POST staging e chunks binários ordenados; no-clobber. |
| `/api/control/export`, `/transfer/cancel` | POST cópia/solicitação de cancelamento de transferência própria. |
| `/api/control/attachment` | POST binário até 8 MiB na entrada da entidade; sem auto-send/execução. |
| `/api/control/overlay`, `/overlay/start` | GET estado; POST abre processo UI opcional. |
| `/api/control/social`, `/focus` | POST mensagem social deduplicada / relato de foco da aba. |
| `/api/audio/test`, `/api/audio/interrupt` | POST síntese de teste confirmada / interrupção por entidade. |
| `/api/control/shutdown` | POST pedido confirmado para drenagem existente, sem sucesso fictício. |
| `/ui/central.css`, `/ui/control.js` | GET estático, allowlist sem traversal. |

Rotas abreviadas na tabela mantêm o prefixo `/api/control` da primeira coluna.

## Correções encontradas no desenvolvimento

1. Síntese done não implica WAV encerrado: reprodução tem observações próprias
   no job existente, com cancelamento por entidade, inclusive fora de foco.
2. Anotar playback corria contra término do job: `job_bus.annotate` agora
   mescla observação atomicamente sem ressuscitar status ou adotar PID.
3. Importar knowledge_store poderia abrir memória vetorial: `memory/records.py`
   isola funções puras; contratos antigos reexportados, sem migração.
4. Log da central com entity=Lilith no diretório Hoshino precisava filtragem
   pela autoria; diagnostic_id também evita duplicação do espelho atual.
5. Seletor do botão de anexos derrubava boot JS: corrigido e detectado pelo
   navegador. O teste antigo também precisava selecionar explicitamente Enviar
   após existir mais de um botão, sem relaxar verificação de envio/IDs.
6. CSS legado sobrescrevia shell: ordem corrigida e telas inspecionadas.
7. Playwright bundled referenciava revisão de browser ausente: usa Chromium
   já instalado explicitamente; NENHUM download para fazer o teste passar.
8. Card esperava `model` no lease, mas o RM fornece `model_key`: projeção
   corrigida e ensaio de navegador verifica executor/isolamento, inclusive
   quando um lease genérico aparece antes do compute lease.

## Testes e evidências

Baseline antes de mudanças: **70/70 grupos offline**. Resultado completo final:
**72/72 grupos offline**, sem excluir grupos anteriores.

Novos grupos:

- `test_central_control`: **34 testes**, fixtures temporárias: revisão/backup,
  comentários/unknowns, contexto/saída inválidos, entidade/job/lock ativo,
  isolamento/modelo inexistente, segredo ausente/rejeitado, switching sem
  quota, áudio ocupado, Azure inválida, memória read-only/zero/origem/filtros,
  ausência de import de Chroma, timeline/autoria/dedup, log combinado redigido,
  overlay/config/posições/assets, upload/hash/reserva/no-overwrite/cancel,
  exportação verificada, anotação terminal, playback cancel H/L, carinho
  deduplicado, foco, processo UI desligado/crash, Qt offscreen e anexo seguro.
- `test_central_browser`: **1 ensaio de navegador real, 12 fluxos/áreas
  simulados**, 1920×1080 e 390×844: boot/navigation/cards/chat/IDs/contexto,
  providers sem síntese, memória/timeline/saída, RM, serviços/configs,
  redimensionamento e fechamento. Todas as APIs interceptadas; NÃO valida
  mic, alto-falante, LLM ou provider real. Playwright/Chromium precisam existir
  localmente; falta de dependência falha explicitamente, não instala nada.

Também repetidos especificamente: central anterior (17), áudio (37), voz
streaming (19), integridade da memória (9), autoria (10), prontidão R1–R7 (19).
Qt5 disponível e abriu três orbes no teste offscreen; fechamento manteve o
servidor-fixture vivo. Isso não prova arraste/topmost no compositor real.

Projeção do catálogo REAL instalada conferida sem inferência/daemon/banco mental:
Hoshino 9B e 7B, Lilith 9B e 7B, Alistair 4B, todos com arquivos/tamanhos
esperados presentes. Hashes dos três DBs mentais permanecem iguais aos
registrados na rodada R1–R7; nenhum teste usou banco mental real.

## Desempenho observado, não extrapolado

`central_20261007/metricas-central-fixture.json` contém a medição do navegador:
Chromium headless/renderização software, 15 s idle, 35 mudanças de área.
RSS SOMADO do navegador completo ~970 MiB, incluindo páginas compartilhadas;
não é RAM exclusiva do código da UI. CPU idle ~3,3% de UM núcleo. Heap JS após
GC ~2,56 MiB; DOM anexado ~483 nós. Nós/heap transitórios recuam com GC nesses
ciclos; não é prova de ausência de leaks durante horas.

Overlay Qt offscreen: três orbes, timer 80 ms (~12,5 fps), ~57 MiB RSS pico;
~0,035 s CPU em ~2,1 s (~1,7% de um núcleo). Ensaio curto de UI, não medida
do compositor/GPU real. Não afirmamos GPU idle/overlay validado fisicamente.

Polling: estado 2 s, painel ativo de recursos/atividade 5 s, áudio 15 s, foco
15 s, overlay 2 s. Painéis ocultos pausam; monitor de cancelamento continua
enquanto áudio estiver ativo. Jobs/históricos/arquivos/renderização têm limites.
Medição prolongada, muitos dados reais e custo do compositor continuam pendentes.

## Arquivos

Modificados:

- `iniciar_entidades.py`
- `app/ui/central.html`
- `app/core/audio_service.py`
- `app/core/job_bus.py`
- `app/core/diagnostics.py`
- `app/memory/knowledge_store.py`
- `testes/catalogo.py`

Criados:

- `app/core/central_control.py`
- `app/memory/records.py`
- `app/ui/central.css`, `app/ui/control.js`, `app/ui/overlay.py`
- `app/ui/assets/hoshino/orb.json`
- `app/ui/assets/lilith/orb.json`
- `app/ui/assets/alistair/orb.json`
- `testes/test_central_control.py`, `testes/test_central_browser.py`
- `testes/central_browser.cjs`
- `docs/ARQUITETURA_CENTRAL_20261007.md`, este relatório
- `docs/central_20261007/central-conversa-fixture.png`
- `docs/central_20261007/central-entidades-fixture.png`
- `docs/central_20261007/metricas-central-fixture.json`

Backups de fontes em `arquivo/central_20261007/`; configurações reais não foram
reescritas pela validação. Nenhum peso apagado, banco mental migrado ou chave
recebida. Config `interface.json` é criada só após salvar preferência pela UI.

## Primeira sessão e riscos restantes

Abra pelo iniciador existente. Vá a Entidades para wake/sleep e Conversa para
apresentações. Em Áudio, confirme captura/saída local antes de usar provider
pago. ElevenLabs fica desligado até sua habilitação explícita. Em Configurações,
ative overlay, salve e clique Abrir orbes. Arraste cada orb e teste menu/carinho/
stop/sleep, observando confirmação no backend, não só o clique.

Não há bloqueador determinístico reproduzido nos contratos testados. Ainda
faltam validação humana de áudio/desktop, ElevenLabs/Azure reais, coexistência
Minecraft 1.16.5, PC2 físico e uso prolongado. Defaults conservadores continuam.
Balões/representações são versão mínima, não toda a personalização visual
solicitada. Usar “SIM, MAS” reconhece esses limites; não significa “tudo aprovado”.
