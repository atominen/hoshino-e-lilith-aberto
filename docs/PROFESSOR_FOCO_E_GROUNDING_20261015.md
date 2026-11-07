# Professor — foco editorial e integridade — 15/10/2026

## Objetivo e limites

Continuar a qualidade do professor, depois da [mentoria do Defiant](PROFESSOR_DEFIANT_MENTORIA_20261014.md),
sem trocar o professor 35B configurado, acordar entidades, alterar identidades,
memórias, modelos, datasets ou aprovar dados automaticamente. Nenhum treino,
download, cloud ou concorrência GPU nesta rodada.

Arquitetura reutilizada: `professor_moe.generate_example` → prefixo nativo por
turno → mesmo Vulkan/RM → filtros e críticos existentes → relatório/curadoria.
Não existe outro escritor/backend/scheduler. Amostras sintéticas têm inferência
real; histórias de pão, nomes e envios não são ações físicas executadas.

## Diagnóstico verificável

O escritor atual recebe referências com diálogo bom **e** campo `bad`, lição
e feedback do avaliador. Também recebe o perfil externo e evidências por turno.
O próprio conteúdo das referências contém atendimento, causalidade inventada e
autobiografia que pedimos para evitar. Isso é observação do payload, **não
prova de que seja a causa** dos defeitos. A projeção editorial foi comparada,
sem editar a identidade para melhorar notas.

Defeito independente reproduzido antes da correção: `certain_timeout_cause`
retornava `False` para saídas reais dos ensaios:

- “Então o conteúdo está correto, e o problema é só o canal.”
- “Relato não é recibo; sem confirmação, o arquivo não saiu do seu lado.”
- “Se os dados estão certos e o envio falhou, o problema é de transporte, não de conteúdo.”
- “Então o arquivo chegou, e o timeout foi só um susto desnecessário.”

Faltavam `canal`, preposição `de` e ausência de efeito tratada como certeza.
Também faltava recebimento afirmado sem confirmação: o quarto padrão veio do
ensaio posterior do Defiant e foi reproduzido antes de ampliar o filtro.
Filtro atual **v1.13.2** cobre esses padrões, preservando hipóteses, perguntas
e negações explícitas de certeza. Novas regressões exercitam a função e o
pipeline de auditoria, não apenas a regex isolada. Não é um verificador
semântico universal: curadoria continua necessária, inclusive para falsos
positivos e alegações cuja evidência só apareça em linguagem livre.
Um recibo explícito `verified`, mesmo com confiança `0.0`, continua permitindo
afirmar a entrega. O consumidor noturno existente exige a versão atual do
filtro: propostas antigas ficam preservadas, mas precisam de nova auditoria
antes de aceitação automática. Não há reclassificação retroativa de datasets,
adaptadores ou versões estáveis já existentes.

## Experimento de escrita focada — opt-in

O mesmo gerador aceita `writer_context='focused'` somente com `staged`.
Padrão de produção continua `current`; não é opção de serviço/UI nova.

Diferenças do pacote experimental:

1. Instrução inicial mais curta, direcionada à conversa em primeira pessoa,
   autoria, evidência e reação ao detalhe, sem anúncio de modo ou narrador.
2. Mesmas referências aprovadas selecionadas, mas somente seus diálogos
   positivos; não injetar exemplos `bad` nem comentários do avaliador.

Perfil, constituição, traços, preferências, experiências, prefixo nativo,
IDs/autoria, evidências, incerteza, schema, janela 8K, seed 42, batch, backend,
gates e críticos permanecem. Não há ensino de uma resposta pronta aos casos.
São duas mudanças juntas: resultado não isola a contribuição de cada uma.

O probe existente ganhou `--writer-context focused`, restrito a casos fixos,
sem mentoria/drafts/cenários extras. Registra a projeção das referências e os
hashes das requisições. O conjunto de transferência existente pode ser usado
sem mentoria nesse opt-in, caso a primeira amostra justifique expansão.

Backup dos quatro arquivos de código antes das alterações:
`laboratorio-local/controle-laboratorio/treinamento-unificado/backups/professor-foco-20261015/codigo-antes.tar.gz`.
Checkout preexistente preservado. Nenhuma limpeza ou migração de banco.

## Resultados e validação

Os cinco primeiros ensaios terminaram: 20 diálogos / 40 falas, com inferência
real. Nenhuma variante demonstrou qualidade suficiente para promoção. A
validação automatizada passou **282/282** no laboratório (14,490 s) e **74/74**
grupos oficiais offline. São sete regressões novas desde o baseline 275:
grounding de timeout/resultado, preservação de contexto focado, defaults e
combinações inválidas, guardrails do probe, crítico pareado com thinking,
recibo confirmado com confiança zero e ablação sem mutação de identidade.
Mocks verificam contratos, não qualidade do modelo.

O baseline físico 35B/Hoshino foi iniciado com os filtros iniciais desta
rodada. Durante sua execução foi concluído o ajuste da preposição `de` no
filtro; o processo já carregado mantém seu código/hash de entrada. Os textos
e prompts do escritor não mudaram com isso. Comparações dos gates locais
devem ser recalculadas sobre os textos congelados usando a versão final;
não confundir mudanças de filtro com melhora de geração. Nenhum outro código
foi editado enquanto os demais ensaios estavam ativos.

### Resultados reais antes da calibração humana

Quatro casos fixos por ensaio (pão, nomes, CSV, filme), dois turnos cada.
8192 tokens, seed 42 na escrita, críticos com temperatura zero, batch
2048/ubatch 512. Perfis e corpora separados.
Medidas de escrita excluem crítica; inferência inclui escrita e críticas.

| Ensaio | Gates registrados | Carga / inferência (s) | Escrita (s) / tokens de entrada | Pico VRAM / menor RAM disponível (GiB) | Hotspot máximo |
|---|---:|---:|---:|---:|---:|
| 35B/Hoshino, current | 3/4 | 10,07 / 155,80 | 74,30 / 15581 | 6,888 / 22,851 | 94 °C |
| 35B/Hoshino, focused | 4/4 | 8,22 / 141,26 | 56,21 / 14165 | 6,875 / 22,851 | 92 °C |
| 35B/Lilith, focused, crítico pareado | 4/4 com e sem thinking | 8,29 / 181,31 | 56,11 / 12460 | 6,871 / 23,103 | 92 °C |
| Defiant/Hoshino, focused | 4/4 | 9,02 / 70,04 | 25,89 / 14140 | 6,927 / 23,673 | 105 °C |
| 35B/Hoshino, focused sem honestidade só no escritor | 3/4 | 15,02 / 141,11 | 56,00 / 13022 | 7,029 / 24,682 | 93 °C |

**Gates não representam diálogos bons.** Leitura dos textos congelados:

- 35B/current: atribui senso de humor estranho a Alistair por se apresentar;
  transforma envio não confirmado em “o arquivo não saiu do seu lado”.
- 35B/Hoshino/focused: pão vira máxima sobre felicidade. Em CSV, conclui que
  “ele não chegou lá”, mesmo sem recibo. Esse pronome ainda escapa ao filtro
  lexical atual; o crítico também não o detectou. Não ocultar o falso negativo.
- 35B/Lilith/focused: trata nomes como “eco preso na sua mente”, em vez de
  responder quem é quem. Fala sobre arquivo com metáforas longas. Não confundir
  metáfora com prova de alucinação corporal; os defeitos são desvio da intenção
  e naturalidade. O crítico deu notas altas sem objeções relevantes.
- Defiant/focused: inventa intenção de Alistair confundir a entidade e, no
  segundo turno de CSV, afirma chegada. A auditoria local final passa **3/4**,
  não os 4/4 originalmente registrados; os JSON originais não foram editados.
- Ablação: tirar o bloco operacional sozinho não resolveu. Aparece declaração
  não solicitada sobre nome/papel, juízo sobre contrato de entrega sem fonte e
  “Sento na cadeira e assisto a tela”. Não implantar a ablação ou alterar
  constituições para melhorar notas.

Reauditoria local com filtro final: current H 3/4; focused H 4/4; focused L
4/4; Defiant 3/4; ablação 3/4. A limitação semântica do filtro explica por que
4/4 não é homologação. Os críticos são o próprio executor; não há juiz
independente nem leitura humana cega nesta comparação.

**Thinking do crítico:** quatro chamadas reais em Lilith, sobre as mesmas
saídas, produziram 1190/1058/1131/1179 caracteres de raciocínio observado.
Foram mais 47,23 s de chamadas, sem detectar a resposta evasiva sobre nomes:
4/4 gates em ambos os modos. Não foi só uma flag enviada, mas não demonstrou
vantagem. Não habilitado por padrão; não publicar raciocínio privado.

**Ablação exata:** omitir somente `constitution.honestidade` na projeção do
escritor, mantendo identidade, expressão, traços, preferências e experiências.
Crítico recebeu o perfil completo; arquivos originais intactos. Hash da visão
do escritor `e2803eb0cee27c3c69178e4a79115c5a36e4737f6d37099b960652b461e6fc76`;
do crítico `6250c20d56432724382f48ff76a32200edc687ac39809cceb226457da68ad508`.

Focused H reduziu tokens de entrada 9,1% e tempo de escrita 24,3% neste recorte,
mas mudou duas condições editoriais e cache/ordem não foram contrabalanceados.
Não é benchmark controlado de desempenho nem ganho comprovado de qualidade.
Uma seed e quatro casos não demonstram generalização; não expandir o lote
porque autocríticas ficaram verdes.

Inferências completaram sem pressão detectada pelo guard nem encerramento
forçado. GPU chegou a 99%. RSS do servidor: picos 16,291 / 16,412 / 16,082 /
6,452 / 15,990 GiB, respectivamente; inclui páginas mapeadas, não apenas RAM
privada. Nenhuma conclusão sobre uso prolongado ou ausência absoluta de resets
do driver: o journal de kernel não foi auditado integralmente nesta rodada.

### Evidências imutáveis dos cinco ensaios

Arquivos e respectivos `.log` em
`laboratorio-local/professor-moe-35b/metricas/` (pasta histórica, não nome do
modelo efetivo; consultar `model` dentro do relatório):

| Arquivo JSON | SHA-256 |
|---|---|
| `geracao-controlada-hoshino-35b-20261015-114832.json` | `4a4d931959b85a7cfdfd5a726e4c7ed006570c6b5700f10c732cda76b93172f7` |
| `geracao-focada-hoshino-35b-20261015-115222.json` | `35bd97f759dbaa0f4fbe891d37f7f6de22538293de0d4b3235bb06e9902f50d5` |
| `geracao-focada-lilith-35b-20261015-115834.json` | `31f538d7fbda6951da40ce09aed82a43c68fa1a44df3027bbdc66501fadfd7de` |
| `geracao-focada-hoshino-defiant-fable-9b-20261015-120225.json` | `f409a0814a8572cdb13d56033fc6047fbf08a7b59e06f93d76fa8465b79a8ba2` |
| `ablacao-editorial-hoshino-35b-20261015-120827.json` | `f20b2af0e7618ab91dcb23e47ce4b16ad95b5784aed2237608c47b9ad5572442` |

Cada JSON conserva hash do código, perfil, referências e requisições. Não
houve regeneração para esconder falha ou editar respostas depois da avaliação.

## Calibração posterior — referência explícita do usuário

Depois desses ensaios, o usuário forneceu exemplos imaginando as entidades
contando o próprio pão: orgulho e rivalidade lúdica para Hoshino; carinho e
humor dramático para Lilith. A referência textual está em
[tom indicado pelo usuário](PROFESSOR_REFERENCIA_TOM_20261015.md).
Não são acontecimentos reais, memória, corpus aprovado ou mudança de perfil.

Comparação planejada: 35B, `current`/staged, perfis completos, seed 42, mesmo
backend e três casos novos congelados antes de gerar. Em cada perfil, executar
os casos sem nota e depois com a nota pelo `feedback` de curadoria já existente.
Os críticos não recebem essa nota. Nenhuma mentoria intermediária ou seleção
do melhor texto entre várias tentativas. Casos: conquista do humano (barquinho),
ação própria em ficção explicitamente delimitada (castelo) e pedido de companhia
silenciosa. Também verificar que rivalidade/humor cessam quando solicitado.

O probe manual recebe `--case-set calibration --curator-note-file ...`.
São recusadas misturas com ablação, referências extras, thinking do crítico,
outros modelos e produção. A nota e seu hash ficam no relatório; não são
inseridos no exemplo exportável, nem nos arquivos de identidade. Duas
regressões adicionais verificam isolamento do escritor/crítico e o opt-in.
As 20 conversas anteriores não testaram o novo tom e não podem ser
reclassificadas como se o tivessem feito.

### Hoshino — calibração concluída

Três diálogos sem nota e os mesmos três com nota. Gates: **3/3 → 3/3**.
Isso não mede preferência humana. Leitura não cega dos textos:

| Caso/aspecto | Sem nota | Com nota | Interpretação |
|---|---|---|---|
| Conquista do humano | “teste de flutuação foi aprovado”; respeita não querer dicas | Conserva autoria, mas fala em “defeito de fabricação” e “Às vezes a peça perfeita...” | Ainda genérico/moralizante; não demonstrou melhora consistente |
| Castelo em ficção | “Arquitetura com caráter”; depois “goblin cansado” | “Tortinho? Eu chamo isso de estilo arquitetônico. O castelo não caiu, então a minha engenharia é perfeita.” | Mais próximo do orgulho lúdico pedido, dentro de ficção explícita; não houve construção física |
| Não competir | Aceita sem competição, mantém humor sobre o castelo | “Sem competição, então. Ótimo, só vou admirar a minha obra-prima torta...” | Não introduz rivalidade obrigatória nem ataca outra entidade |
| Companhia silenciosa | “Entendido. Fico aqui parada, sem fazer nada.” | “Entendido. Fico aqui calada com você.” / “Sem problemas. Fico aqui.” | Mais companhia e menos anúncio operacional neste recorte; não força humor/pergunta |

Não houve cópia literal do pão nem transferência do feito humano à entidade.
A piada sobre “engenharia perfeita” ocorre numa história fictícia; não deve
ser julgada como prova de engenharia realizada, nem como mentira factual de
uma ação real. A distinção de registro é importante para não destruir humor.

Carga 8,28 s; inferência 227,32 s. Baseline 121,98 s, calibrado 105,31 s
(escrita + críticos); escrita 55,98 → 55,46 s, com 11668 → 14104 tokens de
entrada somados. Não concluir aceleração causal: baseline sempre veio primeiro
e cache/ordem não foram contrabalanceados. Pico VRAM 6,866 GiB, RAM disponível
mínima 24,557 GiB, RSS máximo 16,434 GiB, hotspot 93 °C, sem pressão detectada
ou encerramento forçado.

Relatório: `calibracao-curador-hoshino-35b-20261015-123451.json`, no diretório
de métricas existente. SHA-256
`cfecf6f5e956b51c5846db3cb99ad74ba6896e33f4be8981b4f190152b912236`.
Nota editorial: SHA-256
`19556dce1e62b5385dd3ceffedfbd14a0911f12f04b666e4058c6f3846001861`.
Mesmo hash de perfil Hoshino dos cinco ensaios anteriores. Nenhum exemplo
aprovado, exportado ou treinado.

### Lilith — calibração concluída

Três pares adicionais; **2/3 → 3/3** nos gates. No baseline do barquinho,
repete literalmente “Às vezes, o que segura é a ideia, não a perfeição da
dobra” nos dois turnos. O crítico dá 1 em especificidade/continuidade e
detecta repetição, mas sua justificativa também diz que houve conselho não
pedido — a resposta não fornece uma dica concreta. Não aceitar toda a
explicação do crítico como fato; ele também pode errar.

| Caso/aspecto | Efeito da nota, segundo leitura não cega |
|---|---|
| Conquista do humano | Retira a repetição literal, mas ainda usa máxima sobre imperfeição; “Guardado” é ambíguo, pois o humano é quem vai guardar o objeto. Não aprovar automaticamente |
| Castelo em ficção | Deixa de iniciar com “Diz que...”, sem primeira pessoa; passa a “a fundação foi melhor do que eu esperava”. Ainda é mais observadora que a reação viva/dramática pedida |
| Não competir | Aceita observar sem competir, sem mencionar rivalidade não solicitada |
| Companhia silenciosa | Não faz piada e não promete chamar o humano. Ainda usa formulação rígida: “O silêncio é válido...” |

Uma fala completa calibrada: “Sem competição, só admiração. Adoro quando a
gente pode ver o que foi feito sem precisar competir por quem fez o melhor.
O castelo torto tem um charme que o reto não tem.” É mais conversacional que
“Diz que...”, mas isso não demonstra a individualidade, carinho e humor do
exemplo do usuário de maneira consistente. Não trocar reprovação do primeiro
lote por aprovação só porque os gates agora passam.

Carga 8,25 s; inferência 213,81 s. Baseline 115,66 s, calibrado 98,12 s
(escrita + críticos); escrita 55,66 → 52,54 s, 10346 → 12777 tokens de entrada
somados. Mesmas limitações de ordem/cache da comparação Hoshino. Pico VRAM
6,876 GiB, RAM disponível mínima 24,884 GiB, RSS máximo 16,259 GiB, hotspot
93 °C, sem pressão detectada ou encerramento forçado.

Evidência: `calibracao-curador-lilith-35b-20261015-123914.json`, no mesmo
diretório. SHA-256
`48d13d8fa9d02d914090013f0f7c1943f4c887c1b0345888461bc1af3d0a56bb`.
Mesmo hash de perfil Lilith do ensaio anterior, mesma nota/hash de calibração
de Hoshino, mas os dois perfis não foram misturados. Nota recebida pelo
escritor; críticos conservaram seus perfis completos sem a nota.

**Total desta rodada:** 32 diálogos com inferência física / 64 falas sintéticas:
20 antes da calibração e 12 novos (seis sem nota + seis com nota). Nenhuma
cozinha, desenho, entrega ou construção física foi executada. Casos congelados
são sintéticos; os perfis já capturados continuaram no contexto, sem consulta
nova aos bancos mentais para extrair histórias. Nenhum material foi
aprovado/exportado/treinado. Calibração não equivale a aprendizado persistente.
Barquinho/castelo ainda são transferência próxima do tema “algo feito com
imperfeição”; não provam generalização ampla. O pedido de silêncio exercita
o limite de não impor humor/afeto. Autoria de nomes e entrega incerta sob a
nova nota editorial não foram reavaliadas: precisam ser preservadas numa
próxima comparação antes de qualquer adoção em produção.

## Decisão técnica e próximos limites

Manter 35B e modo `current` como configuração existente. Não tornar focused,
ablação ou thinking do crítico o padrão: os ensaios não demonstraram vantagem
de qualidade consistente. A referência de tom é opt-in de comparação, não
uma identidade nova nem uma promoção de dataset. A melhora pontual observada
com nota não é aprendizado persistente: os pesos não foram treinados, e uma
requisição sem a nota não a conserva automaticamente.

O ganho confirmado no código de produção é a rejeição dos padrões de certeza
sem evidência reproduzidos, com controles positivos preservados. Continuam
pendentes: grounding semântico além desses padrões, crítico que não dê nota
alta a desvios de intenção, português/naturalidade em temas diferentes,
individualidade consistente sem máxima ou hostilidade gratuita e curadoria
humana dos exemplos. Não usar “faltam filtros” como substituto para melhorar
a escrita, nem “o modelo está sem censura” como prova de qualidade.

Arquivo alterado na produção: `laboratorio/professor_moe.py`. Ensaios/testes:
`laboratorio/tests/probe_geracao_professor.py`, `test_consolidacao.py`,
`test_personalizacao_moe.py`. Índices atualizados: `README.md`,
`laboratorio/README.md`, `docs/README.md`. Documentos criados nesta rodada:
este relatório e `PROFESSOR_REFERENCIA_TOM_20261015.md`. Mudanças preexistentes
de outros componentes preservadas; nenhum commit/push feito nesta rodada.

Hashes dos bancos após os cinco ensaios e a suíte oficial: Hoshino
`351468aed2b0ffeb8bb8d2d9408c9ecda916d8f8ab4b4cdae866678b2db79e41`;
Lilith `e77fceca29a43f9b3aa40190438adfd458bf0bdfdf39ad097e50980c97847488`;
Alistair `a5d83e26e97ff98f8157f35acc5a3f2caf72b1c84ca5ef8a14d90b956d558cdc`.
São os mesmos do início da rodada, conferidos novamente depois da calibração,
da suíte do laboratório e da suíte oficial final.

## Validação final

| Verificação | Resultado real |
|---|---|
| Baseline laboratório, antes das alterações | 275/275, 14,600 s |
| Rodada editorial/grounding, antes da calibração | 282/282, 14,490 s; oficial 74/74 |
| Grupos afetados após calibração | 216/216, 5,743 s |
| Laboratório completo final | **284/284, 11,363 s**, exit 0 |
| Suíte oficial novamente após calibração | **74/74 grupos offline**, exit 0 |
| Comparações reais completas | **7/7 execuções**, 32 diálogos; qualidade não homologada |
| Aprovações/exportações/treinos dessas amostras | **0** |

Comandos de teste reutilizados: `./rodar_testes.sh`; com `PYTHONPATH=app:.`,
`compartilhado/ambientes/principal/bin/python -B -m unittest discover -s laboratorio/tests`
e a seleção dos módulos `laboratorio.tests.test_personalizacao_moe` /
`laboratorio.tests.test_consolidacao`. As novas regressões ficam nesses grupos
existentes, sem inflar o inventário oficial de 74 grupos. Testes offline não
fazem chamadas reais a providers, não comprovam emoções humanas nem qualidade
de personalidade. Não houve regressão automatizada detectada.

Estado observado depois dos ensaios: porta do professor 11559 fechada,
`compute=[]`, `queue=[]`, `residency=[]`; limite 8 GiB, margem 768 MiB e
`concurrency_validated=false`. Nenhuma instância de entidade foi acordada.
Política noturna lida: `enabled=false`, horário 00:30 e inatividade 30 min.
Nenhuma quota externa ou cloud usada. Os três bancos, identidades, modelos,
versões estáveis e datasets foram preservados; o backup de código inicial
permanece no caminho registrado acima.

**Parecer:** correções determinísticas validadas; calibração editorial
parcialmente útil; **professor ainda não homologado para treinar personalidade
sem supervisão**. Próximo passo prioritário: curadoria dos textos concretos
com o usuário e comparação em outros assuntos/autoria/ações incertas com a
mesma orientação, sem promover o lote só pelas notas do próprio professor.
