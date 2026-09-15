"""Filtres joueurs / boutiques / items."""

import unittest

from ecotrade import market as mk
from ecotrade.blacklist import Blacklist

import fixtures


class TestBlacklist(unittest.TestCase):
    def setUp(self):
        self.stores = mk.parse_stores(fixtures.messy_payload())
        self.dirty = next(s for s in self.stores if s.owner == "Dave")

    def test_liste_vide_ne_filtre_rien(self):
        blacklist = Blacklist(exclude_own=False)
        self.assertIsNone(blacklist.blocks_store(self.dirty))
        self.assertIsNone(blacklist.blocks_item("Stone"))

    def test_correspondance_partielle_et_insensible_a_la_casse(self):
        blacklist = Blacklist(stores=["DIRTY"], exclude_own=False)
        self.assertIsNotNone(blacklist.blocks_store(self.dirty))

    def test_le_motif_est_compare_au_nom_nettoye(self):
        # Le nom brut contient "<color=orange>", pas le nom nettoye.
        blacklist = Blacklist(stores=["color=orange"], exclude_own=False)
        self.assertIsNone(blacklist.blocks_store(self.dirty))

    def test_motif_joueur(self):
        blacklist = Blacklist(players=["dav"], exclude_own=False)
        reason = blacklist.blocks_store(self.dirty)
        self.assertIn("joueur", reason)

    def test_le_motif_declencheur_est_nomme(self):
        blacklist = Blacklist(items=["ston"], exclude_own=False)
        self.assertEqual(blacklist.blocks_item("Stone"), "item 'ston'")

    def test_boutiques_propres_exclues_par_defaut(self):
        blacklist = Blacklist(own_names=["Dave"])
        self.assertEqual(
            blacklist.blocks_store(self.dirty), "boutique du joueur"
        )

    def test_include_own_reintegre_ses_boutiques(self):
        blacklist = Blacklist(own_names=["Dave"], exclude_own=False)
        self.assertIsNone(blacklist.blocks_store(self.dirty))

    def test_identite_comparee_exactement(self):
        # "Dav" ne doit pas capturer "Dave" : un pseudo est une
        # identite, pas un motif de recherche.
        blacklist = Blacklist(own_names=["Dav"])
        self.assertIsNone(blacklist.blocks_store(self.dirty))

    def test_full_access_compte_comme_sienne(self):
        stores = mk.parse_stores(fixtures.store_with_full_access())
        blacklist = Blacklist(own_names=["Helper"])
        self.assertEqual(
            blacklist.blocks_store(stores[0]), "boutique du joueur"
        )

    def test_rejections_est_lisible(self):
        blacklist = Blacklist(players=["Dave"], exclude_own=False)
        lines = blacklist.rejections(self.stores)
        self.assertEqual(len(lines), 1)
        self.assertIn("Dirty Shop", lines[0])


if __name__ == "__main__":
    unittest.main()
