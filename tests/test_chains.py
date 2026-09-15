"""Boucles de change entre devises."""

import unittest

from ecotrade import chains
from ecotrade import market as mk

import fixtures


def full_market(payload):
    return mk.build_market(mk.parse_stores(payload), currency=None)


class TestAretes(unittest.TestCase):
    def setUp(self):
        self.market = full_market(fixtures.cross_currency_payload())

    def test_deux_aretes_de_change(self):
        edges = chains.best_edges(self.market)
        self.assertIn(("Calories", "Credits"), edges)
        self.assertIn(("Credits", "Calories"), edges)

    def test_taux_calcule_sur_les_prix(self):
        edges = chains.best_edges(self.market)
        self.assertAlmostEqual(
            chains._rate(edges[("Calories", "Credits")]), 2.0, places=3
        )

    def test_pas_d_arete_intra_devise(self):
        # L'arbitrage a devise constante est le travail de routes.py.
        edges = chains.best_edges(full_market(fixtures.simple_payload()))
        self.assertEqual(edges, {})


class TestCycles(unittest.TestCase):
    def test_trouve_la_boucle_et_son_taux(self):
        cycles = chains.find_cycles(
            full_market(fixtures.cross_currency_payload())
        )
        self.assertEqual(len(cycles), 1)
        self.assertAlmostEqual(cycles[0].rate, 3.0, places=3)
        self.assertAlmostEqual(cycles[0].gain_pct, 200.0, places=1)

    def test_volume_engageable_borne_par_les_stocks(self):
        cycles = chains.find_cycles(
            full_market(fixtures.cross_currency_payload())
        )
        # 50 bois a 1.00 calorie = 50.00 engageables au premier leg.
        self.assertLessEqual(cycles[0].volume, 50.0)
        self.assertGreater(cycles[0].volume, 0.0)

    def test_min_gain_filtre(self):
        cycles = chains.find_cycles(
            full_market(fixtures.cross_currency_payload()),
            min_gain_pct=500.0,
        )
        self.assertEqual(cycles, [])

    def test_pas_de_boucle_en_mono_devise(self):
        cycles = chains.find_cycles(full_market(fixtures.simple_payload()))
        self.assertEqual(cycles, [])

    def test_boucle_non_rentable_ignoree(self):
        payload = fixtures.cross_currency_payload()
        # Le retour devient defavorable : 1 credit -> 0.20 calorie.
        payload["Stores"][3]["AllOffers"][0]["Price"] = 0.20
        cycles = chains.find_cycles(full_market(payload))
        self.assertEqual(cycles, [])


if __name__ == "__main__":
    unittest.main()
