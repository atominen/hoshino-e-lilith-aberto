"""
Ponte para o Discord.

Roda como processo separado, com o token dele, e conversa com a Hoshino só por
arquivos (`social/channels.py`). A separação é de propósito:

* se o Discord cair, ela continua viva no terminal;
* se ela cair ou você reiniciar, o bot acumula as mensagens e ela responde quando
  voltar;
* o token nunca entra no processo dela, nem no contexto do modelo;
* qualquer outro canal (Telegram, webhook, um app seu) é escrito do mesmo jeito.

Como usar:

    pip install discord.py
    export HOSHINO_DISCORD_TOKEN="o-token-do-bot"
    python integracoes/discord_bot.py

No portal do Discord, o bot precisa da intenção **MESSAGE CONTENT** ligada, senão
ele recebe as mensagens vazias.

Por padrão ele só responde em mensagem direta ou quando é mencionado num servidor,
o que evita a Hoshino tentando responder um canal de 200 pessoas. Para liberar um
canal inteiro:

    export HOSHINO_DISCORD_CANAIS="123456789,987654321"
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from social import channels  # noqa: E402
from tools import discord as discord_tool  # noqa: E402
from integracoes.discord_env import carregar as carregar_env  # noqa: E402
import config  # noqa: E402
from core import ui_policy

CANAL = "discord"
INTERVALO_ENTREGA = 1.5
NOTIFICACOES_ATIVAS = os.environ.get("HOSHINO_DISCORD_NOTIFICACOES", "1") != "0"
ESTADO_DISCORD = os.path.join(config.BUS_DIR, "discord_estado.json")
LIMITE_DISCORD = 1900        # o limite real é 2000; deixo folga para prefixo


def _canais_liberados() -> set:
    bruto = os.environ.get("HOSHINO_DISCORD_CANAIS", "")
    return {c.strip() for c in bruto.split(",") if c.strip()}


def texto_sem_mencao_bot(texto: str, bot_id: str) -> str:
    """Só remove a invocação deste bot, sem apagar outros interlocutores."""
    if not bot_id:
        return texto
    return texto.replace(f'<@{bot_id}>', '').replace(f'<@!{bot_id}>', '').strip()



def _salvar_estado(mensagem, destino):
    if not NOTIFICACOES_ATIVAS:
        return
    estado = {
        "ultimo_destino": str(destino),
        "ultimo_autor": getattr(mensagem.author, "display_name", ""),
        "ultimo_autor_id": str(getattr(mensagem.author, "id", "")),
        "ultimo_username": str(getattr(mensagem.author, "name", "")),
        "ultimo_global_name": str(getattr(mensagem.author, "global_name", "") or ""),
        "ultima_mensagem_em": mensagem.created_at.isoformat() if getattr(mensagem, "created_at", None) else "",
    }
    try:
        os.makedirs(os.path.dirname(ESTADO_DISCORD), exist_ok=True)
        tmp = ESTADO_DISCORD + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(estado, f, ensure_ascii=False)
        os.replace(tmp, ESTADO_DISCORD)
        discord_tool.registrar_usuario_observado(
            getattr(mensagem.author, "id", ""),
            username=getattr(mensagem.author, "name", ""),
            display_name=getattr(mensagem.author, "display_name", ""),
            global_name=getattr(mensagem.author, "global_name", "") or "",
            destino=str(destino),
            visto_em=mensagem.created_at.isoformat() if getattr(mensagem, "created_at", None) else "",
        )
    except OSError:
        pass


def _fatiar(texto: str, limite: int = LIMITE_DISCORD) -> list:
    """Corta mensagem longa em pedaços, quebrando em parágrafo quando dá."""
    if len(texto) <= limite:
        return [texto]
    pedacos, atual = [], ""
    for linha in texto.split("\n"):
        if len(atual) + len(linha) + 1 > limite:
            if atual:
                pedacos.append(atual)
            while len(linha) > limite:
                pedacos.append(linha[:limite])
                linha = linha[limite:]
            atual = linha
        else:
            atual = f"{atual}\n{linha}" if atual else linha
    if atual:
        pedacos.append(atual)
    return pedacos


async def entregar_mensagem(canal, msg, file_factory):
    """Checkpoint no envelope existente antes/depois de cada envio externo.

    Crash durante POST é incerto, não uma licença para repetir. Confirmar um
    trecho não equivale a confirmar a mensagem inteira.
    """
    if not ui_policy.capability_allowed(config.RAIZ,config.ENTIDADE_ID,'discord'):return False
    delivery = msg.get('delivery', {})
    if delivery.get('status') in {'sending', 'uncertain'}:
        return False
    parts = _fatiar(msg.get('texto', ''))
    attachment = msg.get('anexo', '')
    if attachment and not os.path.isfile(attachment):
        channels.saida_estado(msg['id'], status='uncertain', reason='anexo_indisponivel', auto_retry=False)
        return False
    total = len(parts) + bool(attachment)
    first = int(delivery.get('next_chunk', 0))
    if not 0 <= first <= total:
        raise ValueError('cursor de entrega inválido')
    for index in range(first, total):
        channels.saida_estado(msg['id'], status='sending', next_chunk=index, auto_retry=False)
        try:
            sent = (await canal.send(parts[index]) if index < len(parts)
                    else await canal.send(file=file_factory(attachment)))
        except Exception as exc:
            channels.saida_estado(msg['id'], status='uncertain', next_chunk=index,
                                 reason=type(exc).__name__, auto_retry=False)
            raise
        channels.saida_estado(msg['id'], status='pending', next_chunk=index+1,
                             last_message_id=str(getattr(sent, 'id', '')), auto_retry=False)
    return channels.confirmar_entrega(msg['id'])


def main() -> int:
    if not ui_policy.capability_allowed(config.RAIZ,config.ENTIDADE_ID,'discord'):
        print('[discord] Desativado na Central; nenhuma conexão iniciada.')
        return 0
    # O arquivo é lido como dotenv restrito; nunca usamos ``source`` num arquivo
    # que contém segredo e pode ter sido editado fora deste processo.
    env_file = sys.argv[1] if len(sys.argv) > 1 else ""
    if env_file:
        valores, avisos = carregar_env(env_file)
        for chave, valor in valores.items():
            os.environ[chave] = valor
        for aviso in avisos:
            print(f"[discord] configuração: {aviso}")
    try:
        import discord
    except ImportError:
        print("Falta o discord.py. Instale com:  pip install discord.py")
        return 1

    token = os.environ.get("HOSHINO_DISCORD_TOKEN", "").strip()
    if not token:
        print("Defina HOSHINO_DISCORD_TOKEN com o token do bot.")
        return 1

    intents = discord.Intents.default()
    intents.message_content = True
    intents.dm_messages = True
    cliente = discord.Client(intents=intents)
    liberados = _canais_liberados()
    esperando = {}        # destino -> quantos turnos esperando resposta
    tarefa_entrega = None
    tarefa_ponto = None

    @cliente.event
    async def on_ready():
        nonlocal tarefa_entrega, tarefa_ponto
        print(f"[discord] conectado como {cliente.user}")
        channels.marcar_vivo(CANAL)
        if tarefa_entrega is None or tarefa_entrega.done():
            tarefa_entrega = asyncio.create_task(entregar_pendentes())
        if tarefa_ponto is None or tarefa_ponto.done():
            tarefa_ponto = asyncio.create_task(bater_ponto())

    @cliente.event
    async def on_message(mensagem):
        if not ui_policy.capability_allowed(config.RAIZ,config.ENTIDADE_ID,'discord'):return
        if mensagem.author.bot:
            return
        direta = isinstance(mensagem.channel, discord.DMChannel)
        mencionada = cliente.user in mensagem.mentions
        no_canal_liberado = str(mensagem.channel.id) in liberados
        if not NOTIFICACOES_ATIVAS:
            return
        if not (direta or mencionada or no_canal_liberado):
            return

        texto = texto_sem_mencao_bot(mensagem.content,str(cliente.user.id))
        anexos = [a.url for a in mensagem.attachments]
        texto = texto.strip()
        if not texto and not anexos:
            return

        _salvar_estado(mensagem, str(mensagem.channel.id))
        channels.publicar_entrada(
            CANAL, texto, autor=mensagem.author.display_name,
            autor_id=str(mensagem.author.id), responder_para=str(mensagem.channel.id),
            anexos=anexos, source_id=str(mensagem.id))
        esperando[str(mensagem.channel.id)] = 12     # ~18 s de "digitando..."
        print(f"[discord] {mensagem.author.display_name}: {texto[:70]}")

    async def entregar_pendentes():
        """Leva para o Discord o que ela deixou na saída do barramento."""
        await cliente.wait_until_ready()
        while not cliente.is_closed():
            if not ui_policy.capability_allowed(config.RAIZ,config.ENTIDADE_ID,'discord'):
                await cliente.close()
                return
            try:
                for msg in channels.pendentes_de_saida(CANAL):
                    destino = str(msg.get("destino", ""))
                    canal = None

                    # Destino user:<ID> = DM iniciada pela Hoshino.
                    if destino.startswith("user:") and destino[5:].isdigit():
                        try:
                            usuario = await cliente.fetch_user(int(destino[5:]))
                            canal = await usuario.create_dm()
                        except Exception as exc:  # noqa: BLE001
                            print(f"[discord] não consegui abrir DM para {destino}: {type(exc).__name__}: {exc}")
                            canal = None
                    elif destino.isdigit():
                        canal = cliente.get_channel(int(destino))
                        if canal is None:
                            try:
                                canal = await cliente.fetch_channel(int(destino))
                            except Exception:  # noqa: BLE001
                                canal = None

                    if canal is None:
                        # Não remove a mensagem: pode ser uma falha temporária de rede/permissão.
                        continue

                    texto = msg.get("texto", "")
                    anexo = msg.get("anexo", "")
                    if not await entregar_mensagem(canal, msg, discord.File):
                        continue
                    esperando.pop(destino, None)
                    print(f"[discord] entregue em {destino}: {texto[:60]}")
            except Exception as e:  # noqa: BLE001 — a ponte nunca pode morrer sozinha
                print(f"[discord] erro ao entregar: {type(e).__name__}: {e}")
            await asyncio.sleep(INTERVALO_ENTREGA)

    async def bater_ponto():
        """Avisa a Hoshino que o canal está vivo e mostra 'digitando' enquanto pensa."""
        await cliente.wait_until_ready()
        while not cliente.is_closed():
            if not ui_policy.capability_allowed(config.RAIZ,config.ENTIDADE_ID,'discord'):
                await asyncio.sleep(INTERVALO_ENTREGA)
                continue
            channels.marcar_vivo(CANAL)
            for destino, restante in list(esperando.items()):
                if restante <= 0:
                    esperando.pop(destino, None)
                    continue
                esperando[destino] = restante - 1
                canal = cliente.get_channel(int(destino)) if destino.isdigit() else None
                if canal is not None:
                    try:
                        await canal.typing()
                    except Exception:  # noqa: BLE001
                        pass
            await asyncio.sleep(1.5)

    cliente.run(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
