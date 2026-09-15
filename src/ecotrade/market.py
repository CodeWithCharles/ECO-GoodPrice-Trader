"""Construction du carnet d'ordres a partir de la reponse /stores.

C'est la seule couche qui connait la forme des dicts JSON d'Eco. Elle
fait trois choses que le reste du code n'a plus a refaire :

1. nettoyer (balises `<color=...>` dans les noms, `ItemName` a null,
   balance "Infinity", prix sentinelle 999999) ;
2. ne garder que les offres reellement echangeables ;
3. indexer par (devise, item) en triant deja dans le bon sens.
"""

import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .models import Market, Offer, Quote, Store

_COLOR_TAG = re.compile(r"</?color[^>]*>", re.IGNORECASE)


def clean_name(raw: Optional[str]) -> str:
    """Retire les balises de couleur Eco et les espaces superflus."""
    if not raw:
        return ""
    return _COLOR_TAG.sub("", raw).strip()


def _to_balance(raw: Any) -> float:
    """"Infinity" (boutiques admin) -> inf ; valeur absente -> 0."""
    if isinstance(raw, str):
        return float("inf") if raw.strip().lower().startswith("inf") else 0.0
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def _to_int(raw: Any) -> int:
    try:
        return int(raw or 0)
    except (TypeError, ValueError):
        return 0


def _to_float(raw: Any) -> float:
    try:
        return float(raw or 0.0)
    except (TypeError, ValueError):
        return 0.0


def parse_offer(raw: Dict[str, Any]) -> Optional[Offer]:
    """Convertit une offre brute, ou None si elle est inexploitable.

    Les emplacements vides d'une boutique arrivent avec `ItemName` a
    null (73 cas sur le snapshot de reference) : on les jette ici.
    """
    item = clean_name(raw.get("ItemName"))
    if not item:
        return None
    return Offer(
        item=item,
        buying=bool(raw.get("Buying")),
        price=_to_float(raw.get("Price")),
        quantity=_to_int(raw.get("Quantity")),
        limit=_to_int(raw.get("Limit")),
        max_num_wanted=_to_int(raw.get("MaxNumWanted")),
        min_durability=_to_float(raw.get("MinDurability", -1.0)),
        enabled=raw.get("Enabled", True) is not False,
    )


def parse_store(raw: Dict[str, Any]) -> Optional[Store]:
    """Convertit une boutique brute, ou None si elle est inutilisable."""
    name = clean_name(raw.get("Name"))
    owner = clean_name(raw.get("Owner"))
    currency = clean_name(raw.get("CurrencyName"))
    if not name or not currency:
        return None
    offers = tuple(
        offer
        for offer in (parse_offer(o) for o in raw.get("AllOffers") or ())
        if offer is not None
    )
    return Store(
        name=name,
        owner=owner or "?",
        balance=_to_balance(raw.get("Balance")),
        currency=currency,
        enabled=raw.get("Enabled", True) is not False,
        full_access_users=tuple(
            clean_name(u) for u in raw.get("FullAccessUsers") or ()
        ),
        offers=offers,
    )


def parse_stores(payload: Dict[str, Any]) -> List[Store]:
    """Extrait la liste des boutiques de la reponse /stores."""
    raw_stores = (payload or {}).get("Stores") or []
    stores = [parse_store(raw) for raw in raw_stores]
    return [s for s in stores if s is not None]


def build_market(
    stores: Iterable[Store],
    currency: Optional[str] = None,
    skip_broke_bids: bool = True,
) -> Market:
    """Assemble le carnet d'ordres.

    Les soldes sont agreges par `wallet` = (proprietaire, devise) et non
    par boutique : l'API renvoie la balance du compte du proprietaire,
    donc deux boutiques du meme joueur ne disposent pas de deux budgets.
    On prend le max plutot que la somme, pour ne jamais surestimer.

    `skip_broke_bids` ecarte les demandes d'achat des comptes a zero.
    Ce n'est pas cosmetique : une boutique sans un sou qui affiche un
    prix d'achat genereux se retrouverait en tete du carnet et
    masquerait le vrai meilleur acheteur, puisque l'appariement
    consomme le stock du vendeur au premier venu.
    """
    kept = [
        s for s in stores
        if s.enabled and (currency is None or s.currency == currency)
    ]

    # Premiere passe : les soldes, dont on a besoin pour trier le bon
    # grain de l'ivraie a la seconde.
    wallets: Dict[Tuple[str, str], float] = {}
    for store in kept:
        wallets[store.wallet] = max(
            wallets.get(store.wallet, 0.0), store.balance
        )

    asks: Dict[Tuple[str, str], List[Quote]] = {}
    bids: Dict[Tuple[str, str], List[Quote]] = {}

    for store in kept:
        solvent = wallets.get(store.wallet, 0.0) > 0
        for offer in store.offers:
            key = (store.currency, offer.item)
            if offer.is_tradable_ask:
                asks.setdefault(key, []).append(Quote(store, offer))
            elif offer.is_tradable_bid:
                if skip_broke_bids and not solvent:
                    continue
                bids.setdefault(key, []).append(Quote(store, offer))

    for quotes in asks.values():
        quotes.sort(key=lambda q: (q.price, -q.available, q.store.name))
    for quotes in bids.values():
        quotes.sort(key=lambda q: (-q.price, -q.available, q.store.name))

    return Market(stores=kept, asks=asks, bids=bids, wallets=wallets)


def parse_players(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Normalise /players -> {nom: {online, city}}.

    L'endpoint est facultatif et sa forme peut varier selon la version
    du plugin : on ne se fie qu'a `Name`, et on tolere l'absence du
    reste.
    """
    players: Dict[str, Any] = {}
    for raw in (payload or {}).get("Players") or []:
        name = clean_name(raw.get("Name"))
        if not name:
            continue
        players[name] = {
            "online": raw.get("IsOnline"),
            "city": clean_name(raw.get("City")) or None,
        }
    return players
