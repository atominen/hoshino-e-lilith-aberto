import hashlib
import importlib.util
import json
import os
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pc2"))
from verificar_pc2 import verify
from configurar_pc2 import configure
spec = importlib.util.spec_from_file_location("builder", ROOT / "scripts/montar_pacote_alistair.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "source"
        for source in builder.ALLOWED:
            path = self.root / source
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("test source")
        # Essas coisas não pertencem à exportação, mesmo estando no projeto.
        (self.root / "discord.env").write_text("SENSITIVE_TEST_MARKER")
        (self.root / "mind.db").write_text("SENSITIVE_TEST_MARKER")
        self.models = self.base / "models"
        blob = b"fake model bytes"
        digest = hashlib.sha256(blob).hexdigest()
        path = self.models / "blobs" / ("sha256-" + digest)
        path.parent.mkdir(parents=True)
        path.write_bytes(blob)
        manifest = self.models / builder.MODEL_PATH
        manifest.parent.mkdir(parents=True)
        manifest.write_text(json.dumps({"config": {"digest": "sha256:" + digest, "size": len(blob)}, "layers": []}))
        self.binary = self.base / "ollama"
        self.binary.write_text("fake engine")
        self.libs = self.base / "libs"
        self.libs.mkdir()
        (self.libs / "libggml.so.1").write_text("cpu")
        (self.libs / "libggml.so").symlink_to("libggml.so.1")
        (self.libs / "cuda_v12").mkdir()
        (self.libs / "cuda_v12/gpu.so").write_text("gpu")
        (self.libs / "libgomp.so.1").write_text("system library")

    def build(self):
        return builder.build(self.root, self.base / "output", model_root=self.models,
                             executable=self.binary, libraries=self.libs, engine_version="test")

    def test_allowlist_hashes_symlinks_archive_no_private_files(self):
        result = self.build()
        root = Path(result["folder"])
        manifest = verify(root)
        self.assertFalse(manifest["credentials_included"])
        self.assertFalse(manifest["entity_minds_included"])
        self.assertFalse((root / "discord.env").exists())
        self.assertFalse((root / "mind.db").exists())
        self.assertFalse((root / "engine/lib/ollama/cuda_v12").exists())
        self.assertFalse((root / "engine/lib/ollama/libgomp.so.1").exists())
        self.assertTrue((root / "engine/lib/ollama/libggml.so").is_symlink())
        with tarfile.open(result["archive"]) as archive:
            self.assertTrue(all(m.name == "alistair_pc2" or m.name.startswith("alistair_pc2/") for m in archive.getmembers()))
        with self.assertRaises(ValueError): self.build()

    def test_blob_tampering_aborts_before_export(self):
        next((self.models / "blobs").iterdir()).write_text("damaged")
        with self.assertRaises(ValueError): self.build()
        self.assertFalse((self.base / "output").exists())

    def test_library_escape_aborts(self):
        (self.libs / "libggml-evil.so").symlink_to(self.binary)
        with self.assertRaises(ValueError): self.build()

    def test_config_only_once_private_key_no_initial_remote_activation(self):
        root = self.base / "target"
        root.mkdir()
        pair = configure(root, "192.168.1.3", "192.168.1.2")
        self.assertEqual((root / "lan.key").stat().st_mode & 0o777, 0o600)
        self.assertEqual((root / "lan.key").read_text(), (pair / "lan.key").read_text())
        self.assertEqual(json.loads((root / "worker.json").read_text())["allowed_clients"], ["192.168.1.2"])
        with self.assertRaises(ValueError): configure(root, "192.168.1.3", "192.168.1.2")
        self.assertFalse((root / "alistair_pc2.json").exists())

    def test_integrity_detects_post_transfer_modification(self):
        root = Path(self.build()["folder"])
        (root / "pc2_node.py").write_text("modified")
        with self.assertRaises(ValueError): verify(root)


if __name__ == "__main__": unittest.main()
