"""Ponte de áudio PC1 ↔ PC2 (11/11): HTTP real em loopback, gravador/tocador falsos (sem placa de som)."""
import os
import struct
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app/ui'))
import native_ponte as ponte

# Gravador falso: amostras s16 crescentes (mod 2^16), em blocos de 20 ms no ritmo real.
GRAVADOR = r'''
import sys,time,struct
canais=int(sys.argv[1]);n=0;out=sys.stdout.buffer
while True:
    quadros=[]
    for _ in range(960):
        quadros.append(struct.pack('<'+'h'*canais,*([((n+32768)%65536)-32768]*canais)));n+=1
    out.write(b''.join(quadros));out.flush();time.sleep(0.02)
'''


def gravar_falso(_dispositivo, canais, _nome='x'):
    return [sys.executable, '-c', GRAVADOR, str(canais)]


def continuo(dados, canais):
    """Todas as amostras em sequência, sem buraco (só vale sem descarte)."""
    quadro = 2 * canais
    valores = [struct.unpack_from('<h', dados, i)[0] for i in range(0, len(dados) - quadro + 1, quadro)]
    return all(((b - a) % 65536) == 1 for a, b in zip(valores, valores[1:]))


class Ponte(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.saidas = []

        def tocar_falso(_dispositivo, canais, _nome='x'):
            arquivo = Path(self.tmp.name) / f'tocado-{len(self.saidas)}-{canais}.raw'
            self.saidas.append(arquivo)
            return ['sh', '-c', 'cat > "$0"', str(arquivo)]
        self.tocar_falso = tocar_falso
        self.servidor = ponte.Servidor(gravar=gravar_falso, tocar=lambda d, c: tocar_falso(d, c))
        servidor = self.servidor

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def do_GET(self):
                if self.path == '/api/control/pc2/som': servidor.servir_som(self)
            def do_POST(self):
                if self.path == '/api/control/pc2/microfone': servidor.receber_microfone(self)
        self.http = ThreadingHTTPServer(('127.0.0.1', 0), Handler);self.http.daemon_threads = True
        threading.Thread(target=self.http.serve_forever, daemon=True).start()
        self.addCleanup(self.http.server_close);self.addCleanup(self.http.shutdown)
        self.base = f'http://127.0.0.1:{self.http.server_port}'

    def esperar(self, condicao, segundos=5):
        fim = time.monotonic() + segundos
        while time.monotonic() < fim:
            if condicao(): return True
            time.sleep(0.05)
        return False

    def test_som_do_pc1_e_microfone_do_pc2_atravessam_continuos(self):
        cliente = ponte.Cliente(self.base, 'x', gravar=gravar_falso, tocar=lambda d, c: self.tocar_falso(d, c))
        self.addCleanup(cliente.parar)
        cliente.ligar('som', True);cliente.ligar('microfone', True)
        self.assertTrue(self.esperar(lambda: set(self.servidor.estado()) == {'som', 'microfone'}))
        time.sleep(1.5)
        estado = self.servidor.estado()
        self.assertGreater(estado['som']['bytes'], 100_000)        # ~192 kB/s estéreo
        self.assertGreater(estado['microfone']['bytes'], 50_000)   # ~96 kB/s mono
        self.assertIn('desde', cliente.estado()['som']);self.assertIn('desde', cliente.estado()['microfone'])
        cliente.parar()
        self.assertTrue(self.esperar(lambda: self.servidor.estado() == {}), self.servidor.estado())
        tocados = {int(p.stem.rsplit('-', 1)[1]): p.read_bytes() for p in self.saidas}
        self.assertGreater(len(tocados[2]), 100_000);self.assertTrue(continuo(tocados[2], 2))
        self.assertGreater(len(tocados[1]), 50_000);self.assertTrue(continuo(tocados[1], 1))

    def test_nova_conexao_de_som_substitui_a_anterior(self):
        a = ponte.Cliente(self.base, 'x', tocar=lambda d, c: self.tocar_falso(d, c));self.addCleanup(a.parar)
        a.ligar('som', True)
        self.assertTrue(self.esperar(lambda: 'som' in self.servidor.estado()))
        primeiro = self.servidor.estado()['som']['desde']
        b = ponte.Cliente(self.base, 'x', tocar=lambda d, c: self.tocar_falso(d, c));self.addCleanup(b.parar)
        b.ligar('som', True)
        self.assertTrue(self.esperar(lambda: self.servidor.estado().get('som', {}).get('desde', primeiro) != primeiro))
        a.parar();b.parar()
        self.assertTrue(self.esperar(lambda: self.servidor.estado() == {}))

    def test_desligar_so_o_microfone_mantem_o_som(self):
        cliente = ponte.Cliente(self.base, 'x', gravar=gravar_falso, tocar=lambda d, c: self.tocar_falso(d, c))
        self.addCleanup(cliente.parar)
        cliente.ligar('som', True);cliente.ligar('microfone', True)
        self.assertTrue(self.esperar(lambda: set(self.servidor.estado()) == {'som', 'microfone'}))
        cliente.ligar('microfone', False)
        self.assertTrue(self.esperar(lambda: set(self.servidor.estado()) == {'som'}))
        self.assertEqual(cliente.estado()['microfone'], 'desligado')

    def test_pc1_fechado_vira_aviso_e_reconecta_quando_volta(self):
        porta = self.http.server_port
        self.http.shutdown();self.http.server_close()
        cliente = ponte.Cliente(f'http://127.0.0.1:{porta}', 'x', tocar=lambda d, c: self.tocar_falso(d, c))
        self.addCleanup(cliente.parar)
        cliente.ligar('som', True)
        self.assertTrue(self.esperar(lambda: 'tentando de novo' in cliente.estado()['som']))

    def test_tocador_atrasado_descarta_em_vez_de_acumular(self):
        # Tocador que nunca lê: a fila não pode passar do teto; o excesso é descartado.
        tocador = ponte.Tocador(None, 2, 'teste', comando=['sh', '-c', 'sleep 30'])
        self.addCleanup(tocador.fechar)
        bloco = bytes(ponte.BLOCO_MS * ponte.bytes_por_ms(2))
        for _ in range(100):  # 2 s de áudio
            tocador.alimentar(bloco)
        self.assertLessEqual(tocador.na_fila, ponte.FOLGA_MAX_MS * ponte.bytes_por_ms(2))
        self.assertGreater(tocador.descartado_ms, 1000)
        self.assertEqual(tocador.na_fila % 4, 0)  # nunca corta um quadro estéreo ao meio

    def test_microfone_sem_chunked_e_recusado(self):
        import http.client
        conexao = http.client.HTTPConnection('127.0.0.1', self.http.server_port, timeout=5)
        conexao.request('POST', '/api/control/pc2/microfone', body=b'abc', headers={'Content-Length': '3'})
        with self.assertRaises(Exception):
            conexao.getresponse().read()
        self.assertEqual(self.servidor.estado(), {})


if __name__ == '__main__':
    unittest.main()
