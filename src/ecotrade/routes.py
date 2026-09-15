"""Moteur d'arbitrage direct : acheter chez A, revendre chez B.

Difference avec l'approche naive (ne comparer que la meilleure offre de
vente a la meilleure offre d'achat) : on deroule le carnet d'ordres.
Tant que la prochaine offre la moins chere reste en dessous de la
prochaine demande la mieux payee, on continue a matcher. Sur un item
demande par plusieurs boutiques, cela trouve plusieurs legs la ou la
version naive s'arrete au premier.

Ce module ne connait ni le capital du joueur ni le solde des acheteurs
en tant que budget global : il produit des `Leg` bornes par le stock et
la demande. Les contraintes d'argent dependent de l'ordre d'execution,
c'est le travail du planner.
"""

from typing import Dict, Iterable, List, Optional, Tuple

from .blacklist import Blacklist
from .models import Leg, Market, Quote


def _usable(
    quotes: Iterable[Quote],
    blacklist: Optional[Blacklist],
) -> List[Quote]:
    if blacklist is None:
        return list(quotes)
    return [q for q in quotes if blacklist.blocks_store(q.store) is None]


def match_item(
    market: Market,
    currency: str,
    item: str,
    blacklist: Optional[Blacklist] = None,
    allow_same_owner: bool = True,
) -> List[Leg]:
    """Tous les legs rentables sur un item, du plus marge au moins.

    On travaille sur des copies des quantites disponibles : une meme
    offre peut alimenter plusieurs acheteurs, et une meme demande peut
    etre servie par plusieurs vendeurs.
    """
    asks = _usable(market.asks.get((currency, item), []), blacklist)
    bids = _usable(market.bids.get((currency, item), []), blacklist)
    if not asks or not bids:
        return []

    ask_left = [q.available for q in asks]
    bid_left = [q.available for q in bids]

    legs: List[Leg] = []
    i = j = 0
    while i < len(asks) and j < len(bids):
        if ask_left[i] <= 0:
            i += 1
            continue
        if bid_left[j] <= 0:
            j += 1
            continue
        ask, bid = asks[i], bids[j]
        if bid.price <= ask.price:
            # Le carnet est trie : plus rien ne sera rentable au-dela.
            break
        if not allow_same_owner and ask.store.owner == bid.store.owner:
            # On ne peut pas juste avancer d'un cran : cette offre peut
            # servir un autre acheteur, et cet acheteur un autre
            # vendeur. On tente la paire suivante du cote le plus
            # profond, quitte a rater un appariement exotique.
            if len(asks) - i >= len(bids) - j:
                i += 1
            else:
                j += 1
            continue

        quantity = min(ask_left[i], bid_left[j])
        legs.append(Leg(
            item=item,
            currency=currency,
            buy_from=ask.store,
            buy_price=ask.price,
            sell_to=bid.store,
            sell_price=bid.price,
            quantity=quantity,
        ))
        ask_left[i] -= quantity
        bid_left[j] -= quantity

    return legs


def find_legs(
    market: Market,
    currency: str,
    blacklist: Optional[Blacklist] = None,
    min_profit: float = 0.0,
    items: Optional[Iterable[str]] = None,
    allow_same_owner: bool = True,
) -> List[Leg]:
    """Tous les legs rentables d'une devise, tries par profit decroissant."""
    wanted = list(items) if items is not None else market.items(currency)
    legs: List[Leg] = []
    for item in wanted:
        if blacklist is not None and blacklist.blocks_item(item):
            continue
        for leg in match_item(
            market, currency, item, blacklist, allow_same_owner
        ):
            if leg.profit >= min_profit:
                legs.append(leg)
    legs.sort(key=lambda lg: (-lg.profit, -lg.roi, lg.item))
    return legs


def cap_by_wallet(
    legs: Iterable[Leg],
    market: Market,
) -> Tuple[List[Leg], Dict[Tuple[str, str], float]]:
    """Reduit les legs pour respecter le solde des acheteurs.

    Un joueur avec trois boutiques n'a qu'un compte en banque : si ses
    boutiques veulent nous acheter pour 300 alors qu'il a 50, on ne
    touchera que 50. On sert les legs dans l'ordre recu (donc les plus
    rentables d'abord) et on decremente le porte-monnaie commun.

    Renvoie les legs ajustes et le solde restant par porte-monnaie.
    """
    remaining = dict(market.wallets)
    adjusted: List[Leg] = []
    for leg in legs:
        wallet = leg.sell_to.wallet
        budget = remaining.get(wallet, 0.0)
        if budget == float("inf"):
            adjusted.append(leg)
            continue
        if budget <= 0 or leg.sell_price <= 0:
            continue
        affordable = int(budget // leg.sell_price)
        quantity = min(leg.quantity, affordable)
        if quantity <= 0:
            continue
        capped = leg.with_quantity(quantity)
        remaining[wallet] = round(budget - capped.revenue, 2)
        adjusted.append(capped)
    return adjusted, remaining
