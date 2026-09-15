"""Appariement du carnet d'ordres et bornes liees a l'argent."""

import unittest

from ecotrade import market as mk
from ecotrade import routes
from ecotrade.blacklist import Blacklist

import fixtures


def market_from(payload, currency="Calories"):
    return mk.build_market(mk.parse_stores(payload), currency)


class TestAppariement(unittest.TestCase):
    def setUp(self):
        self.market = market_from(fixtures.simple_payload())

    def test_deroule_le_carnet_au_lieu_de_s_arreter_au_meilleur(self):
        legs = routes.match_item(self.market, "Calories", "Wood")
        self.assertEqual(len(legs), 2)
        self.assertEqual((legs[0].sell_price, legs[0].quantity), (1.50, 60))
        self.assertEqual((legs[1].sell_price, legs[1].quantity), (1.20, 40))

    def test_profit_total_attendu(self):
        legs = routes.match_item(self.market, "Calories", "Wood")
        self.assertAlmostEqual(sum(lg.profit for lg in legs), 38.0, places=2)

    def test_s_arrete_quand_le_spread_se_ferme(self):
        payload = fixtures.simple_payload()
        # Personne ne paie plus que le prix de vente.
        payload["Stores"][1]["AllOffers"][0]["Price"] = 0.90
        payload["Stores"][2]["AllOffers"][0]["Price"] = 0.80
        market = market_from(payload)
        self.assertEqual(routes.match_item(market, "Calories", "Wood"), [])

    def test_min_profit_filtre(self):
        legs = routes.find_legs(self.market, "Calories", min_profit=20.0)
        self.assertEqual(len(legs), 1)
        self.assertEqual(legs[0].sell_to.owner, "Bob")

    def test_tri_par_profit_decroissant(self):
        legs = routes.find_legs(self.market, "Calories")
        profits = [lg.profit for lg in legs]
        self.assertEqual(profits, sorted(profits, reverse=True))


class TestMemeProprietaire(unittest.TestCase):
    def setUp(self):
        payload = fixtures.simple_payload()
        payload["Stores"][1]["Owner"] = "Alice"   # Bob devient Alice
        self.market = market_from(payload)

    def test_autorise_par_defaut(self):
        legs = routes.match_item(self.market, "Calories", "Wood")
        self.assertTrue(any(lg.same_owner for lg in legs))

    def test_peut_etre_ecarte(self):
        legs = routes.match_item(
            self.market, "Calories", "Wood", allow_same_owner=False
        )
        self.assertFalse(any(lg.same_owner for lg in legs))
        # Carol reste une contrepartie valable.
        self.assertEqual([lg.sell_to.owner for lg in legs], ["Carol"])


class TestBornesArgent(unittest.TestCase):
    def test_acheteur_sans_argent_ne_pollue_pas_le_carnet(self):
        # Frank paie 5.00 mais a 0 en banque : s'il restait dans le
        # carnet il raflerait le stock de Dave et masquerait Eve, qui
        # elle peut payer.
        market = market_from(fixtures.messy_payload())
        legs = routes.find_legs(market, "Calories")
        owners = {lg.sell_to.owner for lg in legs}
        self.assertNotIn("Frank", owners)
        self.assertIn("Eve", owners)

    def test_solde_infini_non_borne(self):
        market = market_from(fixtures.messy_payload())
        legs = routes.find_legs(market, "Calories")
        capped, _ = routes.cap_by_wallet(legs, market)
        eve = [lg for lg in capped if lg.sell_to.owner == "Eve"]
        self.assertEqual(eve[0].quantity, 20)

    def test_wallet_partage_borne_les_deux_boutiques(self):
        market = market_from(fixtures.shared_wallet_payload())
        legs = routes.find_legs(market, "Calories")
        capped, remaining = routes.cap_by_wallet(legs, market)
        vendu = sum(lg.revenue for lg in capped)
        self.assertLessEqual(vendu, 10.0)
        self.assertGreaterEqual(remaining[("Ivy", "Calories")], 0.0)


class TestBlacklistDansLeMoteur(unittest.TestCase):
    def test_exclut_un_acheteur(self):
        market = market_from(fixtures.simple_payload())
        blacklist = Blacklist(players=["bob"], exclude_own=False)
        legs = routes.find_legs(market, "Calories", blacklist=blacklist)
        self.assertEqual([lg.sell_to.owner for lg in legs], ["Carol"])

    def test_exclut_un_item(self):
        market = market_from(fixtures.simple_payload())
        blacklist = Blacklist(items=["wood"], exclude_own=False)
        self.assertEqual(
            routes.find_legs(market, "Calories", blacklist=blacklist), []
        )


if __name__ == "__main__":
    unittest.main()
