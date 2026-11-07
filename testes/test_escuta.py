"""Escuta seletiva: varios canais, cada frase com a sua origem.

O ponto do modulo nao e transcrever (isso o Transcritor ja fazia); e nao
confundir quem falou o que, e separar perceber de responder.
"""
import os
import queue
import sys
import tempfile
from datetime import datetime

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "app"))

TMP = tempfile.mkdtemp(prefix="hoshino_escuta_")
import config  # noqa: E402

config.RUNTIME_DIR = TMP

from social import escuta  # noqa: E402

ok, falhas = 0, []


def checar(desc, cond, det=""):
    global ok
    if cond:
        ok += 1
        print(f"  ok   {desc}")
    else:
        falhas.append(desc)
        print(f"  FALHA {desc} {det}")


class TranscritorFalso:
    """Faz o papel do Transcritor sem microfone, placa de som nem Whisper."""

    def __init__(self, origem):
        self.origem = origem
        self.escutando = True
        self.fila = queue.Queue()

    def falar(self, texto):
        self.fila.put({"texto": texto, "origem": self.origem, "quando": datetime.now()})

    def pegar(self):
        try:
            return self.fila.get_nowait()
        except queue.Empty:
            return None

    def parar_escuta(self):
        self.escutando = False
        return "parei"


def abrir(canal, atencao):
    """Injeta um canal ja aberto, pulando a abertura de hardware."""
    t = TranscritorFalso(canal)
    escuta._CANAIS[canal] = {"transcritor": t, "dispositivo": f"fake:{canal}",
                             "atencao": atencao, "desde": datetime.now()}
    return t


print("== Escuta seletiva ==")

escuta._CANAIS.clear()
escuta._OUVIDO.clear()

checar("sem canal aberto, ela diz isso claramente",
       "não estou escutando" in escuta.estado().lower(), escuta.estado())

discord = abrir("discord", "ativa")
jogo = abrir("jogo", "passiva")
micro = abrir("microfone", "ignorar")

checar("estado mostra todos os canais abertos",
       all(c in escuta.estado() for c in ("discord", "jogo", "microfone")))

discord.falar("Gustavo, depois dessa partida a gente joga outra?")
jogo.falar("som ambiente da partida")
micro.falar("isso aqui nao deveria ser coletado")

novos = escuta.coletar()
origens = [n["origem"] for n in novos]

checar("canal ativo chega para ela agir", "discord" in origens, str(origens))
checar("canal passivo NAO vira evento de acao", "jogo" not in origens, str(origens))
checar("canal ignorado nem e lido", "microfone" not in origens, str(origens))

# ...mas o passivo continua consultavel: perceber != responder, nao != esquecer.
ouvido = escuta.o_que_ouvi()
checar("o passivo fica guardado e consultavel", "som ambiente" in ouvido, ouvido)
checar("o ignorado nao entra nem no historico",
       "nao deveria ser coletado" not in ouvido, ouvido)
checar("cada frase carrega a origem", "[discord]" in ouvido, ouvido)

# Duas frases iguais de origens diferentes sao coisas diferentes.
escuta._OUVIDO.clear()
discord.falar("pode ser")
jogo.falar("pode ser")
escuta.coletar()
linhas = escuta.o_que_ouvi().splitlines()
checar("mesmo texto de origens diferentes nao se funde",
       len(linhas) == 2 and "[discord]" in escuta.o_que_ouvi()
       and "[jogo]" in escuta.o_que_ouvi(), escuta.o_que_ouvi())

# Filtro por canal.
so_jogo = escuta.o_que_ouvi("jogo")
checar("da para olhar um canal so", "[jogo]" in so_jogo and "[discord]" not in so_jogo, so_jogo)

# Trocar atencao sem reabrir.
checar("mudar atencao responde ok", "passiva" in escuta.mudar_atencao("discord", "passiva"))
discord.falar("agora isso e so contexto")
checar("apos virar passiva, nao age mais",
       "discord" not in [n["origem"] for n in escuta.coletar()])
checar("atencao invalida e recusada", "Erro" in escuta.mudar_atencao("discord", "meia-boca"))
checar("canal inexistente e recusado", "não está aberto" in escuta.mudar_atencao("fantasma", "ativa"))

# Fechar.
checar("fecha um canal", "discord" in escuta.parar_de_ouvir("discord"))
checar("canal fechado sai do estado", "discord" not in escuta.estado())
escuta.parar_de_ouvir()
checar("fecha todos de uma vez", escuta.canais_abertos() == [], str(escuta.canais_abertos()))

# Descoberta de fontes nao pode explodir numa maquina sem pactl.
try:
    texto = escuta.listar_fontes()
    checar("listar fontes nunca levanta excecao", isinstance(texto, str) and texto)
except Exception as e:  # noqa: BLE001
    checar("listar fontes nunca levanta excecao", False, repr(e))

# As ferramentas estao registradas no nucleo (entram no manual sozinhas).
from core import dispatch  # noqa: E402

nomes = {e["function"]["name"] for e in dispatch.ESQUEMAS}
esperadas = {"listar_fontes_audio", "ouvir_canal", "parar_de_ouvir",
             "mudar_atencao_canal", "o_que_ouvi", "estado_da_escuta"}
checar("as 6 ferramentas de escuta estao no registro", esperadas <= nomes,
       str(sorted(esperadas - nomes)))
checar("todas tem executor", all(n in dispatch.HANDLERS for n in esperadas))
checar("aparecem no manual de habilidades",
       all(n in dispatch.executar("manual_habilidades", {}) for n in esperadas))

print()
print("=" * 58)
print(f"{ok} verificacoes ok, {len(falhas)} falha(s)")
for f in falhas:
    print("  -", f)
sys.exit(1 if falhas else 0)
