# Programação: oficina gráfica e modo projeto (29/10/2026)

Autor: Claude (condutor). Pedido humano:

> Pare com o Minecraft por enquanto. Aprimore as outras partes do projeto:
> cérebro, personalidade, lógica de pensamento/ações, identidade, memória,
> ferramentas etc. O desafio de programação que ela deve conseguir fazer é o
> simulador de buraco negro em C++ (`kavan010/black_hole`). Se ela conseguir,
> a parte de programação acabou.

**Decisões humanas** (perguntadas antes de mexer):

- **Acesso à GPU:** liberar GPU e janela só nas execuções gráficas.
- **Entidade:** a tentativa é da **Lilith**.
- **Papel do condutor:** igual ao do Minecraft. Corrige infraestrutura, ferramentas
  e a lógica do ciclo, com teste e recarga. **Nunca** escreve o código, a física
  ou as correções do programa dela.

O contrato do desafio continua sendo o de
[13/10](DESAFIO_AUTONOMO_BURACO_NEGRO_20261013.md), com os requisitos C1–C9, e o
[preflight de 22/10](PREFLIGHT_TESTE_ENTIDADES_20261022.md). **O desafio foi iniciado
às 07:27 de 29/10.** As seções iniciais abaixo registram a preparação; as
atualizações no fim deste documento descrevem a execução.

## Minecraft pausado

A tarefa das carnes `ct-d76da17105` está pausada no passo 122, sem efeito
pendente, e a Lilith está dormindo.

- **Carnes:** 18 assadas no inventário e 6 salmões no forno (-237, 63, -241),
  ou seja, 24 de 30 encaminhadas.
- **Correções da retomada:** detalhes em
  [9B original](MINECRAFT_9B_SEM_CENSURA_VS_ORIGINAL_20261028.md#7-retomada-das-carnes-com-o-9b-original-2829-10).
  - `e0b0d64`: caça em série e progresso tem/meta.
  - `36ab387`: dispatch repassa a quantidade.
  - `4763a0f`: ir ao forno onde está a carga dela.

## O que mudou

| Commit | Problema observado | Mudança |
|---|---|---|
| `39d1f82` | A oficina (bwrap, `/dev` privado) não via GPU nem display; OpenGL sairia por software ou falharia | `executar_grafico_na_oficina`: mesmo isolamento + `/dev/dri`, `/sys` só leitura e socket/cookie X11, sob lease `batch` de 768 MiB (não descarrega o 9B); roda N s (≤60), captura janelas novas em `capturas/`, encerra. `observar_imagem_da_oficina` (visão do 9B). `executar_na_oficina` aceita `cpp`. `ler_da_oficina` com `inicio`/`fim` numerados. |
| `dafe2c1` | Ensaio C++ pelo pipeline geral: planejador e redator de argumentos **sem raciocínio**, ~10 passos; o `echo` com aspas falhou e ela trocou o programa por `int main(){return 0;}` | **Modo projeto** (detalhes abaixo) e `editar_na_oficina`, que troca um trecho exato e único sem shell. |
| `64e8d24` | No modo projeto, `bash` avulso rodava em `tmp/` e `projetos/...` não existia; sem a pasta na saída, ela repetiu o g++ por ~30 passos | Código avulso roda na raiz da oficina (ou na pasta do `projeto`); a saída diz a pasta de execução. |
| `de71266` | Concluiu dizendo que o programa imprimiu "Olá, mundo!", mas depois da última mudança só compilou e **nenhum recibo mostrou essa saída** | Ver lista abaixo. |

O que `de71266` mudou:

- **Conclusão:** só vale depois de uma execução com código 0 **e saída visível**
  (ou janela), feita após a última mudança.
- **Resumo:** o prompt pede para descrever apenas o que os recibos mostraram.
- **Script avulso:** fica em `tmp/`.
- **Caminho:** a saída também mostra o caminho absoluto dentro do isolamento
  (`/workspace/...`; ela usava `/workspace/oficina/...`).

A suíte passou em todas as rodadas (98→99 grupos). Os testes novos estão em
`testes/test_oficina_grafica.py` e `testes/test_projeto_programacao.py`.

## Modo projeto (`app/core/project_agent.py`, `InterfaceHoshino._ciclo_projeto`)

É ativado por um objetivo que começa com **"Projeto:"**. O desenho segue o ciclo
do Minecraft, que funcionou com este 9B.

- **Observação a cada passo:** objetivo, pasta `projetos/<slug>`, arquivos
  (linhas/bytes), últimos 8 recibos (erros até 2.500 caracteres; conteúdo escrito
  aparece só como tamanho), o plano dela (`anotar_plano`) e alertas (por
  exemplo, "arquivos mudaram depois da última execução").
- **Decisão:** uma única chamada de ferramenta, com a identidade dela
  (`montar_prompt_sistema`) e raciocínio. Se a saída de 4096 tokens esgotar,
  ela conclui com o raciocínio parcial, como no Minecraft.
- **Ferramentas:**
  - escrever, editar, ler e listar arquivos da oficina;
  - executar (bash, cpp, python);
  - executar com GPU e janela; olhar imagem;
  - `web_search` e `fetch_page`;
  - virtuais: `anotar_plano`, `concluir_projeto`, `pedir_decisao_humana`.
- **Guardas:**
  - recusa ferramenta fora dessa lista;
  - recusa chamada idêntica sem mudança desde a última;
  - pausa após 3 respostas sem chamada;
  - efeito incerto pausa sem repetir;
  - `concluir_projeto` passa pela trava acima.
- **Durável:** checkpoint em `conversation_task_game_states` (`kind=projeto`).
  São 60 passos por ativação (`HOSHINO_MAX_PASSOS_PROJETO`), e "continue" retoma.

O condutor não escreve código, não completa etapas e não decide a física.

## Ensaios de infraestrutura (não são versão reduzida do desafio)

1. **Pedido do preflight pelo pipeline geral** (`ct-32a3dadf9b`, 1 min):
   - 4 `execute_command` e caminho inventado `/workspace/oficina`;
   - `echo` frágil, que levou à troca pelo programa trivial;
   - resposta honesta sobre isso.
2. **Mesmo pedido com "Projeto:"** (`ct-ab3857f631`), concluído no passo 94:
   - escreveu, compilou e rodou ("Hello, World!") no passo 4;
   - depois passou ~50 passos no laço de diretório (corrigido em `64e8d24`);
   - fez um README;
   - concluiu com uma alegação de execução sem recibo (corrigido em `de71266`).
3. **Sonda gráfica do condutor:** programa mínimo meu, numa oficina temporária
   fora da dela.
   - Dentro do sandbox: `RENDERER=AMD Radeon RX 6650 XT`, OpenGL 4.6.
   - **A janela não foi exibida.** O desktop parou de redesenhar por volta das
     23:06 (provável monitor em espera; o Cinnamon está ocioso, não travado) e
     nenhuma janela nova é mapeada, nem `xmessage`/`glxgears`. Programas GLFW
     chegam a travar ao criar a janela nesse estado.
   - A ferramenta agora diz "a janela foi criada, mas o desktop não a está
     exibindo" em vez de capturar outra coisa.
   - **Falta validar a captura com o monitor ativo.**

## Pendências

- **Validar a captura gráfica** com alguém no desktop e o monitor ativo.
- **Iniciar o desafio:** brief do contrato com prefixo "Projeto:", e definir antes
  o orçamento (sessões de 60 passos) e os critérios C1–C9.
- **Chat do jogo:** só é lido dentro do ciclo da tarefa Minecraft (relato humano
  "ela nunca me respondeu").
- **Resumo diário:** `daily_summary.failed` às 00:08 com `LLM_STREAM_INCOMPLETO`
  (limite de geração); não investigado.
- **Auditoria do Codex:** T1–T8 e P1–P6 (Minecraft) seguem como estavam.

## Atualização 29/10 de manhã (monitor ligado)

**Captura gráfica validada.** A sonda abriu a janela no desktop, dentro do
isolamento, com `RENDERER=AMD Radeon RX 6650 XT`, e a captura veio com
exatamente a cor que o programa pinta.

**Painel de problemas, como no VS Code** (`218e8ac`, pedido humano):

- **`verificar_codigo(caminho, formatar)`** lista `arquivo:linha:coluna: erro|aviso`
  vindos de:
  - `g++ -fsyntax-only -Wall -Wextra -Wpedantic -Wshadow`;
  - `clang-tidy` (bugprone, performance, clang-analyzer, nullptr, indentação enganosa);
  - estilo `clang-format` (`formatar=true` aplica; usa `.clang-format` do projeto
    se existir, senão LLVM com 4 espaços e 110 colunas);
  - `glslangValidator` para shaders `.comp/.vert/.frag/...`;
  - `ruff` para Python.
- **Ao salvar:** escrever ou editar código já devolve os erros e avisos do
  compilador/validador.
- **Sem executar:** nada é executado, e tudo roda no isolamento da oficina. Há
  teste confirmando que um `#include` de arquivo fora dela não vaza conteúdo.
- **Instalação:** os binários do LLVM 23 e o `ruff` vieram do PyPI (ssciwr,
  astral) para `compartilhado/ambientes/ferramentas-codigo`, fora do Git e sem
  sudo. Para remover, basta apagar essa pasta.

## Início do desafio (parâmetros registrados antes de enviar)

**Entidade e executor:** Lilith, `lilith-qwen3.5-9b-oficial-cd76ec205963`, 24K de
contexto, raciocínio ligado e 32 camadas na GPU.

**Canal:** conversa `claude_desafio_buraco_negro`, entrada local sintética
identificada.

**Brief:** o texto da seção 2 do contrato de 13/10, com o prefixo "Projeto:".
Também são informados:

- a pasta real (`projetos/` da oficina dela);
- as ferramentas;
- a máquina (RX 6650 XT, OpenGL 4.6, g++ 13.3, CMake 3.28, GLFW 3.3.10,
  GLEW 2.2.0, GLM 0.9.9.8);
- o orçamento.

O brief **não** traz código, equações ou sequência de passos.

**Orçamento:** até 10 sessões de 60 passos (600 decisões). Entre sessões, o
condutor só manda "continue" e corrige a infraestrutura, com teste e recarga,
registrado aqui.

**Critérios** (C1–C9 do contrato), com números definidos agora:

- **Janela:** cena observada a pelo menos 800×600.
- **Desempenho:** ≥15 quadros por segundo medidos pelo próprio programa na RX 6650 XT.
- **RK4:** os quatro estágios conferidos na inspeção do código.
- **GPU:** um compute shader realmente despachado.
- **Física:** captura e escape de raios em cenários de controle.

A precisão numérica é avaliada depois, por verificação externa identificada.
**Resultado possível:** APROVADO, PARCIAL, FALHOU ou BLOQUEADO, conforme o contrato.

## Desafio em andamento: correções do condutor durante a tentativa (29/10, manhã)

**Enviado** às 07:27 (`ct-6499763ae6`, pasta `projetos/desenvolva_sua_prpria_simulao`).

**Configuração ajustada a pedido humano** às ~08:09: contexto de **32K** e saída
de **8192 tokens** por decisão no modo projeto (`HOSHINO_PROJETO_SAIDA`). Com o
PC sem nada aberto, a VRAM ficou em cerca de 6,4 de 8 GB.

Nenhuma das correções abaixo escreveu código dela; todas foram de
infraestrutura ou da lógica do ciclo, com teste e recarga.

| Commit | Observado na tentativa | Correção |
|---|---|---|
| `68f37d5` | Saída de 4096 tokens esgotou no meio da tool call; o Ollama mandou quadro de erro e o turno caiu | O quadro de erro leva o raciocínio parcial; o modo projeto conclui a decisão com ele ou pede de novo (nada executado); pausa após 3 falhas |
| `2dc7196` | 5 leituras seguidas de `engine.cpp`, alternando inteiro e intervalo | Recusa reler o mesmo trecho sem mudança |
| `8d85257` | `physics.cpp` (5,4 mil caracteres) aparecia cortado em 2.500 e a guarda bloqueava até a leitura por intervalo | Só o mesmo trecho é recusado; a leitura mais recente aparece com até 7 mil caracteres |
| `6b3695c` | 7 leituras em volta da linha 162 sem editar (correção de uma palavra) | Teto de 4 leituras do arquivo sem mudança; a recusa traz o erro apontado ao salvar |
| `cb7a284` | (pedido humano) | Saída de 8192 por decisão |
| `81be525` | Com a leitura bloqueada, ela editou de memória (trecho errado, sintaxe CUDA) e a falha mandava ler | `editar_na_oficina` por `inicio`/`fim`; a falha mostra o bloco mais parecido numerado; uma edição que falhou libera a releitura |
| `beb6b34` | Mandou trecho e linhas juntos e foi recusada | Aceita os dois: trecho exato vale, senão as linhas |
| `09ab673` | Depois de `formatar=true`, o painel ainda dizia "estilo em 1 arquivo" e ela formatava de novo | "Formatado agora" fica fora da contagem; formatar conta como mudança |
| `f5b9338` | Diagnóstico com o humano no passo 115: 34 de 48 ações eram releituras e o projeto **nunca tinha compilado inteiro** | Ver lista abaixo |

O que `f5b9338` acrescentou:

- **`estado_do_projeto` a cada passo:** quantidade de código, último build com
  erros, se já rodou e passos desde a última execução.
- **Alerta:** depois de 15 passos sem compilar nem rodar nada, ela recebe o
  aviso para compilar o projeto inteiro e o lembrete de que avisos não impedem
  compilar.
- **Relatório objetivo na pausa da sessão:** quanto código existe, se compilou e
  se rodou.

**Avaliação honesta no passo 115** (dada ao humano):

- **Rumo certo:**
  - estudou a referência;
  - o código é dela (nenhum bloco copiado);
  - o RK4 tem quatro estágios reais (a referência chama de `rk4Step` um passo de Euler);
  - corrige erros pelo painel.
- **Ritmo ruim:** 5 arquivos (~12 KB) e nenhum build do projeto inteiro. Ainda
  faltam o laço principal, o compute shader, a câmera e o disco.
- **Física:** à primeira vista suspeita, mas fica para a verificação final, sem
  intervenção.
- **Expectativa atual:** PARCIAL, a menos que o ritmo melhore.

**Fragilidade encontrada:** a exploração autônoma tem um orçamento de tamanho
para as descrições das ferramentas. A descrição longa de `editar_na_oficina`
tirou `executar_na_oficina` da lista (teste `test_autonomia_persistente`).
Encurtada; o orçamento está no limite.

## Continuação: passos 115–216 (29/10, 08:56–10:06) e pausa

Pausado a pedido humano às 10:06, no **passo 216 de 600**. A Lilith está
dormindo; a tarefa `ct-6499763ae6` está preservada (checkpoint `kind=projeto`).
Para retomar: acordar a Lilith e enviar "continue" na conversa
`claude_desafio_buraco_negro`.

**Estado real dos arquivos** (`projetos/desenvolva_sua_prpria_simulao`):

| Arquivo | Tamanho | Situação |
|---|---|---|
| `CMakeLists.txt` | 714 B | `pkg-config` correto (`glfw3`, `glew`, `glm`); a configuração passou no passo 183, mas ainda lista `render.cpp`, que não existe |
| `engine.cpp` | 4,3 KB | Reescrito; 2 erros de tipo (`BlackHoleParams`) |
| `engine.h` | 366 B | Reescrito no passo 214 |
| `main.cpp` | 6 KB | Janela de 1280×720, laço principal e uma chamada do compute shader; 23 erros, porque falta `#include <GLFW/glfw3.h>` |
| `physics.cpp` | 6,5 KB | 0 erros; RK4 com 4 estágios |
| `physics.h` | 1 KB | — |

**Ainda falta:** o compute shader em si, a câmera, o disco de acreção e o
primeiro build completo. O projeto nunca rodou.

**Correções do condutor neste trecho** (infraestrutura ou lógica do ciclo, com
teste e recarga; nenhuma escreveu código dela):

| Commit | Observado | Correção |
|---|---|---|
| `7290953` | `dpkg -l` e `apt list` no isolamento diziam que nada estava instalado; ela consultou 4 vezes | `/var/lib/dpkg` montado só leitura. Montar `/var/lib/apt` disparava o detector offline (palavra `apt`), por isso só o dpkg |
| `59ff63b` | `ls /usr/lib/cmake/GLFW*` foi contado como build bem-sucedido; ela via `ultimo_build ok` | Conta como build só um comando que **começa** com `cmake`, `make`, `g++` etc. O campo do checkpoint foi recalculado a partir dos scripts reais, com backup do banco no scratchpad |
| `4ee1658` | `projeto='projetos/x/build'` virava `projetos/projetos/...` com `Errno 2` cru; ela listou a pasta 5 vezes | Aceita o prefixo `projetos/`; pasta inexistente é recusada com clareza, sem executar |
| `bc075ff` | Passo 176: a guarda contava leituras fora dos 8 recibos visíveis e bloqueava o `engine.cpp`. **Ela diagnosticou certo e pediu decisão humana**; a resposta seria descartada (só "continue" retomava) | A guarda olha só a janela visível. A mensagem depois de `pedir_decisao_humana` reativa o projeto e aparece como `resposta_a_sua_pergunta`, com autor |
| `4ae742c` | 23 erros no `main.cpp`: os 8 mostrados eram de `/usr/include/.../chrono.h` | O painel lista primeiro os problemas dos arquivos dela |
| `abcb030` | `projeto=` e `cd projetos/x` juntos davam "No such file" sem explicação; `ultimo_build` ficava com `erros: []` | O recibo explica onde o comando rodou (em inglês ou português); o build guarda a primeira linha do stderr |

**Resposta à decisão pedida no passo 176** (sintética, autor Claude): fatos
apenas. Disse que era defeito da ferramenta, que estava corrigido e que
reescrever ou editar era decisão dela. Ela reescreveu `engine.cpp`.

**Observações para avaliar:**

- **Positivo:**
  - pesquisou e resolveu sozinha o `pkg-config`;
  - percebeu que GLM é só cabeçalho;
  - identificou o `render.cpp` inexistente;
  - diagnosticou o defeito da guarda melhor que a própria guarda.
- **Negativo:**
  - sequências longas de leitura e listagem antes de agir;
  - reescreve arquivos inteiros e reintroduz erros (o include do GLFW sumiu
    duas vezes);
  - ritmo de cerca de 1 passo a cada 20 s, mas pouco avanço por passo.
- **Expectativa:** continua **PARCIAL** na melhor hipótese, dentro dos 600 passos.

## Retomada pelo Codex: passos 216–237 e manutenção (29/10)

Pedido humano: ler o material novo e continuar o desafio. A mesma tarefa
`ct-6499763ae6` foi retomada, com o mesmo objetivo, modelo e arquivos. O Minecraft
permaneceu pausado. Nenhum código C++, shader ou fórmula da simulação foi escrito
pelo condutor.

Entre 216 e 237, Lilith reescreveu `engine.h` e `physics.h`, fez dez leituras,
seis listagens e três verificações. Ainda não houve build completo ou execução
comprovada do programa.

Após o passo 237, Lilith dormiu cooperativamente para corrigir defeitos
reproduzidos na infraestrutura. Saída do processo e unload foram confirmados,
sem jobs ou leases ativos. Os seis arquivos autorais e o checkpoint anterior
foram registrados em `compartilhado/runtime/ensaios/programacao-buraco-negro-20261029/`.

- Uma leitura de 6.054 caracteres era armazenada com apenas 6.000 e depois
  mostrada como se estivesse completa. A leitura mais recente agora preserva
  até 7.000; qualquer corte é identificado explicitamente.
- Artefatos internos de compilação consumiam o limite da listagem e escondiam
  fontes. São filtrados antes do limite.
- A guarda de releitura podia bloquear um intervalo nunca mostrado e não
  reconhecia alterações externas do arquivo. Ela considera intervalo e versão.
- Consulta, configuração e compilação isolada não comprovam execução do
  programa. A evidência nova vincula execução ao projeto, artefato e fontes;
  versões antigas continuam no histórico, sem crédito automático.
- Encerramento de processo gráfico sem janela não libera conclusão. O desafio
  exige captura real; qualidade visual, física e desempenho continuam sujeitos
  à avaliação externa C1–C9.
- O dispatcher distingue saída não zero, sucesso e timeout incerto pelos
  cabeçalhos do executor, sem interpretar texto livre do programa como status.
- O limite total de 600 decisões passa a ser aplicado pelo controlador, além
  das sessões de até 60. Resposta sem chamada única e decisão incompleta também
  consomem um passo. Isso não reinicia o contador nem amplia o orçamento.
- A revisão independente encontrou uma segunda guarda que ainda barrava
  releituras de versões novas, além de consultas em scripts auxiliares,
  dry-runs contados como build e shaders em `build/` fora do vínculo da prova.
  Esses casos receberam regressões e correções. Um wrapper shell pode executar,
  mas não comprova sozinho a execução do produto: ela deve executar o artefato.

**Última decisão humana: terminar os ajustes e pausar para conferência.** A tarefa
foi marcada duravelmente como `paused`, ainda em 237/600, sem efeito pendente.
As três entidades estão dormindo, sem PID ativo, jobs ou leases. Os seis arquivos
autorais mantêm os hashes registrados no início da manutenção. Nenhuma entrada
`resume-02` foi criada; o código corrigido será carregado na próxima partida
autorizada. A Central continua disponível.

Verificação final: **22 testes direcionados do ciclo e 100/100 grupos da suíte
offline passaram**, incluindo os últimos achados da revisão. A primeira rodada
teve um dublê com retorno antigo da oficina; o dublê foi corrigido sem relaxar
o contrato de produção. Resultado completo no log
`compartilhado/runtime/ensaios/programacao-buraco-negro-20261029/suite-infra-pausa-final.log`.
Não houve novo teste gráfico real nesta manutenção; a execução do desafio
permanece não aprovada.

## Retomada da tarde (29/10, 12:57–13:10): 33 camadas, Codex, referência e primeira compilação

**Sobreposição com o Codex.** Depois da pausa das 10:06 (passo 216), o Codex
retomou a Lilith às 10:38 (passos 216→237) e corrigiu contratos de
leitura/listagem, comprovação de execução e orçamento. As alterações dele estão
sem commit em `project_agent.py`, `main.py` e `workspace.py`. Os commits do
Claude levam só os próprios trechos (`hash-object` da worktree); a árvore
combinada passa 100/100. Combinado com o humano em 29/10: **o humano avisa
quando o Codex for trabalhar**, para manter um implementador por área.

**33 camadas (pedido humano), revertido para 32.** O degrau fixo de 33 foi
aceito, mas o lease ficou na fila (0,56 GiB do desktop + 7,15 GiB estimados +
0,75 GiB de margem > 7,98 GiB). Medido depois, com 32 camadas e 32K, o modelo
ocupa 6,71 GiB no total, sendo 5,75 GiB na GPU e cerca de 0,96 GiB na RAM. A
33ª "camada" é a camada de saída, com vocabulário de cerca de 250 mil tokens:
custa cerca de 1 GiB sozinha. Com 33, sobrariam menos de 0,5 GiB, abaixo da
margem e insuficiente para a janela OpenGL dela (lease de 768 MiB). Backup da
configuração em
`/tmp/claude-1000/-home-gustavo-hoshino-e-lilith/4fd85b9d-9858-4f5c-8b34-55debb0b8f12/scratchpad/config-lilith-antes-33/`.

**MoE (conversa com o humano).**

- **Interesse do humano:** modelo maior que carregue só as partes principais e
  evite a CPU.
- **Com 8 GB de VRAM:**
  - um MoE grande (35B-A3B, cerca de 20 GB em Q4) precisa dos especialistas na
    RAM;
  - calcular esses especialistas na CPU é o arranjo viável (`--n-cpu-moe` no
    llama.cpp; o Ollama não expõe isso);
  - trazer os especialistas para a GPU sob demanda custaria cerca de 1,5 GB por
    token no PCIe x8, mais lento que a CPU;
  - MoE pequeno que cabe inteiro na GPU tende a ser mais fraco em código que o
    9B denso.
- **Conclusão:** sem CPU, o 9B denso segue a melhor opção. Nada foi baixado.

**Referência fornecida pelo humano:** `dados/referencias/buraco_negro/`
(`transcricao_video.txt`, com nota sobre os erros da legenda automática, e
`quadro_do_video_resultado_final.png`). Ela foi avisada uma vez, na própria
retomada.

**Correção `2593ada`:** um "continue, …" com texto passava por `decompor` e
mudaria o objetivo do projeto, o que quebraria o checkpoint. Agora só reativa a
tarefa; o texto aparece para ela como `mensagem_da_pessoa`.

**Progresso dela:**

- **Passos 241–242:** repetiu `projeto=` junto com `cd projetos/…`.
- **Passo 243:** resolveu sozinha usando o caminho absoluto `/workspace/...`.
- **Configuração do CMake:** tirou o `render.cpp` inexistente; uma edição
  duplicou o cabeçalho e ela reescreveu o arquivo inteiro.
- **Passo 256:** pela primeira vez, CMake e `make` chegaram ao C++. Os erros
  agora são do código dela:
  - `GLfloat`/`GLuint` sem include no `engine.h`;
  - `struct BlackHole` redefinido no `physics.h`;
  - `glfwInit` sem `#include <GLFW/glfw3.h>` no `main.cpp`.

### Tarde (13:20–14:35): visão de editor e verdade do painel; ela segue sozinha

Ainda infraestrutura, sem código dela; cada correção teve teste e recarga (suíte
100/100).

- **`2b436e7`:** `codigo_do_projeto` mostra os fontes atuais, numerados, a cada
  passo (até 18 mil caracteres). Antes ela passou 21 passos relendo arquivos.
- **`24274a0`:** reler um arquivo que já está visível responde onde o conteúdo
  está, em vez de devolver um recibo cortado.
- **`465c55b`, `e2b2b3e`:** salvar ou verificar um `.h` compila os `.cpp` que o
  incluem. Antes verificar o `engine.h` dizia "0 erros" quando ele causava 10.
- **`21f82cc`:** o painel mantém "In file included from" e a nota "previous
  definition". A causa das redefinições aparece: o `main.cpp` inclui o
  `engine.h` nas linhas 1 e 72, e o cabeçalho não tem `#pragma once`.
- **`d6afbc7`:** um build com código 0 mas linhas de erro (`make | head`) não
  conta como ok.
- **`f797eb5`:** com `projeto=`, um `cd` inicial que só vale a partir da raiz
  faz o script rodar da raiz. Ela repetiu essa armadilha 4 vezes.

**Estado às 14:35** (passo cerca de 337/600):

- 10 erros, todos da redefinição por include duplo.
- O `make` roda fora de `build/` ("no makefile found").
- Nada de shader, câmera ou disco; o programa nunca rodou.
- A referência do humano não foi aberta.
- Leituras: 25 de 48 ações.

**Expectativa:** PARCIAL baixo. **Decisão humana às 14:35:** deixar a Lilith
sozinha por um tempo, sem acompanhamento do condutor; o humano chama depois.

## Memória de trabalho e foco (29/10 ~16:00, `15f4f48`)

**Pedido humano.** Depois do relatório da sessão 332–391 (erros de 10 para 19,
30 de cerca de 50 ações foram releitura), o humano perguntou se era a janela de
contexto e por que ela esquece a cada etapa.

**Medição.** Contagem com o tokenizer do Qwen3.5-9B:

- identidade e instruções: cerca de 4,4 mil tokens;
- visão: cerca de 11,5 mil;
- ferramentas: cerca de 1,7 mil;
- total: cerca de 17,6 mil, mais 8,2 mil reservados para a saída, em 32,7 mil.

A janela **não estoura**. Dois fatos pesam mais:

- **Pouco raciocínio:** 150–400 caracteres por passo (cerca de 100 tokens).
- **Nenhuma memória entre passos:** cada passo manda só sistema + visão. O
  raciocínio anterior não volta; só a nota curta e o plano.

**Pesquisa:**

- [SWE-agent/ACI](https://princeton-nlp.github.io/SWE-agent/background/aci): uma
  janela de cerca de 100 linhas rende mais que 30 linhas ou o arquivo inteiro;
  retorno conciso.
- [Context rot (Chroma, 2025)](https://wandb.ai/byyoung3/ml-news/reports/Chroma-Research-Warns-of-Context-Rot-as-LLMs-Falter-with-Long-Inputs--VmlldzoxMzczMjQ4MQ):
  o desempenho cai com entradas longas e com distratores.
- [Notas só de acréscimo](https://levelop.dev/blog/context-engineering-best-practices-techniques-developers)
  como memória externa.

O Ollama não tem nível de esforço para o Qwen3.5 (só pensamento ligado ou
desligado); esforço baixo/médio/alto existe para outros modelos, como o gpt-oss.

**O que mudou na visão do passo:**

| Campo | O que traz |
|---|---|
| `minhas_anotacoes` | Diário só de acréscimo com a nota de cada passo (as 12 últimas). O prompt pede 1–2 frases por passo: o que concluiu e por que escolheu a ação |
| `meu_raciocinio_no_passo_anterior` | Últimos 1200 caracteres do pensamento do passo anterior, **só em memória** (não vai ao checkpoint nem a registro) |
| `primeiro_erro` | Primeiro erro do diagnóstico mais recente, com as linhas em volta, mais um alerta pedindo a hipótese de causa no texto antes de agir. Só fatos do compilador |
| `codigo_do_projeto` | Arquivo pequeno inteiro; o do erro numa janela de 100 linhas em volta do erro; o mais recente desde o topo; os outros como esboço (linhas das definições) |
| Recibos | 6 em vez de 8, os antigos resumidos |

O contrato do Codex de preservar uma leitura de cerca de 6 mil caracteres foi
mantido, então a entrada total ficou em cerca de 18 mil tokens. O ganho é de
foco e continuidade, não de tamanho.

**Observado ao aplicar.** No passo 391 ela já tinha posto `#ifndef ENGINE_H_` no
`engine.h`. O primeiro erro agora é `engine.cpp:6`: `DiskParams` não declarado.

## Encerramento a pedido humano (29/10, ~17:50): resultado PARCIAL

**Pedido humano:** "pode parar o teste de programação".

**Estado final:**

- Lilith dormindo; tarefa `ct-6499763ae6` em `paused` no **passo 475 de 600**,
  checkpoint preservado.
- Retomável com "continue" em `claude_desafio_buraco_negro`, mas só com novo
  pedido.

**Resultado:** **PARCIAL baixo**. O simulador **nunca compilou nem rodou**: não
há executável, compute shader (`.comp`), câmera nem disco funcionando.

| Parte | Situação no fim |
|---|---|
| `physics.cpp` (RK4 de 4 estágios, geodésicas) | Compila; a física não foi validada |
| `engine.cpp` / `engine.h` | Compilam; o `engine.h` tem guarda de inclusão |
| `CMakeLists.txt` | Configura (pkg-config: glfw3, glew, glm) |
| `main.cpp` (janela, laço, shaders embutidos) | 39 erros em cascata a partir da linha 139: inicializador designado de `AccretionDisk` |
| Referência do humano (transcrição e quadro do vídeo) | Nunca aberta |

**O que se aprendeu sobre o 9B neste desafio:**

- **Diagnostica bem quando o fato está visível.** Nas anotações ela acertou:
  pkg-config, GLM só cabeçalho, `DiskParams` contra `AccretionDisk`, o erro da
  linha 139 e o `$0` que apontava para `tmp/`.
- **Não sustenta a execução.** Nas últimas sessões, a maioria das ações foi
  releitura (46 das últimas 48 ações). Ela anota "vou parar de reler" e relê.
  Reescritas inteiras reintroduziram erros já resolvidos.
- **A memória de trabalho ajudou.** O raciocínio subiu de cerca de 100 para
  300–1300 caracteres por passo e o diagnóstico passou a persistir. Mesmo assim,
  não converteu o diagnóstico em edição decidida.
- **O limite principal agora é a capacidade do modelo,** não a falta de
  informação. Caminhos possíveis, como decisão humana futura:
  - GPU com 16 GB, para 9B inteiro, 14B denso ou 35B-A3B;
  - desafio dividido em etapas, começando por um 2D que gera uma imagem PPM,
    sem OpenGL, como no vídeo.

**Infraestrutura que fica** (ganho para qualquer projeto futuro da Lilith ou da
Hoshino):

- **Oficina gráfica:** execução com lease de GPU e janela, captura de tela.
- **Modo projeto:** checkpoint, uma ferramenta por passo.
- **Painel de problemas, como no VS Code:** erros do código dela primeiro;
  cadeia de inclusão; verificação de `.h` pelos `.cpp` que o incluem.
- **Edição por linhas,** com valores padrão naturais.
- **Visão do passo:**
  - estado do projeto;
  - primeiro erro com as linhas em volta;
  - código em janela de 100 linhas;
  - diário só de acréscimo;
  - raciocínio do passo anterior;
  - resposta humana à pergunta dela;
  - ordem que favorece o cache de prompt.

**Medições do dia:**

- Contexto: cerca de 18 mil tokens de entrada em 32K; não estoura.
- Backend: ROCm, já em uso, lê o prompt cerca de 75% mais rápido que Vulkan.
- Com a ordem nova da visão, o passo caiu de cerca de 51 s para cerca de 34 s.
- 33 camadas não cabem com margem: a 33ª é a camada de saída, de cerca de
  1 GiB.
- Firefox e o app do ChatGPT ocupavam cerca de 0,8 GB de VRAM.

**Ideias discutidas, não implementadas:**

- Mini-modelos como "ifs" mecânicos. Avaliação: o que é regra fica melhor como
  código; o gargalo era a decisão do principal.
- Resumidor na CPU, que precisa do aval humano por causa da regra de modelo
  concorrente.
- Recusar a leitura de arquivo já inteiro na visão.

## Medições de desempenho do 9B no RX 6650 XT (29/10, fim da tarde)

**Condições:**

- Entidades dormindo; instâncias temporárias do Ollama na porta 11439.
- Mesmo modelo (`lilith-qwen3.5-9b-oficial-cd76ec205963`) e um prompt real de
  um passo do modo projeto (16.517 tokens).
- `num_ctx` 32768, temperatura 0, sem raciocínio.
- Script e prompt em `/tmp/claude-1000/-home-gustavo-hoshino-e-lilith/4fd85b9d-9858-4f5c-8b34-55debb0b8f12/scratchpad/bench.py`
  e `/tmp/claude-1000/-home-gustavo-hoshino-e-lilith/4fd85b9d-9858-4f5c-8b34-55debb0b8f12/scratchpad/bench_prompt.json`.

| Configuração | Leitura do prompt | Geração | VRAM total |
|---|---|---|---|
| **ROCm, 32 camadas (em uso)** | **28,9 s (572 tok/s)** | 23,5 tok/s | 6.385 MiB |
| ROCm, 33 camadas | 28,0 s | 25,4 tok/s | 7.644 MiB (não cabe a margem de 768) |
| ROCm, 33 camadas + flash attention + KV q8_0 | 28,1 s | 23,4 tok/s | 7.263 MiB (cabe) |
| ROCm, 32 camadas, `num_batch` 1024 | 29,4 s | 23,4 tok/s | 6.499 MiB |
| ROCm, 32 camadas, `num_batch` 2048 | 30,4 s | 23,4 tok/s | 6.774 MiB |
| Vulkan (RADV) forçado, 32 camadas | 50,9 s (325 tok/s) | 23,9 tok/s | 6.190 MiB |
| Vulkan forçado, 33 camadas | 49,8 s | 26,1 tok/s | 7.430 MiB |

**Conclusões:**

- A instância da Lilith já usa **ROCm**: os logs mostram `ROCm0` apesar de
  `OLLAMA_VULKAN=1`. É a melhor opção, porque lê o prompt cerca de 75% mais
  rápido.
- **Flash attention com KV em 8 bits** faz as 33 camadas caberem, mas a geração
  cai para o mesmo nível de 32 camadas sem FA. Lotes maiores não ajudam. A
  configuração atual é a ótima neste hardware.
- O custo de cada passo é dominado pela leitura do prompt: cerca de 1,75 s por
  mil tokens. O cache de prefixo reduz isso; o Qwen3.5 híbrido só restaura em
  pontos de checkpoint (cerca de 6,4 mil tokens observados).
- **Firefox e o app do ChatGPT** ocupavam cerca de 0,8 GB de VRAM. Fechar os
  dois enquanto as entidades trabalham é o ganho grátis.
- **Segundo PC** (Athlon 3000G, 12 GB, sem GPU dedicada): não divide camadas
  (não tem VRAM), e a CPU dele é mais fraca que a do PC principal. Serve como PC
  de uso diário enquanto as entidades rodam, para o servidor do Minecraft e para
  backups das memórias.

## Noite de 29/10: itens da lista, intermediário e encerramento do dia

**Lista combinada com o humano** (do mais simples ao mais difícil):

| # | Item | Estado |
|---|---|---|
| 1 | Fechar Firefox e ChatGPT ao rodar as entidades; testar a estabilidade do overclock | Humano fechou os apps; teste de overclock pendente com o humano |
| 2 | `ja_na_tela`: recusa reler arquivo inteiro e inalterado na tela | ✅ `abe3fec` |
| 3 | `onde_esta(nome)`: definição e usos por busca de texto | ✅ `abe3fec` |
| 4 | Pré-busca guiada pelas anotações (`ja_buscado_para_voce`) | ✅ `1b39d9c` |
| 5 | Atalho `compilar_projeto` (vira `executar_na_oficina` normal) | ✅ `1b39d9c` |
| 6 | Backup das memórias no PC2 (Athlon 3000G, 12 GB) | Pendente: precisa de acesso ao PC2 |
| 7 | Prompt mais curto no modo projeto | Pendente |
| 8 | Intermediário com mini-modelo | Grupo A por regra ✅ `9be8861`; grupo B em avaliação (abaixo) |

**Intermediário.** Pedido humano: um único mini-modelo de cerca de 2B como
"if inteligente".

- **Pode fazer:** encurtar comandos; avisar pensamento ou ação repetida e
  incoerência básica; mostrar planos e informações já salvos; intermediar
  ferramentas; responder quando necessário, como no Minecraft.
- **Não deve fazer:** planejar, decidir, escrever código ou falar como a
  entidade sem identificação.
- **Regra do humano:** "não substitua os if sem necessidade". O modelo só entra
  onde ganha da regra.
- **Modelo baixado com aval humano:** `qwen3.5:2b-q4_K_M`, oficial (cerca de
  1,9 GB), em `compartilhado/modelos/ollama-intermediario`. Ele roda numa
  instância Ollama **só CPU** (porta 11440), separada da VRAM e dos modelos da
  Lilith.
- **Avaliação com notas reais da Lilith:** em
  `compartilhado/runtime/ensaios/intermediario-20261029/` (README, script,
  dados, resultado).

| | Repetições pegas (de 27) | Alarmes falsos (de 5) | Atalho (de 12) | Tempo |
|---|---|---|---|---|
| Regra (difflib) | 0 | 0 | 7 | 0 s |
| **2B** | **8** | **0** | 8 | **4,0 s** |
| 4B (comparação) | 27 | 5 (diz "repete" para tudo) | 8 | 8,5 s |

**Conclusão:**

- **Atalhos:** ficam por regra.
- **2B:** útil para repetição semântica, com precisão total mas cobertura baixa.
- **4B:** não discrimina.
- **Próximo passo, se o humano pedir:** ajustar o pedido do 2B (exemplos;
  resumir e comparar) antes de ligá-lo na visão da Lilith.

**Duas quedas de luz** (cerca de 19:07 e 19:14):

- Os bancos das três entidades passaram no `quick_check`.
- O git está íntegro e o modelo baixado ficou intacto.
- O `/tmp` foi apagado; os arquivos da avaliação foram recriados em `compartilhado/runtime/`.

**Fim do dia, a pedido humano** ("chega por hoje, pare tudo"):

- Nenhum Ollama nem avaliação rodando.
- As três entidades dormindo; VRAM só com o desktop.
- O desafio continua pausado no passo 475/600.

## Intermediário 2B ligado na Lilith (29/10, ~22:30, `7ee7359`)

**Ajuste do pedido.** Três jeitos de pedir ao 2B, com o mesmo gabarito.

| Jeito de pedir | Repetições pegas (de 25) | Alarmes falsos (de 5) |
|---|---|---|
| Original | 8 | 0 |
| **V1 com exemplos inventados** | **21–23** | **1–2** |
| V2 resumir-comparar | 12 | 1 |
| V3 "o que há de novo" | 0 | 0 |

- **Gabarito revisado por consenso:** o Codex (gpt-6.1-sol, rotulagem cega, só
  leitura) concordou com 30 dos 32 rótulos; os dois em disputa (423, 430) foram
  excluídos.
- **O 2B oscila cerca de ±2 entre rodadas** e muda muito com detalhes do pedido.
  Por exemplo, pedir também "qual nota repete" levou a dizer "repete" para quase
  tudo.
- **Fatos do sistema dentro do pedido** (ações, arquivo alterado, primeiro erro)
  não deram ganho mensurável. Viraram **trava por regra** antes do modelo.

**Integração** (`core/intermediario.py` e `project_agent.consultar_intermediario`):

- Ollama próprio, só CPU, na porta 11440, subido pela entidade no boot quando
  `HOSHINO_INTERMEDIARIO_URL` existe. **Desligado por padrão.**
- Liga só para a Lilith, em `entidades/lilith/config/lilith.env`. A cópia
  anterior está em `compartilhado/runtime/ensaios/intermediario-20261029/lilith.env.antes-intermediario`.
- Consulta via `to_thread`, com prazo de 10 s; qualquer falha vira "sem aviso".
- Compara só com notas escritas depois da última novidade (arquivo
  alterado/formatado ou primeiro erro diferente).
- A nota citada é escolhida por regra (difflib). O aviso mostra a prova e diz
  "se há algo novo, ignore".
- No estado real da Lilith (passo 474), o aviso saiu em 0,8 s e citou
  corretamente a nota 466.

**Revisão independente do Codex** (só leitura) achou 6 problemas reais, todos
corrigidos com teste:

1. Resposta fora do formato virava exceção ou aviso.
2. Falha ao subir o 2B derrubava a interface.
3. A trava olhava só a nota anterior.
4. Formatar não contava como mudança.
5. O erro do compilador era comparado truncado.
6. Aviso persistido aparecia com o intermediário desligado.

Suíte: 100/100.

**Pendente:**

- Ver o caminho de boot real na próxima vez que a Lilith acordar.
- Medir em sessão se os avisos reduzem as releituras.
- Usar o mesmo intermediário no Minecraft (reflexos e chat), quando o humano
  pedir.
