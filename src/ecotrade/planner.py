"""Chaine d'execution sous contrainte de capital.

Le probleme n'est pas "quels legs sont rentables" (routes.py repond
deja) mais "dans quel ordre les faire quand on n'a pas de quoi tout
acheter d'un coup". Comme on revend immediatement apres avoir achete,
le capital se recycle : chaque leg rembourse sa mise plus le profit, et
finance le suivant.

Pourquoi un glouton *iteratif* et pas un simple tri : la faisabilite
d'un leg depend de la tresorerie du moment. Avec 25 calories, un leg a
90 de mise est injouable au depart mais le devient une fois deux ou
trois legs encaisses. Un tri fige une fois pour toutes passerait a
cote ; ici on rejoue le choix a chaque etape, sur la quantite
reellement finançable, et un leg ecarte reste candidat pour plus tard.

Ce n'est pas un optimum exact -- le probleme est un sac a dos ordonne
avec budgets partages, donc NP-difficile -- mais le choix "meilleur
coup jouable maintenant" est ce qu'un joueur fait de toute facon, et il
reste deterministe et explicable etape par etape.
"""

from typing import Dict, Iterable, List, Optional, Tuple

from .models import Leg, Plan, PlanStep

INFINITY = float("inf")

#: Criteres de selection du prochain leg.
ORDERS = ("profit", "roi")


def _feasible_quantity(
    leg: Leg,
    cash: float,
    budgets: Dict[Tuple[str, str], float],
) -> Tuple[int, List[str]]:
    """Quantite reellement executable maintenant, et pourquoi bornee."""
    quantity = leg.quantity
    notes: List[str] = []

    budget = budgets.get(leg.sell_to.wallet, INFINITY)
    if budget != INFINITY:
        if leg.sell_price <= 0:
            return 0, notes
        affordable = int(budget // leg.sell_price)
        if affordable < quantity:
            notes.append("limite par le solde de l'acheteur")
            quantity = affordable

    if cash != INFINITY:
        if leg.buy_price <= 0:
            return 0, notes
        payable = int(cash // leg.buy_price)
        if payable < quantity:
            notes.append("limite par la tresorerie")
            quantity = payable

    return max(0, quantity), notes


def _score(leg: Leg, order: str) -> Tuple[float, float]:
    """Plus c'est grand, plus le leg est prioritaire."""
    if order == "roi":
        return (leg.roi, leg.profit)
    return (leg.profit, leg.roi)


def build_plan(
    legs: Iterable[Leg],
    currency: str,
    start_cash: float = INFINITY,
    wallets: Optional[Dict[Tuple[str, str], float]] = None,
    max_steps: Optional[int] = None,
    order: str = "profit",
) -> Plan:
    """Ordonne les legs en une chaine executable.

    `start_cash` a l'infini = "montre-moi tout ce qui est rentable sans
    te soucier de ma bourse". Dans ce cas la chaine se reduit a un
    classement, ce qui est exactement ce qu'on veut afficher dans
    Routes.py.

    `wallets` est le solde par (proprietaire, devise). Il est decremente
    au fil des etapes, donc un joueur a trois boutiques ne se retrouve
    pas a payer trois fois son compte en banque.
    """
    budgets: Dict[Tuple[str, str], float] = dict(wallets or {})
    cash = start_cash
    plan = Plan(currency=currency, start_cash=start_cash)

    # Ordre stable avant selection : deux legs de score identique
    # doivent toujours sortir dans le meme ordre d'un run a l'autre.
    remaining = sorted(
        legs,
        key=lambda lg: (lg.item, lg.buy_from.name, lg.sell_to.name),
    )

    while remaining:
        if max_steps is not None and len(plan.steps) >= max_steps:
            break

        best_index = -1
        best_leg: Optional[Leg] = None
        best_notes: List[str] = []
        best_score = (0.0, 0.0)

        for index, leg in enumerate(remaining):
            quantity, notes = _feasible_quantity(leg, cash, budgets)
            if quantity <= 0:
                continue
            candidate = leg.with_quantity(quantity)
            if candidate.profit <= 0:
                continue
            score = _score(candidate, order)
            if best_leg is None or score > best_score:
                best_index, best_leg, best_notes = index, candidate, notes
                best_score = score

        if best_leg is None:
            # Plus rien de finançable : le reste est hors de portee.
            plan.skipped_for_cash = len(remaining)
            break

        # Execution partielle : le reliquat reste candidat. C'est ce
        # qui permet de finir un gros leg en deux passages quand la
        # tresorerie ne suivait pas au premier tour.
        full = remaining[best_index]
        if best_leg.quantity < full.quantity:
            remaining[best_index] = full.with_quantity(
                full.quantity - best_leg.quantity
            )
        else:
            remaining.pop(best_index)

        cash_before = cash
        if cash != INFINITY:
            cash = round(cash - best_leg.cost + best_leg.revenue, 2)
        wallet = best_leg.sell_to.wallet
        if budgets.get(wallet, INFINITY) != INFINITY:
            budgets[wallet] = round(budgets[wallet] - best_leg.revenue, 2)

        notes = list(best_notes)
        if best_leg.same_owner:
            notes.append("meme joueur des deux cotes")

        plan.steps.append(PlanStep(
            leg=best_leg,
            cash_before=cash_before,
            cash_after=cash,
            notes=notes,
        ))

    return plan


def summarize(plan: Plan) -> Dict[str, float]:
    """Chiffres cles d'un plan, pour l'affichage et l'export JSON."""
    legs = [s.leg for s in plan.steps]
    invested = round(sum(lg.cost for lg in legs), 2)
    units = sum(lg.quantity for lg in legs)
    return {
        "steps": len(legs),
        "units": units,
        "invested": invested,
        "profit": plan.profit,
        "roi": round(plan.profit / invested, 4) if invested else 0.0,
        "peak_outlay": plan.peak_outlay,
        "start_cash": plan.start_cash,
        "end_cash": plan.end_cash,
    }
