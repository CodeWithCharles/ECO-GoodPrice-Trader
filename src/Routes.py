"""Routes d'arbitrage direct : ou acheter, ou revendre, combien on gagne.

Repond a la question "qu'est-ce qui est rentable la, maintenant, sur ce
serveur". Pour l'ordre d'execution sous contrainte de bourse, voir
Chains.py.
"""

import argparse
import sys
import time

from ecotrade import cli, planner, render, routes
from ecotrade.client import ApiError
from ecotrade.config import ConfigError
from ecotrade.presence import is_alert


def parse_args() -> argparse.Namespace:
    parser = cli.base_parser(
        description=__doc__,
    )
    parser.add_argument(
        "--min-profit", metavar="N", type=float,
        help="ignore les routes rapportant moins que N (defaut: 0)",
    )
    parser.add_argument(
        "--top", metavar="N", type=int,
        help="nombre de routes affichees (defaut: 25, 0 = toutes)",
    )
    parser.add_argument(
        "--item", metavar="NOM", action="append",
        help="restreint l'analyse a cet item (repetable)",
    )
    parser.add_argument(
        "--sort", choices=planner.ORDERS, default="profit",
        help="classement: profit (defaut) ou roi",
    )
    parser.add_argument(
        "--no-same-owner", action="store_true",
        help="ecarte les routes ou le meme joueur vend et rachete",
    )
    parser.add_argument(
        "--html", metavar="FICHIER",
        help="ecrit aussi un rapport HTML autonome",
    )
    return parser.parse_args()


def run(args: argparse.Namespace) -> None:
    render.set_color(not args.no_color)
    context = cli.bootstrap(args)
    config = context.config

    legs = routes.find_legs(
        context.market,
        currency=context.currency,
        blacklist=context.blacklist,
        min_profit=config.min_profit,
        items=args.item,
        allow_same_owner=not args.no_same_owner,
    )

    # Le solde de l'acheteur est une contrainte reelle : une boutique
    # sans argent ne paiera pas, meme si son prix d'achat est genereux.
    legs, _ = routes.cap_by_wallet(legs, context.market)

    # On passe par le planner meme sans budget : il fournit les memes
    # objets PlanStep que Chains.py, donc un seul chemin d'affichage.
    capital = config.capital if config.capital > 0 else float("inf")
    plan = planner.build_plan(
        legs,
        currency=context.currency,
        start_cash=capital,
        wallets=context.market.wallets,
        order=args.sort,
    )
    stats = planner.summarize(plan)

    activity = {
        owner: context.activity_label(owner)
        for owner in {s.leg.sell_to.owner for s in plan.steps}
    }

    print(render.title(f"Routes rentables - {context.currency}"))
    print(render.info(
        f"  source: {context.source_label}"
        + (f"  |  joueur: {context.user_name}" if context.user_name else "")
    ))
    print()
    print(render.plan_summary(plan, stats, context.currency))

    steps = plan.steps
    top = config.top if config.top > 0 else len(steps)
    print()
    print(render.routes_table(
        steps[:top], activity, show_cash=capital != float("inf"),
    ))
    if len(steps) > top:
        print(render.paint(
            f"  ... {len(steps) - top} route(s) de plus (--top 0 pour tout)",
            render.DIM,
        ))

    alerts = _alerts(context, plan, activity)
    if alerts:
        print()
        print(render.paint("Points d'attention", render.BOLD))
        for line in alerts:
            print(f"  {render.warn(line)}")

    rejected = context.blacklist.rejections(context.stores)
    if rejected:
        print()
        print(render.paint(
            f"  {len(rejected)} boutique(s) ecartee(s) par les filtres",
            render.DIM,
        ))

    if args.json_out:
        cli.write_json(args.json_out, {
            "currency": context.currency,
            "source": context.source_label,
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "summary": stats,
            "activity": activity,
            "alerts": alerts,
            "routes": [_leg_dict(s.leg, activity) for s in steps],
        })
        print(render.info(f"\n  JSON ecrit dans {args.json_out}"))

    if args.html:
        page = render.html_report(
            currency=context.currency,
            source=context.source_label,
            generated_at=time.strftime("%Y-%m-%d %H:%M:%S"),
            stats=stats,
            steps=steps[:top],
            activity=activity,
            alerts=alerts,
        )
        with open(args.html, "w", encoding="utf-8") as handle:
            handle.write(page)
        print(render.info(f"  HTML ecrit dans {args.html}"))


def _leg_dict(leg, activity):
    return {
        "item": leg.item,
        "quantity": leg.quantity,
        "buy_store": leg.buy_from.name,
        "buy_owner": leg.buy_from.owner,
        "buy_price": leg.buy_price,
        "sell_store": leg.sell_to.name,
        "sell_owner": leg.sell_to.owner,
        "sell_price": leg.sell_price,
        "cost": leg.cost,
        "revenue": leg.revenue,
        "profit": leg.profit,
        "roi": round(leg.roi, 4),
        "seller_activity": activity.get(leg.sell_to.owner),
        "same_owner": leg.same_owner,
    }


def _alerts(context, plan, activity):
    """Messages courts, un par contrepartie problematique.

    C'est le warning demande : on ne bloque pas la route, on signale
    que l'acheteur n'a pas l'air actif et qu'un autre client vaudrait
    peut-etre mieux.
    """
    lines = []
    flagged = sorted(
        owner for owner, label in activity.items() if is_alert(label)
    )
    for owner in flagged:
        label = activity[owner].lstrip("! ")
        concerned = sorted({
            s.leg.sell_to.name for s in plan.steps
            if s.leg.sell_to.owner == owner
        })
        shops = ", ".join(concerned[:3])
        lines.append(
            f"{owner} ({label}) - peu actif, mieux vaut peut-etre "
            f"vendre ailleurs [{shops}]"
        )

    # Un item dont le meilleur acheteur est a court d'argent : le prix
    # affiche est bon mais l'encaissement ne suivra pas.
    for step in plan.steps:
        if "limite par le solde de l'acheteur" in step.notes:
            lines.append(
                f"{step.leg.sell_to.name} n'a pas de quoi tout payer sur "
                f"{step.leg.item} (qte ramenee a {step.leg.quantity})"
            )
    return lines[:12]


def main() -> int:
    try:
        run(parse_args())
    except (ApiError, ConfigError, OSError, ValueError) as exc:
        print(render.error(str(exc)), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
