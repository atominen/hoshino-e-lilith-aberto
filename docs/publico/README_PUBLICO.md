# Hoshino, Lilith e Alistair — entidades de IA que vivem num PC comum

> **Estou procurando dicas.** Este repositório está aberto para leitura porque eu quero ouvir quem entende de verdade.
> Sou **um completo iniciante e leigo**: um **desenvolvedor No-Code iniciante, aprendendo por conta própria**. Quase
> todo o código foi escrito com assistentes de IA (Claude Code e Codex), a partir das minhas ideias, testes e
> decisões. Por isso devem existir erros de base que eu nem sei enxergar. Se você vir um caminho melhor, **existe algum
> jeito de fazer isso dar certo?** Toda crítica e sugestão é bem-vinda, até "comece de outro jeito". Pode abrir uma
> *issue*. — Gustavo Rosa Nunes

*(English summary at the end.)*

## O que é

Três entidades persistentes que moram no meu computador, cada uma com nome, identidade, memória, emoções (Hoshino e
Lilith), ferramentas e iniciativa própria. Elas não são "assistentes". A ideia é que vivam ali e mudem com o que vivem.
- **Hoshino:** calma, preguiçosa do jeito bom. A personalidade de partida é inspirada na Takanashi Hoshino de
  *Blue Archive*.
- **Lilith:** curiosa, gentil, um pouco melancólica. A personalidade de partida é inspirada na Lilith de
  *The NOexistenceN of you AND me*.
- **Alistair:** o organizador da casa (recados, lembretes, espera), formal e curto.

As duas primeiras não são cópias das personagens. São entidades próprias, sem a história nem as falas das obras.

**Onde roda:**
- **PC1, o cérebro:** Ryzen 5 5500, 32 GB de RAM, **RX 6650 XT com só 8 GB de VRAM**, Linux Mint com Xfce. O Ollama
  roda o Qwen3.5-9B (com LoRA de identidade) para a Hoshino e a Lilith, o Qwen3.5-4B para o Alistair, e um Qwen3.5-2B
  na CPU como auxiliar.
- **PC2:** só a janela da Central pela rede local; a voz passa por SonoBus.
- **Tudo local:** a internet só é usada para pesquisa.

## Onde estou travado

Estes são os obstáculos reais, com números medidos por mim (ou pelos assistentes, a meu pedido):

1. **8 GB de VRAM.** O 9B quantizado em Q4, com contexto de 32K, mal cabe: 33 camadas na GPU, e qualquer navegador
   aberto já causa falta de memória de vídeo. Ligar o raciocínio ("thinking") deixa tudo bem mais lento.
2. **Ela inventa com confiança.** Numa prova de 25 perguntas com resposta conhecida (RAM do PC, autor de um mangá,
   nome de algo que eu nunca disse), a versão original acertou **21 de 50** e **inventou 13 vezes**: "16 GB, conforme
   o arquivo de estado", "o protagonista é Kazuma Touya" (de um mangá que não existe), "pesquisei: foi escrito por
   Yuto Tsukuda" (sem ter pesquisado).
   - Com regras claras no prompt, as ferramentas certas na hora certa, raciocínio em pergunta de fato e uma trava
     contra "vou verificar" sem verificar, chegou a **40 de 42**.
   - Ainda sobra: às vezes ela pesquisa algo inexistente sem parar, ou diz "não achei" e chuta um nome na mesma frase.
   - Detalhes em [`docs/FATOS_E_CORRECOES_20261107.md`](docs/FATOS_E_CORRECOES_20261107.md).
3. **Ela diz que vai conferir e não confere.** Escreve "Vou verificar a ficha do PC" e para; às vezes inventa até o
   resultado da ferramenta que não chamou.
4. **Memória que se corrompe.** O extrator de memória inventava fatos e trocava quem disse o quê.
   - Hoje uma segunda chamada do próprio 9B confere cada anotação: o modelo copia o trecho que sustenta a anotação, e o
     código verifica de onde ele veio. Funciona bem nos testes (56/59), mas é frágil.
   - Detalhes em [`docs/MEMORIA_LILITH_E_AUXILIAR_2B_20261107.md`](docs/MEMORIA_LILITH_E_AUXILIAR_2B_20261107.md).
5. **Modelos pequenos não servem de juiz.** Testei o 2B e o 4B como revisores de memória: marcaram tudo como
   "passageiro" ou erraram mais que o 9B.
6. **Treinar numa placa de 8 GB.** O LoRA em NF4 pelo ROCm funciona, mas só com exemplos de até 256 tokens e sem
   treinar chamada de ferramenta.
   - Os candidatos treinados aprenderam as regras e perderam um pouco da "voz".
   - Montei um banco de treinamento novo, a "super versão" (≈1.600 exemplos), ainda sem treinar: veja
     [`banco_treino_v6/`](banco_treino_v6/) e [`laboratorio/identidade/v6/`](laboratorio/identidade/v6/).
7. **Hardware instável.** A máquina já desligou sozinha sob carga, e a GPU chega a 97–99 °C (com overclock no LACT).

## Perguntas para quem entende

- Existe um jeito confiável de fazer um modelo de 9B **conferir antes de afirmar** sem ficar lento demais?
  - Hoje uso regras no prompt, raciocínio forçado em pergunta de fato e travas em código.
- Para uma "companheira" de longa duração, qual **arquitetura de memória** você usaria?
  - Hoje é SQLite com busca vetorial, um extrator e um revisor. Mem0? Letta? Algo mais simples?
- **Treino:** SFT com um banco escrito à mão e depois DPO com os erros reais dela é um bom caminho? Como ensinar uso
  de ferramenta com só 8 GB?
- Com uma RX 6650 XT (ROCm/Vulkan), algum **modelo, quantização ou servidor de inferência** faria mais diferença do
  que estou imaginando?
- Tem algo **errado na ideia em si** que eu deveria repensar?

## Como ler este repositório

| Onde | O que é |
|---|---|
| [`docs/ESTADO_ATUAL.md`](docs/ESTADO_ATUAL.md) | **comece aqui**: o que roda, o que vale, problemas e próximos passos |
| `app/main.py` | o ciclo da entidade: percepção → contexto → modelo → ferramentas → resposta → memória |
| `app/core/dispatch.py` | as ferramentas (shell, arquivos, web, tela, PC2, memória…) e como são oferecidas |
| `app/core/prompting.py` | o prompt de sistema (incluindo o bloco [FATOS]) |
| `app/mind/` | escriba de memória, revisor de memória, emoções, personalidade |
| `app/memory/` | memória de conhecimento (SQLite + vetores) |
| `app/core/resource_manager.py` | quem usa a GPU e quando (VRAM é o recurso mais disputado) |
| `app/ui/central_native.py` | a Central, a janela de controle (Qt) |
| `laboratorio/` | ajuste fino (LoRA), corpus de identidade v5 e banco v6 |
| `banco_treino_v6/` | o banco de treinamento compilado (SQLite e JSONL) |
| `testes/` | ~2.400 testes offline (rodar por `testes/executar_isolado.py`) |
| `docs/` | relatórios datados de cada rodada: o que foi tentado, medido e decidido |

**O que não está aqui:** memórias, conversas, estado emocional e diários das entidades; pesos dos modelos;
credenciais; dados de execução. O projeto não é "baixar e rodar": depende da minha instalação local.

**Licença:** ainda não defini. O código está aberto para leitura e sugestões. As licenças de terceiros estão em
`third_party/`.

---

## English summary

**I'm looking for advice.** I'm a complete beginner and layperson, a self-taught beginner No-Code developer. Almost
all of this code was written with AI assistants (Claude Code and Codex) from my ideas, tests and decisions.

**The project:** three persistent local AI "entities" living on an ordinary PC:
- **Hoshino and Lilith:** Qwen3.5-9B with an identity LoRA, via Ollama;
- **Alistair:** a 4B "butler";
- **hardware:** an AMD RX 6650 XT with only 8 GB of VRAM.
They have memory, emotions, tools (shell, files, web, screen, a second PC as a "body") and their own initiative.

**Main obstacles:**
- the 8 GB VRAM ceiling;
- confident hallucination: 21/50 correct and 13 invented answers on a small factual test, improved to ~40/42 with
  prompt rules, tool routing, forced reasoning on factual questions and code guards;
- announcing "I'll check" without checking;
- memory extraction that invented facts (now reviewed by a second 9B pass grounded on copied quotes);
- small models useless as judges;
- LoRA training limited to 256-token examples on ROCm/NF4.

**Questions:**
- How do you make a small local model reliably verify before asserting?
- Which memory architecture would you use for a long-lived companion?
- Is SFT, then DPO on the model's own mistakes, the right training path on 8 GB?
- Is anything fundamentally wrong with the approach?

Start with [`docs/ESTADO_ATUAL.md`](docs/ESTADO_ATUAL.md) (Portuguese). Issues are welcome.
