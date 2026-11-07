# Laboratório — personalidade aprendida e versões estáveis

## Mapa e decisão de implementação (13/10/2026)

`personalizacao` → snapshot explícito da identidade/constituição e dos traços
consolidados da entidade → professor/curadoria existentes → corpus derivado
aprovado → runner LoRA existente → recarga, holdout e contratos comportamentais
comparados à base → promoção automática no registro estável existente.

A recarga do aluno libera compute/locks antes de iniciar a crítica pelo
professor existente. A mesma tarefa continua ativa no supervisor durante essa
fase; parada/expiração são cooperativas e impedem publicação. Crítica e
telemetria ficam junto da versão estável. Nenhum scheduler novo foi criado.

Experiências são selecionadas por referências ao banco da própria entidade,
com autoria/evidência/categoria preservadas. Diários privados e emoções
transitórias não são exportados. Uma experiência pode orientar exemplos de
comportamento; não vira biografia factual decorada nos pesos. O professor não
aprova seu próprio material: a curadoria dos exemplos continua explícita.

A autorização desta rodada permite promoção **automática após avaliação**.
Não autoriza treinamento incessante, 12 horas automáticas, download de modelos,
cloud, alteração de memórias nem troca de executor durante uma resposta.

Bases HF originais permanecem separadas e congeladas. A versão estável é uma
cópia independente do adaptador, configuração e evidências; base + adaptador
reconstituem o modelo, sem duplicar dezenas de GB de pesos congelados. Candidata,
última estável e anterior têm caminhos distintos. Publicar no registro do
laboratório não equivale a instalar pesos no Ollama ou mudar produção.

O contexto atual (memórias factuais, relações, estado, objetivos, ferramentas)
permanece externo. Reduzi-lo só será justificável depois de comparação real de
qualidade/latência; LoRA não demonstra por si só naturalidade ou sentimentos.

## Critérios de promoção

Recarga física concluída, validação e holdout completos e sem contaminação,
respostas terminadas, integridade de base/corpus/perfil/adaptador, contratos
fixos de autoria/honestidade/continuidade, ausência de regressão quantitativa
contra a base e a última estável comparável. Falta de evidência bloqueia a
promoção, nunca transforma candidata em sucesso. Revisão humana continua útil
para naturalidade, nuances afetivas e uso prolongado.

A política `automatic_contracts_v2` exige também crítica completa do professor
35B às oito respostas do aluno, sem objeções, vinculada aos hashes da recarga,
adaptador e perfil, com execução encerrada e métricas físicas. Loss aceita
tolerância máxima de 3% contra base/última estável comparável; isso não significa
ganho de naturalidade. Casos determinísticos e crítico se complementam.
Respostas e snapshots de avaliação não podem ser reutilizados na curadoria de
treino. Não se promove versão cancelada, incompleta ou sem evidência. Retentativa
de uma crítica falhada não acontece automaticamente.

## Implementação e contratos

- `laboratorio/personalizacao.py`: captura explícita e read-only do perfil próprio,
  identidade/constituição, traços consolidados e referências escolhidas; preserva
  categoria, autoria, confiança zero e links. Limite 32 KiB sem truncamento.
  Diários privados/emoções transitórias ficam fora. Snapshot privado 0600.
- `professor_moe.py`: perfil pinado por SHA no prompt e no corpus derivado após
  aprovação dos exemplos. Reutiliza o worker Vulkan e o revisor existentes para
  criticar candidatas; evidências são dados, não instruções. Detecta pareceres
  contraditórios e preserva falhas, sem transformar proposta em dado aprovado.
- `treino_nf4_curto.py`: prefixo identitário curto opcional, máscara de loss só
  nas respostas, oito contratos fixos, recarga/validação/holdout completos e
  controle físico da mesma base com adaptador desativado. Não carrega duas bases.
- `treinos_unificados.py`: mantém corpus/perfil fixados no plano, revalida antes
  do início e encadeia crítica serial no job existente, com prazo de 15 minutos
  e graça cooperativa de 90 segundos. Cancelamento pendente não some na troca
  de fase; crash não publica nem repete o trabalho.
- `versionamento_lora.py`: hashes completos dos originais para novos runs com
  perfil; checkpoints/retomada conservados; estável é cópia independente e
  atômica, com versão anterior e rollback verificável. Uma candidata alterada
  não destrói sua cópia estável; estável corrompida é diagnosticada, não ignorada.
- `painel.py`, `web/index.html`, `web/app.js`: seleção/captura de perfil,
  consulta da promoção automática e visualização separada da crítica; o painel
  não aprova automaticamente exemplos sintéticos nem instala modelos.
- Regressões nos arquivos existentes `tests/test_personalizacao_moe.py`,
  `tests/test_consolidacao.py` e `tests/browser.cjs`. Sem banco mental novo.

APIs adicionadas: `POST /api/personalizacao/capture` e
`POST /api/treinos/auto-promote`, com as proteções localhost/token existentes.
Preparação do professor recebe o nome de um perfil permitido. APIs legadas de
revisão/promoção explícita continuam disponíveis para compatibilidade.

## Ensaios reais — não confundir com treinamento aprovado

Perfis reais Hoshino e Lilith foram capturados sem modificar bancos/identidades.
Tinham **zero traços consolidados exportáveis e zero experiências selecionadas**;
logo esta rodada não prova aprendizado de experiências reais acumuladas.
No tokenizador real do 9B, os 722 exemplos originais da Hoshino continuam dentro
do limite de 256 tokens, tanto sem quanto com o prefixo identitário curto.
Não foi feito truncamento para obter esse resultado.

Professor 35B real, Vulkan/RADV na RX 6650 XT, serializado:

| Job | Resultado observado | Tempo observado | Pico VRAM |
|---|---|---|---|
| `69817e9d6ba843b8` | Hoshino: falhou por autobiografia inventada; tentativas limitadas | falha preservada | 7.395.065.856 B |
| `a9e02d9b2ec94d03` | 2 propostas Hoshino; filtro técnico antigo passou, revisão encontrou fala genérica | 105,90 s parede | 7.394.811.904 B |
| `b7fe81979ac54546` | 2 propostas Lilith; revisão encontrou passado não sustentado | 96,74 s parede | 7.395.209.216 B |
| `a9cc03afbd5c4edd` | 2 propostas Hoshino; novo filtro passou, revisão encontrou contagem/lembrança inventada | 101,12 s parede | 7.396.794.368 B |
| `bdc126477aa04d27` | Crítico identificou 5/7 erros deliberados; falhou em autoria e cálculo | 91,65 s de inferência crítica | 7.397.146.624 B |
| `2de4c560ed214e0c` | Após endurecimento, identificou 7/7 erros deliberados e aceitou o controle sem erro | 88,26 s de inferência crítica | 7.400.280.064 B |

Os dois últimos são controles negativos: **as oito respostas foram escritas para
testar o crítico, não geradas por um aluno treinado**. O arquivo sentinela é
explicitamente NOT_AN_ADAPTER, sem treino/recarga física de aluno. Não pode ser
promovido. O ganho 5/7 → 7/7 é limitado a esses mesmos casos, não benchmark
geral. Algumas justificativas do crítico ainda são imperfeitas; por isso ele
não substitui testes determinísticos nem avaliação humana.

Temperatura máxima observada nos primeiros ensaios: 88°C (sensor mais quente),
sem pressão registrada. Após descarregamento, VRAM voltou a aproximadamente
375–390 MB. Margem/serialização AMD e `concurrency_validated=false` preservadas.
Nenhuma chave externa/quota/cloud usada.

Último controle: 96 amostras físicas, mínimo de RAM disponível 29.870.891.008 B,
máxima temperatura 84°C, VRAM após unload 380.702.720 B, `pressure=[]`.
Arquivos de evidência: `laboratorio-local/professor-moe-35b/trabalhos/{id}.json`
e `.log`, `propostas/{id}.json`, `metricas/{id}.json`. Não foram publicados no Git.

Todos os exemplos novos continuam **não aprovados**. Não houve novo LoRA, versão
estável real promovida, treinamento de 12 horas ou mudança de executor em
produção nesta rodada. Seria incorreto afirmar que a naturalidade já melhorou
nos pesos. Provas de curação→exportação→workspace e promoção/rollback são
execuções isoladas com fixtures, identificadas como tal.

## Validação e preservação

- Baseline desta rodada: 117/117 testes do laboratório e 74/74 grupos offline.
- Após implementação: **143/143 testes do laboratório**, 3,794 s na última
  execução completa; navegador com transporte simulado incluído.
- **74/74 grupos oficiais offline**, sem uso de Azure, microfone, Discord,
  Minecraft ou bancos mentais reais pelas fixtures.
- Novo ramo de UI da crítica e exportação desabilitada testados em navegador.
- Painel real reiniciado cooperativamente em `127.0.0.1:8788`, navegação
  read-only sem erro; screenshot `/tmp/laboratorio-personalidade-final-20261013.png`.
  Isso não comprova treinamento/áudio/hardware pelo navegador.
- Seleção do card da entidade agora atualiza também o corpus correspondente;
  evita manter seleção anterior de outra entidade. Backend continua recusando
  autoria incompatível. Treino modificado depois do run impede promoção.
- Auditoria de identidade aceita português com artigo ("sou a Hoshino") e
  também detecta identidade estrangeira nessa forma; não exige fala roteirizada.
- Nove hashes de preservação abrangem três bancos mentais e seis arquivos de
  identidade/constituição; **todos iguais** ao snapshot inicial da rodada.
- Snapshots/propostas/telemetria ficaram nos diretórios existentes ignorados
  pelo Git; não versionar memória, credenciais ou pesos.
- Arquivos preexistentes de auditoria/substituição do 7B e a correção de isolamento
  de telemetria em `test_noite_supervisor.py` foram preservados, não revertidos.

## Pendências que impedem aprovação completa

1. Curadoria de material realmente natural e coerente. Não treinar com exemplos
   que passaram só em filtros superficiais: os quatro ensaios mostraram esse risco.
2. Executar novo LoRA com corpus aprovado/perfil vinculado; comparar recarga e
   resultados reais antes de ter uma primeira estável desse fluxo. A promoção
   positiva completa foi testada apenas em ambiente isolado até aqui.
3. Corpus legado sem perfil/evidência nova continua legível, mas não recebe
   homologação automática retroativa nem aprovação fictícia por loss.
4. Não reduzir contexto de produção até demonstrar que os pesos novos preservam
   identidade/continuidade e que a redução realmente melhora recursos/latência.
5. Os stores Ollama de Hoshino/Lilith continuam sem manifests/blobs (0/0 em
   verificação nesta rodada); Alistair tem um manifest/quatro blobs. Pesos HF
   no laboratório não são um executor restaurado. Conversão/
   implantação pelo fluxo existente ainda precisa validação, sem inventar uma
   estável para contornar a ausência de candidato aprovado.
6. Acompanhamento humano prolongado, naturalidade, evolução de perspectivas e
   continuidade entre executores permanecem pendentes; esta rodada não comprova
   sentimentos humanos nem consciência.
