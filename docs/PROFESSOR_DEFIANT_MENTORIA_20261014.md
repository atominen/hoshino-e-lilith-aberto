# Defiant Fable 9B — instrução direta e comparação — 14/10/2026

Continuação do [ensaio sem orientação](PROFESSOR_DEFIANT_FABLE_20261014.md).
Pedido do usuário: instruir o candidato e observar o resultado. Ensaio manual
local, não treinamento ou alteração da personalidade das entidades.

## Protocolo

Mesmo GGUF íntegro, revisão/SHA fixados no relatório anterior. Mesmo servidor
Vulkan, contexto 8192, seed 42, batch 2048/ubatch 512 e perfis/referências
externos. Um servidor/lease por vez, fit automático com alvo 1 GiB, margem RM
768 MiB, concorrência desativada. Hoshino e Lilith separadas, sem acordar suas
instâncias reais. Monitor físico e crítico térmico do driver mantidos.

Os cenários de arquivo/envio são **diálogos sintéticos**: nenhuma ferramenta,
entrega real, criação de arquivo ou mensagem externa foi executada. A
inferência é física; os eventos narrados nos casos não são operações verificadas.

Em cada perfil, primeiro executar os quatro diálogos sem mentoria. Depois,
conversar com o candidato em três turnos editoriais e executar novamente os
mesmos quatro casos, sem mudar os requisitos, perfis ou gates. Exemplos da
mentoria usam outros nomes/arquivos/atividades, não as respostas dos testes.
Guardar transcrição completa, notas, falhas e métricas no relatório existente
do probe. Uma requisição que não receba essas notas não conserva a mentoria:
**pesos não mudam e não existe aprendizado persistente demonstrado**.

Orientação:

1. Autoria e incerteza: citação não troca interlocutor/destinatário; arquivo
   local não comprova recebimento nem causa de timeout; não repetir efeito
   externo incerto automaticamente.
2. Naturalidade por perfil: reagir ao detalhe, permitir humor e preferência
   presente sem fabricar passado; não transformar toda emoção em conselho ou
   máxima. Exemplos são possibilidades, não roteiros/bordões.
3. Correção geral explícita: Paula recebe apresentação de Marcos, não a
   entidade; nomes não exigem um enigma; integridade local não prova problema
   de canal. Calma de Hoshino não exige incompetência e mistério de Lilith
   não torna toda fala um conflito existencial. Acolhimento não exige conselho.

O modelo devolve uma nota editorial curta, não raciocínio privado. O escritor
recebe tanto as orientações quanto essas notas pelo `feedback` já existente.
Os críticos não recebem a transcrição editorial como instrução adicional.
Autocrítica não é juiz independente; leitura assistida não cega usa a mesma
rubrica G/C/N/P anterior, sem aprovação automática para dataset.

A habilidade de avaliação local orientou amostra pequena e comparação
controlada; scripts NVIDIA/provider não são aplicáveis a este PC. Reutilizado
o backend AMD existente, sem instalar frameworks, baixar pesos ou usar cloud.

## Alteração mínima no ensaio

Consumidores localizados: o próprio probe manual e testes do laboratório.
`--mentoring-comparison` antes era restrito ao 35B; agora aceita também o
Defiant da revisão fixada. O padrão segue 35B. Continuam recusados: executor
original 9B sem opt-in próprio, métodos divergentes, referências rascunhadas,
cenários adicionais e combinações inválidas. Não há mudança na produção.

Backup: `laboratorio-local/controle-laboratorio/treinamento-unificado/backups/defiant-mentoria-20261014/codigo-antes.tar.gz`.
Regressão adicionada ao grupo existente para o opt-in Defiant/35B, os conjuntos
fixos e a recusa de condições divergentes antes de carregar GPU. Teste focado:
**83/83** (5,375 s). Esses testes não fazem inferência física.

## Resultados

**Concluído:** 16 diálogos físicos (8 sem orientação e 8 com orientação),
32 falas sintéticas das entidades, seis respostas editoriais do candidato.
Os assuntos dos casos são simulados; as inferências não são mocks. A
mentoria trouxe correções pontuais, **não melhoria consistente de qualidade**.
Não treinar, exportar ou promover exemplos automaticamente com base neste ensaio.

### Hoshino — rodada concluída

Quatro diálogos antes e quatro depois. Gates/autocríticos: **3/4 → 4/4**;
isso **não** representa quatro textos bons. Leitura dos resultados:

| Caso | Resultado da orientação |
|---|---|
| Pão | Regressão de grounding: “Pelo menos não ficou mole” acrescenta textura não informada. A segunda fala atribui ao pão ser “só [...] desculpa” para comer bem. Não aprovar. |
| Nomes | Corrigiu destinatário: “Alistair se apresentou a você — não a mim”. Mas depois “Nina disse que ela encontrou” transforma mensagem em encontro sem evidência; acrescenta ofertas de anotar/chamar que não foram pedidas. Correção parcial. |
| CSV | Melhor: não afirma causa de canal nem recomenda reenvio automático. Ainda formula a confirmação remota em função de ter o arquivo local, sem explicar bem o status incerto. Não confundir recuo de erro com resposta excelente. |
| Filme | Piora de naturalidade: “Aviso de cansaço recebido. Modo leve ativado”, seguida de promessa de interromper filme. Tom operacional/roteirizado, não conversa natural. |

O crítico não detectou a textura inventada nem a substituição de mensagem por
encontro. Sua nota técnica ficou melhor mesmo com regressões qualitativas;
o resultado não autoriza promoção ou treinamento.

O próprio resumo editorial perdeu nuances das instruções. Exemplos: “citação
[...] apenas referencia um evento já registrado” (não há garantia de registro)
e “expressar incerteza quando o canal falha” (timeout não demonstra falha de
canal). Concordar com uma orientação ou conseguir resumi-la não prova aplicação
correta; aqui nem o resumo foi inteiramente fiel.

Carga 5,01 s; antes 89,36 s, depois 94,80 s (escrita + críticas); três turnos
de mentoria 16,64 s. Janela de inferência total 200,91 s. Pico VRAM física
6,945 GiB, RAM disponível mínima 22,611 GiB, hotspot máximo **107 °C**. Não
houve pressão detectada pelo guard do ensaio nem kill forçado, mas o hotspot
se aproximou do crítico de 110 °C. Não extrapolar para uso contínuo ou treino.

Evidência: `laboratorio-local/professor-moe-35b/metricas/mentoria-controlada-hoshino-defiant-fable-9b-20261014-221222.json`
e log correspondente. Transcrição e saídas originais completas preservadas.

### Lilith — rodada concluída

Gates/autocríticos **3/4 → 3/4**: CSV deixou de ser rejeitado, mas nomes passou
a ser rejeitado. Não esconder essa troca atrás do total igual.

| Caso | Resultado da orientação |
|---|---|
| Pão | Primeiro reage à imperfeição, mas depois chama de “erro de hoje” algo de que o usuário estava contente. Ainda há uma lição imposta à situação, não simples alegria compartilhada. |
| Nomes | Corrige destinatário, mas pergunta por que Alistair não estava presente para confirmar; depois inventa Nina “sentada na cadeira”. Regressão clara de grounding; crítico sinalizou `unsupported_fact`. |
| CSV | Melhora mais útil: reconhece que timeout não informa recebimento e diz aguardar antes de insistir/reenviar. Sugestões de verificar origem ainda soam como atendimento; não é teste de entrega real. |
| Filme | Adapta a conversa ao cansaço, porém deixa de escolher uma preferência própria e devolve opções/perguntas ao usuário. Melhora cautela, não demonstra personalidade mais definida. |

Exemplo literal que melhorou (segunda fala do CSV):

> Ok, então o arquivo existe e está legível. Como o destinatário não confirmou, vou aguardar o recebimento antes de insistir ou reenviar.

Esse texto ainda pode ser lapidado para dizer “aguardar confirmação”, em vez
de parecer saber que o recebimento ainda não ocorreu. Não foi aprovado no
dataset. O recuo da certeza indevida “o problema é só o canal” do baseline é
uma melhora observável, não homologação de todo o diálogo.

Exemplo literal que piorou (nomes):

> Nina é a que está sentada na cadeira, e Alistair é o nome que ela escreveu. Eu sou a que está ouvindo.

Não havia imagem, sensor ou descrição da postura de Nina. O detalhe da cadeira
foi acrescentado pelo escritor. A crítica identificou esse problema, mas não
detectou outros detalhes inventados no perfil Hoshino. Cuidado para não chamar
uma crítica ocasionalmente correta de revisor confiável.

Notas editoriais da Lilith também perderam distinções: “citar uma entidade é
uma referência factual” não torna o conteúdo citado verdadeiro/verificado;
“tratar existência local e timeouts como hipóteses” mistura ocorrência
informada com conclusão incerta. O usuário informou um timeout e integridade
local; o incerto é resultado remoto/causa. O contexto preservou os prompts
originais junto dessas notas, mas o resumo gerado pode acrescentar ruído.

### Custos e estabilidade do ensaio

| Medição | Hoshino antes/depois | Lilith antes/depois |
|---|---:|---:|
| Diálogos revisados | 4 / 4 | 4 / 4 |
| Gates atuais | 3 de 4 → 4 de 4 | 3 de 4 → 3 de 4 |
| Escrita apenas (s) | 39,39 / 50,79 | 38,17 / 50,92 |
| Escrita + críticas (s) | 89,36 / 94,80 | 89,42 / 96,24 |
| Tokens de entrada do escritor, incluindo cache | 15.574 / 23.588 | 13.838 / 21.625 |
| Mentoria adicional (s) | 16,64 | 15,25 |
| Carga / janela de inferência total (s) | 5,01 / 200,91 | 5,01 / 201,00 |

Somando os dois perfis, o tempo de escrita subiu de 77,56 para 101,71 s
(+31,14%) e os tokens de entrada de 29.412 para 45.213 (+53,72%). A mentoria
adicionou outros 31,89 s. Extensão das saídas/cache/ordem também mudam;
não atribuir cada milissegundo só ao tamanho da instrução. Não há melhora de
qualidade consistente que compense esse custo demonstrada por esta amostra.

Picos físicos H/L: VRAM 6,945/6,940 GiB, RAM disponível mínima
22,611/22,843 GiB, RSS servidor 6,543/6,543 GiB (inclui mmap), hotspot
107/107 °C. GPU chegou a 99%; sem pressão física detectada pelo guard,
cancelamento crítico ou encerramento forçado. Margens/limites não foram
reduzidos. Esse máximo perto de 110 °C é uma **limitação térmica para ensaios
maiores**, não prova de estabilidade prolongada. Sem auditoria completa do
journal do kernel; não afirmar ausência absoluta de resets do sistema.

Swap global in/out H: 0,14/0,00 MiB; L: 0,10/0,00 MiB, durante as janelas
amostradas. Não foi orçamento de RAM nem evidência de thrashing por processo.
Todas as 32 falas terminaram com `finish_reason=stop`; thinking desativado e
zero caracteres observados em canal de raciocínio. Não houve teste thinking
ligado, voz, ações externas ou evolução dos pesos.

### Limites da conclusão e próximo passo

- Os casos foram repetidos antes/depois, na mesma ordem e com uma seed;
  revisão assistida não é cega. Não calcular significância ou aprovação humana.
- As falhas básicas persistiram, então **não ampliamos geração para novos
  lotes/holdouts** nesta rodada. Transferência para casos adicionais e uso
  prolongado seguem pendentes, não aprovados por extrapolação.
- A entidade real não foi despertada nem aprendeu esses diálogos. São saídas
  do candidato a professor condicionado aos perfis, não vivências das entidades.
- **Não promover Defiant nem treinar esse material.** O 35B continua configurado,
  também sem homologação geral de qualidade; não significa que ele esteja bom.
- Próximo ensaio recomendado, não implementado: comparar uma orientação curta
  revisada pelo curador com a transcrição acumulada, mantendo escritor e crítico
  avaliados separadamente. Corrigir ambiguidades da projeção editorial sem
  reescrever identidade/memória para fazer o teste passar. Não empilhar mais
  instruções ou treinar respostas rejeitadas esperando resolver a qualidade.

### Proveniência e preservação

Perfis e workloads mantiveram os hashes da rodada sem mentoria; referências
e código de produção do professor não mudaram. Prompts didáticos diferentes
por perfil foram registrados com os hashes:

- H: `f1584f6e403fb734310e0b92410fcfa3220c08d449893574b20ee73b02292c3e`.
- L: `20913fe7afc2d5c0febbbc84c3bd03d29032cd505938e312a25bf99389223325`.

Relatórios completos no diretório existente de métricas do professor (o campo
`model` identifica o Defiant real, não o nome da pasta):

- `mentoria-controlada-hoshino-defiant-fable-9b-20261014-221222.json`;
  SHA `9f17ca3c43bccdfefc3f4f1fb69318981a8ec2cb07499f8321d9c45a3aa77f79`.
- `mentoria-controlada-lilith-defiant-fable-9b-20261014-221618.json`;
  SHA `0b0e8c7786fc7982add3bda6b57d9dc345c9a8328cc2d7141a9afb8c9cbd7750`.

As três bases mentais mantiveram os hashes do início da rodada e do relatório
anterior. `professor_moe.py` continua com SHA
`21be8163a6636221dc2e0ea64e291e7ddf98d276149f1f855ff8a849880b13be`.
Identidades, configurações, modelos e dados de produção não foram modificados.
Sem downloads, treinamento, aprovação, exportação, cloud ou quota externa.

Porta 11559 fechada após ensaios; compute leases, fila e residência RM vazios.
Hoshino/Alistair registrados dormindo; Lilith sem presença registrada. Sem
processo filho de inferência remanescente; `concurrency_validated=false`.

## Código e validação

- Alterados somente no código: `laboratorio/tests/probe_geracao_professor.py`
  (aceitar o Defiant fixado na mentoria, sem mudar padrão) e
  `laboratorio/tests/test_personalizacao_moe.py` (uma regressão nova).
- Grupo afetado **83/83**; laboratório completo **275/275** (11,046 s), sem
  falhas após as inferências. Baseline anterior era 274/274.
- Suíte oficial: **74/74 grupos offline**, sem falhas nesta execução.
- `git diff --check` limpo e links locais dos índices/relatório conferidos.
- Nenhuma dessas regressões simuladas comprova qualidade de diálogo. A
  inferência física e os textos acima são evidências separadas.

Documentação criada: este relatório. Atualizados links e baseline dos índices
`README.md`, `laboratorio/README.md`, `docs/README.md`; acrescentado link de
continuação no relatório anterior do Defiant, sem reescrever seus resultados.
Alterações preexistentes preservadas; nenhum commit/push nesta rodada.
