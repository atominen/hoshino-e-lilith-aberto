import sys
from pathlib import Path
from unittest.mock import patch,Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from tools import minecraft_launcher as ml

def test_owned_pending_bridge_does_not_start_duplicate():
    child=Mock();child.poll.return_value=None
    with patch.object(ml,'_bridge_proc',child),patch.object(ml,'_saude_ponte',return_value=None),patch.object(ml.subprocess,'Popen') as spawn:
        result=ml.iniciar_ponte()
    assert 'própria' in result
    spawn.assert_not_called()


def test_estado_shape():
    e = ml.estado()
    assert "servidor_porta" in e
    assert "ponte_online" in e
    assert "ponte_compativel" in e


def test_nao_preparado_sem_node_modules():
    with patch.object(ml, "MC_DIR", Path("/tmp/hoshino_nonexistent_mc")):
        ok, motivo = ml._preparado()
        assert not ok
        assert "Mineflayer" in motivo


def test_ponte_online():
    class R:
        ok = True
        def json(self):
            return {"ok": True, "protocol": 3}
    with patch.object(ml.requests, "get", return_value=R()):
        assert ml.ponte_online() is True
        assert ml.ponte_compativel() is True


def test_ponte_sem_protocolo_nao_e_compativel():
    class R:
        ok = True
        def json(self):
            return {"ok": True, "state": {"connected": True}}
    with patch.object(ml.requests, "get", return_value=R()):
        assert ml.ponte_online() is True
        assert ml.ponte_compativel() is False


def test_iniciar_ponte_independe_do_servidor_local():
    class R:
        ok = True
        def json(self):
            return {"ok": True, "protocol": 3, "state": {}}
    with patch.object(ml.requests, "get", return_value=R()), \
         patch.object(ml, "_preparado", return_value=(False, "servidor ausente")):
        assert ml.iniciar_ponte() == "ponte Mineflayer já estava rodando"


if __name__=='__main__':
    checks=[fn for name,fn in list(globals().items()) if name.startswith('test_') and callable(fn)]
    for check in checks:check()
    print(str(len(checks))+' verificações do lançador passaram (offline).')
