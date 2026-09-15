"""Chaines de trading : dans quel ordre enchainer les routes.

Deux choses que Routes.py ne fait pas :

1. la chaine d'execution a capital limite -- avec 30 calories en poche
   on ne peut pas acheter 139 farines d'un coup, mais on peut faire un
   petit leg, encaisser, et remettre la mise sur le suivant ;
2. les boucles de change entre devises, quand un item achete dans une
   devise se revend dans une autre.
"""

import argparse
import sys
import time

from ecotrade import chains, cli, planner, render, routes
from ecotrade.client import ApiError
from ecotrade.config import ConfigError
from ecotrade.market import build_market


def parse_args() -> argparse.Namespace:
    parser = cli.base_parser(description=__doc__)
    parser.add_argument(
        "--capital", metavar="N", type=float,
        help="tresorerie de depart dans la devise (defaut: illimitee)",
    )
    parser.add_argument(
        "--min-profit", metavar="N", type=float,
        help="ignore les legs rapportant moins que N (defaut: 0)",
    )
    parser.add_argument(
        "--max-steps", metavar="N", type=int, default=0,
        help="longueur maximale de la chaine (0 = pas de limite)",
    )
    parser.add_argument(
        "--no-cycles", action="store_true",
        help="n'analyse pas les boucles de change multi-devises",
    )
    parser.add_argument(
        "--min-gain", metavar="PCT", type=float, default=1.0,
        help="gain minimal d'une boucle de change, en %% (defaut: 1)",
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
    )
    legs, _ = routes.cap_by_wallet(legs, context.market)

    capital = config.capital if config.capital > 0 else float("inf")
    plan = planner.build_plan(
        legs,
        currency=context.currency,
        start_cash=capital,
        wallets=context.market.wallets,
        max_steps=args.max_steps or None,
    )
    stats = planner.summarize(plan)

    activity = {
        owner: context.activity_label(owner)
        for owner in {s.leg.sell_to.owner for s in plan.steps}
    }

    print(render.title(f"Chaine d'execution - {context.currency}"))
    print(render.info(f"  source: {context.source_label}"))
    print()
    print(render.plan_summary(plan, stats, context.currency))
    print()
    print(render.routes_table(
        plan.steps, activity, show_cash=capital != float("inf"),
    ))

    if capital != float("inf") and plan.steps:
        print()
        print(render.paint(
            f"  Ordre a respecter : chaque etape finance la suivante."
            f" Mise a avancer au plus gros passage :"
            f" {render.money(plan.peak_outlay)}.",
            render.DIM,
        ))

    cycles = []
    if not args.no_cycles:
        full_market = build_market(context.stores, currency=None)
        cycles = chains.find_cycles(
            full_market,
            blacklist=context.blacklist,
            min_gain_pct=args.min_gain,
        )
        print(render.title("Boucles de change entre devises"))
        currencies = full_market.currencies()
        print(render.info(
            f"  devises detectees: {', '.join(currencies) or 'aucune'}"
        ))
        print()
        if cycles:
            print(render.cycles_table(cycles))
        else:
            print(render.paint(
                "  Aucune boucle rentable. C'est le cas normal quand une"
                " seule devise est vraiment utilisee sur le serveur :"
                " il n'y a alors pas de taux de change a exploiter.",
                render.DIM,
            ))

    if args.json_out:
        cli.write_json(args.json_out, {
            "currency": context.currency,
            "source": context.source_label,
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "summary": stats,
            "chain": [
                {
                    "order": index + 1,
                    "item": step.leg.item,
                    "quantity": step.leg.quantity,
                    "buy_store": step.leg.buy_from.name,
                    "buy_price": step.leg.buy_price,
                    "sell_store": step.leg.sell_to.name,
                    "sell_price": step.leg.sell_price,
                    "profit": step.leg.profit,
                    "cash_after": (
                        None if step.cash_after == float("inf")
                        else step.cash_after
                    ),
                    "notes": step.notes,
                }
                for index, step in enumerate(plan.steps)
            ],
            "currency_cycles": [
                {
                    "path": list(cycle.currencies),
                    "items": [lg.item for lg in cycle.legs],
                    "rate": cycle.rate,
                    "gain_pct": cycle.gain_pct,
                    "volume": cycle.volume,
                }
                for cycle in cycles
            ],
        })
        print(render.info(f"\n  JSON ecrit dans {args.json_out}"))

    if args.html:
        page = render.html_report(
            currency=context.currency,
            source=context.source_label,
            generated_at=time.strftime("%Y-%m-%d %H:%M:%S"),
            stats=stats,
            steps=plan.steps,
            activity=activity,
            cycles=cycles,
        )
        with open(args.html, "w", encoding="utf-8") as handle:
            handle.write(page)
        print(render.info(f"  HTML ecrit dans {args.html}"))


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
