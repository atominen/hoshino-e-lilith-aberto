# Discord como ferramenta da Hoshino

O Discord não é um modo separado. A Hoshino pode usar `discord_enviar` quando sua decisão interna indicar que faz sentido.

## Conversar com uma pessoa específica

Configure no `runtime/discord.env`:

```bash
HOSHINO_DISCORD_CONTATOS=ID_DO_AMIGO=NomeDoAmigo
```

É possível configurar vários contatos:

```bash
HOSHINO_DISCORD_CONTATOS=123=Joao;456=Maria
```

Depois Hoshino pode chamar `discord_enviar` com `destino="Joao"` sem precisar conhecer o ID.

A ponte transforma isso em uma DM para o usuário e o adaptador abre o DM no Discord.

## Conversa recebida

DMs recebidas ficam ativas por padrão (`HOSHINO_DISCORD_NOTIFICACOES=1`). Em servidores, a Hoshino responde quando é mencionada ou em canais explicitamente liberados por `HOSHINO_DISCORD_CANAIS`.

## Capacidade operacional

`discord_estado` mostra se a ponte está viva.
`discord_contatos` mostra os contatos configurados para uso pelo nome.

O token permanece somente no processo `integracoes/discord_bot.py`.
