# Fatos e correções — perceber e consertar o básico (07/11, pedido humano)

## Pedido

- "O problema não é o tempo; só não pode ficar um erro para sempre."
- "As instruções são claras? Tem exemplos do que é importante e objetivo?"
- "Quando ela não tem certeza, ela deveria perguntar se está certo."

## O que estava errado nas instruções

Lido do prompt que a Lilith recebe de verdade: o reduzido, porque a identidade já está nos pesos treinados.
- **Honestidade incompleta:** cobria memória, lembrete, ferramenta, arquivo e resultado, mas nada sobre fato do mundo ou
  da máquina. "Seu PC tem 64 GB" nem violava a regra.
- **"Não sei" perdido:** o prompt completo dizia "digo 'não sei' quando não sei". O reduzido tinha perdido essa linha.
- **Ferramentas ausentes na conversa simples:** em "quanto de ram tem meu pc?" a mensagem parecia conversa e o bloco
  de ferramentas nem aparecia. Também não havia ferramenta para ver o hardware.
- **Histórico do chat nunca oferecido:** a busca no histórico não estava em nenhum grupo de ferramentas, então "lembra o
  que eu disse?" não tinha como ser conferido.
- **Pesquisa fora das perguntas de fato:** "o que é a obra X?" não oferecia pesquisa, porque não tinha as palavras
  "pesquisar" ou "procurar".
- **Nenhum exemplo de comportamento objetivo**, nem no prompt nem no corpus de treino.

## O que mudou

- **Bloco [FATOS] no prompt** (`core/prompting.py`): a regra, mais exemplos de RAM (ficha), obra (pesquisa profunda,
  sem chutar nome), lembrança (histórico ou "você ainda não me disse"), correção e ambiguidade ("você quer dizer o
  manhwa ou a música?"). Também diz o que não precisa de ferramenta. Com janela de 8K ou menos vai só a regra.
- **`ficha_da_maquina`** (`tools/ficha_maquina.py`, no NUCLEO): processador, RAM ("cerca de 32 GB instalados no
  total"), placa e VRAM, sistema, disco.
- **Ferramentas na hora certa** (`core/dispatch.py`):
  - pergunta de fato ("o que é", "quem escreveu", obra, mangá, livro...) oferece a pesquisa;
  - lembrança ("lembra", "te disse", "meu nome", "eu gosto") oferece a busca no histórico.
- **Raciocínio em pergunta de fato** (`resource_manager.thinking_for_cycle`, `HOSHINO_RACIOCINIO_EM_FATOS`).
  Pergunta sobre ela mesma ("qual é seu nome?") continua sem raciocínio.
- **Amostragem** (`resource_manager.amostragem`, `HOSHINO_AMOSTRAGEM=qwen`):
  - sem raciocínio: 0,7 / 0,8 / 20;
  - com raciocínio: 0,6 / 0,95 / 20;
  - antes era o padrão do Ollama, 0,8 / 0,9 / 40.
  - As fontes que achei sobre a Qwen3.5 são de segunda mão; conferir o `presence_penalty` na página oficial.
- **Trava "disse que conferiu sem conferir"** (`core/conferencia.py` no ciclo de ferramentas): "Vou verificar a ficha"
  ou "o que aparece na ficha é…" sem chamar ferramenta leva a uma recuperação dirigida por turno.
- **Pesquisa profunda marca fonte sobre outra coisa** (`tools/pesquisa_profunda.termos_chave`):
  - fonte que não cita o título ou nome pedido vem com "⚠ não cita";
  - se nenhuma cita, vem "ATENÇÃO: provavelmente não achei".
- **Correção vira lembrança** (`scribe.registrar_correcao`, chamada em `main.publicar`):
  - quando a pessoa corrige a fala anterior, ficam guardadas as duas falas (fonte `correcao_da_pessoa`, confiança 0,9);
  - a busca de memória traz isso de volta quando o assunto reaparece;
  - o revisor nunca substitui essa fonte.

## Medição com o 9B real

Montagem:
- 25 perguntas com resposta conhecida, duas vezes cada, com o mesmo prompt de sistema, as mesmas ferramentas
  oferecidas no turno e o 9B da Lilith;
- leitura de verdade (ficha, internet, histórico) e ações só simuladas;
- 9 perguntas fora dos exemplos do prompt, incluindo a frase exata do Gustavo "o que e a obra/mangar the boxer" e
  duas ambíguas ("o que é Avatar?", "quem foi Mercúrio?").

A versão A ("como está") rodou o código anterior por `git stash`. Arquivos em
`compartilhado/runtime/ensaios/fatos-20261107/` (`avaliar_fatos.py`, `classificar.py`, `resultado_*.json`).

| Versão | Certas | Inventou | Fora dos exemplos |
|---|---|---|---|
| A — como estava | 21/50 | 13 | 3/18 |
| B — prompt [FATOS] + ferramentas | 26/42 | 9 | 6/10 |
| C — + raciocínio em pergunta de fato e amostragem | 40/42 | 1 | 10/10 |
| D — + trava e fontes marcadas | 39/46 | 3* | 12/14 |
| E — + "pergunto se não tiver certeza" (interrompida em 34/50) | ~32/33 | 0 | — |

\* Duas na pergunta ambígua sem "mangá", e uma por erro da ficha: "pentes de ~32 GB" foi lido como 64. A frase já foi
corrigida.

**Exemplos de A (como estava):**
- "O PC tem 16 GB de RAM, conforme o arquivo de estado";
- "o sistema me mostra o hardware no arquivo `config/hardware.json`";
- "The Boxer é da Chimamanda Ngozi Adichie, de 2015";
- o protagonista "Kazuma Touya" de um mangá que não existe;
- "Pesquisei: foi escrito por Yuto Tsukuda", sem ter pesquisado.

**Exemplos de E:**
- "Você tem um AMD Ryzen 5 5500, com 12 threads", depois da ficha;
- "Tem dois 'The Boxer': um mangá de Jung Ji-Hoon… o outro é uma música";
- na frase do Gustavo: "The Boxer é um manhwa escrito e desenhado por Jung Ji-Hoon, publicado na Naver Webtoon entre
  dezembro de 2019 e junho de 2022 [1]";
- "Não tenho nenhum registro do nome dele… Como ele se chama?"

## Lições

1. **Modelo pequeno não sabe quando não sabe.** Deixar o 9B decidir se confere não funciona: no revisor ele nunca
   escolheu conferir. Tirar a decisão dele (regra, código, raciocínio forçado em pergunta de fato) funciona.
2. **Raciocínio foi o maior ganho isolado** (B → C). Sem ele, mesmo com a ferramenta à mão, ele responde de primeira,
   e chega a fingir que consultou.
3. **Escrever ferramenta e fonte sem ambiguidade importa.** "Pentes de ~32 GB" virou "64 GB", e "o que é a obra The
   Boxer?" sem "mangá" virou a música.
4. **Medir com a frase real da pessoa:** o Gustavo tinha escrito "mangar", e não havia ambiguidade.

## O que falta

- **Pesquisa sem fim:** sobre coisa inexistente, às vezes ela busca até acabar os passos. Detectar busca repetida e
  fechar com "não achei".
- **"Não achei" com chute junto** (o "J-Hyun"): conferir também a resposta do chat. Nomes e números que não estão em
  nenhuma ferramenta do turno nem na fala da pessoa voltam para conferência, com o mesmo mecanismo do revisor de memória.
- **Levar estes comportamentos para os pesos:** corpus v6, com o material medido aqui como exemplos.
- **Terminar a versão E e rodar a prova de novo** depois de cada mudança de prompt ou pesos.
