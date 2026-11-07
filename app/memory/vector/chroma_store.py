"""
Memória vetorial (Chroma) — agora opcional e com distância.

Duas mudanças que importam:

1. Importação tolerante. Antes, `import chromadb` no topo derrubava tudo que
   dependesse de memória se o pacote não estivesse instalado ou o banco vetorial
   estivesse corrompido. Agora a Hoshino continua de pé com a memória SQLite,
   só perde a busca por significado — e ela sabe disso (`estado()`).

2. As buscas devolvem a distância junto com o texto. Sem isso não dá para fazer
   recuperação híbrida (significado + recência + confiança + uso): o código
   antigo só sabia "esses são os 2 mais parecidos", sem saber o quão parecidos.
"""
import os

# A configuração é obrigatória: um fallback junto ao código criaria outra
# memória silenciosamente depois de mover o pacote para app/.
from config import VECTOR_DIR, ENTIDADE_ID

_PREFIXO = ENTIDADE_ID
_NOMES_COLECOES = {
    "episodio": f"{_PREFIXO}_episodes",
    "conhecimento": f"{_PREFIXO}_knowledge",
    "procedimento": f"{_PREFIXO}_procedures",
}

DISPONIVEL = False
ERRO_INICIALIZACAO = None
client = None
collection = None
knowledge_collection = None
procedure_collection = None

try:
    import chromadb

    os.makedirs(VECTOR_DIR, exist_ok=True)
    client = chromadb.PersistentClient(path=VECTOR_DIR)
    collection = client.get_or_create_collection(name=_NOMES_COLECOES["episodio"])
    knowledge_collection = client.get_or_create_collection(name=_NOMES_COLECOES["conhecimento"])
    procedure_collection = client.get_or_create_collection(name=_NOMES_COLECOES["procedimento"])
    DISPONIVEL = True
except Exception as e:  # noqa: BLE001
    ERRO_INICIALIZACAO = str(e)


def estado() -> str:
    if DISPONIVEL:
        try:
            return (f"memória vetorial ativa ({collection.count()} episódios, "
                    f"{knowledge_collection.count()} conhecimentos, "
                    f"{procedure_collection.count()} procedimentos)")
        except Exception as e:  # noqa: BLE001
            return f"memória vetorial instável: {e}"
    return f"memória vetorial indisponível ({ERRO_INICIALIZACAO}) — usando só SQLite"


def _colecao(tipo: str):
    return {"episodio": collection, "conhecimento": knowledge_collection,
            "procedimento": procedure_collection}.get(tipo)


def salvar(tipo: str, identificador: str, texto: str, metadados: dict = None):
    """Guarda um texto na coleção certa. Silencioso se o Chroma não estiver disponível."""
    if not DISPONIVEL:
        return False
    alvo = _colecao(tipo)
    if alvo is None or not (texto or "").strip():
        return False
    try:
        alvo.upsert(documents=[texto], ids=[identificador],
                    metadatas=[metadados or {"tipo": tipo}])
        return True
    except Exception as exc:  # noqa: BLE001
        from core import diagnostics
        diagnostics.persistence_failure('vector.upsert', VECTOR_DIR, exc, retry_safe=True, record_id=identificador)
        return False


def buscar(tipo: str, consulta: str, limite: int = 4) -> list:
    """Devolve [{'id','texto','distancia','metadados'}] ordenado por similaridade."""
    if not DISPONIVEL or not (consulta or "").strip():
        return []
    alvo = _colecao(tipo)
    if alvo is None:
        return []
    try:
        total = alvo.count()
        if not total:
            return []
        resultado = alvo.query(query_texts=[consulta], n_results=min(limite, total))
    except Exception as exc:  # noqa: BLE001
        from core import diagnostics
        diagnostics.persistence_failure('vector.query', VECTOR_DIR, exc, retry_safe=True)
        return []
    documentos = (resultado.get("documents") or [[]])[0]
    ids = (resultado.get("ids") or [[]])[0]
    distancias = (resultado.get("distances") or [[None] * len(documentos)])[0]
    metadados = (resultado.get("metadatas") or [[{}] * len(documentos)])[0]
    return [{"id": i, "texto": d, "distancia": dist, "metadados": m or {}}
            for i, d, dist, m in zip(ids, documentos, distancias, metadados)]


def remover(tipo: str, identificador: str):
    if not DISPONIVEL:
        return False
    alvo = _colecao(tipo)
    try:
        alvo.delete(ids=[identificador])
        return True
    except Exception as exc:  # noqa: BLE001
        from core import diagnostics
        diagnostics.persistence_failure('vector.delete', VECTOR_DIR, exc, retry_safe=True, record_id=identificador)
        return False


# --- compatibilidade com o código antigo -----------------------------------

def save_vector_memory(ep_id, text, timestamp):
    return salvar("episodio", ep_id, f"[{timestamp}] {text}",
                  {"type": "episodic", "date": timestamp})


def search_memory(query, limit=2):
    return [r["texto"] for r in buscar("episodio", query, limit)]


def save_knowledge_vector(mem_id, text, timestamp):
    return salvar("conhecimento", mem_id, text, {"type": "knowledge", "date": timestamp})


def search_knowledge(query, limit=4):
    return [r["texto"] for r in buscar("conhecimento", query, limit)]
