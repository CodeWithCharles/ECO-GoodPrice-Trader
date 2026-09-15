"""Historique de presence et warnings d'absence.

Tous les tests injectent `now` explicitement : le module doit etre
testable sans attendre des jours reels.
"""

import json
import tempfile
import unittest
from pathlib import Path

from ecotrade import market as mk
from ecotrade import presence
from ecotrade.models import Activity

import fixtures

DAY = 86400.0
T0 = 1_700_000_000.0


class TestEmpreinte(unittest.TestCase):
    def setUp(self):
        self.stores = mk.parse_stores(fixtures.simple_payload())

    def test_stable_a_donnees_identiques(self):
        again = mk.parse_stores(fixtures.simple_payload())
        self.assertEqual(
            presence.store_fingerprint(self.stores[0]),
            presence.store_fingerprint(again[0]),
        )

    def test_change_si_un_prix_change(self):
        payload = fixtures.simple_payload()
        payload["Stores"][0]["AllOffers"][0]["Price"] = 1.01
        modified = mk.parse_stores(payload)
        self.assertNotEqual(
            presence.store_fingerprint(self.stores[0]),
            presence.store_fingerprint(modified[0]),
        )

    def test_change_si_le_solde_change(self):
        payload = fixtures.simple_payload()
        payload["Stores"][0]["Balance"] = 11.0
        modified = mk.parse_stores(payload)
        self.assertNotEqual(
            presence.store_fingerprint(self.stores[0]),
            presence.store_fingerprint(modified[0]),
        )


class TestHistorique(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "presence.json"
        self.stores = mk.parse_stores(fixtures.simple_payload())

    def tearDown(self):
        self.tmp.cleanup()

    def store(self):
        return presence.PresenceStore(self.path)

    def test_premier_run_sans_historique(self):
        history = self.store()
        history.record(self.stores, {}, now=T0)
        activity = history.activity("Alice", {}, now=T0)
        self.assertEqual(activity.snapshots, 1)
        self.assertEqual(activity.history_days, 0.0)
        self.assertIsNone(activity.last_online_days)

    def test_persiste_entre_deux_instances(self):
        history = self.store()
        history.record(self.stores, {}, now=T0)
        history.save()
        reloaded = self.store()
        self.assertEqual(
            reloaded.activity("Alice", {}, now=T0).snapshots, 1
        )

    def test_compte_les_jours_depuis_la_derniere_connexion(self):
        history = self.store()
        history.record(self.stores, {"Alice": {"online": True}}, now=T0)
        history.record(
            self.stores, {"Alice": {"online": False}}, now=T0 + 9 * DAY
        )
        activity = history.activity(
            "Alice", {"Alice": {"online": False}}, now=T0 + 9 * DAY
        )
        self.assertAlmostEqual(activity.last_online_days, 9.0, places=1)

    def test_boutique_figee_detectee(self):
        history = self.store()
        history.record(self.stores, {}, now=T0)
        history.record(self.stores, {}, now=T0 + 20 * DAY)
        activity = history.activity("Alice", {}, now=T0 + 20 * DAY)
        self.assertAlmostEqual(activity.last_change_days, 20.0, places=1)

    def test_changement_de_boutique_remet_le_compteur_a_zero(self):
        history = self.store()
        history.record(self.stores, {}, now=T0)
        payload = fixtures.simple_payload()
        payload["Stores"][0]["AllOffers"][0]["Price"] = 2.0
        history.record(
            mk.parse_stores(payload), {}, now=T0 + 20 * DAY
        )
        activity = history.activity("Alice", {}, now=T0 + 20 * DAY)
        self.assertAlmostEqual(activity.last_change_days, 0.0, places=1)

    def test_historique_corrompu_ne_bloque_pas(self):
        self.path.write_text("{ pas du json", encoding="utf-8")
        history = self.store()
        history.record(self.stores, {}, now=T0)
        self.assertEqual(
            history.activity("Alice", {}, now=T0).snapshots, 1
        )

    def test_fichier_ecrit_est_du_json_lisible(self):
        history = self.store()
        history.record(self.stores, {}, now=T0)
        history.save()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertIn("Alice", data["players"])


class TestSignauxInstantanes(unittest.TestCase):
    def test_compte_a_zero(self):
        stores = mk.parse_stores(fixtures.messy_payload())
        frank = [s for s in stores if s.owner == "Frank"]
        self.assertIn("solde 0", presence.snapshot_flags(frank))

    def test_boutique_vide(self):
        payload = {"Stores": [fixtures.store("Ghost", "Zed", 5.0, [
            fixtures.offer("Wood", False, 1.0, 0),
        ])]}
        stores = mk.parse_stores(payload)
        self.assertIn("boutique vide", presence.snapshot_flags(stores))

    def test_une_boutique_vide_sur_plusieurs_ne_declenche_rien(self):
        payload = {"Stores": [
            fixtures.store("A", "Zed", 5.0, [
                fixtures.offer("Wood", False, 1.0, 0),
            ]),
            fixtures.store("B", "Zed", 5.0, [
                fixtures.offer("Wood", False, 1.0, 10),
            ]),
        ]}
        stores = mk.parse_stores(payload)
        self.assertNotIn("boutique vide", presence.snapshot_flags(stores))

    def test_sans_boutique_aucun_signal(self):
        self.assertEqual(presence.snapshot_flags([]), [])


class TestEtiquettes(unittest.TestCase):
    def test_en_ligne_prime_sur_tout(self):
        activity = Activity(player="A", online=True, history_days=30.0,
                            last_online_days=0.0, last_change_days=99.0)
        self.assertEqual(presence.warning_for(activity), "en ligne")

    def test_historique_trop_court_sans_signal(self):
        activity = Activity(player="A", online=False, history_days=0.2)
        self.assertEqual(presence.warning_for(activity), "? inconnu")

    def test_historique_trop_court_avec_signal_instantane(self):
        activity = Activity(player="A", online=False, history_days=0.2)
        label = presence.warning_for(activity, fallback=["solde 0"])
        self.assertEqual(label, "! solde 0")
        self.assertTrue(presence.is_alert(label))

    def test_absence_au_dela_du_seuil(self):
        activity = Activity(player="A", online=False, history_days=30.0,
                            last_online_days=12.0)
        label = presence.warning_for(activity, absent_days=7.0)
        self.assertEqual(label, "! absent 12j")
        self.assertTrue(presence.is_alert(label))

    def test_absence_en_dessous_du_seuil_pas_d_alerte(self):
        activity = Activity(player="A", online=False, history_days=30.0,
                            last_online_days=2.0)
        label = presence.warning_for(activity, absent_days=7.0)
        self.assertEqual(label, "vu il y a 2j")
        self.assertFalse(presence.is_alert(label))

    def test_boutique_figee_au_dela_du_seuil(self):
        activity = Activity(player="A", online=False, history_days=30.0,
                            last_online_days=1.0, last_change_days=20.0)
        label = presence.warning_for(
            activity, absent_days=7.0, stale_days=14.0
        )
        self.assertEqual(label, "! figee 20j")

    def test_jamais_vu_en_ligne(self):
        activity = Activity(player="A", online=False, history_days=10.0,
                            last_change_days=1.0)
        label = presence.warning_for(activity)
        self.assertTrue(label.startswith("? jamais vu"))
        self.assertTrue(presence.is_alert(label))

    def test_seuils_personnalises(self):
        activity = Activity(player="A", online=False, history_days=30.0,
                            last_online_days=4.0)
        self.assertTrue(presence.is_alert(
            presence.warning_for(activity, absent_days=3.0)
        ))
        self.assertFalse(presence.is_alert(
            presence.warning_for(activity, absent_days=10.0)
        ))


if __name__ == "__main__":
    unittest.main()
