"""Types du domaine.

Aucune de ces classes ne connait ni HTTP ni l'affichage : elles ne
transportent que ce que l'API renvoie, deja nettoye et type. Tout le
reste du package raisonne sur ces objets, jamais sur les dicts JSON
bruts -- c'est ce qui permet de tester les moteurs sans serveur.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# Eco n'a pas de champ "offre desactivee" : le plugin ecrit un prix
# sentinelle quand l'offre est un simple emplacement vide (store.js:645).
SELL_PLACEHOLDER_PRICE = 999999.0


@dataclass(frozen=True)
class Offer:
    """Une ligne d'offre dans une boutique.

    `quantity` et `max_num_wanted` ne veulent pas dire la meme chose
    selon le sens de l'offre, d'ou les deux proprietes plus bas :
    - vente (buying=False) : `quantity` = stock reellement disponible ;
    - achat (buying=True)  : `max_num_wanted` = ce qu'il manque encore
      pour atteindre `limit`, donc ce qu'on peut lui vendre.
    """

    item: str
    buying: bool
    price: float
    quantity: int
    limit: int = 0
    max_num_wanted: int = 0
    min_durability: float = -1.0
    enabled: bool = True

    @property
    def is_tradable_ask(self) -> bool:
        """Vrai si on peut acheter cette offre (elle vend du stock)."""
        return (
            not self.buying
            and self.enabled
            and self.quantity > 0
            and 0 < self.price < SELL_PLACEHOLDER_PRICE
        )

    @property
    def is_tradable_bid(self) -> bool:
        """Vrai si on peut vendre a cette offre (elle achete)."""
        return (
            self.buying
            and self.enabled
            and self.max_num_wanted > 0
            and self.price > 0
        )


@dataclass(frozen=True)
class Store:
    """Une boutique. `balance` peut valoir l'infini ("Infinity" cote API).

    Attention : la balance est celle du *compte du proprietaire*, pas de
    la boutique. Plusieurs boutiques d'un meme joueur renvoient la meme
    valeur (verifie sur les snapshots : Tec a 3 boutiques a 550.20).
    C'est pourquoi le budget acheteur se suit par `wallet`, pas par
    boutique -- voir planner.py.
    """

    name: str
    owner: str
    balance: float
    currency: str
    enabled: bool = True
    full_access_users: Tuple[str, ...] = ()
    offers: Tuple[Offer, ...] = ()

    @property
    def wallet(self) -> Tuple[str, str]:
        """Cle du porte-monnaie partage : (proprietaire, devise)."""
        return (self.owner, self.currency)

    @property
    def looks_abandoned(self) -> bool:
        """Boutique sans aucun stock ni aucune demande active.

        Signal disponible des le premier run, sans historique.
        """
        return not any(
            o.is_tradable_ask or o.is_tradable_bid for o in self.offers
        )


@dataclass(frozen=True)
class Quote:
    """Une offre rattachee a sa boutique, prete a etre matchee."""

    store: Store
    offer: Offer

    @property
    def available(self) -> int:
        """Quantite echangeable sur cette cotation."""
        if self.offer.buying:
            return self.offer.max_num_wanted
        return self.offer.quantity

    @property
    def price(self) -> float:
        return self.offer.price


@dataclass
class Market:
    """Carnet d'ordres consolide du serveur, par devise et par item.

    `asks[(devise, item)]` = la ou on achete (trie du moins cher au plus
    cher), `bids[(devise, item)]` = la ou on revend (trie du mieux paye
    au moins bien paye).
    """

    stores: List[Store] = field(default_factory=list)
    asks: Dict[Tuple[str, str], List[Quote]] = field(default_factory=dict)
    bids: Dict[Tuple[str, str], List[Quote]] = field(default_factory=dict)
    wallets: Dict[Tuple[str, str], float] = field(default_factory=dict)

    def currencies(self) -> List[str]:
        """Devises presentes, la plus utilisee d'abord."""
        counts: Dict[str, int] = {}
        for store in self.stores:
            counts[store.currency] = counts.get(store.currency, 0) + 1
        return sorted(counts, key=lambda c: (-counts[c], c))

    def items(self, currency: str) -> List[str]:
        """Items ayant a la fois une offre d'achat et de vente."""
        sellable = {i for (c, i) in self.bids if c == currency}
        buyable = {i for (c, i) in self.asks if c == currency}
        return sorted(sellable & buyable)


@dataclass(frozen=True)
class Leg:
    """Un aller-retour sur un seul item : acheter ici, revendre la.

    C'est l'unite atomique de tout le reste. `quantity` est deja borne
    par le stock du vendeur et par la demande de l'acheteur, mais *pas*
    par le solde de l'acheteur ni par notre capital : ces deux bornes
    dependent de l'ordre d'execution, donc c'est le planner qui les
    applique.
    """

    item: str
    currency: str
    buy_from: Store
    buy_price: float
    sell_to: Store
    sell_price: float
    quantity: int

    @property
    def cost(self) -> float:
        return round(self.buy_price * self.quantity, 2)

    @property
    def revenue(self) -> float:
        return round(self.sell_price * self.quantity, 2)

    @property
    def profit(self) -> float:
        return round(self.revenue - self.cost, 2)

    @property
    def unit_profit(self) -> float:
        return round(self.sell_price - self.buy_price, 2)

    @property
    def roi(self) -> float:
        """Profit par unite de capital immobilise (0.5 = +50%)."""
        return (self.revenue / self.cost - 1.0) if self.cost > 0 else 0.0

    @property
    def same_owner(self) -> bool:
        """Achat et revente chez le meme joueur : legal mais a signaler."""
        return self.buy_from.owner == self.sell_to.owner

    def with_quantity(self, quantity: int) -> "Leg":
        """Copie du leg avec une quantite reduite (execution partielle)."""
        return Leg(
            item=self.item,
            currency=self.currency,
            buy_from=self.buy_from,
            buy_price=self.buy_price,
            sell_to=self.sell_to,
            sell_price=self.sell_price,
            quantity=quantity,
        )


@dataclass
class PlanStep:
    """Un leg retenu dans un plan, avec l'etat de la tresorerie apres."""

    leg: Leg
    cash_before: float
    cash_after: float
    notes: List[str] = field(default_factory=list)


@dataclass
class Plan:
    """Chaine d'execution ordonnee sous contrainte de capital."""

    currency: str
    start_cash: float
    steps: List[PlanStep] = field(default_factory=list)
    skipped_for_cash: int = 0

    @property
    def end_cash(self) -> float:
        return self.steps[-1].cash_after if self.steps else self.start_cash

    @property
    def profit(self) -> float:
        return round(sum(s.leg.profit for s in self.steps), 2)

    @property
    def peak_outlay(self) -> float:
        """Plus grosse somme a avancer d'un coup sur la chaine."""
        return max((s.leg.cost for s in self.steps), default=0.0)


@dataclass(frozen=True)
class Cycle:
    """Boucle de change entre devises : A -> B -> ... -> A.

    Un cycle dont `rate` depasse 1 rend plus de devise de depart qu'il
    n'en consomme. A une seule devise ce serait de l'arbitrage simple,
    donc on n'en garde que les cycles de longueur >= 2.
    """

    currencies: Tuple[str, ...]
    legs: Tuple[Leg, ...]
    rate: float
    volume: float

    @property
    def gain_pct(self) -> float:
        return round((self.rate - 1.0) * 100.0, 2)


@dataclass
class Activity:
    """Ce qu'on sait de l'activite d'un joueur, historique compris."""

    player: str
    online: Optional[bool] = None
    city: Optional[str] = None
    last_online_days: Optional[float] = None
    last_change_days: Optional[float] = None
    history_days: float = 0.0
    snapshots: int = 0
