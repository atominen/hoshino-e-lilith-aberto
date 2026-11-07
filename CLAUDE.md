# Direção de continuidade — Hoshino, Lilith e Alistair

Atualizado em **07/11/2026** (checkpoint). A última decisão humana e o estado real prevalecem sobre snapshots antigos.
Começar pelo [estado atual](docs/ESTADO_ATUAL.md).

**Direção do momento (Gustavo, 07/11):** "parar de errar é impossível, mas precisamos fazer ela conseguir consertar e
perceber coisas básicas": conferir antes de afirmar, perguntar na dúvida, a correção da pessoa vence e não se perde.

## Estado e escopo mais recentes

- **07/11 · banco de treinamento v6 ([formato e princípios](laboratorio/identidade/v6/README.md)):**
  - **Conteúdo:** "super versão" pedida pelo Gustavo, com o v5 inteiro mais fatos, perceber, consertar, perguntar,
    memória, ferramentas de verdade (`F:`/`R:`), voz, conhecimento geral e pares de preferência com erros reais.
  - **Saída:** `scripts/montar_banco_v6.py` grava `laboratorio-local/banco_treino_v6/banco.sqlite3` e as exportações.
  - **Números:** ~1.600 exemplos, ~1.400 aceitos pelo treinador atual.
  - **Status:** rascunho, aprovação humana pendente, e `corpus_atual` segue no v5.

- **07/11 · fatos e correções ([detalhes](docs/FATOS_E_CORRECOES_20261107.md)):**
  - **Mudanças:**
    - [FATOS] no prompt, com exemplos;
    - `ficha_da_maquina`;
    - pesquisa em pergunta de fato e histórico em lembrança;
    - raciocínio em pergunta de fato e amostragem Qwen;
    - trava "disse que conferiu sem conferir" (`core/conferencia.py`);
    - fontes marcadas quando falam de outra coisa;
    - correção da pessoa guardada (`correcao_da_pessoa`);
    - "pergunto quando não tenho certeza".
  - **Medido com o 9B real:** de 21/50 certas (13 inventadas) para 40/42 e ~32/33 sem invenção. A prova fica em
    `runtime/ensaios/fatos-20261107/`.

- **07/11 · memórias da Lilith ([detalhes](docs/MEMORIA_LILITH_E_AUXILIAR_2B_20261107.md)):** 7 memórias erradas
  desativadas (backup e motivos em `runtime/memory-backups/limpeza-20261107-002715`), pessoa fantasma e curiosidades
  de título de janela fora. Nome por voz ficava adiado para sempre: agora a confirmação seguinte destrava; regra
  aceita "eu sou o Fulano". **Revisor de memória:** segunda chamada do próprio 9B confere cada anotação do escriba
  (apoiada, durável, nova/igual/atualiza) antes de guardar; só substitui anotação do escriba-modelo, nunca apaga
  (`mind/revisor_memoria.py`, `HOSHINO_REVISOR_MEMORIA`). Recebe as fontes do turno; o modelo copia o trecho que
  sustenta e o código apura a origem; o que só a entidade disse é conferido com até 2 ferramentas de leitura
  (internet, página, histórico, `ficha_da_maquina`) e sem confirmação não entra. 9B: 56/59 e 15/16 com fontes, 0
  inventadas guardadas nas fontes; 2B descartou tudo (32/59) e fica só na CPU. Treinar um 2B: falta dado; não agora.

- **06/11 noite · PC2, desktop leve, cópias e navegador ([detalhes](docs/PAINEL_PC2_E_DESKTOP_LEVE_20261106.md)):**
  - **Painel no PC2:** só a janela; o cérebro fica no PC1. Porta 8770 na LAN com código de pareamento, ligada em
    Configurações (aplica na hora de salvar). Instalação: `scripts/instalar_painel_pc2.sh IP CODIGO`.
  - **Desktop leve:** `scripts/instalar_desktop_leve.sh` (Xfce sem compositor), instalado e em uso: 99 MiB de VRAM do sistema.
  - **Margem de VRAM em Configurações:** 128–1024 MiB (piso 128, antes 512 fixo), vale no próximo pedido de GPU.
  - **PC2:** painel instalado e conectado (19:50). À noite virou corpo das entidades: sentidos (`pc2.*` no estado do mundo),
    `executar_no_pc2` (permissão local no PC2, desligada por padrão) e cópias com origem. Ponte de áudio SonoBus no PC1.
  - **Onde fazer:** mensagem leva `origem_maquina` (pc1/pc2) e a entidade age lá; `observar_tela` com máquina (print do PC2
    com permissão local), `abrir_no_pc2`; continuação herda ferramentas por 15 min; `pesquisa_profunda` com links e imagens
    das fontes no chat. Sem botão de acordar as duas juntas; Alistair sem linha de emoção.
  - **Cópias automáticas:** Ctrl+C vai sozinho para `compartilhado/area_de_transferencia`; ferramenta `area_de_transferencia`.
  - **Navegador:** 404 deixou de ser sucesso; janela fechada reabre; busca antes de adivinhar endereço.
  - **Alistair:** mordomo sem emoções (já não rodava a camada mental). Puxar conversa sozinho: aguarda decisão.

- **06/11 tarde · pronto para teste de uso ([detalhes](docs/CORPUS_V5_20261106.md#preparado-para-o-teste-de-uso-0611-tarde-pedido-humano)):**
  - **Candidatos v5 selecionados:** os três acordam com o candidato treinado de manhã. Volta: aba Modelos → "Original · intacto".
  - **9B sem censura apagado** a pedido humano. O original da Hoshino agora é o 9B oficial.
  - **Prompt reduzido** quando os pesos foram treinados no corpus vigente (`core/pesos_treinados.py`): ~3,6 mil → ~1,5 mil tokens.
  - **Despertar:** uma mensagem no chat logo após acordar. Fala por iniciativa agora chega ao chat da Central.
  - **Camadas GPU/CPU** escolhíveis na aba Modelos (degraus medidos).
  - **Reabrir a Central** antes do teste, para carregar a interface nova e a correção do botão "Preparar".
  - **Primeiro teste (17:08–18:20, [detalhes](docs/CORPUS_V5_20261106.md#primeiro-teste-de-uso-0611-17081820-e-alerta-de-vram)):**
    a Lilith travou por `vram_pressure` (33 camadas + 32K + Firefox aberto) até o `vram_guard` fechar o Firefox.
    Novo alerta de VRAM na Central (faixa + `notify-send`) e campos de contexto/saída que viram o valor válido
    mais próximo. Ativa ao reiniciar a Central. Falso positivo "citou agenda" no despertar: pendente.

- **06/11 · resultado do treino e corpus v5 ([detalhes](docs/CORPUS_V5_20261106.md)):**
  - **Treino:** a sessão terminou às ~02:55 sem erro. Nenhum candidato foi aprovado: acertam as regras, mas sem voz.
  - **Alistair:** o passo 150 foi melhor que o final (validação 2,48 contra 3,09).
  - **Auditoria:** passou a `identity-contracts-v2`.
  - **Corpus v5:** escrito pelo Claude a pedido humano, sem professor, em `laboratorio/identidade/v5/`, montado por `scripts/montar_corpus_v5.py`.
  - **Material antigo:** apagado a pedido humano; o que tinha valor está em `laboratorio-local/exemplos-material-antigo/`. O laboratório usa o v5 via `laboratorio/corpus_atual.py`.
  - **Pendente:** aprovação humana e novas medições curtas antes de treinar.
- **05/11 · sessão única de treino, 23:00 até 06/11 12:00 (pedido humano):** três
  originais, 9B Hoshino, 9B Lilith e 4B Alistair.
  - **Base dos 9B:** o Qwen3.5-9B oficial, baixado em `laboratorio-local/modelos/qwen3.5-9b-oficial-hf`.
  - **Corpus:** `pacote_identidade_v4` (v3 avaliado + referências do jeito de partida). Ver `laboratorio/identidade/README.md`.
  - **Candidatos:** são só avaliados, sem promoção automática.
  - **Central:** precisa ficar aberta.
  - **Antes de qualquer outra operação:** conferir `nights/scheduled-once.json` e `nights/current.json`.

- **05/11 · personalidades e laboratório (decisão humana):**
  - **Personalidade de partida:** a Hoshino começa com o jeito da Takanashi Hoshino (*Blue Archive*), e a Lilith com o da Lilith (*The NOexistenceN of you AND me*).
  - **Não são cópias:** são entidades próprias, sem a biografia nem as falas das obras. O "a tia aqui" é costume dela e depende do contexto.
  - **Arquivos:** Hoshino em constituição v3 e self_model v9, Lilith em constituição v2 e self_model v2. As versões anteriores estão em `identity/versions/`.
  - **Laboratório:** o objetivo único passou a ser ensinar nome, identidade e costumes ([escopo e fluxo](laboratorio/identidade/README.md)). O que não serve a isso foi apagado do `laboratorio-local`.

- **05/11 · memórias apagadas (pedido humano: "estamos desenvolvendo, não tem
  nada pronto"):** as três entidades recomeçam sem lembranças. Foram apagados
  bancos, histórico, estado emocional, tarefas, diagnósticos, backups de
  memória, gravações de áudio e os bancos compartilhados de mensagens, jobs e
  mundo. Ficaram identidade, constituição, configurações, workspace, imagens,
  entregas, laboratório e evidências de ensaio. Sem backup, por escolha humana.
  IDs de tarefa (`ct-...`), checkpoints e o estado de Minecraft citados abaixo
  são histórico e não existem mais.

- **05/11 · emoções e orbes (aval humano):** a percepção deixou de tratar o
  ícone giratório do título como app novo, e a curiosidade não satura mais.
  Gatilhos repetidos habituam; risco repetido sensibiliza. Os orbes ganharam
  corpo pulsado do Pestinha, só leitura. A rede não entra em decisão nem prompt.
  [Resultados e escopo](docs/TRAJETORIA_REDE_PULSADA_20261104.md#retomada-de-0511-onde-a-rede-se-justifica).
  Recarregar as entidades só com drenagem cooperativa.
- **05/11 · cérebro/LLM (aval humano):** 79% do tempo do 9B é geração, e pensar
  mais não melhorou o sucesso das ações (669 decisões). A escolha de ação do
  Minecraft e a meta intermediária ganharam orçamento adaptativo de raciocínio:
  pouco na rotina, mais em barreira, falha ou perigo, e o teto aprende com os
  estouros. Projeto descongelado; o orçamento está `ativo` por padrão. Para
  voltar ao teto fixo: `HOSHINO_ORCAMENTO_ADAPTATIVO=observar`.
  [Medição e desenho](docs/ORCAMENTO_ADAPTATIVO_20261105.md).

- **Até 04/11:** Minecraft (kit de ferro, carnes, arco), auditoria de lógica, ensaio 4B, Pestinha e outros ensaios.
  Tudo em [histórico de estado até 04/11](docs/HISTORICO_ESTADO_ATE_20261104.md).

## Propósito e decisões vigentes

- Erro zero não existe num 9B. Prioridade: perceber e consertar o básico, ou seja, conferir antes de afirmar,
  perguntar na dúvida, correção da pessoa guardada e memória revista. Decisões que o modelo faz mal (saber se sabe,
  decidir se confere) ficam no código; medir antes e depois com o modelo real.
- Indivíduos persistentes, com identidade, preferências, iniciativa, decisões
  próprias e continuidade entre conversas e projetos. O computador é o
  ambiente delas; ferramentas devem ampliar suas capacidades. Não apresentar
  esta aspiração ou comportamento plausível como consciência demonstrada.
- Critério humano: perceber estado/problema/erro, recalcular, anotar e tentar
  novamente até conseguir. A recuperação deve mudar a decisão com base em
  fatos, sem o condutor escrever e executar uma rota em nome da entidade.
  Habilidades mecânicas genéricas são distintas das escolhas do LLM.
- [Seleção vigente 4B/9B](docs/ORGANIZACAO_4B_9B_20261027.md):
  Hoshino/Lilith usam só o 9B principal: o Qwen3.5-4B leve delas e o
  Andy-4.2 de teste da Lilith foram removidos e apagados em 05/11 a pedido
  humano (`light_removed` em `executores.json`). Alistair mantém seu 4B/destino configurado.
  O professor 35B é exceção preservada. A decisão substitui mínimo 7B e 6B
  preservado dos handoffs antigos; pesos 6B/7B e adaptadores correspondentes
  foram retirados por pedido humano. Não baixar/restaurar automaticamente.
  Modelos das ferramentas de áudio/imagem permanecem.
- O 9B existente já tem visão: projetor local e inferências com imagens foram
  confirmados. Isso não valida captura do campo de visão do bot sob demanda;
  essa integração permanece proposta, não motivo para trocar/baixar pesos.
- Preservar memórias, identidades, originais treináveis remanescentes,
  configurações e bancos. Não resetar ou injetar lembranças para aprovar teste.
  Fatos, hipóteses, intenções e notas autorais têm origens distintas.
- Registrar autoria, resultado e nota útil para recuperação de contexto, sem
  fabricar história humana ou expor cadeia de pensamento privada. RP do
  condutor é sintético e identificado; intervenções humanas ficam registradas.
  O resultado do kit inclui manutenção e respostas factuais autorizadas.
- Timeout não autoriza replay. Preservar efeito parcial/incerto, recibo
  original e revisão atribuída. Recusa comprovada antes do efeito permite
  outra decisão; não confundir erro HTTP com ausência de efeito.
- Usar Central, dispatcher, RM, job_bus, bancos e ciclo existentes. Sem outro
  scheduler, modelo concorrente ou alteração de código carregado enquanto há
  trabalho. Recarregar somente com drenagem cooperativa e jobs/leases livres.
- A inspeção do forno próximo já existe em `app/main.py`. A proposta é integrar
  sua evidência às decisões/guardas, não criar leituras duplicadas. Consultar
  forno também abre janela: precisa da mesma disciplina de acesso do cliente.
- Áudio deve separar aplicativos, além de microfone/som geral, no painel
  integrado. A origem do som não identifica automaticamente o falante.
- A árvore contém mudanças preexistentes de outras áreas. Não descartar,
  misturar ou commitar tudo indiscriminadamente. Um implementador por área;
  revisão independente não modifica os mesmos arquivos.

## Onde estão as evidências e o histórico

- [Índice por assunto](docs/README.md);
  [política de preservação](docs/POLITICA_PRESERVACAO_PROJETO.md).
- Evidências atuais: `compartilhado/runtime/ensaios/fatos-20261107/` e `revisor-memoria-20261107/`. As de 28/10 estão
  em `auditoria-logica-20261028/` e `minecraft-20261028/`.
  Runtime fica local; não enviar bancos, diários ou credenciais ao Git.
- Ensaios anteriores reunidos em
  `compartilhado/runtime/ensaios/arquivo-20261027/`; manifesto preserva origens.
- [Coordenação Codex/Claude](docs/COORDENACAO_CODEX_CLAUDE_20261027.md),
  [trajetória cognitiva](docs/MINECRAFT_COGNICAO_E_VALIDACAO_20261027.md),
  [autonomia/recuperação](docs/MINECRAFT_AUTONOMIA_E_RECUPERACAO_20261027.md) e
  [passagem de 27/10](docs/HANDOFF_CLAUDE_MINECRAFT_20261027.md)
  são histórico de versões/ensaios, não estado operacional vigente.
