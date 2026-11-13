# Painel no PC2, desktop leve, cópias automáticas e navegador (06/11, pedido humano)

## Painel da Central no PC2

O cérebro continua no PC1: entidades, modelos, memórias e GPU. O PC2 roda só a janela da Central e conversa
com o backend do PC1 pela rede local.

**No PC1, uma vez:**
1. Central → Configurações → "Painel no PC2 pela rede local". Marque, clique em "Salvar acesso pela rede".
2. A porta **8770** abre na hora de salvar e volta a abrir sozinha com a Central. Salvar de novo (ou "Gerar novo
   código") fecha a porta antiga e abre outra; desligar fecha na hora.
3. Se o firewall estiver ligado: `sudo ufw allow from 10.0.0.0/24 to any port 8770 proto tcp`.
4. "Copiar comando do PC2" copia a linha de instalação com o IP e o código. Essa cópia não vai para a área
   compartilhada.

**No PC2 (Linux Mint, git autenticado no GitHub):**

```bash
git clone https://github.com/atominen/hoshino-e-lilith.git ~/hoshino-e-lilith-painel
bash ~/hoshino-e-lilith-painel/scripts/instalar_painel_pc2.sh 10.0.0.102 CODIGO
```

O script faz o seguinte:
- instala só o que falta (`python3-pyqt5`, `git`, `curl`, `pulseaudio-utils`);
- baixa ou atualiza o código (`main`, só avanço rápido, sem apagar nada local);
- grava o endereço com o código em `compartilhado/runtime/launcher/central.url` (0600);
- confere a conexão (HTTP 200) antes de criar o atalho "Central Hoshino e Lilith (PC2)" no menu.

**Atualização automática (11/11, pedido humano):** o atalho abre `scripts/abrir_painel_pc2.sh`, que antes de
abrir a janela busca o `main` no GitHub (até 20 s) e avança só se for avanço rápido. O código novo do PC1 chega ao
PC2 depois do push. Sem rede, sem credencial (não pede senha) ou com alteração local no caminho, abre a
versão que já está lá. Cada abertura fica anotada em `compartilhado/runtime/launcher/atualizacao-painel.log`.
O instalador só precisa rodar de novo se o IP ou o código do PC1 mudarem.

PC2 instalado antes de 11/11, com o atalho antigo que abria a janela direto: uma vez,
`git -C ~/hoshino-e-lilith-painel pull --ff-only && bash ~/hoshino-e-lilith-painel/scripts/abrir_painel_pc2.sh --instalar-atalho`.

**Segurança:**
- **Credencial:** o código é diferente do token local. É fixo entre aberturas e trocado em "Gerar novo código".
- **Quem é aceito:** só IPs de rede privada (10/8, 172.16/12, 192.168/16, ou as redes listadas), com o Host
  igual ao IP do PC1. O token local não vale nessa porta.
- **O que o PC2 não faz:** ver ou trocar o código, nem ligar ou desligar o acesso.
- **Fechar a janela no PC2** fecha só o painel. Não encerra a Central nem as entidades.
- **Conexão:** HTTP simples numa LAN de confiança, como os executores do PC2 e do Xbox. Não expor à internet.

**Arquivos:**
- `app/core/central_rede.py`
- `make_lan_server` em `iniciar_entidades.py`
- `scripts/instalar_painel_pc2.sh`
- `/api/control/rede`, que só a Central local acessa

**Limites:**
- O microfone do PC2 depende do ambiente Python do projeto, que o painel não instala.
- O botão do Laboratório abre o servidor localmente no PC2, sem efeito útil.
- Chat, voz (tocada no PC2), modelos, recursos, memórias e alertas funcionam.

### Ponte de áudio pela Central, sem SonoBus (pedido humano, 11/11)

"Não quero depender de apps externos para o projeto funcionar." A ponte que o SonoBus fazia (servidor
`aoo.sonobus.net`, reconexão manual dos dois lados) passou para a própria Central, pela mesma porta da rede e com o
mesmo código do painel. Só usa `parec`/`pacat` dos dois PCs. Código em `app/ui/native_ponte.py`.

- **Som do PC1 → PC2:** a Central do PC1 grava o monitor da saída padrão (`@DEFAULT_MONITOR@`, tudo o que toca
  no PC1) e manda por um GET contínuo (`/api/control/pc2/som`). O painel do PC2 toca na saída padrão de lá.
- **Microfone do PC2 → PC1:** o painel grava o microfone padrão do PC2 e manda por um POST contínuo chunked
  (`/api/control/pc2/microfone`). A Central do PC1 toca em `voz_do_pc2`, cujo monitor é o microfone padrão do
  PC1. As saídas virtuais `pc1_para_pc2`/`voz_do_pc2` do PipeWire continuam (separadas, sem eco).
- **Formato:** PCM s16le 48 kHz, 2 canais no som e 1 no microfone, sem compressão (~1,5 e ~0,8 Mbit/s).
- **Atraso:** quem recebe lê a rede sem parar e descarta o excesso acima de 150 ms na fila (volta a 40 ms), em vez
  de acumular atraso pela diferença de relógio das placas. Tocador com 60 ms e cano de 4 KiB.
- **Liga sozinho:** com o painel do PC2 aberto. No PC2, em Configurações → "Este PC é o PC2", duas opções ligadas
  por padrão: "Tocar aqui o som do PC1" e "Mandar o microfone deste PC para o PC1", com a situação ao lado.
  Reconecta sozinho a cada 2 s (15 s se o PC1 recusar). Uma conexão de cada tipo por vez; a nova substitui a velha.
- **No PC1:** Configurações → "Painel no PC2 pela rede local" mostra se o PC2 está ouvindo e se o microfone chega.
- **SonoBus:** com a ponte nova, fechar o SonoBus nos dois PCs (e tirar do início automático), senão o som chega
  em dobro.
- **Voz das entidades:** se "Ler novas respostas em voz" estiver ligado nas duas janelas, o PC2 ouve a voz duas
  vezes (a do painel e a do PC1 pela ponte). Deixar ligado só numa.
- **Medido no PC1 (11/11):** `parec` do monitor padrão entrega 576.000 bytes em 3 s (exato) mesmo em silêncio,
  pausa máxima de 31 ms; `pacat` toca em `voz_do_pc2` sem erro. Testes: `testes/test_ponte_audio.py` (HTTP real
  em loopback, gravador e tocador falsos) e o contrato da interface em `testes/native_central_contracts.py`.

### O PC2 como corpo das entidades (pedido humano, 06/11 noite)

O painel do PC2 passou a ser também os sentidos e as mãos das entidades lá. O cérebro continua no PC1.
Nada disso roda no painel do PC1. As rotas `control/pc2/*` só aceitam a porta da rede.

- **Microfone:**
  - o botão de falar do painel grava com `parec` no PC2 e manda o áudio ao PC1 para transcrever;
  - o atalho global de teclado não funciona no PC2, porque depende do ambiente Python do projeto;
  - pela ponte de áudio da Central (abaixo; antes era o SonoBus), a voz do PC2 também chega ao PC1 como
    microfone padrão ("Voz do PC2").
- **Sentidos:**
  - a cada 10 s o painel roda `app/tools/sensors.py` no PC2 (janela ativa, apps abertos, mídia, tempo sem
    teclado e mouse, carga) e manda ao PC1;
  - os dados vão para o estado do mundo como `pc2.*`, com validade de 30 s;
  - quando o PC2 está em uso e o PC1 parado, o "na frente" das entidades passa a ser o do PC2
    (`maquina_em_uso`);
  - `o_que_esta_acontecendo` e `listar_janelas` mostram o PC2;
  - o instalador acrescenta `wmctrl`, `xprintidle`, `playerctl` e `x11-utils`.
- **Comandos:**
  - a ferramenta `executar_no_pc2` (grupo "Executar comandos e código") enfileira o pedido no PC1
    (`compartilhado/runtime/pc2_comandos.sqlite3`);
  - o painel pergunta a cada 2 s, roda com `bash -lc` na pasta pessoal e devolve a saída (até 64 KiB) e o código;
  - só funciona com "Permitir que as entidades executem comandos neste PC" marcado em Configurações no PC2.
    A permissão fica gravada só lá e vem desligada;
  - comandos irreversíveis são recusados, e os arriscados pedem que a pessoa rode;
  - pedido que o painel não pega em 10 s não é executado;
  - comando que começou e não terminou fica incerto e nunca é repetido sozinho;
  - estourou o prazo (até 300 s): o processo é encerrado e isso é avisado.
- **Copiar e colar:**
  - cada cópia registra de qual PC veio ("copiado no PC2");
  - com o Barrier sincronizando as duas áreas de transferência, a mesma cópia chega pelos dois painéis e não
    duplica.

Para ativar:
1. **PC1:** reabrir a Central, porque as rotas novas ficam no backend.
2. **PC2:** `git -C ~/hoshino-e-lilith-painel pull --ff-only`, rodar o instalador de novo e reabrir o painel.

### Teste das 20:36–20:50: tela, último vídeo e pesquisa (diagnóstico e correções)

**O que falhou, pelos registros da Lilith:**
1. **"Pode abrir o último vídeo":** as ferramentas de cada mensagem dependiam só das palavras dela. Sem
   "navegador" ou "página", ela recebeu só abrir, listar abas e ler. Faltavam clicar, rolar e teclar. Respondeu
   "Vou pegar…" sem agir.
2. **"Olhar a minha tela":** `observar_tela` não estava em nenhum grupo acionado por "tela", então ela não recebeu a
   ferramenta e disse que não via. Além disso, só existia a tela do PC1, e a pessoa estava no PC2.
3. **"The Boxer":** a busca achou a Wikipedia, mas ela inventou "uma boxeadora". No "mais detalhes?", recebeu
   comandos e oficina em vez de pesquisa.

**Correções:**
- **Continuação:** o turno herda por 15 minutos os grupos das ferramentas usadas no turno anterior da mesma conversa
  (`dispatch.grupos_das_ferramentas`; evento `tools_inherited`). "tela" passou a ativar `observar_tela`, e
  "vídeo", "YouTube" e "Wikipedia" ativam o navegador.
- **Onde fazer:**
  - a mensagem enviada pelo painel do PC2 leva `origem_maquina=pc2`; pela Central do PC1, `pc1`;
  - a entidade recebe a linha "[ONDE A PESSOA ESTÁ]" e faz no PC de origem, a menos que a pessoa diga o outro;
  - `observar_tela` aceita `maquina`. Sem ela, olha a tela de onde veio a mensagem;
  - no PC2, o painel tira o print da tela onde está o mouse, só com "Permitir que as entidades vejam a tela deste
    PC". O print vai ao PC1 (`compartilhado/runtime/pc2_telas`, os últimos 20), e a visão do modelo descreve;
  - nova ferramenta `abrir_no_pc2`: abre endereço no navegador padrão ou aplicativo pelo nome. Usa a permissão
    "abram e executem coisas". Pesquisar e achar o endereço continua no PC1.
- **Pesquisa profunda** (`pesquisa_profunda`):
  - faz duas buscas e lê até 5 fontes (no máximo duas do mesmo site), com o trecho mais ligado à pergunta;
  - guarda até 3 imagens das fontes (imagem de capa, JPEG até 1024 px) em `compartilhado/anexos_chat`;
  - a resposta cita [1], [2] com os links;
  - o chat mostra links clicáveis, que abrem no navegador do PC onde está o painel, e as imagens marcadas
    `[[imagem:ID]]`;
  - a voz não lê a marca.
- **Interface:** sem o botão "Acordar Hoshino e Lilith" juntas; o cartão do Alistair não tem linha de emoção.

## Desktop leve no PC1

Medido em 06/11:
- O compositor do Cinnamon ocupa 137 a 168 MiB da placa de 8 GB.
- Com a Lilith em 33 camadas e contexto de 32K, faltaram 182 MiB.
- O Xfce com o compositor desligado não desenha com a GPU.

`bash scripts/instalar_desktop_leve.sh` faz o seguinte:
- instala um Xfce mínimo (sessão, xfwm4, painel, configurações, terminal, notificações e Thunar);
- deixa o compositor desligado;
- não remove o Cinnamon.

O script pede a senha do sudo, então rode no seu terminal. Depois, saia da sessão e escolha **Xfce Session**
na tela de login. Para voltar, escolha Cinnamon.

**Medido no Xfce (06/11 ~20:00):**
- A placa ficou com 99 MiB usados pelo sistema e nenhum app na GPU; no Cinnamon eram de 300 a 500 MiB.
- Ficam abertos SonoBus, Barrier e Claude Code, que não usam VRAM.
- Discord, Steam, Hidamari e KClock saíram da abertura automática, só no Xfce. O backup está em
  `~/.config/autostart/.backup-20261106/`.

### Margem de VRAM em Configurações (pedido humano: "alargar o limite")

A margem é quanto da placa o gerenciador deixa livre antes de aceitar um pedido de GPU.
- **Antes:** piso fixo de 512 MiB no código, configurado em 512.
- **Agora:**
  - escolha em Configurações → "VRAM da placa de vídeo": 128, 256, 384, 512, 768 ou 1024 MiB;
  - o piso no código passou para 128 MiB;
  - grava `margin_bytes` em `compartilhado/config/gpu.json`, com revisão e backup, mantendo as outras chaves.
- **Quando vale:**
  - no próximo pedido de GPU;
  - entidade já acordada só usa o piso novo depois de dormir e acordar.
- **Alerta:** o alerta de VRAM sugere a margem que sozinha cobriria a falta.
- **Cuidado:** a escada estima o 9B em 33 camadas e 32K uns 350 MiB abaixo do real (7.389 MiB medidos). Abaixo de
  512 MiB, só com o desktop leve e sem outros apps na GPU.

## Cópias automáticas (área de transferência)

Tudo o que for copiado com Ctrl+C, em qualquer app, vai sozinho para `compartilhado/area_de_transferencia/`.
Não há botão.
- **Quem grava:** a Central, aqui ou no PC2, pelo backend.
- **Como as entidades leem:** pela ferramenta `area_de_transferencia`, quando a conversa fala de cópia
  ("o que eu copiei"):
  - `listar` mostra as cópias guardadas;
  - `ler` devolve o texto inteiro, até 12 mil caracteres;
  - uma imagem vai para a caixa de entrada dela, para `observar_imagem_recebida`.
- **Limites e retenção:** texto até 1 MiB, PNG até 8 MiB. Fica com as 300 cópias mais novas, até 256 MiB.
  Cópia repetida não duplica.
- **Senhas:** não grava o que o gerenciador de senhas marca como segredo (`x-kde-passwordManagerHint`).
- **Git:** a pasta está no `.gitignore`.
- **Controles:**
  - desliga em Configurações, "Guardar sozinho tudo o que eu copiar";
  - o grupo "Ler arquivos" da aba Ferramentas tira a ferramenta das entidades.

## Navegador: por que "tacou o nome no YouTube sem verificar"

No teste das 18:35 ("abrir o canal do games eduu"), quatro coisas falharam:
1. **Endereço adivinhado:** a Lilith montou `youtube.com/@games-eduu` com o nome falado, sem pesquisar.
2. **404 como sucesso:** o YouTube respondeu **404 Not Found**, e `browser_abrir` devolveu "Navegador
   aberto: 404 Not Found" como **sucesso**.
3. **Navegador fechado para sempre:** a janela do navegador foi fechada, e daí em diante toda chamada deu
   `TargetClosedError`. A ferramenta nunca reabria.
4. **Abas e endereços inventados:** ela também chutou `aba-02`, que não existia, e outros endereços
   (`@games_eduu`, `@GamesEduu`, `@gamesedu`). Parou no limite de 16 passos.

Correções em `app/tools/browser.py` e na descrição da ferramenta:
- HTTP 404/410 volta como "Não existe: …" e 4xx/5xx como "Falha: …". Os dois contam como erro e apontam
  para a busca do site (`youtube.com/results?search_query=…`) ou `web_search`.
- Janela fechada: a sessão é descartada e `browser_abrir` abre um navegador novo, uma vez.
- Aba inexistente: o erro lista as abas abertas.
- A descrição de `browser_abrir` pede endereço conhecido ou encontrado. Para canal, perfil ou produto de que
  só se sabe o nome, pede a busca do site ou `web_search`.

## Alistair

Pedido humano: mordomo simples, sem sistema de emoções; o resto fica.
- **Já era assim:** `mind/affect.py` não dá a camada mental a ele, e a Central não calcula expressão dele.
- **Na Central:** o cartão dele agora diz "não usa (mordomo, sem sistema de emoções)".
- **Puxar conversa sozinho:** hoje ele não comenta para instigar conversa entre as entidades. Só responde a
  mensagens e pode mandar recados quando pedem. Falta decisão humana para acrescentar isso.
