# Professor — reteste, correções e curadoria — 14/10/2026

## Parecer

**Infraestrutura refinada e defeitos reproduzidos cobertos; professor NÃO
homologado para produzir/aprovar personalidade sozinho.** Ainda erra fatos,
naturalidade e intenção. A curadoria assistida foi autorizada pelo usuário:
não é avaliação humana direta nem aprovação do próprio professor.

Nenhuma entidade acordada, treino, promoção, exportação de corpus, download/troca
de pesos, cloud/TTS ou concorrência GPU. O desafio do buraco negro continua
apenas documentado, sem execução nesta rodada.

## Ponto de partida e método

Continuação do [plano de 13/10](PROFESSOR_PROXIMAS_CORRECOES_20261013.md), sem
outro laboratório/banco/scheduler. A skill de avaliações locais orientou smoke
e comparação; seus exemplos NVIDIA não se aplicam. Mantido o servidor Vulkan/AMD
existente, sem instalar inspect/vLLM/CUDA ou usar providers remotos.

O checkout já estava modificado; diferenças anteriores preservadas. HEAD
`ccd0133b310255d13269e8f0e91dde9fbb739ea2`, branch
`codex/laboratorio-consolidacao-20261012`. Sem commit/push automático.

Baseline executado: **234/234 testes do laboratório**. Primeira execução direta
da suíte oficial: **73/74**. `test_executores_leves` teve 34 erros de importação:
o lançador incluía `app`, mas não a raiz necessária para importar `laboratorio`.
Incluída a raiz no mesmo lançador, sem alterar o RM. Grupo isolado depois:
**83/83**, seguido da suíte completa final verde.

## Correções

1. **Estado factual por turno:** `case_view` informa autor/ouvinte, origem das
   mensagens, consulta/recibo e evidência disponível naquele prefixo. Futuro,
   fonte estrangeira e IDs duplicados são recusados; confiança `0.0` conservada.
   Resultado confirmado não prova sua causa. São dados do exercício, não
   consultas/gravações na memória real.
2. **Diálogo nativo:** user/assistant anteriores seguem como mensagens do
   protocolo, não uma conversa inteira dentro de uma mensagem JSON. Metadados
   separados e schema de resposta preservado. Hash do request/estado e IDs/SHA
   das referências registram o que entrou. Saída incompleta continua recusada.
3. **Instruções menores e pertinentes:** regras específicas de memória/ações
   nos casos correspondentes. Não cria bordões. Reparação fornece classes de
   erro às respostas iniciais sem revelar detalhes de turnos futuros.
4. **Referências/feedback por relevância:** categoria e termos do objetivo,
   mantendo quatro candidatos/dois exemplos no escritor, mesma entidade e
   aprovação vinculada ao SHA. Registros completos preservados; pendência não
   vira aprovação. Histórico diagnóstico autorizado continua disponível, mas
   explicitamente não é autobiografia da personagem.
5. **Gates de defeitos reais:** diagnóstico de rede/passagem/transporte sem
   prova, incerteza convertida em ausência, sugestão de reenvio sem verificação,
   notas editoriais dentro de falas e inexistência de registros sem consulta.
   Hipótese/negação não deve virar afirmação. São padrões reproduzidos, **não um
   verificador semântico universal**.
6. **Citação versus identidade:** fala atribuída a Alistair entre aspas não é
   autodeclaração da Hoshino. Autodeclaração estrangeira continua recusada.
7. **Cenários independentes:** histórias anteriores “proibidas” induziam
   continuações/paráfrases. Retiradas do prompt, mantidas no verificador sobre
   todo o lote. Comparação lexical cobre a paráfrase reproduzida, sem certificar
   novidade semântica absoluta. Objetivo de cada categoria explicitado.
   Sampling do cenário: temperatura 0,65, top-p 0,9, presence penalty 0,2.
8. **Autoria da curadoria:** `codex_assisted` exige referência à autorização;
   motivo/SHA/histórico preservados. UI distingue do “aprovado por você”.
   Exportação/rotina noturna não renomeiam aprovação assistida como humana.
   Campo legado `human_reviews` conservado, sem migração cega.

## Inferências reais

Professor original `unsloth/Qwen3.5-35B-A3B-GGUF`, Q3_K_M, RX 6650 XT/Vulkan.
Perfis isolados existentes, seed 42 nos controles. São **inferências do professor
escrevendo os perfis**, não testes dos alunos 4B/7B/9B ou das mentes em produção.

21 diálogos controlados + 12 de geração normal = **33 diálogos completos
avaliados / 65 respostas**. Uma execução preliminar cancelada é contabilizada
separadamente. Reauditoria não é nova inferência.

| Controle | Gate técnico registrado | Gates locais finais reaplicados | Tempo sem carga |
|---|---:|---:|---:|
| Hoshino baseline, `094232` | 2/3 | 1/3 | 80,38 s |
| Hoshino estado/referências, `095635` | 2/3 | 2/3 | 104,87 s |
| Hoshino nativo, `100228` | 5/6 | 3/6 | 203,13 s |
| Hoshino compacto, `101944` | 3/3 | 2/3 | 115,42 s |
| Lilith final, `105532` | 2/3 | 2/3 | 113,30 s |
| Alistair final, `110105` | 2/3 | 1/3 | 100,68 s |

Arquivos privados em `laboratorio-local/professor-moe-35b/metricas/`, formato
`geracao-controlada-{entidade}-20261014-{sufixo}.json` e logs. Reauditoria:
`reavaliacao-curadoria-20261014.json`, com SHA dos originais. Ela reaplica
contratos locais sem nova inferência/revisão humana e sem certificar novidade
contra todo o corpus. Não sobrescreve resultados antigos para aparentar sucesso.

Carga: 14,02 s no baseline; aproximadamente 8,01–8,31 s nos demais. Ordem/cache,
amostra pequena e testes CPU/browser coincidentes em algumas fases confundem
a comparação de latência. **Não foi demonstrado ganho global de velocidade.**
Primeiro prompt do quebra-cabeça: 2.131 → 1.869 tokens entre instrução nativa
longa e compacta; o total não caiu consistentemente por revisões/cache.

Falhas preservadas: “o problema foi na passagem”; nota “A resposta anterior foi
corrigida…” dentro da fala; “como se ele não tivesse saído”; “vale tentar reenviar
ou confirmar”; “não tenho registro” sem consulta. O crítico ainda deixou passar
erros que os gates/leitura assistida recusaram. Contexto separado não o tornou
um juiz independente confiável. Nada disso foi usado como prova de sentimentos
humanos ou consciência.

## Geração normal e decisões

| Job | Gerados / categorias | Aprovados por curadoria assistida | Reprovados | Tempo do job |
|---|---:|---:|---:|---:|
| `deee8c27272449fa` | 8 / 4 | 0 | 8 | 432,14 s |
| `96de469e39c64b65`, cenário corrigido | 4 / 4 | 1 | 3 | 251,89 s |

Primeiro lote: oito passaram automaticamente, mas todos foram reprovados.
Repetição do ouriço/torneira, continuação da sardinha, história inventada,
conselho físico inadequado, objetivo não exercitado e resposta genérica.
Parecer antigo permanece visível.

Segundo lote: assuntos distintos e decisão com alternativas realmente construída.
Ainda houve pressão por atenção, caricatura/percepção não fornecida e certeza
excessiva numa carta histórica. Fonte divergente não vira verdade automaticamente.
0/8 → 1/4 é curadoria exploratória, não estimativa universal ou estatística de
classificador: critérios humanos diretos não foram medidos e a amostra mudou.

Aprovado somente como **raciocínio sob premissas do exercício**, não certificado
de persona: `ds:hoshino:000722:fd457902cba7`. Compara táxi/bicicleta pelos custos
e prazos informados, reconsidera com chuva/preço novo. Tokenização **real/local**
da base 9B e seu template: **244 tokens, limite 256, zero truncamento**, sem
carregar pesos. Conteúdo e compatibilidade verificados separadamente.
Não há lote exportável: API exige ao menos dois aprovados. Não exportou/importou
corpus nem iniciou treino; exemplo não virou referência implicitamente.

Nove referências autorais anteriores aprovadas para orientar geração, três por
entidade: jobs `0d99a5e6d2aa4757`, `15dc620410fe4e18`, `6a5a7c5a51854153`.
São textos do Codex, **não do professor**, não exportáveis como treino.
Revisor assistido registrado, não decisão humana direta.

Pode rever em **Central → Laboratório Neural → Professor MoE → Ver detalhes →
Curadoria por exemplo**. A UI/serviço residente devem carregar o código atualizado;
não foi feito restart amplo da Central/entidades. Browser validado com transporte
simulado, não sessão física do serviço residente nesta rodada.

Preliminar `41e0158fd6b14b07`: iniciou durante o ajuste de filtro; parada
cooperativa, estado `cancelled`, parciais/logs conservados. Fora dos 33 completos,
sem treino/promoção/restart do mesmo ID. Nova execução teve correção concreta e
ID próprio, sem repetir efeito externo incerto.

## Recursos e preservação

| Job normal | Pico VRAM total | GPU busy máximo | RAM disponível mínima | Sensor mais quente |
|---|---:|---:|---:|---:|
| Oito diálogos | 7.451.303.936 B | 99% | 27.955.507.200 B | 93 °C |
| Quatro diálogos | 7.450.771.456 B | 99% | 28.661.895.168 B | 92 °C |

427 e 248 amostras. RAM é `MemAvailable` do kernel, incluindo páginas recuperáveis,
não RSS exclusivo nem orçamento garantido sob outros workloads. Swap já ocupado
(~1,81 GiB), não somado à RAM rápida; ocupação variou 8 KiB/132 KiB nesses jobs,
o que não prova ausência de page-ins. Nenhum monitor disparou pressão.
Temperaturas medidas não homologam 12 horas: acompanhar antes de uso prolongado.
Sem alterar fans, power, driver ou margens.

Final: nenhum worker ocupado, compute/fila vazios, VRAM externa ~0,41 GiB.
`concurrency_validated=false`; margem 805.306.368 B mantida; RM não recalibrado.
Nove hashes de constituições/self-models/SQLite mentais iguais ao início.
Pesos originais, datasets, validação/holdout, configurações e evidências preservados.

Backups privados, ignorados pelo Git, em
`laboratorio-local/controle-laboratorio/treinamento-unificado/backups/professor-20261014/`:

- `codigo-antes.tar.gz`: `eff7fd3f94859ae0707bdab9d38a3a517467ec6e47843eb4c9087f8d044351aa`.
- `curadoria-antes.tar.gz`: `6fab70e356628bc06caa7f16c0a56828a7eb1d12e8199da872527574d20610f5`.

Código/registros de curadoria, sem bancos mentais, .env ou pesos.

## Validação e arquivos

Final: **74/74 grupos oficiais**, **253/253 testes do laboratório**. Baseline 234:
19 novos no laboratório + um no runner = **20 regressões**, sem novo grupo.
Browser Chromium/transporte simulado: PASS, zero erros, 28 chamadas; distingue
curadoria assistida e não inicia professor/treino. Não prova hardware/mentes reais.
Sintaxe shell/JS e `git diff --check` aprovados.

Falhas iniciais dos novos testes reproduziram diagnóstico/reenvio indevido,
editor vazado, falsa troca de identidade, paráfrase e causa indevidamente deduzida
de resultado. Negação capitalizada de reenvio também coberta pelo helper
normalizado. Não foram relaxados para aceitar essas falhas. Invocações inválidas
de seleção/consulta foram recusadas e não contam como testes aprovados.

Arquivos desta rodada:

- `laboratorio/professor_moe.py`, `rotina_noturna.py`, `README.md`;
- `laboratorio/web/app.js`;
- `laboratorio/tests/test_consolidacao.py`, `test_personalizacao_moe.py`,
  `test_noite_supervisor.py`, `probe_geracao_professor.py`, `browser.cjs`;
- `rodar_testes.sh`, `testes/test_isolamento_suite.py`;
- este relatório e atualização de status do plano de 13/10.

Outras diferenças no checkout eram preexistentes. JSONs do laboratorio-local
são evidência privada, não novo banco nem conteúdo para Git.

## Pendências

Melhoraram organização/diversidade de situações e proteção contra alguns erros;
**boa escrita de personalidade ainda não foi demonstrada consistentemente**.
O professor confunde relato/comprovação, caricaturiza e avalia mal as próprias
respostas. Os filtros têm limites/falsos positivos possíveis. Curadoria individual
continua necessária; não treinar tudo esperando que o problema desapareça.

Uso longo, qualidade do aluno depois de LoRA, avaliação humana cega e serviço
residente atualizado continuam pendentes. Não houve troca de professor:
censura não foi isolada como causa dos erros em situações inofensivas.

**Produzir propostas para revisão: SIM. Gerar/aprovar sozinho personalidade e
iniciar treino automático com ela: NÃO, pelos defeitos reproduzidos.**
