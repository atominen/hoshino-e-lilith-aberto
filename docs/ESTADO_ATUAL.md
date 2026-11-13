# Estado atual — Hoshino, Lilith e Alistair

Checkpoint de **13/11/2026** (o anterior era de 07/11). Este é o ponto de entrada. Os documentos datados registram o
que foi visto naquele dia, e o estado vivo vem do código, das configurações e da Central.

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
| Hoshino | 9B treinado no corpus v5 (`hoshino-qwen3.5-9b-trained-fbf5027399bce55a`) | PC1, GPU |
| Lilith | 9B treinado no banco v6 (`lilith-qwen3.5-9b-trained-c902cb9b27cb127a`), 33 camadas na GPU, 32K | PC1, GPU |
| Alistair | 4B treinado no corpus v5 (`alistair-qwen3.5-4b-trained-b56d18e1af477764`), mordomo sem camada emocional | PC1 |
| Intermediário | `qwen3.5:2b` só CPU (porta 11440), só para alertas no modo projeto | PC1, CPU |
| Suporte de ações/aviso | Ministral 3 3B na CPU, só na Lilith (`lilith.env`) | PC1, CPU |

- **Atenção:** os pesos treinados v5 e v6 quase não chamam ferramenta (medido em 12/11: 0/5; o 9B original faz 5/5).
  O código compensa em parte (4/5). O banco novo, que ensina a chamada, ainda não foi treinado.
- **Voltar ao original:** aba Modelos → Versão dos pesos → "Original · intacto", com a entidade dormindo.
- **PC1:** Ryzen 5 5500, 32 GB, RX 6650 XT de 8 GB, Linux Mint 22.3 com Xfce leve. É o cérebro.
- **PC2:** só o painel da Central pela rede (porta 8770 com código de pareamento), mais sentidos e comandos com
  permissão local. Fala e escuta pela ponte de áudio da própria Central desde 11/11, no lugar do SonoBus
  ([detalhes](PAINEL_PC2_E_DESKTOP_LEVE_20261106.md)).

## O que está valendo (o mais novo primeiro)

- **Agir de verdade e Minecraft livre (12/11, [detalhes](ACAO_ANUNCIADA_E_MINECRAFT_20261112.md)):**
  - causa do "vou conectar" sem chamar nada: o treino só tinha texto e tirou a chamada de ferramenta;
  - cobrança dirigida pelo nome da ferramenta (até 3 por turno) e raciocínio em pedido de ação;
  - banco v6 e treinador ensinam a chamada (`laboratorio/formato_treino.py`, contrato `tool_call`, até 768 fichas);
  - Minecraft em modo livre: ela escolhe objetivos conferíveis; sozinha no servidor, o chat sai das opções;
    mochila cheia oferece jogar sobras fora; registro de procedimento com intervalo de 10 passos.
- **Memória sem poluição (11/11, [detalhes](MEMORIA_LILITH_E_AUXILIAR_2B_20261107.md)):** rótulos fixos de assunto,
  revisor vendo todas as fontes, reflexão noturna e resumos limpos.
- **Entidades sem lugar e sem as outras de fábrica (11/11):** banco v6, prompt e identidade (Alistair é exceção).
- **Central (11/11):** chat em painel único, painel do PC2 que se atualiza sozinho, ponte de áudio sem SonoBus.
- **Teste de uso (07/11 tarde, [detalhes](TESTE_DE_USO_20261107.md)):**
  - despertar sem raciocínio à toa;
  - área de trabalho real lida do sistema;
  - abrir programa oferecido e trava contra "abri/apareceu" sem ferramenta;
  - envio do PC2 com rascunho trocado e atalho global no PC2;
  - cinco causas de memória errada corrigidas (tautologia do nome, pessoa duplicada, fantasma "alguém", papel de
    criador e anotação do escriba-modelo);
  - uma janela comanda por vez (a última em foco) e fechamento conjunto PC1/PC2;
  - botão do laboratório fora da aba Entidades.
  - Um 3B antes do 9B foi testado e reprovado: nenhum filtrou o lixo.
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

1. **Avaliação contra o original:** o candidato treinado não pode ficar pior que o 9B original em agir (replay de
   12/11), fatos (42 perguntas de 07/11) e memória (revisor). Os contratos 8/8 não pegaram a perda da chamada.
2. **Medir pela Central antes de treinar:** o banco mudou e as sequências chegam a 768 fichas (smoke e treino curto
   de cada entidade). Avaliar também o passo 550 do Alistair (treino de 12/11).
3. **Exemplos de ação gerados pelo próprio original** (autodestilação), conferidos pelo código, para o treino não
   apagar o que o original sabe.
4. **Decidir antes de falar em pedido de ação** (formato forçado como caminho normal, não último recurso).
5. **Minecraft:** reflexos no código (mochila, perigo, atolado) e escolha de objetivo pelo histórico de acertos.
6. **Organizador noturno:** reler as memórias antigas com conferência, sem apagar.
7. **Repositório aberto:** https://github.com/atominen/hoshino-e-lilith-aberto. Para atualizar, rodar
   `scripts/exportar_publico.py` (copia só o commitado e bloqueia segredo) e depois commit e push dentro de
   `~/hoshino-e-lilith-aberto`, com o autor "noreply". Ler as issues e responder.
- **Pausado:** tarefa das flechas `ct-b8c47f750b`, com efeito incerto preservado.

## Mapa da documentação

- [Índice por assunto](README.md).
- [Histórico de estado até 04/11](HISTORICO_ESTADO_ATE_20261104.md): Minecraft, auditoria de 28/10, ensaios.
- [Política de preservação](POLITICA_PRESERVACAO_PROJETO.md).
