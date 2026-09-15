"""Activite des joueurs : qui est encore la, qui a laisse sa boutique.

L'API Eco ne donne aucune date de derniere connexion (cf.
docs/activite-joueurs.md). Ce script enregistre un instantane a chaque
appel et affiche ce que l'historique accumule permet de dire. Les deux
autres scripts enregistrent aussi, donc un usage normal suffit a
alimenter l'historique -- celui-ci sert a le consulter, et a le lancer
en tache planifiee si on veut un rythme regulier.
"""

import argparse
import sys
import time

from ecotrade import cli, render
from ecotrade.client import ApiError
from ecotrade.config import ConfigError
from ecotrade.presence import is_alert


def parse_args() -> argparse.Namespace:
    parser = cli.base_parser(description=__doc__)
    parser.add_argument(
        "--alerts-only", action="store_true",
        help="n'affiche que les joueurs qui declenchent une alerte",
    )
    parser.add_argument(
        "--sort", choices=("name", "activity", "balance"),
        default="activity",
        help="ordre de tri (defaut: activity)",
    )
    return parser.parse_args()


def run(args: argparse.Namespace) -> None:
    render.set_color(not args.no_color)
    context = cli.bootstrap(args)
    config = context.config

    owners = {}
    for store in context.stores:
        if not store.owner:
            continue
        entry = owners.setdefault(
            store.owner, {"stores": 0, "balance": 0.0, "abandoned": 0}
        )
        entry["stores"] += 1
        entry["balance"] = max(entry["balance"], store.balance)
        entry["abandoned"] += int(store.looks_abandoned)

    # Les joueurs sans boutique comptent aussi : ils peuvent apparaitre
    # dans /players et etre des clients potentiels.
    for name in context.players:
        owners.setdefault(name, {"stores": 0, "balance": 0.0,
                                 "abandoned": 0})

    rows = []
    for name, stats in owners.items():
        activity = context.activity_of(name)
        label = context.activity_label(name)
        rows.append({
            "player": name,
            "city": activity.city,
            "label": label,
            "alert": is_alert(label),
            "stores": stats["stores"],
            "balance": stats["balance"],
            "abandoned": stats["abandoned"],
            "history_days": activity.history_days,
            "snapshots": activity.snapshots,
            "online": activity.online,
            "last_online_days": activity.last_online_days,
            "last_change_days": activity.last_change_days,
        })

    if args.alerts_only:
        rows = [r for r in rows if r["alert"]]

    if args.sort == "name":
        rows.sort(key=lambda r: r["player"].lower())
    elif args.sort == "balance":
        rows.sort(key=lambda r: -r["balance"])
    else:
        rows.sort(key=lambda r: (
            not r["alert"], not r["online"], r["player"].lower()
        ))

    online = sum(1 for r in rows if r["online"])
    alerts = sum(1 for r in rows if r["alert"])

    print(render.title("Activite des joueurs"))
    print(render.info(
        f"  source: {context.source_label}"
        f"  |  historique: {context.config.presence_path}"
    ))
    print(
        f"  {len(rows)} joueur(s) suivi(s), {online} en ligne, "
        f"{alerts} alerte(s)"
    )
    print()
    print(render.activity_table(rows))

    fresh = [r for r in rows if r["history_days"] < 1]
    if len(fresh) == len(rows) and rows:
        print()
        print(render.paint(
            "  Historique tout neuf : l'API ne fournit pas de date de\n"
            "  derniere connexion, l'app la reconstruit en observant.\n"
            "  Relancez n'importe quel script chaque jour (ou en tache\n"
            "  planifiee) et les colonnes se rempliront d'elles-memes.",
            render.DIM,
        ))

    abandoned = [r for r in rows if r["abandoned"] and r["stores"]]
    if abandoned:
        print()
        print(render.paint(
            f"  {len(abandoned)} joueur(s) avec au moins une boutique sans"
            " stock ni demande (signal immediat, sans historique)",
            render.DIM,
        ))

    if args.json_out:
        cli.write_json(args.json_out, {
            "source": context.source_label,
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "absent_days": config.absent_days,
            "stale_days": config.stale_days,
            "players": rows,
        })
        print(render.info(f"\n  JSON ecrit dans {args.json_out}"))


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
