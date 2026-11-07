"""Ferramentas do Discord para a Hoshino.

O Discord é uma capacidade do agente, não um modo separado. O adaptador roda
em outro processo e conversa com o núcleo por runtime/bus.

Além dos contatos configurados manualmente, a ponte mantém um pequeno registro
local de usuários que ela realmente observou em conversas relevantes (DM,
menção ou canal liberado). Isso permite que a Hoshino reconheça um usuário por
username/display name depois que ele interagir com o bot, sem exigir que o
usuário descubra um ID de 17/18 dígitos para cada pessoa.
"""
import json
import importlib.util
import os
import re
import tempfile

import config
from social import channels

# Os caminhos são resolvidos a cada chamada, não fixados no import. Antes eram
# constantes de módulo: quem trocasse config.BUS_DIR depois de importar (os
# testes fazem exatamente isso) continuava lendo e ESCREVENDO no bus real — foi
# assim que um usuário fictício de teste acabou gravado no arquivo de produção,
# colidindo com o username de um contato real e quebrando a busca por nome.
# social/channels.py sempre resolveu em tempo de chamada; aqui estava a exceção.
def _estado_path():
    return os.path.join(config.BUS_DIR, "discord_estado.json")


def _usuarios_path():
    return os.path.join(config.BUS_DIR, "discord_usuarios.json")


def _contatos_path():
    return os.path.join(config.BUS_DIR, "discord_contatos.json")


def _ler_json(caminho, padrao):
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return padrao


def _gravar_json(caminho, dados):
    try:
        os.makedirs(os.path.dirname(caminho), exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".discord_", dir=os.path.dirname(caminho))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(dados, f, ensure_ascii=False, indent=2)
            os.replace(tmp, caminho)
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
        return True
    except OSError:
        return False


def _ler_estado():
    return _ler_json(_estado_path(), {})


def _ativo():
    return "discord" in channels.canais_ativos(tolerancia_seg=20)


def _contatos_configurados() -> dict[str, str]:
    """Lê HOSHINO_DISCORD_CONTATOS no formato ``id=Nome;id2=Outro``."""
    bruto = os.environ.get("HOSHINO_DISCORD_CONTATOS", "")
    contatos = {}
    for item in bruto.split(";"):
        item = item.strip()
        if not item:
            continue
        if "=" in item:
            user_id, nome = item.split("=", 1)
        elif ":" in item:
            user_id, nome = item.split(":", 1)
        else:
            user_id, nome = item, item
        user_id, nome = user_id.strip(), nome.strip()
        if user_id.isdigit() and nome:
            contatos[nome.casefold()] = user_id
    return contatos


def _contatos_persistentes() -> dict[str, dict]:
    dados = _ler_json(_contatos_path(), {})
    return dados if isinstance(dados, dict) else {}


def _usuarios_observados() -> dict[str, dict]:
    dados = _ler_json(_usuarios_path(), {})
    return dados if isinstance(dados, dict) else {}


def _normalizar(v: str) -> str:
    return re.sub(r"\s+", " ", str(v or "").casefold()).strip()


def registrar_usuario_observado(user_id: str, username: str = "", display_name: str = "",
                               global_name: str = "", destino: str = "", visto_em: str = "") -> None:
    """Registra um usuário que a ponte efetivamente observou."""
    user_id = str(user_id or "").strip()
    if not user_id.isdigit():
        return
    usuarios = _usuarios_observados()
    anterior = usuarios.get(user_id, {})
    usuarios[user_id] = {
        "id": user_id,
        "username": str(username or anterior.get("username", ""))[:100],
        "display_name": str(display_name or anterior.get("display_name", ""))[:100],
        "global_name": str(global_name or anterior.get("global_name", ""))[:100],
        "ultimo_destino": str(destino or anterior.get("ultimo_destino", ""))[:100],
        "visto_em": str(visto_em or anterior.get("visto_em", ""))[:80],
    }
    _gravar_json(_usuarios_path(), usuarios)


def _candidatos() -> list[dict]:
    itens = []
    for nome, user_id in _contatos_configurados().items():
        itens.append({"id": user_id, "nome": nome, "origem": "config"})
    for nome, contato in _contatos_persistentes().items():
        if isinstance(contato, dict) and str(contato.get("id", "")).isdigit():
            itens.append({"id": str(contato["id"]), "nome": nome, "origem": "persistente", **contato})
    for user_id, contato in _usuarios_observados().items():
        if not str(user_id).isdigit() or not isinstance(contato, dict):
            continue
        for chave in ("username", "global_name", "display_name"):
            valor = contato.get(chave, "")
            if valor:
                itens.append({"id": str(user_id), "nome": str(valor), "origem": "observado", **contato})
    return itens


def localizar_usuario(identificador: str) -> str:
    """Localiza usuário por ID, username, nome exibido ou contato conhecido."""
    q = str(identificador or "").strip()
    if not q:
        return "Erro: identificador vazio."
    if q.startswith("user:"):
        q = q.split(":", 1)[1].strip()
    if q.isdigit():
        obs = _usuarios_observados().get(q, {})
        return json.dumps({"encontrado": True, "id": q, "dados": obs}, ensure_ascii=False)

    nq = _normalizar(q)
    exatos = []
    for item in _candidatos():
        nomes = {_normalizar(item.get("nome", "")),
                 _normalizar(item.get("username", "")),
                 _normalizar(item.get("global_name", "")),
                 _normalizar(item.get("display_name", ""))}
        if nq in nomes:
            exatos.append(item)
    ids = {x["id"] for x in exatos}
    if len(ids) == 1:
        alvo = next(x for x in exatos if x["id"] in ids)
        return json.dumps({"encontrado": True, "id": alvo["id"], "dados": alvo}, ensure_ascii=False)
    if len(ids) > 1:
        return "Erro: mais de um usuário conhecido corresponde a esse nome; use o ID do Discord."

    return (f"Usuário não localizado. Para eu aprender esse contato sem precisar do ID, "
            f"faça a pessoa enviar uma DM para {config.ENTIDADE_NOME} ou mencionar "
            f"{config.ENTIDADE_NOME} em um canal que a ponte leia; depois use novamente "
            "o username exato.")


def adicionar_contato(nome: str, identificador: str) -> str:
    """Cria contato persistente resolvendo ID/username de usuário já observado."""
    nome = str(nome or "").strip()
    identificador = str(identificador or "").strip()
    if not nome or not identificador:
        return "Erro: informe nome e identificador do contato."
    resultado = localizar_usuario(identificador)
    try:
        dados = json.loads(resultado)
    except json.JSONDecodeError:
        return resultado
    if not dados.get("encontrado"):
        return resultado
    contatos = _contatos_persistentes()
    contatos[_normalizar(nome)] = {
        "nome": nome,
        "id": str(dados["id"]),
        "identificador_original": identificador,
    }
    if not _gravar_json(_contatos_path(), contatos):
        return "Encontrei o usuário, mas não consegui salvar o contato."
    return f"Contato '{nome}' salvo com ID {dados['id']}."


def listar_contatos() -> str:
    linhas = [f"CONTATOS DISCORD CONHECIDOS PELA {config.ENTIDADE_NOME.upper()}:"]
    vistos = set()
    for nome, contato in _contatos_persistentes().items():
        if isinstance(contato, dict):
            uid = str(contato.get("id", ""))
            if uid:
                linhas.append(f"- {contato.get('nome', nome)} (id {uid}; contato persistente)")
                vistos.add(uid)
    for nome, uid in sorted(_contatos_configurados().items()):
        linhas.append(f"- {nome} (id {uid}; configuração)")
        vistos.add(uid)
    for uid, contato in _usuarios_observados().items():
        if uid in vistos:
            continue
        nome = contato.get("username") or contato.get("display_name") or contato.get("global_name") or uid
        linhas.append(f"- {nome} (id {uid}; observado)")
    if len(linhas) == 1:
        linhas.append("- nenhum ainda")
    return "\n".join(linhas)


def _resolver_destino(destino: str) -> tuple[str, str]:
    destino = str(destino or "").strip()
    if not destino:
        estado = _ler_estado()
        destino = str(estado.get("ultimo_destino", "")).strip()
        if destino:
            # O adaptador guarda o ID do canal real da última mensagem.
            return "channel", destino
        return "", ""

    if destino.casefold().startswith("user:"):
        user_id = destino.split(":", 1)[1].strip()
        return ("user", user_id) if user_id.isdigit() else ("", "")

    if destino.isdigit():
        return "user", destino

    # Contatos persistentes/configurados e usuários observados.
    nq = _normalizar(destino)
    for item in _candidatos():
        if nq in {_normalizar(item.get("nome")), _normalizar(item.get("username")),
                  _normalizar(item.get("global_name")), _normalizar(item.get("display_name"))}:
            return "user", str(item["id"])

    return "", ""


def estado() -> str:
    s = _ler_estado()
    ativo = _ativo()
    partes = [f"Discord: {'online' if ativo else 'offline'}"]
    if s.get("ultimo_destino"):
        partes.append(f"última conversa: {s['ultimo_destino']}")
    if s.get("ultimo_autor"):
        partes.append(f"último interlocutor: {s['ultimo_autor']}")
    if s.get("ultimo_username"):
        partes.append(f"username: {s['ultimo_username']}")
    if s.get("ultimo_autor_id"):
        partes.append(f"ID do interlocutor: {s['ultimo_autor_id']}")
    if s.get("ultima_mensagem_em"):
        partes.append(f"última mensagem: {s['ultima_mensagem_em']}")
    return " | ".join(partes)


def diagnostico() -> str:
    """Pré-voo local do Discord, sem expor token nem tentar conectar à rede."""
    ativo = _ativo()
    tem_biblioteca = importlib.util.find_spec("discord") is not None
    tem_token = bool(os.environ.get("HOSHINO_DISCORD_TOKEN", "").strip())
    origem_token = "ambiente do processo" if tem_token else ""
    if not tem_token:
        try:
            # O processo principal não precisa herdar a chave. O adaptador lê
            # runtime/discord.env no próprio processo, por isso o diagnóstico
            # consulta somente a presença literal da chave, nunca seu valor.
            from integracoes.discord_env import carregar
            valores, _ = carregar(str(os.path.join(config.RUNTIME_DIR, "discord.env")))
            tem_token = bool(valores.get("HOSHINO_DISCORD_TOKEN", "").strip())
            if tem_token:
                origem_token = "arquivo local"
        except Exception:  # noqa: BLE001
            pass
    pendentes = len(channels.pendentes_de_saida("discord"))
    itens = [f"adaptador={'online' if ativo else 'offline'}",
             f"biblioteca_discord_py={'ok' if tem_biblioteca else 'ausente'}",
             f"token={'configurado (' + origem_token + ')' if tem_token else 'ausente'}",
             f"mensagens_pendentes={pendentes}"]
    if not ativo:
        if not tem_biblioteca:
            itens.append("ação: instale discord.py no ambiente que executa integracoes/discord_bot.py")
        elif not tem_token:
            itens.append("ação: defina HOSHINO_DISCORD_TOKEN antes de iniciar o adaptador")
        else:
            itens.append("ação: inicie integracoes/discord_bot.py e confira as permissões MESSAGE CONTENT")
    return "Discord diagnóstico: " + " | ".join(itens)


def enviar(texto: str, destino: str = "", autor_ref: str = "") -> str:
    texto = (texto or "").strip()
    if not texto:
        return "Erro: texto vazio."
    if not _ativo():
        return "Erro: o adaptador do Discord não está online."

    tipo, resolvido = _resolver_destino(destino)
    if not resolvido:
        return ("Erro: destino Discord não encontrado. Posso usar um contato conhecido, "
                "username de alguém que já interagiu com a ponte, um ID de canal, user:<ID>, "
                "ou o destino vazio para a conversa Discord mais recente.")

    barramento_destino = f"user:{resolvido}" if tipo == "user" else resolvido
    msg_id = channels.enviar("discord", barramento_destino, texto)
    alvo = destino or "última conversa"
    return f"Mensagem colocada na saída do Discord ({msg_id}) para {alvo}."


def abrir_canal(destino: str = "") -> str:
    """Abre no navegador a última conversa observada ou um ID de canal informado."""
    alvo = str(destino or _ler_estado().get("ultimo_destino", "")).strip()
    if alvo.startswith("user:"):
        alvo = "@me/" + alvo.split(":", 1)[1]
    elif alvo.isdigit():
        alvo = f"@me/{alvo}"
    if not alvo or not all(parte == "@me" or parte.isdigit() for parte in alvo.split("/")):
        return "Erro: informe um ID de canal Discord válido ou aguarde uma conversa observada."
    from tools import desktop
    return desktop.abrir_url(f"https://discord.com/channels/{alvo}")
