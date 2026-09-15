"""Bout en bout : les trois scripts, lances comme l'utilisateur le fait.

Ces tests ne verifient pas des chiffres (les autres fichiers s'en
chargent) mais le cablage : argparse, imports, bootstrap, ecriture de
l'historique, exports. C'est ce qui casse quand on refactore, et c'est
invisible depuis les tests unitaires.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import fixtures

SRC = Path(__file__).resolve().parent.parent / "src"


class TestScripts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.snapshots = root / "snap"
        self.snapshots.mkdir()
        self.data = root / "data"
        (self.snapshots / "stores.json").write_text(
            json.dumps(fixtures.integration_payload()), encoding="utf-8"
        )
        # Le joueur ne possede aucune boutique du jeu de test : sinon
        # l'exclusion automatique de ses propres boutiques fausserait
        # ce qu'on mesure ici.
        (self.snapshots / "user.json").write_text(
            json.dumps({"UserName": "Kiwi"}), encoding="utf-8"
        )
        (self.snapshots / "players.json").write_text(
            json.dumps({"Players": [
                {"Name": "Bob", "IsOnline": True, "City": "Rome"},
                {"Name": "Carol", "IsOnline": False},
            ]}), encoding="utf-8"
        )

    def tearDown(self):
        self.tmp.cleanup()

    def script(self, name, *extra):
        command = [
            sys.executable, str(SRC / name),
            "--offline", str(self.snapshots),
            "--data-dir", str(self.data),
            "--config", str(self.snapshots / "absent.toml"),
            "--no-color",
            *extra,
        ]
        return subprocess.run(
            command, capture_output=True, text=True, cwd=str(SRC),
        )

    def test_routes_sort_en_zero(self):
        result = self.script("Routes.py")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Routes rentables", result.stdout)

    def test_chains_trouve_la_boucle_de_change(self):
        result = self.script(
            "Chains.py", "--capital", "10", "--currency", "Calories"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Boucles de change", result.stdout)
        self.assertIn("Calories -> Credits", result.stdout)

    def test_presence_affiche_le_statut_en_ligne(self):
        result = self.script("Presence.py")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("en ligne", result.stdout)
        self.assertIn("Rome", result.stdout)

    def test_l_historique_est_ecrit_tout_seul(self):
        self.script("Routes.py")
        files = list(self.data.glob("presence_*.json"))
        self.assertEqual(len(files), 1)
        data = json.loads(files[0].read_text(encoding="utf-8"))
        self.assertIn("Bob", data["players"])

    def test_no_record_n_ecrit_rien(self):
        self.script("Routes.py", "--no-record")
        self.assertFalse(self.data.exists() and list(self.data.iterdir()))

    def test_export_json_et_html(self):
        out = Path(self.tmp.name)
        result = self.script(
            "Routes.py",
            "--json", str(out / "r.json"),
            "--html", str(out / "r.html"),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads((out / "r.json").read_text(encoding="utf-8"))
        self.assertIn("routes", payload)
        page = (out / "r.html").read_text(encoding="utf-8")
        self.assertTrue(page.startswith("<!doctype html>"))
        self.assertIn("</html>", page)

    def test_blacklist_en_ligne_de_commande(self):
        clean = self.script("Routes.py", "--currency", "Calories")
        blocked = self.script(
            "Routes.py", "--currency", "Calories", "--block-player", "Bob"
        )
        self.assertIn("Bob Shop", clean.stdout)
        self.assertNotIn("Bob Shop", blocked.stdout)

    def test_blacklist_item(self):
        blocked = self.script(
            "Routes.py", "--currency", "Calories", "--block-item", "Wood"
        )
        self.assertEqual(blocked.returncode, 0, blocked.stderr)
        self.assertNotIn("Bob Shop", blocked.stdout)

    def test_source_absente_echoue_proprement(self):
        result = subprocess.run(
            [sys.executable, str(SRC / "Routes.py"),
             "--config", "/inexistant.toml"],
            capture_output=True, text=True, cwd=str(SRC),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("Erreur", result.stderr)

    def test_aide_disponible(self):
        for name in ("Routes.py", "Chains.py", "Presence.py"):
            result = subprocess.run(
                [sys.executable, str(SRC / name), "-h"],
                capture_output=True, text=True, cwd=str(SRC),
            )
            self.assertEqual(result.returncode, 0, name)
            self.assertIn("--offline", result.stdout, name)


if __name__ == "__main__":
    unittest.main()
