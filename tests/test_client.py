"""Client offline : c'est lui qui rend les tests possibles sans token."""

import json
import tempfile
import unittest
from pathlib import Path

from ecotrade import client as api

import fixtures

HTTP_DUMP = """GET /api/v1/plugins/GoodPrice/stores HTTP/1.1
Host: example.com:3001
X-Auth-Token: fake

{payload}
"""


class TestOfflineClient(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_lit_du_json_pur(self):
        payload = json.dumps(fixtures.simple_payload())
        (self.dir / "stores.json").write_text(payload, encoding="utf-8")
        client = api.OfflineClient(self.dir)
        self.assertEqual(len(client.fetch("stores")["Stores"]), 3)

    def test_lit_un_dump_http_avec_entetes(self):
        payload = json.dumps(fixtures.simple_payload())
        (self.dir / "stores").write_text(
            HTTP_DUMP.format(payload=payload), encoding="utf-8"
        )
        client = api.OfflineClient(self.dir)
        self.assertEqual(len(client.fetch("stores")["Stores"]), 3)

    def test_alias_de_casse_sur_allitems(self):
        (self.dir / "allitems").write_text(
            '{"AllItems": {}}', encoding="utf-8"
        )
        client = api.OfflineClient(self.dir)
        self.assertEqual(client.fetch("allItems"), {"AllItems": {}})

    def test_endpoint_absent_leve_une_erreur_claire(self):
        client = api.OfflineClient(self.dir)
        with self.assertRaises(api.ApiError):
            client.fetch("stores")

    def test_fetch_optional_avale_l_erreur(self):
        client = api.OfflineClient(self.dir)
        self.assertIsNone(api.fetch_optional(client, "players"))

    def test_dossier_inexistant(self):
        with self.assertRaises(api.ApiError):
            api.OfflineClient(self.dir / "nope")

    def test_json_invalide_leve_une_erreur_claire(self):
        (self.dir / "stores").write_text("{ nope", encoding="utf-8")
        client = api.OfflineClient(self.dir)
        with self.assertRaises(api.ApiError):
            client.fetch("stores")


if __name__ == "__main__":
    unittest.main()
