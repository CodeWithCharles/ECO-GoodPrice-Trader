"""Plomberie partagee par les trois scripts de src/.

Regroupe ici pour que Routes.py, Chains.py et Presence.py restent des
fichiers courts et lisibles : chacun ne fait qu'assembler des briques
et choisir un affichage. Les options communes (serveur, token,
blacklists, seuils d'activite) sont definies une seule fois.
"""

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import client as api
from . import config as cfg
from . import market as mk
from .blacklist import Blacklist
from .models import Market, Store
from .presence import PresenceStore, snapshot_flags, warning_for


def base_parser(description: str) -> argparse.ArgumentParser:
    """Parser avec toutes les options communes deja branchees."""
    parser = argparse.ArgumentParser(
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    source = parser.add_argument_group("source des donnees")
    source.add_argument(
        "--url", metavar="URL",
        help="URL du serveur Eco, ex: http://mon-serveur.com:3001",
    )
    source.add_argument(
        "--token", metavar="JWT",
        help="X-Auth-Token (defaut: $ECO_AUTH_TOKEN, sinon saisie "
             "masquee)",
    )
    source.add_argument(
        "--offline", metavar="DOSSIER",
        help="rejoue des snapshots locaux au lieu d'appeler le serveur",
    )
    source.add_argument(
        "--config", metavar="FICHIER", default="config.toml",
        help="fichier de configuration (defaut: config.toml)",
    )
    source.add_argument(
        "--data-dir", metavar="DOSSIER", default="data",
        help="ou stocker l'historique de presence (defaut: data)",
    )

    filters = parser.add_argument_group("filtres")
    filters.add_argument(
        "--currency", metavar="NOM",
        help="devise a analyser (defaut: la plus repandue du serveur)",
    )
    filters.add_argument(
        "--block-player", metavar="NOM", action="append",
        help="exclut un joueur (repetable, correspondance partielle)",
    )
    filters.add_argument(
        "--block-store", metavar="NOM", action="append",
        help="exclut une boutique (repetable, correspondance partielle)",
    )
    filters.add_argument(
        "--block-item", metavar="NOM", action="append",
        help="exclut un item (repetable, correspondance partielle)",
    )
    filters.add_argument(
        "--include-own", action="store_true",
        help="inclut ses propres boutiques (exclues par defaut)",
    )

    activity = parser.add_argument_group("seuils d'activite")
    activity.add_argument(
        "--absent-days", metavar="N", type=float,
        help="jours sans connexion avant alerte (defaut: 7)",
    )
    activity.add_argument(
        "--stale-days", metavar="N", type=float,
        help="jours sans changement de boutique avant alerte (defaut: 14)",
    )
    activity.add_argument(
        "--no-record", action="store_true",
        help="n'enregistre pas d'instantane de presence pour ce run",
    )

    parser.add_argument(
        "--json", metavar="FICHIER", dest="json_out",
        help="ecrit le resultat brut en JSON",
    )
    parser.add_argument(
        "--no-color", action="store_true",
        help="desactive les couleurs ANSI",
    )
    return parser


@dataclass
class Context:
    """Tout ce dont un script a besoin apres le bootstrap."""

    config: cfg.Config
    market: Market
    stores: List[Store]
    blacklist: Blacklist
    presence: PresenceStore
    players: Dict[str, Any]
    user_name: Optional[str]
    currency: str
    source_label: str

    def stores_of(self, owner: str) -> List[Store]:
        return [s for s in self.stores if s.owner == owner]

    def activity_of(self, owner: str):
        return self.presence.activity(owner, self.players)

    def activity_label(self, owner: str) -> str:
        """Etiquette d'activite prete a afficher pour ce joueur.

        Centralise ici pour que les trois scripts affichent exactement
        la meme chose, seuils de config compris.
        """
        return warning_for(
            self.activity_of(owner),
            absent_days=self.config.absent_days,
            stale_days=self.config.stale_days,
            fallback=snapshot_flags(self.stores_of(owner)),
        )


def make_client(config: cfg.Config, interactive: bool = True):
    """Client offline ou HTTP selon la config."""
    if config.offline is not None:
        return api.OfflineClient(config.offline)
    token = cfg.resolve_token(config, interactive=interactive)
    return api.ApiClient(config.url, token)


def bootstrap(args: argparse.Namespace) -> Context:
    """Config -> donnees -> carnet d'ordres, en une fonction.

    L'instantane de presence est enregistre ici, donc a chaque appel de
    n'importe quel script : c'est ce qui fait que l'historique se
    remplit sans que l'utilisateur ait a y penser.
    """
    config = cfg.load(args)
    client = make_client(config)

    stores = mk.parse_stores(client.fetch("stores"))
    if not stores:
        raise api.ApiError("aucune boutique renvoyee par le serveur")

    players = mk.parse_players(api.fetch_optional(client, "players"))
    user = api.fetch_optional(client, "user") or {}
    user_name = mk.clean_name(user.get("UserName")) or None

    presence = PresenceStore(config.presence_path)
    if not getattr(args, "no_record", False):
        presence.record(stores, players)
        presence.save()

    currency = config.currency
    if not currency:
        counts: Dict[str, int] = {}
        for store in stores:
            if store.enabled:
                counts[store.currency] = counts.get(store.currency, 0) + 1
        currency = max(counts, key=lambda c: (counts[c], c)) if counts else ""

    blacklist = Blacklist(
        players=config.players,
        stores=config.stores,
        items=config.items,
        own_names=[user_name] if user_name else [],
        exclude_own=not config.include_own,
    )

    market = mk.build_market(stores, currency=currency)
    return Context(
        config=config,
        market=market,
        stores=stores,
        blacklist=blacklist,
        presence=presence,
        players=players,
        user_name=user_name,
        currency=currency,
        source_label=client.label,
    )


def write_json(path: str, payload: Any) -> None:
    import json
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
