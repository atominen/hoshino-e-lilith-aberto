# Professor 35B — diagnóstico e próxima rodada proposta

Data: 13/10/2026. **Proposta documentada, NÃO IMPLEMENTADA NESTA RODADA.**

Atualização em 14/10: partes deste plano foram implementadas/retestadas após nova
autorização. Este texto preserva o diagnóstico de 13/10; resultados atuais em
[PROFESSOR_RETESTE_RESULTADOS_20261014.md](PROFESSOR_RETESTE_RESULTADOS_20261014.md).

Pedido atual: explicar soluções para os novos problemas e documentar o desafio,
sem executar. Não houve inferência, curadoria aprovada em nome do usuário,
exportação, treino, promoção, troca de modelo ou alteração de código nesta rodada.

Base da análise:

- [Últimos ensaios e recuperação](PROFESSOR_E_RECUPERACAO_RESULTADOS_20261013.md).
- [Curadoria por turnos e ensaios anteriores](PROFESSOR_CURADORIA_RESULTADOS_20261013.md).
- Código atual de `laboratorio/professor_moe.py` e seus consumidores/contratos
  descritos nos relatórios; não uma reimplementação de laboratório.

## 1. O que realmente falhou

O último relatório registra 18 diálogos na comparação controlada e mais três
no reteste Hoshino. **21 diálogos naquele conjunto**, não o total de todas as
rodadas históricas. Os perfis Hoshino/Lilith/Alistair foram escritos pelo
professor 35B; não eram testes físicos dos três modelos alunos.

No último reteste físico, o crítico aprovou 3/3; a inspeção encontrou duas
certezas sem suporte: ausência de registros sem consulta e causa da entrega
deduzida de um arquivo local íntegro. Os gates v1.12.3 reaplicados aos mesmos
textos aceitam só 1/3 tecnicamente. **Reauditar não é gerar novamente**; não
existe comprovação de que o escritor já parou de produzir esses defeitos.
O caso restante é genérico e não está aprovado como referência de personalidade.

Problemas reais observados nesses ensaios:

- Antecipação de informação futura no método de diálogo conjunto.
- Ausência de contexto confundida com inexistência de memória/acontecimento.
- Timeout confundido com diagnóstico de falha/culpado.
- Autoria equivocada, incluindo Alistair chamar o interlocutor de Alistair.
- Respostas genéricas ou poesia excessiva; emoção pouco ligada ao detalhe.
- Crítico deixando passar erros e rejeitando metáfora como corpo físico literal.

Não houve aprovação/exportação/treino dos 21 diálogos. Não usar seus 3/3 antigos
como certificado de personalidade. Os dados e pareceres anteriores devem ficar
preservados, inclusive quando a avaliação posterior divergir.

## 2. O que já existe — não refazer

O código atual já possui:

- Cenários separados e escrita por prefixo (`generate_situation` e
  `generate_example`); revelações futuras excluídas das mensagens do método staged.
- Quatorze blueprints e seis categorias, com mudanças de condição e até três
  pares de turnos. Portanto, “adicionar diversidade” não começa do zero.
- Perfil/corpus isolado por entidade e projeção pertinente do perfil.
- Filtro de integridade, crítica semântica e avaliação conversacional distintas.
- Curadoria humana por source ID/SHA, referências aprovadas e notas de rejeição.
- Correção limitada a duas tentativas, preservação de candidatos/erros,
  bloqueio de saída incompleta e exportação revalidada.
- Métricas de inferência, prompt hash, tokens/tempos quando disponíveis e jobs
  do laboratório/Resource Manager existentes.

O problema não é falta de mais um crítico ou banco. É a qualidade do conteúdo
que entra no escritor, a seleção das referências e a confiabilidade da decisão
de aprovação. Mais restrições textuais, sozinhas, já não demonstraram resolver.

## 3. Lacunas verificadas no código atual

### Estado factual pouco explícito

`generate_situation` retorna falas humanas em strings; o escritor recebe
mensagens, intenção, perfil e referências. Não existe nesse payload uma
representação explícita e separada de “consulta não realizada”, “consulta com
resultado”, “fato informado” e “recibo incerto”, acompanhada de sua evidência.
Instruções dizem para respeitar essas diferenças, mas os ensaios mostram que
isso não basta. Não significa que falte memória ao produto: falta grounding
mais claro no **exercício sintético**.

### Seleção de referências não condicionada à situação

`approved_references` retorna os primeiros quatro resultados aprovados na ordem
da listagem; `curation_feedback` retorna as primeiras duas notas de rejeição.
Há limite de contexto e isolamento corretos, mas não seleção explícita por
tema, intenção ou defeito atual. Um exemplo de acolhimento pode ocupar espaço
enquanto falta um bom contraste de autoria/entrega incerta. Isso é uma lacuna
estática, não causa demonstrada por A/B nesta rodada.

### Histórico diagnóstico ainda pouco específico por exemplo

A categoria/intenção vem dos blueprints. Na geração, o histórico diagnóstico
é fatiado em duas linhas por grupo, não associado por um diagnóstico explícito
ao defeito de cada `source_id`. A origem é preservada para integridade/novidade,
mas isso não demonstra um currículo que corrige precisamente o problema da
conversa de origem. Não copiar uma conversa privada para “resolver” essa lacuna.

### Aprovação técnica não é excelência conversacional

O pipeline aceita a avaliação conversacional quando todas as notas do próprio
professor são pelo menos 2/4 (“adequado”). A existência desse corte não comprova
emoção/persona de boa qualidade. Ele precisa ser calibrado com decisões humanas,
não simplesmente aumentado até os testes parecerem melhores.

## 4. Correções propostas, por ordem

| Prioridade | Refinamento no componente existente | Como comprovar |
|---|---|---|
| P1 | Evidências explícitas por turno no exercício: autor/sujeito, origem e estado de consulta/recibo | Casos de consulta ausente/vazia/positiva e timeout pendente; nenhuma certeza sem suporte |
| P2 | Referências humanas escolhidas por relevância, mantendo limite de contexto e mesma entidade | A/B com e sem seleção contextual, casos novos e rastreio de IDs/SHA |
| P3 | Calibrar crítico e separar erro factual de preferência estilística | Decisões cegas humanas; falsos aceites/rejeições por defeito e por perfil |
| P4 | Diagnóstico da conversa orienta o objetivo pedagógico do exemplo, sem copiar o episódio | Vínculo evidência → defeito → cenário novo → requisito verificado |
| P5 | Cobertura de comportamentos, não só nomes de categorias | Situações inéditas, medidas de repetição e avaliações em holdout separado |
| P6 | Comparar custo por exemplo realmente aprovado, não por JSON gerado | Tempo/tokens de geração + críticas + reparos + carga e taxa de aprovação humana |

### P1 — Dar chão ao escritor, não um manual infinito de proibições

Ampliar o cenário/payload existente com evidências sintéticas rastreáveis:
o que foi dito, por quem, o que foi consultado, qual o resultado e quando ficou
disponível. Diferenciar **não consultado**, **resultado vazio de uma consulta
limitada**, **resultado positivo** e **serviço indisponível**. Nem uma consulta
vazia limitada prova que um acontecimento nunca ocorreu.

Para ações: arquivo local verificado é diferente de envio aceito, entregue,
incerto ou falho com causa comprovada. Falas anteriores da própria entidade
não viram evidência independente. Preservar o estado do efeito, sem reenvio
automático. A visibilidade acompanha o prefixo, inclusive na correção e crítica:
nenhuma nota do reparo pode revelar ao primeiro turno uma notícia posterior.

Não permitir que o gerador invente retrospectivamente um “recibo” para justificar
sua resposta. O estado do cenário fica congelado/validado antes da escrita;
reparar a resposta não altera as evidências. Usar registros de propostas/IDs
existentes, não outro sistema de memória ou banco.

Encurtar e estruturar a instrução apenas se o A/B provar equivalência dos
contratos. Não remover os gates atuais nem trocar uma lista de regex por outra
lista crescente de regex como única estratégia.

### P2 — Ensinar perspectiva com exemplos aprovados, não bordões

Revisar primeiro os rascunhos já disponíveis na Central: Laboratório Neural →
Professor MoE → detalhes/curadoria. Escolher boas referências por entidade,
com motivos de aprovação/rejeição. Os rascunhos do Codex permanecem autorais e
pendentes, não resultados do professor nem material automaticamente treinável.

Selecionar poucos exemplos relevantes ao caso atual, com diversidade e orçamento
de tokens; não injetar o arquivo inteiro nem referências da outra entidade.
O exemplo deve ensinar uma escolha/tom revisável, não uma frase para repetir.

Avaliar diferenças nas decisões, preferências, limites, humor e forma de reparar
erros. “Hoshino diz uhe” e “Lilith fala em universo” não são critérios suficientes
de identidade. O perfil autorizado continua externo aos pesos do professor.

Emoção proporcional pode aparecer como alegria, frustração, curiosidade,
discordância, interesse ou silêncio. Não exigir afeto/humor/pergunta em toda
resposta, experiências físicas inventadas, dependência ou cobrança de atenção.
Não transformar rigor factual em falas de banco de dados dirigidas ao usuário.

### P3 — O professor não deve ser seu próprio certificado

Manter geração, integridade e qualidade separadas, mas reconhecer que usam o
mesmo 35B: contexto separado ajuda, **não torna a avaliação independente**.
Calibrar seus pareceres contra rótulos humanos no conteúdo exato/SHA, sem
mostrar qual variante escreveu a resposta antes da decisão de qualidade.

Registrar falso aceite e falsa rejeição por caso. Reprovar certezas e autoria
erradas, mas não confundir metáfora, preferência atual, emoção conversacional
ou discordância com corpo físico/contradição/recusa indevida.

Não impor “emoção alta” a todas as falas. Para os casos de persona, propor um
alvo humano de qualidade boa (3/4 na escala atual), calibrado antes da rodada;
para todos os casos, erro factual crítico continua inaceitável. Nota automática
baixa/alta é sinal de triagem, não aval humano. Nenhum candidato vai para treino
só porque duas chamadas do mesmo modelo concordaram.

### P4/P5 — Currículo a partir de erros, sem decorar histórias

Relacionar o problema observado a um objetivo pedagógico claro: falsa lembrança,
autoria, reparação, limite, humor deslocado, preferência inconsistente etc.
Criar outra situação que exija a mesma habilidade. Preservar vínculo à evidência
autorizada e sua autoria, sem transformar nomes privados/episódios em fatos
universais aprendidos pelos pesos.

Usar a variedade de blueprints já instalada, mas medir a variedade efetiva das
saídas: intenções, objetos, conflitos, turnos, escolhas e reações. Trocar só o
objeto ou adjetivo não torna um exemplo novo. Comparar também com corpora e
propostas anteriores; validação/holdout nunca servem como fonte de geração.

Uma falha deve orientar a correção daquele exemplo; cenário/evidências bons
continuam intactos. Preservar as duas tentativas atuais. Se falhar, marcar
pendente/reprovado e conservar o registro, não regenerar indefinidamente.

## 5. Ensaio compacto proposto — depende de autorização

Não iniciar agora. Antes de novas gerações, registrar decisões humanas dos
textos reais preservados e referências que efetivamente poderão entrar.

1. Congelar seis casos por perfil: lembrança sem consulta, consulta limitada,
   autoria entre participantes, entrega incerta, discordância e acolhimento/
   humor após mudança de condição. Definir evidências e critérios antes.
2. Comparar A = pipeline atual e B = estado explícito + referências aprovadas
   selecionadas. Mesma base/quantização, cenário, orçamento e configuração.
   Alternar ordem A/B e registrar sementes, prompt hash, carga/cache e recursos.
3. Julgar às cegas, por caso, os erros críticos e quatro dimensões existentes:
   especificidade, persona, continuidade e naturalidade. Primeiro piloto de
   36 diálogos: seis casos × três perfis × duas variantes; resultado exploratório,
   não significância estatística ou homologação geral.
4. Se houver melhoria, validar em situações reservadas inéditas. Se não houver,
   separar o efeito de grounding do de referências antes de mexer em temperatura,
   thinking ou modelo. Não alongar uma sequência sem hipótese verificável.
5. Depois, e só com dados individualmente aprovados, considerar um treino
   candidato curto e avaliar generalização/recarga no aluno. Não iniciar noite
   automática ou 12 horas com material cuja qualidade segue não homologada.

Métricas: erros críticos/número de respostas, falsos aceites/rejeições do crítico,
preferência humana A/B, notas por perfil, duplicatas, cobertura, tokens/tempo
por exemplo aprovado e custo dos rejeitados. Separar carga de geração e
informar amostra/limitações. Relatar todas as falhas, não só os melhores exemplos.

Critério proposto para prosseguir: nenhum erro crítico no conjunto controlado,
melhoria humana no conteúdo/persona sem regressão de autoria/continuidade e
custo conhecido. Isso não garante ausência de erro no uso aberto.

## 6. Trocar o professor ou usar “uncensored”?

**Não é a primeira solução sustentada pelos dados.** Os erros reproduzidos
ocorreram em quebra-cabeça, livro e entrega de arquivo: não eram recusas de
conteúdo. Os ensaios não isolam censura como causa de certeza inventada ou
estilo genérico. Mudar alinhamento não demonstra corrigir essas habilidades.

Também não há prova de que o 35B seja suficiente. Só vale concluir limitação
do modelo depois de comparar o método com evidências explícitas e referências
realmente aprovadas, em casos novos. Se o ganho não aparecer, documentar o teto
e então discutir substituição, sem baixar candidatos ou criar outro professor
por iniciativa nesta rodada.

Thinking mais longo e temperature mais alta não são soluções presumidas:
ensaios anteriores custaram mais com thinking sem vantagem clara de estilo.
Usá-los como variáveis controladas, não como promessa de emoção/consciência.

## 7. Superfície mínima de uma futura implementação

Principal: `laboratorio/professor_moe.py` — contratos de cenário, geração,
seleção de referências/feedback, crítica e métricas existentes. Consumidores a
revisar antes de mudar contratos: `painel.py`, `trabalhador.py`,
`rotina_noturna.py`, exportação e testes/probes do laboratório. UI somente se
a curadoria já existente precisar exibir evidência/parecer adicional.

Regressões: prefixo e correção sem futuro; consulta ausente/vazia/positiva;
autor/sujeito/ouvinte separados; recibo incerto imutável; referências da entidade
correta e por relevância; metáfora sem falsa reprovação; SHA invalidando aprovação;
estado do cenário preservado; rejeitado não exportado; fim de stream confirmado.
Inferência real é outro nível de prova, não substituível por esses mocks.

Não criar crítico/modelo/banco/scheduler novo. Não alterar identidades, memórias,
pesos originais ou margens de GPU para maquiar resultados. Promoção automática
de adaptador avaliado continua distinta de aprovação de conteúdo sintético.

## 8. Estado desta rodada

Somente dois documentos novos: este plano e
[o desafio autônomo](DESAFIO_AUTONOMO_BURACO_NEGRO_20261013.md).
Nenhuma suíte foi rodada nesta etapa de documentação. O último resultado
registrado continua **74/74 grupos oficiais e 234/234 testes do laboratório**,
não uma validação executada hoje para estes documentos. Código/alterações
preexistentes, memórias, propostas, modelos e configurações foram preservados.

Parecer: a infraestrutura impede mais dados defeituosos de entrar no treino,
mas **o professor ainda precisa comprovar boa escrita e avaliação confiável**.
Primeiro corrigir grounding e medir curadoria; depois qualidade de persona;
só então treino e avaliação no aluno. O desafio permanece documentado, não iniciado.
