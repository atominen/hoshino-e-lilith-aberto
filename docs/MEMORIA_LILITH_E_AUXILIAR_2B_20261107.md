# Memórias da Lilith, limpeza e o 2B como auxiliar de memória (07/11, pedido humano)

## O que estava errado

Lido do banco `entidades/lilith/memory/sqlite/lilith.db`.

**Pessoas:**
- A pessoa continuava cadastrada como "usuario". O nome "Gustavo" e o papel de criador nunca foram registrados.
- Havia uma pessoa fantasma, "alguém", criada ao acordar, sem nenhuma conversa.

**Memórias do escriba-modelo** (o 9B resumindo cada troca), 7 erradas de 12:

| Memória | Problema |
|---|---|
| "A pessoa do chat quase fechou uma edição na Wikipedia" (0,9) | Inventada. Era "quase lá, mais algumas correções", sobre o código. |
| "A pessoa quer saber o que ela queria fazer ao voltar" | Invertida: foi ela quem perguntou. |
| "Não sabemos seu nome verdadeiro ainda" | Desatualizada. |
| "…terminou sem resposta explícita do usuário no trecho fornecido" | Resto das instruções do escriba. |
| "A pessoa pediu para abrir a Wikipedia…" como **regra**; "pediu um vídeo…" como **preferência**; a intenção dela como preferência da pessoa | Tipo errado. |

**Curiosidades:** títulos de janela viraram assunto, por exemplo "O que é Wikipédia… Google Chrome for Testing" (o navegador dela), "Clock", "Projeto Hoshino…".

## Por que o nome se perdeu

1. "Eu sou o Gustavo rosa nunes prazer em te conhecer" e "Eu sou o responsável pela sua existência…" vieram **por voz**. A transcrição estava certa, mas a percepção de fala pediu confirmação (`clarify`), e o aprendizado ficou adiado (`speech.learning_deferred`).
2. A resposta seguinte, por texto ("não, esse é o meu nome, você é Lilith"), confirmava, mas nada destravava o pendente.
3. A regra de nome falhava com o artigo: em "eu sou **o** Gustavo", o "o" parava a leitura.

## Correções no código

- `scribe._extrair_nome` pula o artigo e para em "prazer", "tudo" e "obrigado". "Eu sou o Gustavo rosa nunes prazer…" vira "Gustavo Rosa Nunes".
- **Aprendizado adiado:** a fala duvidosa fica guardada (`_aprendizado_adiado`, 10 min, mesma conversa). Se a mensagem seguinte confirmar ("sim", "isso mesmo", "esse é o meu nome"), o pendente é aprendido como fala entendida (`speech.learning_confirmed`). Sem confirmação, é descartado.
- **Escriba-modelo:**
  - descarta restos das instruções;
  - pedido pontual vira "evento", não "regra" nem "preferência";
  - "regra" exige combinado, "sempre" ou "nunca";
  - confiança máxima 0,6 (era 0,9).
- **Curiosidades** ignoram as janelas dela e do projeto (`scribe.janela_vale_curiosidade`).

## Limpeza feita (aprovada pelo Gustavo, executada pelo Claude)

Backup em `entidades/lilith/runtime/memory-backups/limpeza-20261107-002715/`, com o banco, a busca vetorial e o `limpeza.json` com o motivo de cada item.
- As 7 memórias da tabela foram desativadas pelo caminho oficial (`knowledge_store.esquecer` → `retired`, saem da busca vetorial). Nada foi apagado.
- A pessoa fantasma ficou `retired`, e as 4 curiosidades de título de janela, `descartada`.
- O nome não foi escrito por nós: com a regra corrigida, o Gustavo diz por texto e ela aprende com a autoria dele.

## Revisor de memória: segunda chamada do 9B (implantado em 07/11)

O Gustavo propôs usar o 2B para organizar a memória por baixo dos panos e, depois, uma segunda chamada do próprio
9B só para isso. Os dois foram comparados com as mesmas instruções e as mesmas regras. Ficou o 9B.

**Como funciona** (`app/mind/revisor_memoria.py`, chamado em `main.revisar_memoria`):
1. O escriba-modelo propõe as anotações, como antes.
2. Para cada anotação, uma segunda chamada recebe a conversa, a anotação e até três anotações parecidas já
   guardadas (`knowledge_store.semelhantes`). Ela responde:
   - se a conversa sustenta a anotação;
   - se vale lembrar daqui a semanas;
   - a relação com as antigas: `nova`, `igual X` ou `atualiza X`.
3. Este código decide, não o modelo:
   - sem apoio ou passageira: não guarda;
   - igual ou atualiza: guarda a nova e a antiga fica `superseded`, com o vínculo `supersedes` na nova;
   - nova: guarda.
   - Confundir "igual" com "atualiza" não faz estrago, porque os dois dão o mesmo resultado.
4. **Travas:**
   - só anotações do próprio escriba-modelo (`escriba_llm`) aparecem para comparação e podem ser substituídas;
   - o que veio de regra (nome), da pessoa ou de reflexão nunca é tocado;
   - nada é apagado;
   - se a revisão falhar ou vier fora do formato, a anotação é gravada como antes (`memory.review_failed`).
5. Cada decisão aparece na aba Atividade como `memory.review`, com o texto, o motivo e a antiga substituída.
6. **Chamada curta:** temperatura 0, até 60 tokens de saída, prioridade de fundo, sem raciocínio.

**Para mudar:** `HOSHINO_REVISOR_MEMORIA`, com os valores `entidade` (padrão), `intermediario` (2B) ou `desligado`.

### Comparação: 9B (segunda chamada) contra 2B

- **Casos:** 59 rotulados, em `compartilhado/runtime/ensaios/revisor-memoria-20261107/`, local:
  - 21 das conversas reais de 06/11, 38 escritos à mão;
  - 27 para guardar e 32 para descartar;
  - 11 em que uma anotação antiga deveria sair, 10 em que uma antiga parecida deveria ficar.
- **Rótulos:** do Claude; o Codex não estava disponível para rotular às cegas.
- **Configuração:** temperatura 0, saída com esquema.

| | Juiz (guardar ou não) | Guardou ruim | Perdeu boa | Organizar | Desativaria certa | Tempo por anotação |
|---|---|---|---|---|---|---|
| **9B da Lilith (treinado), segunda chamada** | **55/59** | 2 | 2 | **19/20** | 1 | **1,6 s** (GPU, já carregado) |
| 2B, mesmas instruções | 32/59 | 0 | 27 | — | — | 5,4 s (CPU) |
| 2B, pergunta simplificada e invertida | 32/59 | 0 | 27 | — | — | — |

**Erros do 9B:**
- guardou "The Boxer é sobre uma boxeadora", algo que só ela afirmou (e está errado);
- guardou "Clara gosta de chocolate", que foi só uma pergunta dela;
- descartou "pensa em trocar Direito por Computação" e "leu Duna e achou o final corrido";
- desativaria "é alérgica a camarão" ao guardar "quase morreu por causa de camarão".

**O 2B** marcou todas as anotações como passageiras nos dois formatos. Acertar 32 é o mesmo que descartar tudo.

**Defeito achado no caminho:** o Ollama devolvia as chaves do JSON em ordem alfabética. Com um campo `antiga`
separado, o 9B escolhia a letra antes de decidir a relação e nunca apontava nenhuma: organizar dava 9/20. A letra
agora vai dentro da relação ("igual A"), e só as letras que existem podem ser escolhidas.

**Correção do que foi dito antes:** o primeiro teste (26 casos) concluiu que o 2B "descartaria o nome". Isso só
valia se "igual" descartasse a anotação nova. Com a regra adotada, "igual" e "atualiza" guardam a nova. Os rótulos
do juiz daquele teste também estavam errados: pedidos pontuais marcados como "fica". Com eles corrigidos, só 1 dos
14 casos devia ficar, e descartar tudo acertava 13. O teste pequeno não distinguia os modelos; o de 59 casos
distingue.

**Calibração da busca:**
- "A pessoa …" está em quase toda anotação e não conta como palavra em comum;
- limiares de 0,12 por palavras e 0,5 pelo índice vetorial, escolhidos nos pares da avaliação.
- Na memória real da Lilith, "A pessoa se chama Gustavo Rosa Nunes" traz "O usuário corrige o nome 'usuario' e
  revela-se como Gustavo".

### Fontes e conferência com ferramentas (ideia do Gustavo, 07/11)

O primeiro revisor via só a conversa. Por isso guardava "The Boxer é sobre uma boxeadora": a Lilith tinha dito, e
nada ali desmentia. O Gustavo propôs que o revisor recebesse também as fontes da informação e ferramentas para ver se
ela bate.

**Como ficou:**
- **Fontes do turno:** o revisor recebe as saídas das ferramentas que ela usou na conversa. São as que o fio guarda
  (até 3, cortadas em 1.500 caracteres; se não couberem, ficam as mais novas).
- **Trecho em vez de opinião:** o modelo copia o trecho que sustenta a anotação (`citacao`), e o código vê onde esse
  trecho está: nas fontes, na fala da pessoa, só na fala dela ou em lugar nenhum (`apurar_base`).
  - Nomes e números da anotação que não estão nesse texto, mas estão na fala dela, vieram dela (o "Thor").
- **O que só ela afirmou é conferido**, por regra do código e não a critério do modelo:
  - até duas ferramentas de leitura: `web_search`, `fetch_page`, `buscar_historico_chat` e a nova `ficha_da_maquina`
    (`tools/ficha_maquina.py`: processador, RAM, placa e VRAM, sistema, disco do PC1);
  - as ferramentas rodam pelo despachante de sempre, então a chave da internet e as ferramentas desligadas na Central
    continuam valendo;
  - depois o modelo decide de novo, com o que achou;
  - se não houver confirmação, a anotação não entra (`nao_conferida`).
- **Resgate estreito:** depois de conferir, se todos os nomes e números da anotação (pelo menos dois) estão no que a
  ferramenta trouxe, ela entra mesmo que o modelo tenha copiado a fala da entidade. Isso resolveu a "RX 6650 XT de 8 GB"
  confirmada pela ficha.
- **No 2B (modo `intermediario`)** não há ferramentas. O que só a entidade disse não entra.

**Avaliação:** 16 casos que dependem de fonte ou de conferência, com 9B, ferramentas reais e o histórico do chat
simulado:
- The Boxer com a página real da Wikipedia;
- RAM e placa conferidas na ficha real;
- Linux com uma busca de resultados reais;
- um endereço que deu 404;
- o nome de um cachorro que só ela disse.

| Versão | Certas | Guardou ruim | Perdeu boa | O que mudou |
|---|---|---|---|---|
| "apoiada: sim / não / conferir" | 12/16 | 4 | 0 | o modelo nunca escolheu conferir |
| "quem sustenta: pessoa / fonte / entidade" | 10/16 | 4 | 2 | chamou de "a pessoa disse" o que ela disse sobre a pessoa |
| trecho copiado + origem apurada pelo código | 14/16 | **0** | 2 | |
| idem, pedindo o trecho só da conferência | 12/16 | 0 | 4 | o modelo deixava o trecho vazio |
| **trecho + resgate estreito (adotado)** | **15/16** | **0** | 1 | |

- **Perda que sobrou:** "o canal favorito da pessoa é o Games Eduu"; o modelo deixa o trecho vazio.
- **Tempo:** a revisão leva ~2 s sem conferência e 8 a 25 s com conferência (busca e leitura de página), em segundo
  plano.

**Ajuste final:** o 9B marcava "contradiz" quando a pessoa corrigia uma memória já guardada ("agora quero respostas
curtas" diante de "gosta de respostas detalhadas"), mesmo instruído a não fazer isso. Com o trecho nas palavras da
pessoa e relação "atualiza", isso conta como atualização. Desmentido por fonte, conferência ou fala da entidade
continua descartando.

**Desenho final nos dois conjuntos** (`resultado_9b_v7.json` e `resultado_fontes_9b_v7.json`):

| Conjunto | Certas | Guardou ruim | Perdeu boa | Organizar | Desativaria certa |
|---|---|---|---|---|---|
| 59 originais (antes das fontes: 55/59) | **56/59** | 1 | 2 | 17/19 | 1 |
| 16 com fontes e conferência | **15/16** | 0 | 1 | — | — |

**Erros que sobraram:**
- **"A capital da Austrália é Camberra":** guardada depois de a busca confirmar. Discutível: é um fato confirmado,
  só não é da vida da pessoa.
- **"A pessoa se chama Gustavo e a entidade, Lilith":** perdida porque, nesse turno, o nome estava só na fala dela, e
  na avaliação o histórico do chat era simulado e vazio. Em uso real, a busca no histórico acha "Eu sou o Gustavo
  rosa nunes".
- **"Cursa Direito" e "canal favorito":** o modelo deixou o trecho vazio.
- **Alergia a camarão:** ainda seria desativada ao guardar "quase morreu por causa de camarão".

**Tempo:** a média sobe de 1,6 s para ~3 s por anotação. Só ~1 em cada 9 anotações passa pela conferência.

### Treinar um modelo pequeno (2B/3B) para essa função: possível, mas não agora

- **Modelo:** o Qwen3.5 não tem 3B; os tamanhos pequenos são 0,8B, 2B e 4B.
  - O 2B usado no intermediário só existe aqui como GGUF. Treinar exige baixar os pesos originais (~4,5 GB, com
    aval humano; o disco tem 51 GB livres).
  - O 4B do Alistair já está no formato de treino (`laboratorio-local/modelos-extras/alistair-qwen35-4b/hf`), mas
    na CPU levaria ~10 s por anotação.
- **Treino em si: fácil.** O laboratório já faz LoRA (rank 4/8) nessa família na RX 6650 XT e prepara o
  resultado para o Ollama.
  - O 4B do Alistair treinou 630 passos dentro da sessão de 06/11.
  - Um 2B levaria uns 20 a 40 minutos de GPU, com as entidades dormindo.
- **Difícil: os dados.**
  - A tarefa é estreita (três respostas curtas), o tipo que um modelo pequeno aprende bem. Mas precisa de
    algumas centenas a ~1.000 exemplos variados e conferidos, com equilíbrio entre guardar, descartar, repetir
    e atualizar.
  - Os 59 casos de hoje ficam de fora, como prova final.
  - **Fontes possíveis:**
    - as decisões do próprio 9B em uso (`memory.review`), conferidas por amostragem; o ritmo de conversa de
      hoje rende dezenas por semana, não centenas;
    - exemplos escritos à mão ou pelo professor 35B, com rótulo conferido.
- **Ganho real hoje: pequeno.** O 9B já está carregado quando ela conversa e decide em 1,6 s sem VRAM extra.
  O 2B treinado tiraria a revisão da GPU, mas seria mais lento (~5 s na CPU) e exigiria manter outro modelo.
- **Recomendação:** juntar as decisões reais por algumas semanas e reavaliar. Se a GPU disputada pelo revisor
  virar problema, treinar o 2B com essas decisões mais exemplos escritos.

## 2B na CPU, com ajuda da GPU, ou tudo na GPU

Medido com o `llama-server` do Ollama. Para ver a placa, o executável precisa de
`GGML_BACKEND_PATH=…/rocm_v7_2/libggml-hip.so`.

| Modo | ~500 tokens | ~1.400 tokens | VRAM |
|---|---|---|---|
| A · só CPU (atual) | 7,6 s | 12,6 s | 0 |
| B · pesos na RAM, GPU processa a entrada (`-ngl 0`, op-offload) | 5,3 s | 6,2 s | ~300 MiB |
| C · tudo na GPU | 2,0 s | 2,3 s | ~1,5 GB |

A GPU ajudando só acelera a leitura da entrada (5 a 6 vezes); a escrita continua a ~31 tok/s, como na CPU.

**Fica só na CPU:** o trabalho é de fundo, ninguém espera por ele. O modo B economiza de 2 a 6 s, mas custa ~300 MiB justamente onde a VRAM é apertada (Lilith 33 camadas + 32K) e disputa a placa com o 9B. O modo C não cabe junto com o 9B.
