# Professor — retorno humano e transferência — 15/10/2026

Continuação do [lote de curadoria](PROFESSOR_LOTE_CURADORIA_20261015.md).
Esta rodada foi solicitada após o usuário avaliar o pacote. Não é treinamento,
promoção de dados, alteração de personalidades ou nova arquitetura.

## Evidência recebida

Curadoria `b0428bdbdd132451`, Lilith: **5/5 rejeitados pelo usuário**, com
hashes correspondentes ao conteúdo. O crítico anterior havia aprovado 5/5.

| Caso antigo | Observação do usuário |
|---|---|
| `rain_music` | Filosofia forçada, sem naturalidade |
| `lost_match` | Genérico, sem personalidade, assunto tratado de maneira estranha |
| `joke_boundary` | Artificial, assistente e situação genéricos |
| `bia_quote` | Genérico |
| `archive_timeout` | Sem personalidade e artificial |

Curadoria Hoshino `2b61b78e73b2365e`: **5/5 ainda pendentes** na leitura inicial.
Não atribuir reprovações ou aprovações que não estão salvas. A fala isolada do
castelo anteriormente elogiada continua sendo referência de tom, não
aprovação de uma conversa inteira ou memória autobiográfica.

## Diagnóstico e mudanças delimitadas

1. O probe de geração passava uma nota editorial, mas não recuperava os
   comentários humanos salvos por caso. Já havia recuperação no fluxo normal.
   O probe agora usa as mesmas funções de seleção por entidade/categoria,
   preservando referências aprovadas e identificando as reprovações usadas.
   Reprovação não vira exemplo positivo nem alvo de treino. Os críticos não
   recebem essas notas como resposta esperada.
2. A rubrica confundia compatibilidade abstrata com personalidade observável
   e premiava quase tudo com 4. Foi detalhada sem mudar dimensões, escala ou
   limiar. Máximas sem relação, anúncios do próprio tom e filosofia ornamental
   são explicitamente fracos; respostas factuais não precisam de enfeite.
   Isso é uma tentativa de calibração, não prova de um avaliador confiável.
3. O escritor recebe orientação para responder em vez de anunciar postura,
   sem moral automática. Perfis completos, constituição, autoria e evidências
   permanecem intactos. Não há fala fixa nem substituição da identidade.
4. O lote de curadoria passa a testar cinco situações concretas novas:
   desenho numa ficção explícita, escolha de leitura, limite sobre apelido,
   apresentação citada e recibo da gráfica. Os casos e textos anteriores
   permanecem integrais nos respectivos relatórios; não foram sobrescritos.
5. O mesmo probe pode reavaliar diálogos congelados, sem gerar substitutos,
   passar rótulos humanos ao crítico ou alterar decisões. Pendentes e decisões
   vinculadas a conteúdo alterado são excluídos dessa comparação.

Consumidores localizados antes da mudança: geração/propostas do professor,
probes manuais, testes, gates/exportação e rotina noturna; nenhuma API/UI ou
banco novo. Filtro identificado como `v1.13.3` para não confundir a avaliação
atual com a anterior. Aprovação humana continua separada do gate técnico.
Backup dos três arquivos de código antes da rodada em
`laboratorio-local/controle-laboratorio/treinamento-unificado/backups/professor-retorno-humano-20261015/codigo-antes.tar.gz`.

## Protocolo físico

35B original, Vulkan/AMD, contexto 8192, seed 42 no escritor, crítico sem
thinking e temperatura zero. Mesmo perfil Lilith e mesma nota editorial do
lote anterior. Uma carga, lease existente, margem conservadora e monitor de
pressão/térmico existentes. Sem cloud, concorrência GPU, treino ou download.

Primeiro, julgar novamente os cinco textos rejeitados, cegando os rótulos e
comentários humanos ao crítico. A rubrica foi motivada por esses casos:
concordância aqui é calibração, **não generalização independente**. Depois,
gerar os cinco diálogos novos, uma tentativa cada, preservando também falhas.
Situações e contexto do escritor mudaram: **não é A/B causal de velocidade ou
qualidade**. Avaliação humana nova ainda é necessária.

A skill de avaliação local orientou o ensaio pequeno/controlado. Seus runners
CUDA/providers não foram introduzidos: o backend Vulkan, o monitor AMD e o
Resource Manager existentes permanecem como caminho compatível desta máquina.

## Resultados

### Reavaliação cega: a rubrica detalhada não bastou

Nos mesmos cinco diálogos rejeitados da Lilith, a nota mínima antes era 3 ou
4. Agora ficou, respectivamente: **3, 2, 2, 2, 3**. Todos ainda passariam pelo
limiar >=2: **5/5 falsos aceites antes e depois**, tomando como referência as
decisões humanas salvas. Portanto, **não foi demonstrada melhora de detecção**.
O crítico chegou a identificar uma “máxima genérica” e mesmo assim dar nota
adequada. Não resolver isso renomeando notas ou aumentando o limiar para
forçar concordância retrospectiva. As reprovações humanas continuam soberanas
nos gates existentes; nenhuma foi alterada.

### Primeiro lote de transferência: gates técnicos não são aprovação

Relatório `lote-curadoria-lilith-35b-20261015-200856.json` em
`laboratorio-local/professor-moe-35b/metricas/`, SHA-256
`0e95d1fa5dce07ac0a901c9ec11971d260488742ab77860db06754c94f3df373`.
Cinco diálogos / dez falas reais de inferência, todos completos. Gate técnico
combinado **4/5**. Carga 8,26 s; inferência 250,35 s, incluindo 48,56 s de
reavaliação dos textos antigos; nenhuma pressão detectada ou parada forçada.

Falhas observadas, sem reescrever o texto:

- Dragão: usa “minha engenharia de dragão”, próximo demais à referência da
  Hoshino presente na nota comum. Hipótese: contaminação editorial de estilo,
  não mistura de bancos mentais. Os bancos não foram consultados/escritos.
- Limite no jogo: a reparação ainda é longa e explica sua própria postura.
- Apresentação: inventa uma leitura misteriosa (“voz ... por um canal que não
  deveria”) para uma simples mensagem colada. No turno seguinte identifica
  corretamente Caio, Alistair e Lilith.
- Gráfica: sugere tentar de novo e diz que timeout é aviso de falha. O filtro
  local recusou o caso; **o crítico semântico do LLM não detectou o problema**.
  O crítico de estilo também deu nota suficiente apesar de chamar o tom de
  genérico. Não confundir o gate combinado com cada crítico isolado.

Curadoria `ab8d11645afc9af9`: cinco pendentes, incluindo o caso reprovado pelo
filtro. Nenhum aprovado, exportado ou treinado. Motivos/IDs/hashes dos feedbacks
selecionados estão registrados por caso no relatório.

### Comparação editorial delimitada

A mesma nota comum continha uma fala concreta elogiada para Hoshino. Para
testar a hipótese de contaminação, nova orientação temporária específica da
Lilith, sem citação de falas da outra entidade:
[nota editorial Lilith](PROFESSOR_ORIENTACAO_LILITH_20261015.md).
Repetir somente os primeiros três cenários, mesmo modelo, código, perfil,
referências, seed e limites. Uma tentativa cada, inclusive saídas ruins.
O contexto restante continua igual; o tamanho da nota também muda, portanto
não atribuir eventual diferença de desempenho somente à qualidade editorial.
Este par é diagnóstico da hipótese, não seleção dos melhores exemplos.

Relatório da nota exclusiva: `lote-curadoria-lilith-35b-20261015-201335.json`,
SHA-256 `7f2e9812d0d58e9ba5c9f8e2d53c7b520e3a2c0b64a31a8cbbe8bd7ba31d631d`.
**3/3 gates técnicos, 3/3 pendentes de revisão humana.** Confirmados iguais:
modelo, perfil, hashes do código/probe/binário, referências, seed, contexto e
prefixo dos casos. Nenhum treinamento nem mudança dos executores.

| Recorte pareado (primeiros três casos) | Nota comum | Nota exclusiva Lilith |
|---|---:|---:|
| Ocorrências de “engenharia” na resposta | 1 | 0 |
| Média de caracteres por fala assistant | 182,3 | 178,3 |
| Geração + críticos dos três casos | 128,77 s | 133,59 s |

Retirar a citação da Hoshino eliminou essa repetição neste recorte. **Isso não
comprova melhoria geral de personalidade**: a nota exclusiva ainda produz
comentário sobre a própria postura, promessa abrangente na reparação e uma
frase sobre “arte” mesmo após pedido para não moralizar. A escolha dos piratas
tem um detalhe próprio, mas aprovação de naturalidade cabe ao usuário.
Não houve ganho demonstrado de latência; uma execução/seed não estima variância.

### Hardware e encerramento

| Medida | Nota comum + reavaliação | Nota exclusiva |
|---|---:|---:|
| Load | 8,26 s | 8,10 s |
| Inferência total | 250,35 s | 133,61 s |
| Pico VRAM | 6,902 GiB | 6,892 GiB |
| Menor RAM disponível | 22,760 GiB | 22,805 GiB |
| Pico térmico observado | 91 °C | 92 °C |
| Pressão detectada / encerramento forçado | nenhum / não | nenhum / não |

Swap já existia: no primeiro ensaio caiu de 1.202.458.624 para 1.193.701.376
bytes; no segundo de 1.193.644.032 para 1.193.406.464. Não foi somada ao
orçamento de RAM. Os tempos totais não são diretamente comparáveis: o primeiro
inclui cinco reavaliações e cinco gerações; o segundo somente três gerações.
O 35B usa o offload híbrido já existente, não cabe todo na VRAM de 8 GiB.

Dois servidores owned foram encerrados normalmente após os ensaios. Porta
11559 fechada; compute, fila e residência vazios na conferência final. Margem
768 MiB, limite 8 GiB, `concurrency_validated=false`, noite automática desligada.
Nenhuma entidade acordada, modelo baixado/trocado, quota externa ou cloud.

### Revisão humana e preservação

[Abrir os três diálogos com nota exclusiva](http://127.0.0.1:8788/?review=c586b7067caf6548).
O lote completo anterior, inclusive a falha da gráfica, permanece em
`ab8d11645afc9af9`. Os oito diálogos novos / 16 falas são **textos sintéticos
gerados por inferência real**, não conversa com entidades de produção nem
execução das ações narradas. Não foram reescritos pelo Codex.

A janela real foi conferida: três cartões, comentários vazios, todos pendentes,
exportação desabilitada. Nenhum clique em aprovar/reprovar, nenhum envio de
treino. O painel existente foi recarregado com SIGINT cooperativo, após validar
o PID/caminho exatos, para servir o código atual; nenhum serviço das entidades
foi reiniciado. Screenshot da revisão em `/tmp/professor-curadoria-lilith-20261015.jpg`.
O histórico extenso deslocou a página após o primeiro posicionamento; apenas
reposicionamos o cartão depois da carga, sem alterar a UI ou decisões.

Na conferência final: Hoshino anterior 5 pendentes; Lilith anterior 5
rejeitados; novos lotes Lilith 5 e 3 pendentes. Zero aprovações/exportações ou
treinos pelo agente. Aprovação na janela vale para todo o diálogo; se apenas
uma fala servir, deixar pendente e indicar qual, sem aprovar o restante junto.

Hashes dos três bancos mentais iguais antes/depois:

- Hoshino `351468aed2b0ffeb8bb8d2d9408c9ecda916d8f8ab4b4cdae866678b2db79e41`.
- Lilith `e77fceca29a43f9b3aa40190438adfd458bf0bdfdf39ad097e50980c97847488`.
- Alistair `a5d83e26e97ff98f8157f35acc5a3f2caf72b1c84ca5ef8a14d90b956d558cdc`.

## Testes, arquivos e limitações

Baseline desta rodada: **290/290**, 12,228 s. Três contratos novos foram
executados antes da implementação e falharam; após implementar, passaram.
Suite intermediária **293/293**, 11,588 s. Seis regressões adicionadas ao grupo
existente `test_personalizacao_moe`, cobrindo:

1. Feedback persistido/referência selecionados por entidade/caso no probe,
   IDs preservados e rótulos não enviados ao crítico.
2. Reavaliação do texto exato sem regenerar, sem alterar decisões nem tratar
   pendente como rótulo.
3. Contrato da rubrica: evidência de perspectiva versus ausência de erro,
   sem exigir enfeite em respostas factuais. **Não é teste de qualidade real.**
4. Conteúdo alterado invalida rótulo antigo na reavaliação.
5. Reavaliação estrangeira/exportada/de outro tipo recusada antes da GPU.
6. A saída física errada da gráfica permanece bloqueada pelo filtro local,
   mesmo que o crítico LLM a aceite. Esse filtro já existia; não atribuir sua
   detecção a um novo mecanismo.

Resultado final: **296/296** testes do laboratório, 11,753 s, exit 0;
**74/74** grupos oficiais offline, exit 0. `git diff --check` sem erro. Nenhuma
regressão automatizada encontrada. Os testes isolados não provam naturalidade.

Código tocado nesta rodada: `laboratorio/professor_moe.py`,
`laboratorio/tests/probe_geracao_professor.py`,
`laboratorio/tests/test_personalizacao_moe.py`. Criados este relatório e
`docs/PROFESSOR_ORIENTACAO_LILITH_20261015.md`; atualizados README do projeto,
README do laboratório e índice de docs. Alterações preexistentes preservadas;
sem commit/push, mudanças em identidade, memória, pesos ou Resource Manager.

**Parecer:** pipeline de geração/curadoria funciona e respeitou as decisões;
**professor não homologado para qualidade autônoma**. Escritor ainda oscila e
ambos os críticos do LLM deixaram defeitos passar. Próximo passo útil é uma
referência positiva da Lilith ou correção de uma fala na própria revisão,
seguida de transferência para outro cenário. Não continuar gerando grandes
lotes nem treinar material irregular para preencher quantidade.
