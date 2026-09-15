"""Chaines de change entre devises.

A l'interieur d'une devise, l'argent est fongible : enchainer deux legs
n'a pas d'autre effet que de recycler la tresorerie, ce dont s'occupe
deja planner.py. La seule vraie chaine *structurelle* dans Eco vient du
multi-devises : un item achete en calories peut se revendre a une
boutique qui paie en credits, ce qui donne un taux de change implicite
calories -> credits. Si le produit des taux le long d'une boucle
depasse 1, la boucle cree de la monnaie de depart a partir de rien.

Taux d'une arete A -> B, pour un item donne :

    taux = prix_de_vente_en_B / prix_d_achat_en_A

On garde, pour chaque couple (A, B), l'item qui offre le meilleur taux,
puis on cherche les boucles rentables. Avec une poignee de devises par
serveur, une recherche exhaustive des cycles courts (longueur 2 a 4)
est largement suffisante et bien plus lisible qu'un Bellman-Ford.
"""

from itertools import permutations
from typing import Dict, Iterable, List, Optional, Tuple

from .blacklist import Blacklist
from .models import Cycle, Leg, Market, Quote

MAX_CYCLE_LENGTH = 4


def _usable(
    quotes: Iterable[Quote],
    blacklist: Optional[Blacklist],
) -> List[Quote]:
    if blacklist is None:
        return list(quotes)
    return [q for q in quotes if blacklist.blocks_store(q.store) is None]


def best_edges(
    market: Market,
    blacklist: Optional[Blacklist] = None,
) -> Dict[Tuple[str, str], Leg]:
    """Meilleur leg de conversion pour chaque couple de devises.

    Le leg renvoye porte `currency` = devise de *depense*, et sa
    boutique de revente est dans une autre devise : c'est le seul
    endroit du code ou un Leg est volontairement bi-devise, d'ou la
    presence de cette fonction ici et pas dans routes.py.
    """
    edges: Dict[Tuple[str, str], Leg] = {}

    asks_by_item: Dict[str, List[Tuple[str, Quote]]] = {}
    bids_by_item: Dict[str, List[Tuple[str, Quote]]] = {}
    for (currency, item), quotes in market.asks.items():
        for quote in _usable(quotes, blacklist):
            asks_by_item.setdefault(item, []).append((currency, quote))
    for (currency, item), quotes in market.bids.items():
        for quote in _usable(quotes, blacklist):
            bids_by_item.setdefault(item, []).append((currency, quote))

    for item, asks in asks_by_item.items():
        if blacklist is not None and blacklist.blocks_item(item):
            continue
        for bid_currency, bid in bids_by_item.get(item, []):
            for ask_currency, ask in asks:
                if ask_currency == bid_currency:
                    continue  # arbitrage simple : voir routes.py
                if ask.price <= 0:
                    continue
                key = (ask_currency, bid_currency)
                leg = Leg(
                    item=item,
                    currency=ask_currency,
                    buy_from=ask.store,
                    buy_price=ask.price,
                    sell_to=bid.store,
                    sell_price=bid.price,
                    quantity=min(ask.available, bid.available),
                )
                if leg.quantity <= 0:
                    continue
                current = edges.get(key)
                if current is None or _rate(leg) > _rate(current):
                    edges[key] = leg

    return edges


def _rate(leg: Leg) -> float:
    return leg.sell_price / leg.buy_price if leg.buy_price else 0.0


def find_cycles(
    market: Market,
    blacklist: Optional[Blacklist] = None,
    min_gain_pct: float = 1.0,
    max_length: int = MAX_CYCLE_LENGTH,
) -> List[Cycle]:
    """Boucles de change rentables, du meilleur gain au moins bon.

    `min_gain_pct` a 1 % par defaut pour ne pas remonter le bruit
    d'arrondi sur des prix a deux decimales.
    """
    edges = best_edges(market, blacklist)
    if not edges:
        return []

    currencies = sorted({c for pair in edges for c in pair})
    cycles: List[Cycle] = []
    seen = set()

    for length in range(2, max(2, min(max_length, len(currencies))) + 1):
        for combo in permutations(currencies, length):
            legs = []
            rate = 1.0
            for index, currency in enumerate(combo):
                nxt = combo[(index + 1) % length]
                leg = edges.get((currency, nxt))
                if leg is None:
                    break
                legs.append(leg)
                rate *= _rate(leg)
            else:
                gain = (rate - 1.0) * 100.0
                if gain < min_gain_pct:
                    continue
                # Une meme boucle apparait une fois par point de
                # depart : on ne garde qu'une rotation canonique.
                canonical = min(
                    tuple(combo[i:] + combo[:i]) for i in range(length)
                )
                if canonical in seen:
                    continue
                seen.add(canonical)
                cycles.append(Cycle(
                    currencies=tuple(combo),
                    legs=tuple(legs),
                    rate=round(rate, 4),
                    volume=_volume(legs, market),
                ))

    cycles.sort(key=lambda c: -c.rate)
    return cycles


def _volume(legs: List[Leg], market: Market) -> float:
    """Montant de devise de depart reellement engageable sur la boucle.

    Chaque leg est borne par son stock, par la demande de l'acheteur et
    par le solde de cet acheteur. On convertit tout en devise de depart
    en remontant la chaine, et on garde le minimum.
    """
    capacity = float("inf")
    rate_so_far = 1.0
    for leg in legs:
        wallet_cap = market.wallets.get(leg.sell_to.wallet, float("inf"))
        leg_cap = min(leg.cost, wallet_cap / _rate(leg) if _rate(leg) else 0.0)
        capacity = min(capacity, leg_cap / rate_so_far)
        rate_so_far *= _rate(leg)
    return round(capacity, 2) if capacity != float("inf") else 0.0
