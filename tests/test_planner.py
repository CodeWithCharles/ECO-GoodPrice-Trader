"""Chaine d'execution : recyclage du capital et bornes de solde."""

import unittest

from ecotrade import market as mk
from ecotrade import planner, routes

import fixtures

INF = float("inf")


def legs_from(payload, currency="Calories"):
    market = mk.build_market(mk.parse_stores(payload), currency)
    return routes.find_legs(market, currency), market


class TestSansContrainte(unittest.TestCase):
    def test_capital_infini_garde_tous_les_legs(self):
        legs, market = legs_from(fixtures.simple_payload())
        plan = planner.build_plan(legs, "Calories", INF, market.wallets)
        self.assertEqual(len(plan.steps), 2)
        self.assertAlmostEqual(plan.profit, 38.0, places=2)

    def test_ordre_profit_puis_roi(self):
        legs, market = legs_from(fixtures.simple_payload())
        plan = planner.build_plan(
            legs, "Calories", INF, market.wallets, order="profit"
        )
        self.assertEqual(plan.steps[0].leg.sell_to.owner, "Bob")

    def test_resume_coherent(self):
        legs, market = legs_from(fixtures.simple_payload())
        plan = planner.build_plan(legs, "Calories", INF, market.wallets)
        stats = planner.summarize(plan)
        self.assertEqual(stats["units"], 100)
        self.assertAlmostEqual(stats["invested"], 100.0, places=2)
        self.assertAlmostEqual(stats["profit"], 38.0, places=2)
        self.assertAlmostEqual(stats["roi"], 0.38, places=3)


class TestCapitalLimite(unittest.TestCase):
    def setUp(self):
        self.legs, self.market = legs_from(fixtures.simple_payload())

    def test_la_caisse_se_recycle(self):
        plan = planner.build_plan(
            self.legs, "Calories", 10.0, self.market.wallets
        )
        self.assertGreater(plan.end_cash, plan.start_cash)
        self.assertAlmostEqual(
            plan.end_cash, plan.start_cash + plan.profit, places=2
        )

    def test_un_gros_leg_se_termine_en_plusieurs_passages(self):
        # 10 calories ne permettent d'acheter que 10 bois a la fois ;
        # le reliquat doit rester candidat jusqu'a epuisement.
        plan = planner.build_plan(
            self.legs, "Calories", 10.0, self.market.wallets
        )
        self.assertGreater(len(plan.steps), 2)
        vendu = sum(s.leg.quantity for s in plan.steps)
        self.assertEqual(vendu, 100)
        self.assertAlmostEqual(plan.profit, 38.0, places=2)

    def test_chaque_etape_est_finançable(self):
        plan = planner.build_plan(
            self.legs, "Calories", 10.0, self.market.wallets
        )
        for step in plan.steps:
            self.assertLessEqual(step.leg.cost, step.cash_before + 1e-9)

    def test_max_steps_tronque(self):
        plan = planner.build_plan(
            self.legs, "Calories", 10.0, self.market.wallets, max_steps=2
        )
        self.assertEqual(len(plan.steps), 2)

    def test_caisse_nulle_ne_plante_pas(self):
        plan = planner.build_plan(
            self.legs, "Calories", 0.0, self.market.wallets
        )
        self.assertEqual(plan.steps, [])
        self.assertGreater(plan.skipped_for_cash, 0)


class TestSoldeAcheteur(unittest.TestCase):
    def test_le_wallet_partage_plafonne_les_ventes(self):
        legs, market = legs_from(fixtures.shared_wallet_payload())
        plan = planner.build_plan(legs, "Calories", INF, market.wallets)
        encaisse = sum(s.leg.revenue for s in plan.steps)
        self.assertLessEqual(encaisse, 10.0)

    def test_la_note_explique_la_limite(self):
        legs, market = legs_from(fixtures.shared_wallet_payload())
        plan = planner.build_plan(legs, "Calories", INF, market.wallets)
        notes = [n for s in plan.steps for n in s.notes]
        self.assertIn("limite par le solde de l'acheteur", notes)

    def test_meme_joueur_des_deux_cotes_est_signale(self):
        payload = fixtures.simple_payload()
        payload["Stores"][1]["Owner"] = "Alice"
        legs, market = legs_from(payload)
        plan = planner.build_plan(legs, "Calories", INF, market.wallets)
        notes = [n for s in plan.steps for n in s.notes]
        self.assertIn("meme joueur des deux cotes", notes)


class TestDeterminisme(unittest.TestCase):
    def test_deux_runs_donnent_le_meme_plan(self):
        legs, market = legs_from(fixtures.simple_payload())
        first = planner.build_plan(legs, "Calories", 7.0, market.wallets)
        second = planner.build_plan(legs, "Calories", 7.0, market.wallets)
        self.assertEqual(
            [(s.leg.item, s.leg.quantity) for s in first.steps],
            [(s.leg.item, s.leg.quantity) for s in second.steps],
        )

    def test_les_wallets_passes_ne_sont_pas_modifies(self):
        legs, market = legs_from(fixtures.shared_wallet_payload())
        before = dict(market.wallets)
        planner.build_plan(legs, "Calories", INF, market.wallets)
        self.assertEqual(market.wallets, before)


if __name__ == "__main__":
    unittest.main()
