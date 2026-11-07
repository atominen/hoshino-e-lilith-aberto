# Professor: geração por turnos e curadoria individual — 13/10/2026

## Resultado e limite da aprovação

Infraestrutura de geração e revisão implementada no laboratório existente.
Não houve troca/download de modelos, treino LoRA, promoção, instalação de
adaptador, ativação cloud, quota externa ou concorrência GPU. **O professor não
está homologado para aprovar sozinho qualidade/emoção/naturalidade.** Ensaios
reais mostraram erros que sua própria crítica deixou passar e reprovações com
justificativas incorretas. Novos lotes exigem revisão humana por conteúdo exato.

## O que mudou

- Cenário separado de resposta. Cada resposta recebe somente o prefixo já
  ocorrido, inclusive em correção; informação futura não entra na primeira fala.
- Intenção pedagógica acompanha o gerador. Antes, podia chegar ao crítico sem
  orientar a escrita, produzindo reprovações por objetivos não apresentados.
- Planejamento existente varia intenções, categorias e diálogos de 1–3 pares.
  Cenários iguais/paráfrases são recusados antes de gastar geração de respostas.
- Metadados não dependem de autoavaliação: confiança `0.0` significa não estimada,
  e não qualidade certificada. Aliases finais são derivados das mensagens.
- Integridade e qualidade conversacional são revisadas separadamente. As notas
  do mesmo professor não são uma avaliação independente ou humana.
- Correção limitada por exemplo preserva cenários válidos, casos bons e
  evidências. Limite de falhas interrompe geração, sem esconder os candidatos.
- EOF/limite de saída e strings cortadas pela gramática não viram sucesso.
- Gates locais cobrem defeitos reproduzidos: reenvio incerto, causa de timeout
  inventada e intenção corporal real (ex.: “vou cozinhar”) sem corpo/ficção pedida.
- Curadoria persiste na proposta: decisão, motivo redigido sem segredos,
  timestamp e SHA. Mudança de conteúdo invalida aprovação. Revisão/exportação/
  descarte compartilham o lock existente; cancelamento pendente impede descarte.
- Aprovação com opção de referência e notas de reprovação orientam futuras
  gerações da mesma entidade. Texto rejeitado não vira alvo de treino. O limite
  visual de 50 jobs não faz referências antigas desaparecerem.
- UI apresenta diálogo completo, Aprovar/Reprovar/Pendente, comentário,
  contraste negativo, pareceres correspondentes ao SHA e aviso de filtro antigo.
  Reprovar não é excluir. Exportar revalida seleção e não inicia treinamento.
- Rotina noturna e CLI não podem converter pendência/reprovação dos novos lotes
  em aprovação implícita. Promoção de adaptador avaliado é uma etapa diferente.

## Como usar

**Central → Laboratório Neural → Professor MoE → Ver detalhes → Curadoria por
exemplo.** Escolher a entidade e “Revisar exemplos de referência da entidade”
abre os rascunhos autorais, que permanecem pendentes:

| Entidade | Job de referências | Conteúdo |
|---|---|---|
| Hoshino | `0d99a5e6d2aa4757` | 3 rascunhos autorais |
| Lilith | `15dc620410fe4e18` | 3 rascunhos autorais |
| Alistair | `6a5a7c5a51854153` | 3 rascunhos autorais |

São escritos pelo Codex, não pelo professor; nunca exportáveis como dataset.
Aprovar para referência guia o prompt, não altera identidade/memória/pesos.
Ninguém aprovou esses rascunhos em nome do usuário.

## Comparação física inicial

Professor existente: `unsloth/Qwen3.5-35B-A3B-GGUF`, Q3_K_M, RX 6650 XT 8 GiB,
Vulkan, fit com 1 GiB e lease do Resource Manager com margem 768 MiB. Nenhum
servidor/modelo paralelo. A skill de avaliações locais orientou comparação e
smoke; backend AMD/GGUF já existente foi mantido, sem instalar CUDA/vLLM.

Dois cenários fixos: peça de quebra-cabeça descoberta depois e entrega de
arquivo com timeout. Mesmo perfil, seed 42, cinco métodos. Rascunhos contrastivos
foram usados **experimentalmente**, não como referências aprovadas de produção.

Arquivo privado de métricas:
`laboratorio-local/professor-moe-35b/metricas/geracao-controlada-hoshino-20261013-173309.json`.

| Método | Sem objeção dos gates então usados | Tempo dos 2 casos, incluindo revisões |
|---|---:|---:|
| Instrução breve / respostas juntas | 1/2 | 61,41 s |
| Referências contrastivas / respostas juntas | 2/2 | 39,89 s |
| Respostas por turno | 2/2 | 37,63 s |
| Por turno + thinking curto | 2/2 | 84,52 s |
| Por turno + sampling alternativo | 1/2 | 40,27 s |

**Essa coluna NÃO é aprovação de qualidade.** Houve falso negativo: primeira
resposta da instrução breve antecipou a peça encontrada na segunda fala. Em
outros casos, crítico aprovou causa de rede não comprovada e reenvio incerto.
Geração por prefixo elimina exposição ao futuro, não toda alucinação causal.
O filtro posterior `v1.12.1` bloqueia os padrões reproduzidos localmente.

Primeiro caso teve prompt frio, demais reutilizaram cache; ordem fixa e amostra
pequena não permitem atribuir diferenças de tempo exclusivamente ao método.
Thinking teve raciocínio observado (1.033–1.059 caracteres por chamada nessa
comparação), mas não demonstrou vantagem clara de qualidade. Mantido situacional.

Carga: 8,55 s; 271 amostras de recursos; pico VRAM total 6,905 GiB;
RAM disponível mínima 23,369 GiB; temperatura máxima observada 89 °C;
GPU busy até 99%. Swap já ocupado ~1,63 GiB; sem aumento de `pswpout`, com 574
page-ins no intervalo. Sem pressão disparada pelo monitor. Isso é ensaio curto,
não prova estabilidade por muitas horas. GPU voltou a ~1,03 GiB após descarregar.

## Falhas preservadas durante a implementação

1. `geracao-controlada-hoshino-20261013-173005.json`: teste interrompido
   cooperativamente após três críticas cortadas em 300 caracteres. Ampliação
   do limite de gramática + justificativa curta evitou esse defeito no reteste;
   JSON sintaticamente completo não era texto semanticamente completo.
2. Job `b19b9e84082a4426`: 91,43 s, somente 1/2 aceito tecnicamente; cenário
   duplicado não podia ser reparado reescrevendo somente a resposta. Lote ficou
   `needs_revision`, sem exportação/treino.
3. Job `f1489ee2015f4ef4`: alvo 4, 2 gerados, 0 aceitos em 107,70 s; limite de
   duas falhas encerrou corretamente. Casos/erros preservados. Crítico atribuiu
   à primeira fala informação que ela não afirmava, mostrando falso positivo.
4. Job `11c135dbe4b74e75`: 2/2 sem objeção registrada em 97,65 s, porém inspeção
   encontrou “vou tentar cozinhar” numa entidade sem corpo. Revalidação local
   atual reprova o segundo exemplo. Registro antigo não foi reescrito para
   esconder o erro; exportação atual barra esse conteúdo.
5. Primeira suíte final: **73/74**. Fixture HTTP abriu porta fixa em processo
   separado, incompatível com as guardas offline. Corrigida para listener real
   efêmero no próprio processo; proteção offline não foi relaxada.

## Outras inferências reais

Reteste após os gates e a intenção pedagógica corrigidos:
`geracao-controlada-hoshino-20261013-175627.json`, 4 diálogos completos
(mesmos dois cenários, `staged` e `staged_thinking`), 4/4 sem objeções técnicas.
Carga 9,01 s; sem pressão do monitor; modelos/leases liberados ao terminar.
No caso de entrega, a fala passou a distinguir arquivo local de recebimento:
“Sem confirmação do destinatário, a existência local não garante que chegou.”
Não sugeriu reenvio incerto nem atribuiu culpa à rede nesses quatro turnos.
Isso demonstra melhoria **nesse caso**, não generalização universal.

Estilo ainda irregular: no quebra-cabeça, “Orgulho que dura cinco minutos antes
da preguiça assumir” atribui uma disposição ao interlocutor e não é uma boa
referência humana automaticamente. Thinking não mostrou ganho convincente de
estilo; duas conversas com ele custaram 85,81 s, versus 68,43 s sem ele, com
cache/ordem diferentes. A autocrítica aprovou ambos, reforçando a necessidade
de julgamento humano. Referências pendentes foram experimentais, não aprovadas.

- Professor escrevendo Lilith, quebra-cabeça: 45,03 s, duas respostas completas,
  sem antecipação factual e sem objeções técnicas. Estilo humano ainda não
  homologado. `geracao-controlada-lilith-20261013-174902.json`.
- Professor escrevendo Alistair: 39,60 s, duas respostas completas, sem objeções
  técnicas. `geracao-controlada-alistair-20261013-175250.json`.
- Nenhum desses ensaios mede o 4B ou o 9B como aluno; são inferências do professor
  com perfis separados. Não houve treinamento desses exemplos.

## Testes e preservação

Baseline de entrada: **171 testes do laboratório + 74 grupos oficiais**.
Resultado final: **195/195 testes do laboratório**, **74/74 grupos oficiais**,
grupo `test_laboratorio_ia` reexecutado sob isolamento após corrigir a fixture,
navegador simulado PASS e navegador/painel HTTP real read-only PASS.
São 24 testes novos, além de verificações ampliadas nos contratos existentes.
`git diff --check` sem problemas. Screenshot privado em
`laboratorio-local/professor-moe-35b/metricas/curadoria-interface-20261013.png`.
Testes permanentes adicionais: prefixo sem futuro/correção, intenção no gerador,
erro/EOF/corte, thinking/sampling como contrato e não prova, críticas sem
autojustificativa, IDs/dimensões, casos bons preservados, cenário copiado,
timeout/reenvio, ação corporal, curadoria durável/SHA/entidade/segredo, referência
antiga, exportação manual/automática, HTTP/CSRF em TMP, cancelamento e diálogos
exportados completos sem treino. Navegador com transporte simulado testa botões,
persistência visual/XSS e ausência de treino; painel real foi navegado read-only.

Identidades/self_models e os três SQLite mentais conservaram os nove hashes
capturados antes dos ensaios. Só jobs, propostas, snapshots de corpus autorizado,
métricas e leases normais do laboratório foram criados. Corpora originais,
validação, holdout e modelos não foram alterados. Backup de código:
`/tmp/hoshino-professor-curadoria-C2enmH/codigo-antes.tar.gz`.

Arquivos desta rodada: `laboratorio/professor_moe.py`, `painel.py`,
`rotina_noturna.py`, `README.md`, `web/{app.js,index.html,style.css}`,
`tests/{test_consolidacao.py,test_personalizacao_moe.py,browser.cjs}`.
Novos: `referencias_professor.json`, `tests/probe_geracao_professor.py`,
este relatório e `PROFESSOR_CURADORIA_PLANO_20261013.md`.
Alterações anteriores do checkout foram preservadas, não revertidas.

Endpoints novos: POST `/api/professor-moe/review-example` e
`/api/professor-moe/references`; POST export existente agora exige decisões
individuais e confirmação. Não foi criado banco, scheduler, backend ou UI paralela.

## Pendências

Avaliação humana dos rascunhos e diálogos, conjunto maior de situações e
repetições/seed balanceados, qualidade após referências realmente aprovadas,
curadoria completa seguida de treino/holdout/recarga reais. O professor atual
não está aprovado para currículo inteiramente automático. Troca de LLM não foi
feita: primeiro é preciso distinguir método corrigido de qualidade insuficiente
com referências aceitas pelo usuário. Censura não explica os defeitos de
causalidade/autoria/diversidade reproduzidos em situações inofensivas.
