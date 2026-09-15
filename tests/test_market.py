"""Nettoyage du JSON brut et construction du carnet d'ordres."""

import unittest

from ecotrade import market as mk
from ecotrade.models import SELL_PLACEHOLDER_PRICE

import fixtures


class TestParsing(unittest.TestCase):
    def test_retire_les_balises_de_couleur(self):
        self.assertEqual(
            mk.clean_name("<color=orange>Twitch's</color>"), "Twitch's"
        )
        self.assertEqual(
            mk.clean_name("<color=#3F4A56>A & B</color>"), "A & B"
        )
        self.assertEqual(mk.clean_name(None), "")

    def test_balance_infinity(self):
        stores = mk.parse_stores(fixtures.messy_payload())
        rich = next(s for s in stores if s.owner == "Eve")
        self.assertEqual(rich.balance, float("inf"))

    def test_ignore_les_emplacements_sans_item(self):
        stores = mk.parse_stores(fixtures.messy_payload())
        dirty = next(s for s in stores if s.owner == "Dave")
        self.assertTrue(all(o.item for o in dirty.offers))

    def test_offre_sentinelle_non_echangeable(self):
        stores = mk.parse_stores(fixtures.messy_payload())
        dirty = next(s for s in stores if s.owner == "Dave")
        sentinel = next(
            o for o in dirty.offers if o.price == SELL_PLACEHOLDER_PRICE
        )
        self.assertFalse(sentinel.is_tradable_ask)

    def test_offre_en_rupture_ou_desactivee_non_echangeable(self):
        stores = mk.parse_stores(fixtures.messy_payload())
        dirty = next(s for s in stores if s.owner == "Dave")
        tradable = [o for o in dirty.offers if o.is_tradable_ask]
        self.assertEqual(len(tradable), 1)
        self.assertEqual(tradable[0].price, 0.40)


class TestCarnet(unittest.TestCase):
    def setUp(self):
        self.stores = mk.parse_stores(fixtures.messy_payload())

    def test_filtre_la_devise_et_les_boutiques_fermees(self):
        market = mk.build_market(self.stores, currency="Calories")
        owners = {s.owner for s in market.stores}
        self.assertNotIn("Gina", owners)   # boutique fermee
        self.assertNotIn("Hugo", owners)   # autre devise

    def test_tri_des_cotations(self):
        payload = fixtures.simple_payload()
        market = mk.build_market(mk.parse_stores(payload), "Calories")
        bids = market.bids[("Calories", "Wood")]
        self.assertEqual([q.price for q in bids], [1.50, 1.20])

    def test_wallet_partage_entre_boutiques_du_meme_joueur(self):
        stores = mk.parse_stores(fixtures.shared_wallet_payload())
        market = mk.build_market(stores, "Calories")
        self.assertEqual(market.wallets[("Ivy", "Calories")], 10.0)

    def test_items_echangeables_dans_les_deux_sens(self):
        market = mk.build_market(self.stores, "Calories")
        self.assertEqual(market.items("Calories"), ["Stone"])


class TestPlayers(unittest.TestCase):
    def test_tolere_un_endpoint_absent(self):
        self.assertEqual(mk.parse_players(None), {})

    def test_normalise_les_entrees(self):
        players = mk.parse_players({"Players": [
            {"Name": "<color=red>Zoe</color>", "IsOnline": True,
             "City": "Rome"},
            {"Name": "", "IsOnline": False},
        ]})
        self.assertEqual(list(players), ["Zoe"])
        self.assertTrue(players["Zoe"]["online"])
        self.assertEqual(players["Zoe"]["city"], "Rome")


if __name__ == "__main__":
    unittest.main()
