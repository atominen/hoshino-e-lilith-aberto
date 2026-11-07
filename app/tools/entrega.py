"""
Arquivos que vão e vêm.

Ela cria coisas na oficina — um script, um texto, um gráfico — e antes disso o
resultado morria lá dentro: o usuário tinha que saber o caminho e ir buscar. Aqui
existe entrega de verdade, com dois sentidos:

    runtime/entregas/saida     o que ela te entrega
    runtime/entregas/entrada   o que você deixa para ela

E, quando existe um canal externo ligado (o Discord que você vai montar), a
entrega vira anexo: o arquivo é copiado para a saída e o barramento leva junto com
a mensagem.

**Guarda de segredo.** Assim que existe uma ponte para fora da máquina, "entregar
arquivo" deixa de ser inofensivo: um caminho errado manda sua chave SSH para um
servidor do Discord. Então caminhos com cara de segredo (.ssh, .gnupg, .env,
carteira, credencial, shadow) são recusados na porta, com nome e motivo. Não é
desconfiança dela — é que esse erro é irreversível.

Downloads passam pela chave da internet (`core.rede`) e pelo teto de tamanho do
config, e caem sempre dentro da oficina, nunca soltos no disco.
"""
import os
import re
import shutil
import hashlib
import tempfile
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from core import rede  # noqa: E402

# Nomes/pastas que nunca saem daqui, por mais que o caminho esteja certo.
SEGREDO = re.compile(
    r"(^|/)\.(ssh|gnupg|aws|config/gcloud|docker|kube)(/|$)|"
    r"(^|/)(shadow|passwd|sudoers)$|"
    r"\.(pem|key|keystore|jks|ppk)$|"
    r"(^|/)\.env(\.|$)|"
    r"(credential|token|senha|password|secret|wallet|carteira|seed)",
    re.IGNORECASE)

MAX_ENTREGA_MB = 200


def _seguro(caminho: str) -> tuple:
    from core import entity_access
    if not entity_access.permitted(caminho):return False,'ACESSO_BLOQUEADO: arquivo privado de outra entidade.'
    if SEGREDO.search(caminho.replace("\\", "/")):
        return False, (f"Recusei entregar '{os.path.basename(caminho)}': esse caminho tem "
                       f"cara de segredo (chave, credencial ou senha). Se for mesmo o que "
                       f"você quer enviar, copie o arquivo para outro lugar com outro nome "
                       f"e me peça de novo — assim fica sendo escolha sua, não descuido meu.")
    return True, ""


def _nome_livre(pasta: str, nome: str) -> str:
    """Não sobrescreve entrega anterior: acrescenta -2, -3..."""
    base, extensao = os.path.splitext(nome)
    candidato, n = nome, 2
    while os.path.exists(os.path.join(pasta, candidato)):
        candidato = f"{base}-{n}{extensao}"
        n += 1
    return candidato


def _humano(bytes_: int) -> str:
    for unidade in ("B", "KB", "MB", "GB"):
        if bytes_ < 1024 or unidade == "GB":
            return f"{bytes_:.0f} {unidade}" if unidade == "B" else f"{bytes_:.1f} {unidade}"
        bytes_ /= 1024.0
    return f"{bytes_:.1f} GB"


# ------------------------------------------------------------------ entrega
def entregar(caminho: str, comentario: str = "", canal: str = "", destino: str = "") -> str:
    """Põe um arquivo na caixa de saída. Com `canal`, manda junto pelo barramento."""
    caminho = os.path.expanduser((caminho or "").strip())
    if not caminho:
        return "Erro: preciso do caminho do arquivo."
    if not os.path.isabs(caminho):
        # Relativo é relativo à oficina dela, que é onde ela cria as coisas.
        candidato = os.path.join(config.OFICINA_DIR, caminho)
        caminho = candidato if os.path.exists(candidato) else os.path.abspath(caminho)
    if not os.path.isfile(caminho):
        return f"Erro: não achei o arquivo: {caminho}"

    ok, recusa = _seguro(caminho)
    if not ok:
        return recusa

    tamanho = os.path.getsize(caminho)
    if tamanho > MAX_ENTREGA_MB * 1024 * 1024:
        return (f"O arquivo tem {_humano(tamanho)} e meu teto de entrega é "
                f"{MAX_ENTREGA_MB} MB. Posso compactar ou mandar em pedaços.")

    os.makedirs(config.ENTREGA_SAIDA, exist_ok=True)
    nome = _nome_livre(config.ENTREGA_SAIDA, os.path.basename(caminho))
    alvo = os.path.join(config.ENTREGA_SAIDA, nome)
    def digest(path):
        sha = hashlib.sha256()
        with open(path,'rb') as stream:
            for chunk in iter(lambda:stream.read(1024*1024),b''):
                sha.update(chunk)
        return sha.hexdigest()
    staged = ''
    publicado = False
    try:
        before=digest(caminho)
        fd,staged=tempfile.mkstemp(prefix='.entrega-',dir=config.ENTREGA_SAIDA)
        os.close(fd)
        shutil.copy2(caminho, staged)
        if digest(staged)!=before or digest(caminho)!=before:
            return 'Erro: o arquivo mudou durante a cópia; nenhuma entrega foi publicada.'
        # Publica sem substituir pesos/entregas existentes, inclusive em corrida.
        while True:
            try:
                os.link(staged,alvo)
                publicado=True
                break
            except FileExistsError:
                nome=_nome_livre(config.ENTREGA_SAIDA,os.path.basename(caminho))
                alvo=os.path.join(config.ENTREGA_SAIDA,nome)
        if digest(alvo)!=before:
            raise OSError('hash da entrega não corresponde ao arquivo de origem')
    except OSError as e:
        return (f'RESULTADO_INCERTO: cópia publicada em {alvo}, mas confirmação falhou; não repetir. {e}' if publicado
                else f"Erro: não consegui copiar para a caixa de saída: {e}")
    finally:
        if staged and os.path.exists(staged):
            os.unlink(staged)

    aviso = (f"Entreguei: {alvo} ({_humano(tamanho)}).\nSOURCE={caminho}\nPATH={alvo}\n"
             f"[ENTREGA LOCAL VERIFICADA sha256={before}]")
    if comentario:
        aviso += f" {comentario}"

    if canal:
        try:
            from social import channels
            identifier=channels.enviar(canal, destino, comentario or f"Segue o arquivo: {nome}",anexo=alvo)
            aviso += f"\nCANAL_STATUS=queued\nMESSAGE_ID={identifier}\nEnfileirado para {canal}; entrega remota ainda não confirmada."
        except Exception as e:  # noqa: BLE001
            aviso = f"Erro: cópia local verificada, mas não consegui enfileirar no canal {canal}.\n"+aviso+f"\n{type(e).__name__}"
    return aviso


def listar_entregues(limite: int = 15) -> str:
    pasta = config.ENTREGA_SAIDA
    if not os.path.isdir(pasta):
        return "Ainda não entreguei nada."
    itens = []
    for nome in sorted(os.listdir(pasta), key=lambda n: -os.path.getmtime(
            os.path.join(pasta, n)))[:limite]:
        caminho = os.path.join(pasta, nome)
        if not os.path.isfile(caminho):
            continue
        quando = datetime.fromtimestamp(os.path.getmtime(caminho))
        itens.append(f"- {nome} ({_humano(os.path.getsize(caminho))}, {quando:%d/%m %H:%M})")
    return "Caixa de saída:\n" + "\n".join(itens) if itens else "Ainda não entreguei nada."


# ---------------------------------------------------------------- recebidos
def listar_recebidos(limite: int = 15) -> str:
    """O que você deixou para ela em runtime/entregas/entrada."""
    pasta = config.ENTREGA_ENTRADA
    os.makedirs(pasta, exist_ok=True)
    itens = []
    for nome in sorted(os.listdir(pasta), key=lambda n: -os.path.getmtime(
            os.path.join(pasta, n)))[:limite]:
        caminho = os.path.join(pasta, nome)
        if not os.path.isfile(caminho):
            continue
        quando = datetime.fromtimestamp(os.path.getmtime(caminho))
        itens.append(f"- {nome} ({_humano(os.path.getsize(caminho))}, {quando:%d/%m %H:%M})")
    if not itens:
        return f"Nada na caixa de entrada ({pasta})."
    return "Recebi estes arquivos:\n" + "\n".join(itens)


def ler_recebido(nome: str, max_chars: int = 6000) -> str:
    caminho = os.path.join(config.ENTREGA_ENTRADA, os.path.basename(nome or ""))
    if not os.path.isfile(caminho):
        return f"Não achei '{nome}' na caixa de entrada."
    try:
        with open(caminho, "r", encoding="utf-8", errors="replace") as f:
            conteudo = f.read(max_chars + 1)
    except OSError as e:
        return f"Não consegui ler: {e}"
    if len(conteudo) > max_chars:
        return conteudo[:max_chars] + "\n[...cortado]"
    return conteudo or "(arquivo vazio)"


def analisar_recebido(nome: str) -> str:
    """Inspeciona metadados e texto de um arquivo recebido sem executá-lo."""
    caminho = os.path.join(config.ENTREGA_ENTRADA, os.path.basename(nome or ""))
    if not os.path.isfile(caminho):
        return f"Não achei '{nome}' na caixa de entrada."
    tamanho = os.path.getsize(caminho)
    tipo = os.path.splitext(caminho)[1].lower() or "sem extensão"
    if tipo in {".txt", ".md", ".py", ".json", ".csv", ".log", ".html"}:
        return f"Arquivo: {os.path.basename(caminho)} | tipo={tipo} | tamanho={_humano(tamanho)}\n\n{ler_recebido(nome)}"
    return f"Arquivo: {os.path.basename(caminho)} | tipo={tipo} | tamanho={_humano(tamanho)}. Não executei nem interpretei seu conteúdo."


def caminho_imagem_recebida(nome: str) -> str:
    """Devolve uma imagem da caixa de entrada somente se a extensão for segura."""
    caminho = os.path.join(config.ENTREGA_ENTRADA, os.path.basename(nome or ""))
    if not os.path.isfile(caminho):
        return ""
    if os.path.splitext(caminho)[1].lower() not in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
        return ""
    return caminho


def novidades_na_entrada(desde_segundos: int = 300) -> list:
    """Arquivos que apareceram há pouco — vira percepção no ciclo dela."""
    pasta = config.ENTREGA_ENTRADA
    if not os.path.isdir(pasta):
        return []
    agora = datetime.now().timestamp()
    recentes = []
    for nome in os.listdir(pasta):
        # Importação do clipboard prepara um anexo para o rascunho. O pedido
        # com o nome do arquivo chega pelo chat quando o usuário envia.
        if re.fullmatch(r'[0-9a-f]{12}-clipboard-(?:texto\.txt|print\.png)', nome):
            continue
        caminho = os.path.join(pasta, nome)
        if os.path.isfile(caminho) and agora - os.path.getmtime(caminho) <= desde_segundos:
            recentes.append(nome)
    return recentes


# ----------------------------------------------------------------- download
def baixar_da_web(url: str, nome: str = "") -> str:
    """Baixa para a oficina dela. Passa pela chave da internet e pelo teto de MB."""
    pode, recusa = rede.exigir("baixar arquivo", url=url)
    if not pode:
        return recusa
    from tools import web
    return web.baixar(url, destino=os.path.join(config.OFICINA_DIR, "baixados"), nome=nome)


def resumo() -> str:
    saida = len(os.listdir(config.ENTREGA_SAIDA)) if os.path.isdir(config.ENTREGA_SAIDA) else 0
    entrada = len(os.listdir(config.ENTREGA_ENTRADA)) \
        if os.path.isdir(config.ENTREGA_ENTRADA) else 0
    return f"entregas: {saida} na saída, {entrada} na entrada"
