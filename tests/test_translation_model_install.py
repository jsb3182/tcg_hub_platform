import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


script = Path(__file__).resolve().parents[1] / "deploy/install-translation-model.py"
spec = importlib.util.spec_from_file_location("model_install", script)
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class ModelInstallTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.target = Path(tmp.name) / "installed-model"
        self.source = Path(tmp.name) / "transfer"
        self.source.mkdir()
        hashes = {}
        for name in installer.FILES:
            contents = (name + " exact fixture bytes").encode()
            (self.source / name).write_bytes(contents)
            hashes[name] = (len(contents), hashlib.sha256(contents).hexdigest())
        replace = patch.object(installer, "FILES", hashes)
        replace.start()
        self.addCleanup(replace.stop)
        online = patch.object(installer, "urlopen", side_effect=AssertionError("unexpected network"))
        online.start()
        self.addCleanup(online.stop)

    def test_changed_transfer_keeps_install_invisible_until_verified(self):
        weights = self.source / "model.bin"
        wanted = weights.read_bytes()
        weights.write_bytes(b"!" * len(wanted))
        with self.assertRaises(ValueError):
            installer.install(self.target, self.source)
        self.assertFalse(self.target.exists())
        weights.write_bytes(wanted)
        # Previously verified files in the private stage survive interruption.
        (self.source / "config.json").unlink()
        installer.install(self.target, self.source)
        installer.install(self.target)
        self.assertTrue(all(installer.valid(self.target / n, v) for n, v in installer.FILES.items()))

    def test_repair_one_damaged_file_offline_and_protect_unrelated_paths(self):
        installer.install(self.target, self.source)
        (self.target / "model.bin").write_bytes(b"damaged")
        (self.source / "config.json").unlink()
        own = self.target / "operator-note.txt"
        own.write_text("retain")
        with self.assertRaisesRegex(ValueError, "unrelated"):
            installer.install(self.target, self.source)
        self.assertEqual(own.read_text(), "retain")
        own.unlink()
        installer.install(self.target, self.source)
        self.assertTrue(installer.valid(self.target / "model.bin", installer.FILES["model.bin"]))


if __name__ == "__main__":
    unittest.main()
