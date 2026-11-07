# Estado atual — Hoshino, Lilith e Alistair

Checkpoint de **07/11/2026**. Este é o ponto de entrada. Os documentos datados registram o que foi visto naquele dia,
e o estado vivo vem do código, das configurações e da Central.

## Direção do momento (Gustavo, 07/11)

> "Parar de errar é impossível, mas precisamos fazer ela conseguir consertar e perceber coisas básicas."

As entidades vão errar, porque são um modelo de 9B numa placa de 8 GB. O trabalho agora é fazer com que:
- conferir aconteça antes de afirmar;
- ela pergunte quando não sabe ou quando a pergunta é ambígua;
- um erro não fique guardado: a correção da pessoa vence, e a memória é revista.

Depois disso vem muito mais. Esta é a base.

## Quem roda e onde

| | Modelo em uso | Onde |
|---|---|---|
| Hoshino | 9B treinado no corpus v5 (candidato de 06/11) | PC1, GPU |
| Lilith | 9B treinado no corpus v5 (`lilith-qwen3.5-9b-trained-64fb04061e1c2d27`), 33 camadas na GPU, 32K | PC1, GPU |
| Alistair | 4B treinado no corpus v5, mordomo sem camada emocional | PC1 |
| Intermediário | `qwen3.5:2b` só CPU (porta 11440), só para alertas no modo projeto | PC1, CPU |

- **Voltar ao original:** aba Modelos → Versão dos pesos → "Original · intacto", com a entidade dormindo.
- **PC1:** Ryzen 5 5500, 32 GB, RX 6650 XT de 8 GB, Linux Mint 22.3 com Xfce leve. É o cérebro.
- **PC2:** só o painel da Central pela rede (porta 8770 com código de pareamento), mais sentidos e comandos com
  permissão local. Fala e escuta pela ponte SonoBus
  ([detalhes](PAINEL_PC2_E_DESKTOP_LEVE_20261106.md)).

## O que está valendo (o mais novo primeiro)

- **Fatos e correções (07/11, [detalhes](FATOS_E_CORRECOES_20261107.md)):**
  - bloco [FATOS] no prompt, com exemplos;
  - `ficha_da_maquina`;
  - raciocínio ligado em pergunta de fato;
  - trava contra "vou verificar" sem chamar ferramenta;
  - fontes da pesquisa marcadas quando falam de outra coisa;
  - correção da pessoa guardada;
  - "pergunto quando não tenho certeza".
  - Medido com o 9B real: de 21 para 40 certas em 42, e 10/10 nas perguntas fora dos exemplos.
- **Revisor de memória (07/11, [detalhes](MEMORIA_LILITH_E_AUXILIAR_2B_20261107.md)):** segunda chamada do 9B confere cada
  anotação antes de guardar, com as fontes do turno e conferência por ferramenta. Substitui só o que o próprio
  escriba-modelo escreveu e nunca apaga. Cada decisão aparece na aba Atividade como `memory.review`.
- **Nome por voz e regra "eu sou o Fulano"** (07/11): a confirmação seguinte destrava o aprendizado adiado.
- **PC2 como corpo, cópias automáticas, navegador que não aceita 404 como sucesso** (06/11).
- **Alerta de VRAM e margem configurável** (06/11).
- **Corpus de identidade v5 e candidatos treinados** (06/11, [detalhes](CORPUS_V5_20261106.md)).
- **Personalidades de partida e recomeço sem memórias** (05/11).

## Como verificar

- **Testes:** sempre por `compartilhado/ambientes/principal/bin/python testes/executar_isolado.py testes/<arquivo>.py`.
  - Direto, eles gravam no banco real.
  - A suíte inteira: `testes/catalogo.py` lista os arquivos (108 em 07/11).
- **Laboratório:** `PYTHONPATH=app:. compartilhado/ambientes/principal/bin/python -m unittest discover -s laboratorio/tests`.
- **Avaliações com o modelo real (locais, fora do Git):**
  - `compartilhado/runtime/ensaios/revisor-memoria-20261107/` (revisor de memória);
  - `compartilhado/runtime/ensaios/fatos-20261107/` (perguntas de fato, versões A a E).
  - A segunda serve de prova fixa antes de trocar prompt ou pesos.
- **Código novo do backend:** só vale depois de "Encerrar com segurança" e abrir a Central de novo, e isso faz as
  entidades dormirem.

## Problemas conhecidos

- **PC1 instável em 07/11:**
  - desligou sozinho três vezes de manhã (09:20, 09:33, 09:36), sem erro registrado;
  - a GPU chega a 97–99 °C de junção sob carga, com overclock no LACT (clock máximo 3000);
  - rever o overclock antes de cargas longas.
- **Erros que sobraram nas perguntas de fato:**
  - pesquisa sobre coisa inexistente às vezes fica buscando sem fechar;
  - às vezes ela diz "não achei" e, na mesma frase, chuta um nome.
- **Falso positivo "citou agenda" no despertar:** pendente.
- **Aba Atividade:** a primeira carga da linha do tempo leva 12 a 15 s.
- **Alistair puxando conversa entre as entidades:** aguarda decisão.

## Próximos passos combinados

1. **Banco de treinamento v6 (rascunho pronto em 07/11):** `laboratorio/identidade/v6/` →
   `laboratorio-local/banco_treino_v6/banco.sqlite3`, com cerca de 1.600 exemplos. Falta a aprovação humana. Depois:
   estender o treinador para ferramenta e preferência, e treinar só com pedido.
2. **Conferir também as respostas do chat:** nomes e números sem fonte voltam para conferência, com o mesmo
   mecanismo do revisor.
3. **Organizador noturno:** reler as memórias antigas com conferência, sem apagar.
4. **Repositório aberto para leitura**, com conteúdo seguro, para receber dicas de quem entende (em preparo).

## Mapa da documentação

- [Índice por assunto](README.md).
- [Histórico de estado até 04/11](HISTORICO_ESTADO_ATE_20261104.md): Minecraft, auditoria de 28/10, ensaios.
- [Política de preservação](POLITICA_PRESERVACAO_PROJETO.md).
