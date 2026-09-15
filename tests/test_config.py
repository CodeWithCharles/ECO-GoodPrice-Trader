"""Priorite CLI > env > fichier, et separation des historiques."""

import os
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from ecotrade import config as cfg

TOML = """
[server]
url = "http://from-file:3001"
token = "file-token"

[trading]
currency = "Credits"
capital = 100.0
min_profit = 2.5

[activity]
absent_days = 3

[blacklist]
players = ["Spammer"]
items = ["Garbage"]
"""


def args(**kwargs):
    base = dict(
        url=None, token=None, offline=None, config=None, data_dir=None,
        currency=None, capital=None, min_profit=None, top=None,
        absent_days=None, stale_days=None, include_own=False,
        block_player=None, block_store=None, block_item=None,
    )
    base.update(kwargs)
    return Namespace(**base)


class TestChargement(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "config.toml"
        self.path.write_text(TOML, encoding="utf-8")
        self.env = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.env)
        self.tmp.cleanup()

    def test_lit_le_fichier(self):
        config = cfg.load(args(config=str(self.path)))
        self.assertEqual(config.url, "http://from-file:3001")
        self.assertEqual(config.currency, "Credits")
        self.assertEqual(config.capital, 100.0)
        self.assertEqual(config.absent_days, 3.0)
        self.assertEqual(config.players, ["Spammer"])

    def test_cli_prime_sur_le_fichier(self):
        config = cfg.load(args(config=str(self.path), currency="Calories"))
        self.assertEqual(config.currency, "Calories")

    def test_env_prime_sur_le_fichier(self):
        os.environ[cfg.ENV_TOKEN] = "env-token"
        config = cfg.load(args(config=str(self.path)))
        self.assertEqual(config.token, "env-token")

    def test_cli_prime_sur_env(self):
        os.environ[cfg.ENV_TOKEN] = "env-token"
        config = cfg.load(args(config=str(self.path), token="cli-token"))
        self.assertEqual(config.token, "cli-token")

    def test_les_exclusions_cli_s_ajoutent_au_fichier(self):
        config = cfg.load(
            args(config=str(self.path), block_player=["Other"])
        )
        self.assertEqual(config.players, ["Spammer", "Other"])

    def test_sans_source_erreur_explicite(self):
        with self.assertRaises(cfg.ConfigError):
            cfg.load(args(config="/inexistant.toml"))

    def test_offline_suffit_comme_source(self):
        config = cfg.load(args(config="/inexistant.toml", offline="snap"))
        self.assertEqual(config.offline, Path("snap"))

    def test_config_illisible_erreur_explicite(self):
        bad = Path(self.tmp.name) / "bad.toml"
        bad.write_text("pas = du = toml", encoding="utf-8")
        with self.assertRaises(cfg.ConfigError):
            cfg.load(args(config=str(bad)))


class TestCleDeServeur(unittest.TestCase):
    def test_deux_serveurs_ont_des_historiques_distincts(self):
        first = cfg.Config(url="http://a.com:3001")
        second = cfg.Config(url="http://b.com:3001")
        self.assertNotEqual(first.presence_path, second.presence_path)

    def test_la_cle_est_un_nom_de_fichier_valide(self):
        config = cfg.Config(url="http://eco.sg1-server.com:3001")
        name = config.presence_path.name
        self.assertTrue(name.startswith("presence_"))
        self.assertTrue(name.endswith(".json"))
        self.assertNotIn("/", name)
        self.assertNotIn(":", name)

    def test_token_absent_en_mode_non_interactif(self):
        config = cfg.Config(url="http://a.com")
        with self.assertRaises(cfg.ConfigError):
            cfg.resolve_token(config, interactive=False)


if __name__ == "__main__":
    unittest.main()
