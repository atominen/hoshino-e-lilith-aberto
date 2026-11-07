# Cérebro/LLM: onde o 9B gasta tempo e orçamento adaptativo de raciocínio (05/11/2026)

Pedido humano: melhorar o cérebro/LLM das entidades e "compensar a falta de
poder computacional com código e tecnologias boas", com código dinâmico e
adaptativo que busque qualidade e liberdade.

## 1. Medição (só leitura dos diagnósticos reais, 26 a 30/10)

Script: `scripts/medir_orcamento_raciocinio.py`.

| Parte do tempo do backend | Horas | Fração |
|---|---|---|
| Geração (raciocínio + resposta) | 27,8 | 79% |
| Avaliação do prompt e resto | 7,0 | 20% |
| Carga do modelo | 0,5 | 1% |

A carga é ~0,2 s por chamada. O evento `gpu.reloaded` aparece quase sempre
porque registra qualquer `load_duration` maior que zero, não uma recarga real.

Raciocínio da decisão Minecraft × resultado da ação com efeito que veio em
seguida (669 pares):

| Raciocínio | Decisões | Sucesso | Incerto |
|---|---|---|---|
| nenhum | 53 | 92% | 2% |
| < 1k caracteres | 241 | 91% | 3% |
| 1k a 3k | 285 | 88% | 6% |
| 3k a 6k | 44 | 93% | 2% |
| > 6k | 46 | 98% | 2% |

Decisões e metas acima de ~1536 tokens de raciocínio são 12% das chamadas
(135 de 1106). Elas produzem 33% do texto gerado nas decisões.

Ressalvas:
- O sucesso da ação é um sinal fraco de qualidade da decisão.
- A comparação tem confusão: situações difíceis puxam mais raciocínio.
- A faixa acima de 6k (98%, n=46) pode indicar que pensar muito ajuda quando a
  situação pede. Por isso o teto sobe nesses casos em vez de cair para todos.

## 2. Bancada do backend

Detalhes em `compartilhado/runtime/ensaios/backend-9b-20261105/README.md`.

- **Flash attention e cache KV q8_0:** não aceleram. O Qwen3.5-9B é híbrido:
  só 8 das 32 camadas têm atenção, então o cache já é pequeno.
- **Velocidade de geração:** ~24 tokens/s com 32 camadas e ~26 tokens/s com 33.
  O limite é a banda de memória da RX 6650 XT.
- **Prefixo idêntico:** o Ollama reaproveita o cálculo e o prompt custa 0,2 s em
  vez de 12,9 s.
- **Nas chamadas reais:** o *system* se repete em 65 a 90% delas, mas a mensagem
  seguinte muda quase sempre (no modo projeto, 521 de 574). O ganho de
  reordenar o que muda para o fim fica como próxima etapa medida.

## 3. Orçamento adaptativo (`app/core/orcamento_adaptativo.py`)

Na escolha de ação Minecraft e na escolha de meta intermediária, o teto de
saída passa a depender de sinais que a decisão já recebe. Cada uma dessas
etapas aprende separada (`orcamento_raciocinio` e `orcamento_raciocinio_meta`).
Os níveis:

| Nível | Teto | Sinais |
|---|---|---|
| rotina | 1536 (ajustável de 1024 a 4096) | progresso, último recibo ok |
| atenção | 4096 (o teto fixo de antes) | ≥2 ações sem progresso, recibo com erro ou incerto, perigo, chat, meta nova, início; na meta, também a primeira meta |
| difícil | 6144 | barreira, morte, escolha anterior divergente |

**O que o teto não faz:**
- Não proíbe pensar. Esgotado, a entidade fecha a mesma decisão com o próprio
  raciocínio, pelo fechamento que já existia.
- Não muda o modelo, o prompt, as ferramentas nem as opções oferecidas.

**Como ele aprende:**
- Um estouro eleva a próxima decisão em um nível.
- O teto de rotina sobe 512 tokens quando mais de 30% das últimas rotinas
  estouram. Desce 512 quando, em 10 rotinas seguidas, no máximo 5% estouraram.
- A memória fica no checkpoint da tarefa (`orcamento_raciocinio`), junto com o
  resto do estado dela.

**Onde se aplica:**
- Só na escolha de ação e na meta intermediária, as duas etapas com fechamento.
- O catálogo completo e a chamada nativa continuam no teto fixo, porque um
  estouro ali perderia a decisão.

**Modos** (variável `HOSHINO_ORCAMENTO_ADAPTATIVO`):
- `ativo` (padrão desde o descongelamento de 05/11, a pedido humano): aplica o
  teto escolhido.
- `observar`: calcula e registra `cognition.orcamento` e
  `cognition.orcamento_resultado`, mas aplica 4096 como antes. O estouro é
  estimado pelo tamanho do raciocínio (~3,5 caracteres por token).
  É também o caminho para voltar ao comportamento anterior.
- `desligado`: nem calcula.

A telemetria `llm.backend_timing` ganhou `prompt_tokens`, `prompt_ns` e
`generated_tokens`. Com elas dá para medir o reaproveitamento de prefixo e o
orçamento em tokens reais.

Testes: `testes/test_orcamento_adaptativo.py` (11). As suítes do Minecraft,
Central, integração e mundo continuam passando.

## 4. Como avaliar na primeira sessão real

Comparar com as sessões de 28 a 30/10:
- tempo por passo;
- ações sem progresso, barreiras e recibos;
- distribuição de `cognition.orcamento` por nível e quantos fechamentos houve.

Se a qualidade cair, voltar com `HOSHINO_ORCAMENTO_ADAPTATIVO=observar`.

## 5. Reordenar a vista para reaproveitar o prefixo: medido e descartado

Com o modelo híbrido, o llama.cpp só volta a pontos salvos perto do fim do
prompt anterior.

| Parte que muda no fim | Prompt (~8,5k a 10k tokens) |
|---|---|
| Começo idêntico, ~10 tokens variáveis no fim | 1,0 s |
| Variável no começo | 9,7 s |
| Começo idêntico, ~1,6 mil tokens variáveis no fim | 12,6 s (sem reaproveitamento além do *system*) |

A vista do jogo muda bem mais que ~500 tokens por passo, então reordenar não
compensa. Fica descartado enquanto o backend não permitir pontos de retorno
configuráveis.

## 6. Outras correções do descongelamento (05/11)

- **Recarga falsa:** com o modelo residente, o Ollama relata ~0,2 s de carga.
  Isso era gravado como custo de recarga no RM (0,25 s guardado para o 9B da
  Lilith), quando a recarga real medida nos logs é de 3,2 a 3,8 s (até 9 s).
  O RM usa esse custo na escolha 9B/4B. Agora só uma carga de 1 s ou mais conta.
  O valor errado no banco se corrige na próxima recarga real.
- **Resumo diário:** em 30/10, 46 de 177 lotes esgotaram a saída no raciocínio,
  e o mesmo lote recomeçava do zero um minuto depois. Agora o resumo é fechado
  com o raciocínio já feito, como a decisão Minecraft.
- **Executor isolado:** passou a pôr a raiz do repositório no `sys.path` e no
  `PYTHONPATH` dos subprocessos. Sem isso, `test_integracao`,
  `test_percepcao_fala` e `test_entidades_16gb` falhavam por
  `ModuleNotFoundError`, não por defeito do código.

- **Reflexão noturna:** a janela do executor escolhido na hora podia ser menor
  que a estimada, e em 27/10 houve 11 falhas seguidas. Agora, se o modelo recusa
  por contexto, o material encolhe e a chamada é repetida, sem cortar a
  identidade nem mensagens.
- **Recuperação de arquivo do workspace:** o código usava `filesystem` sem
  importar desde 07/10, então nunca rodou. Quando funcionava, repetia a
  operação sozinho, inclusive uma edição, no primeiro arquivo achado. Agora só
  acrescenta ao resultado onde há arquivos com esse nome, e a entidade decide.

## 7. Próximas etapas propostas

- **Lembrar como resolveu antes:** consultar soluções que já deram certo para a
  mesma situação, usando o conhecimento e os recibos que já existem.
