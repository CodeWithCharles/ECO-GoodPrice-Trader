"""Jeux de donnees synthetiques pour les tests.

Volontairement minuscules et ecrits a la main : chaque test doit
pouvoir se verifier de tete. Les pieges reproduits ici sont ceux
observes sur les vrais snapshots du serveur (balises de couleur,
`ItemName` a null, balance "Infinity", prix sentinelle 999999, budget
partage entre boutiques d'un meme joueur).
"""

from typing import Any, Dict, List


def offer(
    item: str,
    buying: bool,
    price: float,
    quantity: int,
    **extra: Any,
) -> Dict[str, Any]:
    payload = {
        "ItemName": item,
        "Buying": buying,
        "Price": price,
        "Quantity": quantity,
        "Limit": extra.get("limit", 0),
        # Eco renvoie MaxNumWanted == Quantity dans les deux sens ;
        # on reproduit ce comportement pour ne pas tester une API
        # imaginaire.
        "MaxNumWanted": extra.get("wanted", quantity),
        "MinDurability": extra.get("durability", -1.0),
        "Enabled": extra.get("enabled", True),
    }
    return payload


def store(
    name: str,
    owner: str,
    balance: Any,
    offers: List[Dict[str, Any]],
    currency: str = "Calories",
    enabled: bool = True,
    full_access: Any = None,
) -> Dict[str, Any]:
    return {
        "Name": name,
        "Owner": owner,
        "Balance": balance,
        "CurrencyName": currency,
        "Enabled": enabled,
        "FullAccessUsers": full_access or [],
        "AllOffers": offers,
    }


def simple_payload() -> Dict[str, Any]:
    """Un item, un vendeur bon marche, deux acheteurs.

    Bois : Alice vend 100 a 1.00, Bob achete 60 a 1.50, Carol achete
    100 a 1.20. Profit theorique = 60 * 0.50 + 40 * 0.20 = 38.00.
    """
    return {"Stores": [
        store("Alice Shop", "Alice", 10.0, [
            offer("Wood", False, 1.00, 100),
        ]),
        store("Bob Shop", "Bob", 1000.0, [
            offer("Wood", True, 1.50, 60),
        ]),
        store("Carol Shop", "Carol", 1000.0, [
            offer("Wood", True, 1.20, 100),
        ]),
    ]}


def messy_payload() -> Dict[str, Any]:
    """Tous les pieges du vrai serveur dans un seul document."""
    return {"Stores": [
        store("<color=orange>Dirty Shop</color>", "Dave", 50.0, [
            offer(None, False, 1.0, 10),                  # slot vide
            offer("Stone", False, 999999.0, 5),           # sentinelle
            offer("Stone", False, 0.50, 0),               # rupture
            offer("Stone", False, 0.40, 20),              # exploitable
            offer("Stone", False, 0.30, 10, enabled=False),  # desactivee
        ]),
        store("Rich Shop", "Eve", "Infinity", [
            offer("Stone", True, 1.00, 999),
        ]),
        store("Broke Shop", "Frank", 0.0, [
            offer("Stone", True, 5.00, 999),              # ne paiera pas
        ]),
        store("Closed Shop", "Gina", 100.0, [
            offer("Stone", True, 9.00, 10),
        ], enabled=False),
        store("Other Currency", "Hugo", 100.0, [
            offer("Stone", True, 4.00, 10),
        ], currency="Credits"),
    ]}


def shared_wallet_payload() -> Dict[str, Any]:
    """Un joueur, deux boutiques, un seul compte en banque.

    Ivy a 10.00 en tout. Ses deux boutiques veulent acheter pour 20.00
    chacune : on ne doit jamais planifier plus de 10.00 de vente chez
    elle.
    """
    return {"Stores": [
        store("Seller", "Jack", 500.0, [
            offer("Iron", False, 0.50, 100),
        ]),
        store("Ivy North", "Ivy", 10.0, [
            offer("Iron", True, 1.00, 20),
        ]),
        store("Ivy South", "Ivy", 10.0, [
            offer("Iron", True, 1.00, 20),
        ]),
    ]}


def cross_currency_payload() -> Dict[str, Any]:
    """Boucle de change Calories -> Credits -> Calories.

    - Wood : achete 1.00 calorie, revendu 2.00 credits  -> x2
    - Iron : achete 1.00 credit,  revendu 1.50 calorie  -> x1.5
    Taux du cycle = 3.0, soit +200 %.
    """
    return {"Stores": [
        store("Cal Seller", "Kim", 100.0, [
            offer("Wood", False, 1.00, 50),
        ], currency="Calories"),
        store("Cred Buyer", "Leo", 1000.0, [
            offer("Wood", True, 2.00, 50),
        ], currency="Credits"),
        store("Cred Seller", "Mia", 1000.0, [
            offer("Iron", False, 1.00, 50),
        ], currency="Credits"),
        store("Cal Buyer", "Noah", 1000.0, [
            offer("Iron", True, 1.50, 50),
        ], currency="Calories"),
    ]}


def store_with_full_access() -> Dict[str, Any]:
    """Boutique d'un tiers ou le joueur a les pleins droits."""
    return {"Stores": [
        store("Co-managed", "Owner", 10.0, [
            offer("Wood", True, 1.0, 5),
        ], full_access=["Helper"]),
    ]}


def integration_payload() -> Dict[str, Any]:
    """Serveur complet et miniature, pour les tests bout en bout.

    Contient a la fois de l'arbitrage intra-devise (Wood en calories)
    et une boucle de change Calories <-> Credits, afin qu'un seul jeu
    de snapshots exerce les trois scripts.
    """
    payload = simple_payload()
    payload["Stores"] += cross_currency_payload()["Stores"]
    return payload
