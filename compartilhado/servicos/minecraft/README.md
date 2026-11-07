# Minecraft da Hoshino — laboratório local 1.16.5

Esta integração usa Mineflayer + Pathfinder + CollectBlock. A Hoshino recebe estado estruturado do jogo e age pela API; **Minecraft não é controlado por captura de tela**.

## Arquitetura

Hoshino (Python/LLM)
  -> tools/minecraft.py
  -> HTTP em 127.0.0.1:8765
  -> minecraft/bridge.js
  -> Mineflayer
  -> servidor Minecraft Java 1.16.5

## Instalação da ponte

```bash
cd ~/hoshino/minecraft
./install_bridge.sh
```

Requer Node.js 18+ e npm.

## Preparar o servidor local

```bash
cd ~/hoshino/minecraft
./prepare_local_server.sh
```

O script baixa o `server.jar` oficial de 1.16.5 e cria a configuração local.

Depois aceite o EULA editando:

```text
minecraft/server_1.16.5/eula.txt
```

Troque:

```text
eula=false
```

por:

```text
eula=true
```

e inicie:

```bash
./server_1.16.5/start_server.sh
```

O servidor fica em `127.0.0.1:25565`. Para este primeiro teste não é necessário
abrir a porta para a internet.

## Entrar pelo SKLauncher

Use a versão **1.16.5** do Minecraft Java no SKLauncher.

No jogo:

`Multiplayer -> Direct Connect -> 127.0.0.1:25565`

Entre com seu usuário normal. Para observar a Hoshino, deixe seu personagem no
criativo. Como o servidor inicializa em survival, o operador pode usar no console
ou no jogo:

```text
/gamemode creative SEU_NOME
```

Se necessário, primeiro dê operador ao seu usuário no console do servidor:

```text
op SEU_NOME
```

A Hoshino entra como `HoshinoMC` por padrão e permanece em survival.

## Iniciar a ponte

Com o servidor rodando, em outro terminal:

```bash
cd ~/hoshino/minecraft
./start_bridge.sh
```

A ponte deve mostrar:

```text
[minecraft] ponte ouvindo em http://127.0.0.1:8765
```

## Iniciar a Hoshino

Em outro terminal:

```bash
cd ~/hoshino
source venv/bin/activate
./iniciar_hoshino.sh
```

## Primeiro teste

Não diga à Hoshino qual ação deve executar passo a passo. Dê apenas uma meta aberta,
por exemplo:

> Conecte ao Minecraft local 1.16.5. Consulte seu manual, o estado e o inventário.
> Depois escolha sozinha uma tarefa útil que seja possível realizar neste mundo.
> Você decide quais ferramentas usar, verifica os resultados e muda de estratégia
> se alguma coisa falhar. Não use visão da tela.

Depois observe.

## O que a Hoshino consegue consultar/usar

- estado do mundo e conexão;
- posição e dimensão;
- HP e fome;
- inventário;
- entidades próximas;
- chat;
- busca de blocos;
- pathfinding;
- parar navegação;
- mineração;
- coleta de blocos;
- crafting;
- equipamento;
- ataque com alvo explícito;
- colocação de blocos;
- uso de item;
- seguir jogador.

## Regra de controle

Percepção estruturada -> objetivo/subobjetivo -> ferramenta -> resultado ->
verificação -> próxima decisão.

A captura de tela continua disponível para outras partes da Hoshino, mas o grupo
Minecraft não a usa.
