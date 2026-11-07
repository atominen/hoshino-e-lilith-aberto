"""Separação das entidades sem carregar modelos, bancos ou serviços reais."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from entity_paths import carregar_entidade


class EstruturaEntidadesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="hoshino_lilith_estrutura_")
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)

    def entidade(self, identificador, status="ativa", **extras):
        pasta = self.raiz / "entidades" / identificador
        pasta.mkdir(parents=True)
        dados = {"id": identificador, "nome": identificador.title(), "status": status}
        dados.update(extras)
        (pasta / "entidade.json").write_text(json.dumps(dados), encoding="utf-8")
        return pasta

    def test_estado_e_identidade_sao_exclusivos_de_cada_entidade(self):
        for entidade in ("primeira", "segunda"):
            self.entidade(entidade)
        primeira = carregar_entidade(self.raiz, "primeira")
        segunda = carregar_entidade(self.raiz, "segunda")
        self.assertEqual(primeira.id, "primeira")
        self.assertEqual(segunda.nome, "Segunda")
        for campo in ("identity", "memory", "runtime", "workspace", "config"):
            with self.subTest(campo=campo):
                caminho_a = Path(getattr(primeira, campo))
                caminho_b = Path(getattr(segunda, campo))
                self.assertEqual(caminho_a.parent, primeira.raiz)
                self.assertEqual(caminho_b.parent, segunda.raiz)
                self.assertNotEqual(caminho_a, caminho_b)
                caminho_a.mkdir()
                caminho_b.mkdir()
                (caminho_a / "estado.txt").write_text("primeira", encoding="utf-8")
                (caminho_b / "estado.txt").write_text("segunda", encoding="utf-8")
                self.assertEqual((caminho_a / "estado.txt").read_text(), "primeira")
                self.assertEqual((caminho_b / "estado.txt").read_text(), "segunda")

    def test_launcher_absolute_entrypoint_keeps_project_modules_without_inherited_pythonpath(self):
        # A suíte normalmente acrescenta a raiz ao path, mascarando o boot real
        # de app/entity_runner.py. Este filho parte de um ambiente limpo e só
        # usa arquivos descartáveis; não lê .env real nem inicia entidades.
        root=self.raiz;project=Path(__file__).resolve().parents[1]
        (root/'scripts').mkdir();(root/'app').mkdir();(root/'laboratorio').mkdir()
        helper=root/'scripts/ambiente.sh';helper.write_text((project/'scripts/ambiente.sh').read_text())
        (root/'laboratorio/__init__.py').write_text('')
        (root/'laboratorio/recuperacao_modelos.py').write_text('FIXTURE_ONLY=True\n')
        entry=root/'app/entrypoint_fixture.py'
        entry.write_text('import json,os\nfrom laboratorio import recuperacao_modelos\n'
            'print(json.dumps({"module":recuperacao_modelos.__file__,"entity":os.environ["HOSHINO_ENTIDADE"],"model":os.environ["HOSHINO_MODEL"]}))\n')
        for entity in ['hoshino','lilith','alistair']:
            with self.subTest(entity=entity):
                base=self.entidade(entity);(base/'config').mkdir()
                (base/'config'/(entity+'.env')).write_text('HOSHINO_MODEL="'+entity+'-fixture:latest"\n')
                env={'PATH':os.environ.get('PATH','/usr/bin:/bin'),'LANG':'C.UTF-8','HOSHINO_ENTIDADE':entity}
                result=subprocess.run(['bash','-c','source "$1"; exec "$2" -B "$3"','fixture',str(helper),sys.executable,str(entry)],
                    cwd=root,env=env,capture_output=True,text=True,timeout=10)
                self.assertEqual(result.returncode,0,result.stderr)
                data=json.loads(result.stdout);self.assertEqual(data['entity'],entity)
                self.assertEqual(data['model'],entity+'-fixture:latest')
                self.assertEqual(Path(data['module']),root/'laboratorio/recuperacao_modelos.py')

    def test_reservada_nao_inicia_nem_usa_dados_da_hoshino(self):
        hoshino = self.entidade("hoshino")
        identidade = hoshino / "identity"
        identidade.mkdir()
        estado = identidade / "self_model.json"
        estado.write_text('{"nome": "Hoshino"}', encoding="utf-8")
        lilith = self.entidade("futura", status="reservada")
        antes = estado.read_bytes()
        with self.assertRaises(ValueError):
            carregar_entidade(self.raiz, "futura")
        self.assertEqual(estado.read_bytes(), antes)
        self.assertEqual([p.name for p in lilith.iterdir()], ["entidade.json"])

    def test_lilith_ativa_tem_identidade_e_memoria_separadas(self):
        hoshino = self.entidade("hoshino")
        lilith = self.entidade("lilith")
        (hoshino / "identity").mkdir()
        (lilith / "identity").mkdir()
        (lilith / "identity/self_model.json").write_text(
            '{"identity":{"name":"Lilith"}}', encoding="utf-8")
        carregada = carregar_entidade(self.raiz, "lilith")
        self.assertEqual(carregada.nome, "Lilith")
        self.assertNotEqual(carregada.memory, hoshino / "memory")
        self.assertEqual(carregada.identity / "self_model.json",
                         self.raiz / "entidades/lilith/identity/self_model.json")

    def test_desconhecida_nao_cria_entidade_nem_recai_na_hoshino(self):
        self.entidade("hoshino")
        with self.assertRaises((FileNotFoundError, ValueError)):
            carregar_entidade(self.raiz, "desconhecida")
        self.assertFalse((self.raiz / "entidades" / "desconhecida").exists())

    def test_identificador_nao_escapa_da_pasta_entidades(self):
        self.entidade("hoshino")
        for identificador in ("../hoshino", "/tmp/hoshino", "hoshino/lilith", "", "."):
            with self.subTest(identificador=identificador), self.assertRaises(ValueError):
                carregar_entidade(self.raiz, identificador)

    def test_manifesto_de_outra_entidade_nao_e_aceito(self):
        self.entidade("lilith", id="hoshino")
        with self.assertRaises(ValueError):
            carregar_entidade(self.raiz, "lilith")

    def test_link_de_memoria_para_outra_entidade_e_recusado(self):
        primeira = self.entidade("primeira")
        segunda = self.entidade("segunda")
        (segunda / "memory").mkdir()
        (primeira / "memory").symlink_to(segunda / "memory", target_is_directory=True)
        with self.assertRaises(ValueError):
            carregar_entidade(self.raiz, "primeira")

    def test_arquivo_relativo_pertence_a_oficina_da_entidade(self):
        from tools import filesystem
        oficina = self.raiz / "oficina"
        with patch.object(filesystem, "OFICINA_DIR", str(oficina)):
            filesystem.workspace("salvar", "projeto/hello.txt", "hello")
        self.assertEqual((oficina / "projeto/hello.txt").read_text(), "hello")


if __name__ == "__main__":
    unittest.main(verbosity=2)
