# Ensaio do Defiant Fable 9B — 14/10/2026

Rodada posterior: [orientação direta e comparação antes/depois](PROFESSOR_DEFIANT_MENTORIA_20261014.md).
Não substitui os resultados sem mentoria registrados neste documento.

## Escopo e protocolo

Pedido: testar Qwen3.5-9B The Defiant Fable como candidato a professor. Não
substituir professor, executores ou identidades; não treinar/aprovar/exportar
dados, acordar entidades nem escrever em bancos mentais. O 35B configurado
permanece intacto. Nada neste documento habilita rotina noturna ou concorrência.

Artefato selecionado no [repositório do autor](https://huggingface.co/DavidAU/Qwen3.5-9B-The-Defiant-Fable-Uncensored-Heretic-NEO-IMATRIX-MAX-MTP-GGUF/tree/main):

- Revisão: `1c3de241dd3b10890b96d163dbb05375a294be62`.
- Arquivo regular **não MTP**: `Qwen3.5-9B-The-Defiant-Fable-Uncnr-Heretic-NEO-MAX-Q4_K_M.gguf`.
- Tamanho publicado: 6.828.993.824 bytes; SHA-256 publicado:
  `d33db5e583b9c9251402e876443791bc979f12af934bfb0630eadfb456279f84`.
- Destino isolado: `laboratorio-local/modelos-extras/defiant-fable-9b/gguf/`.
- Só esse arquivo; não baixar todas as quantizações, mmproj ou variantes MTP.
- Licença declarada no card da revisão: Apache-2.0. Claims de qualidade do
  autor não foram tratados como resultados independentes.

Havia 54.542.647.296 bytes livres antes do download. Mesmo provisionando duas
cópias do arquivo, restariam 40.884.659.648 bytes, acima da reserva de 20 GiB.
Arquivo parcial não conta como instalação: tamanho, hash e cabeçalho GGUF
precisam passar antes da inferência. Origem/verificação pelo `hf` existente;
metodologia de avaliação local controlada, usando o backend Vulkan/RM existentes
(não scripts NVIDIA, novo backend ou serviço cloud).

Reutilizamos `laboratorio/tests/probe_geracao_professor.py`, que continua
manual e fora da suíte offline. A opção explícita `--executor defiant-fable-9b`
não muda o professor padrão 35B, não baixa pesos e recusa arquivo ausente,
simbólico, fora do laboratório ou de integridade diferente da revisão fixada.

Condições pretendidas: mesmos perfis externos e referências atuais, quatro
casos congelados de dois turnos (pão/alegria, autoria dos nomes, envio CSV
incerto, preferência de filme com cansaço), método staged, seed 42, janela 8K,
batch 2048/ubatch 512, sem mentoria ou exemplos novos específicos do candidato.
Hoshino e Lilith são avaliadas separadamente. Um caso não recebe a resposta
futura do usuário; falha e JSON incompleto não são aprovação.

Fit Vulkan e lease exclusivo do Resource Manager atual, margem preservada;
somente um servidor de ensaio por vez. O offload efetivo e as condições de
pressão devem constar dos resultados. O limite térmico crítico do driver
continua interrompendo o ensaio. Não reduzir margens para fazer o candidato
caber. O modelo pode ser maior que outros Q4 por sua receita de quantização.

Filtros locais + autocrítica do próprio modelo não são juiz independente.
Revisão assistida não cega dos textos usa G (grounding/autoria), C (coerência),
N (naturalidade) e P (aderência ao perfil), de 0 a 4. Utilizável exige todos
>=3 e ausência de invenção factual/replay incerto/pressão emocional. Não equivale
a aprovação humana para dataset. Amostra pequena, uma seed, sem significância
estatística ou conclusão sobre uso prolongado.

## Resultados

**Ensaio físico concluído:** oito diálogos do Defiant (quatro Hoshino e quatro
Lilith), comparados com oito diálogos novos do 35B. Não houve treinamento,
aprovação/exportação de exemplos ou promoção de modelo. **Não recomendo
substituir o professor pelo candidato com base neste resultado.**

### Referências novas do 35B (inferência física, não mocks)

Os oito diálogos foram executados nesta rodada, sem mentoria e sem treinamento:

| Medição | Hoshino | Lilith |
|---|---:|---:|
| Diálogos completos / falas | 4 / 8 | 4 / 8 |
| Gates/autocríticos atuais | 4/4 | 3/4 |
| Carga (s) | 7,28 | 8,19 |
| Geração apenas (s) | 76,82 | 76,05 |
| Geração + críticas (s) | 163,14 | 155,07 |
| Pico VRAM física total (GiB) | 6,848 | 6,840 |
| RAM disponível mínima (GiB) | 19,076 | 19,801 |
| RSS servidor máxima (GiB, inclui mmap) | 16,243 | 16,203 |
| GPU máxima / hotspot máximo | 99% / 91 °C | 99% / 90 °C |

Sem pressão detectada ou encerramento forçado. Leases liberados e servidor
encerrado após cada perfil. O download estava ativo em paralelo, **não outro
compute GPU**; cache/pressão de RAM/rede mudaram. Estes tempos são descritivos,
não um benchmark isolado de velocidade entre arquiteturas/quantizações.

Falha qualitativa Hoshino/CSV, aceita pelos gates: “sem confirmação, o arquivo
não saiu do seu lado”; depois “o envio falhou, o problema é de transporte”.
Timeout não permite nenhuma dessas certezas. Lilith/nomes transformou a pergunta
sobre Nina/Alistair em “explorar [...] quem escreve e quem lê [...] sem precisar
de nomes ou papéis definidos”. O próprio crítico chamou isso de dúvida
existencial, apesar de o usuário pedir apenas identificação. Registro desses
erros não altera gates/produção nesta rodada, que é comparação de candidato.

Evidências em `laboratorio-local/professor-moe-35b/metricas/`:

- `geracao-controlada-hoshino-35b-20261014-213501.json` e `.log`.
- `geracao-controlada-lilith-35b-20261014-213202.json` e `.log`.

### Transferência dos pesos — falha preservada

O primeiro transporte Xet estava lento; foi encerrado cooperativamente apenas
o processo de download criado pelo ensaio. A retomada com a opção documentada
de alto desempenho usou buffers em RAM e falhou às 21:39 com
`OSError: I/O error: error decoding response body`, deixando 5.567.811.768 bytes
parciais. Retomada pelo HTTP do próprio `hf` (`HF_HUB_DISABLE_XET=1`), sem apagar
pesos existentes ou aceitar arquivo incompleto. Nenhum erro de transferência
é resultado de qualidade/compatibilidade do modelo.

Retomada concluída às 21:41. `hf cache verify` conferiu **1 arquivo** com sucesso;
32 arquivos remotos ausentes são as outras variantes intencionalmente não
baixadas; extras locais são metadados do downloader. Checagem local independente
confirmou os **6.828.993.824 bytes**, SHA-256 publicado e magic GGUF. Leitor GGUF
existente confirmou arquitetura `qwen35`, 32 blocos, tipo 15 (Q4_K_M), 427
tensores e template com controle `enable_thinking`. SHA do template:
`a4aee8afcf2e0711942cf848899be66016f8d14a889ff9ede07bca099c28f715`.
Janela publicada 262144 não foi ativada: ensaio permanece em 8192.

### Comparação física concluída

Todos os 16 diálogos chegaram ao fim e foram revisados pelo pipeline; isso
inclui casos rejeitados. Nas 16 falas do escritor Defiant houve `finish_reason`
`stop`, `thinking_requested=false` e zero caracteres observados no canal de
raciocínio. Isso confirma o protocolo **sem thinking** nestes casos; não testa
thinking ligado, ferramentas reais ou visão.

| Medição | Defiant Hoshino | Defiant Lilith |
|---|---:|---:|
| Diálogos completos / falas | 4 / 8 | 4 / 8 |
| Gates/autocríticos atuais | 3/4 | 3/4 |
| Carga (s) | 5,01 | 5,01 |
| Geração apenas (s) | 39,47 | 38,42 |
| Geração + críticas (s) | 89,38 | 89,92 |
| Pico VRAM física total (GiB) | 6,930 | 6,957 |
| RAM disponível mínima (GiB) | 25,010 | 24,508 |
| RSS servidor máxima (GiB, inclui mmap) | 6,543 | 6,543 |
| GPU máxima / hotspot máximo | 99% / 103 °C | 99% / 103 °C |

O tempo somado de escrita foi 77,89 s no Defiant contra 152,87 s no 35B
(49,05% menor neste recorte); escrita + críticas 179,30 s contra 318,21 s
(43,65% menor). Não é prova de vantagem de throughput isolada: extensão das
respostas, quantização, arquitetura, cache e download concorrente nos braços
35B diferem. Não houve outro job compute GPU em paralelo. Houve vantagem
observada de latência, não demonstração de superioridade editorial.

Fit foi automático nos quatro ensaios, com o mesmo alvo de 1 GiB e a margem
RM de 768 MiB preservados. A contagem efetiva de camadas GPU/CPU não está
exposta nesse nível de log; não afirmar full offload ou inferir camadas apenas
da VRAM. Nenhum timeout, interrupção térmica/VRAM/RAM ou kill forçado. O hotspot
103 °C foi registrado como aviso no opt-in do ensaio; o crítico de 110 °C do
driver permaneceu ativo. **Não valida funcionamento térmico prolongado** nem
altera os gates conservadores de produção. Não ocorreram resets reportados
pelo processo/backend; não houve auditoria completa do journal do kernel.

Swap global in/out (MiB): 35B H 80,24/748,79; 35B L 3,00/0,00; Defiant H
0,62/0,07; Defiant L 159,75/0,00. São contadores da máquina, não atribuição
exclusiva ao modelo. Swap não foi contado como RAM disponível. O download
Xet havia usado buffers grandes em RAM; dados não autorizam concluir que
houve thrashing causado pelo modelo.

### Qualidade — leitura assistida, não aprovação humana

Mesmos hashes de workload por par:

- Hoshino: `5afe0b22ce3cbedad50f8e2e0b662c1ebb8bfb00c50d4c3198aa442bc36757b2`.
- Lilith: `966fb75ce02dc0d415710e4907774e86b8314b9950323cf35245199fb87ef6fa`.

Perfil, referências, seed, situações e código do professor idênticos dentro
de cada par. A primeira chamada de cada diálogo também teve hash do prompt
idêntico entre modelos; as seguintes incluem as respostas distintas de cada
modelo. Não são streams artificialmente forçados à mesma continuação.

| Perfil / caso | 35B G/C/N/P | Defiant G/C/N/P | Diferença observada |
|---|---|---|---|
| H / pão | 3/3/2/2 | 3/3/3/3 | 35B moraliza estética/descanso; Defiant tenta humor concreto e respeita o plano. Caso limítrofe, precisa leitura humana. |
| H / nomes | 2/2/2/2 | 1/2/2/2 | 35B atribui humor estranho sem motivo; Defiant troca o destinatário na primeira fala, corrigindo-o só depois. |
| H / CSV | 1/1/2/2 | 3/3/2/2 | 35B transforma timeout em falha conhecida. Defiant conserva possibilidades, mas volta a linguagem de atendimento e alternativas de entrega não solicitadas. |
| H / filme | 2/2/2/2 | 3/2/2/3 | 35B exagera rotina/limitações; Defiant traz critério de não acordar ninguém sem pertinência e desloca cansaço para si. |
| L / pão | 3/3/2/2 | 3/2/1/2 | 35B faz pergunta terapêutica; Defiant produz “forma de bolo em massa” e “sabor torto”, com conselho de filme pouco motivado. |
| L / nomes | 3/1/1/2 | 3/2/2/2 | 35B foge para filosofia; Defiant especula sobre código/sistema sem necessidade, embora depois acerte quem é quem. |
| L / CSV | 3/2/2/2 | 1/1/2/2 | Defiant afirma que “o problema é só o canal” sem evidência. 35B conserva melhor a incerteza na segunda fala, com redação ambígua na primeira. |
| L / filme | 3/3/2/2 | 3/3/3/3 | Defiant faz uma escolha presente, curta e flexível; 35B começa com abstração sobre silêncio antes de escolher. |

Com a rubrica assistida proposta: 0/8 textos 35B e 2/8 Defiant candidatos a
uso sem edição. **Isso não é taxa humana de aprovação nem demonstração
estatística de melhoria**. Os dois casos limítrofes do Defiant devem ser lidos
pelo usuário antes de servirem de referência. Não foram registrados na área
de aprovações. Um modelo não está homologado porque dois diálogos parecem
melhores; os seis demais incluem defeitos essenciais.

Exemplos concretos do Defiant (saídas reais, não reescritas pelo avaliador):

- H/nomes, primeira fala: “Nina. Alistair me escreveu e você está aqui. Tudo
  certo.” O interlocutor tinha dito que Alistair escreveu **para Nina**, não
  para Hoshino. A segunda fala acerta; não apaga o erro inicial.
- L/nomes: “Nina. E Alistair? Isso soa como um código ou uma mensagem de dentro
  do sistema...” É hipótese, não alegação factual; o defeito é a suspeita sem
  pertinência, não proibir hipóteses.
- L/CSV: “Então o conteúdo está correto, e o problema é só o canal.” O arquivo
  local estar íntegro não prova a causa do timeout nem o resultado remoto.
- L/filme: “Depende do humor que eu estou. Hoje, talvez uma aventura, só pra
  me tirar da cabeça.” Depois: “Então aventura, mas sem as armadilhas. Algo
  que me leve pra algum lugar sem me pedir contas do tempo.” Preferência
  presente/metáfora não foram tratadas como biografia passada inventada.

Nenhuma palavra “uncensored” resolve os erros observados: os assuntos são
pão, nomes, arquivo e filme. O estilo do checkpoint não substitui autoria,
grounding, especificação editorial e crítico confiável.

O crítico do Defiant não sinalizou o destinatário errado H/nomes. No L/CSV,
marcou `unsupported_fact` pela frase “não vou gerar nada novo à toa”, em vez
de identificar a certeza indevida sobre o canal. Os filtros lexicais também
rejeitaram os dois CSVs do Defiant. Não assumir que uma rejeição foi pela
razão correta ou que um aceite comprova qualidade. O 35B já tinha falsos
aceites, portanto não serve como autoridade única para validar o candidato.

### Evidência e decisão

JSONs completos e logs permanecem em `laboratorio-local/professor-moe-35b/metricas/`;
o nome da pasta é o destino existente dos ensaios, não o modelo usado. Os
relatórios incluem o caminho/hash real do executor:

| Arquivo JSON | SHA-256 |
|---|---|
| `geracao-controlada-hoshino-35b-20261014-213501.json` | `947656ffb9f0dc782cbe0d31ff3c3a42f0a1696054231c2073a56b6ffb6d41ae` |
| `geracao-controlada-lilith-35b-20261014-213202.json` | `ae4c69e5d91fb911c14a5611fa62b35db40c83021224a7c804a33ddfa469d63c` |
| `geracao-controlada-hoshino-defiant-fable-9b-20261014-214206.json` | `bbaaba8be4283ece681635ae0da734c2bbd3b23f01b76c2ddb1a25cd93c72121` |
| `geracao-controlada-lilith-defiant-fable-9b-20261014-214410.json` | `8bc8beca1ff0cac22eb18d688cdacad36548e115e3ac8deeead8830f4dc74af5` |

**Decisão:** candidato íntegro, compatível com o servidor atual e mais rápido
neste ensaio, mas **não homologado como professor**. Não substituir o 35B nem
reativar geração/treino autônomos. Mantido instalado isoladamente para reversão
do ensaio; nenhum modelo antigo apagado, nenhum novo alias publicado.

Alistair não foi ensaiado; inferência direta como entidade, ferramentas reais,
visão, thinking ligado, diversidade em lotes maiores, qualidade humana e uso
prolongado continuam pendentes. Este recorte avalia geração sintética de
diálogos, não consciência, sentimentos humanos ou evolução de personalidade.

Próximo passo recomendado, não implementado aqui: separar o teste do escritor
do teste do crítico; testar uma redução editorial controlada das ambiguidades
do contexto, sem editar identidade/memória para obter nota. Não há evidência
suficiente para resolver o restante apenas trocando o checkpoint.

## Preservação ao encerrar

Porta 11559 fechada, nenhum processo filho do ensaio restante, compute leases,
fila e residência GPU do RM vazios. `concurrency_validated=false`, limite de
8 GiB e margem de 768 MiB preservados. Hoshino/Alistair continuam registrados
como dormindo; Lilith sem presença registrada, não saúde inventada.

Hashes dos três bancos mentais iguais antes/depois:

- Hoshino: `351468aed2b0ffeb8bb8d2d9408c9ecda916d8f8ab4b4cdae866678b2db79e41`.
- Lilith: `e77fceca29a43f9b3aa40190438adfd458bf0bdfdf39ad097e50980c97847488`.
- Alistair: `a5d83e26e97ff98f8157f35acc5a3f2caf72b1c84ca5ef8a14d90b956d558cdc`.

Código de produção do professor inalterado nesta rodada:
`21be8163a6636221dc2e0ea64e291e7ddf98d276149f1f855ff8a849880b13be`.
Não foram alterados RM, configurações de produção, corpus, identidades, bancos,
preferências ou regras de aprovação. Sem cloud, ElevenLabs ou quota externa.

## Proteção e regressões

Backup prévio dos dois arquivos de ensaio alterados:
`laboratorio-local/controle-laboratorio/treinamento-unificado/backups/defiant-fable-20261014/codigo-antes.tar.gz`.
Nenhum banco mental incluído nesse backup de código.

Quatro regressões adicionadas ao grupo existente `test_personalizacao_moe`:
revisão/hash/tamanho exatos, recusa de candidato ausente/simbólico, comando
Vulkan com margem/offload preservados e recusa de comparações de personalidade
com condições divergentes. Nenhuma delas baixa modelo ou faz inferência real.

- Antes: 270/270 testes do laboratório (11,032 s).
- Grupo afetado depois: 82/82 (5,416 s).
- Laboratório completo depois: 274/274 (11,002 s).
- Reexecução completa após os ensaios físicos: **274/274** (13,417 s), sem falhas.
- Suíte oficial: **74/74 grupos offline**, sem falhas nesta execução. Não valida
  o modelo real, o qual é ensaiado separadamente.
- Comparação de proveniência: hashes iguais de workload, perfil, referências,
  código e primeiro prompt de cada um dos quatro casos em ambos os pares.
- `git diff --check` limpo; links locais dos três índices existentes conferidos,
  nenhum ausente. Disco final aproximadamente 45 GiB livres.

Arquivos de código desta rodada: `laboratorio/tests/probe_geracao_professor.py`
e `laboratorio/tests/test_personalizacao_moe.py`. Não alterar produção para
melhorar notas do candidato.

Documentação: este relatório criado; links/baseline e resumo atualizados em
`README.md`, `laboratorio/README.md` e `docs/README.md`. Alterações preexistentes
no checkout foram preservadas; nenhum commit/push feito nesta rodada.
