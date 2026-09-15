"""Affichage : la seule couche qui met en forme.

Aucun calcul ici. Si un chiffre doit etre derive, il l'est dans
models.py ou dans un moteur -- sinon les tests devraient passer par
l'affichage pour verifier une regle metier.

`tabulate` est utilise s'il est installe, avec un repli maison sinon :
l'outil doit rester utilisable sur une machine ou le pip install n'a
pas encore ete fait.
"""

import html
import shutil
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .models import Cycle, Plan, PlanStep
from .presence import is_alert

BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
RESET = "\033[0m"

_COLOR = True


def set_color(enabled: bool) -> None:
    """Active ou coupe les couleurs pour tout le module."""
    global _COLOR
    _COLOR = bool(enabled)


def paint(text: str, *codes: str) -> str:
    if not _COLOR or not codes:
        return text
    return f"{''.join(codes)}{text}{RESET}"


def table(rows: Sequence[Sequence[Any]], headers: Sequence[str]) -> str:
    """Tableau texte, via tabulate si disponible."""
    if not rows:
        return paint("  (rien a afficher)", DIM)
    try:
        from tabulate import tabulate
        return tabulate(rows, headers=headers, tablefmt="simple")
    except ImportError:
        return _plain_table(rows, headers)


def _plain_table(
    rows: Sequence[Sequence[Any]],
    headers: Sequence[str],
) -> str:
    cells = [[str(c) for c in row] for row in rows]
    widths = [len(h) for h in headers]
    for row in cells:
        for index, cell in enumerate(row):
            if index < len(widths):
                widths[index] = max(widths[index], len(cell))
    lines = [
        "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers)),
        "  ".join("-" * w for w in widths),
    ]
    for row in cells:
        lines.append(
            "  ".join(c.ljust(widths[i]) for i, c in enumerate(row))
        )
    return "\n".join(lines)


def title(text: str) -> str:
    width = min(shutil.get_terminal_size((80, 20)).columns, 100)
    return paint(f"\n{text}\n{'=' * min(len(text), width)}", BOLD)


def money(value: float) -> str:
    if value == float("inf"):
        return "illimite"
    return f"{value:,.2f}".replace(",", " ")


def activity_cell(label: str) -> str:
    if is_alert(label):
        return paint(f"! {label.lstrip('! ')}", YELLOW)
    if label == "en ligne":
        return paint("en ligne", GREEN)
    return paint(label, DIM)


def routes_table(
    steps: Iterable[PlanStep],
    activity: Dict[str, str],
    show_cash: bool = False,
) -> str:
    """Tableau principal : un leg par ligne.

    `activity` fait correspondre un proprietaire a son etiquette
    d'activite ; c'est le warning "cette personne est absente" demande,
    affiche sur la colonne de revente puisque c'est la que ca compte.
    """
    headers = [
        "Item", "Qte", "Acheter chez", "Prix", "Revendre a", "Prix",
        "Profit", "ROI", "Activite vendeur",
    ]
    if show_cash:
        headers.append("Caisse")

    rows: List[List[Any]] = []
    for step in steps:
        leg = step.leg
        label = activity.get(leg.sell_to.owner, "? inconnu")
        row = [
            leg.item,
            leg.quantity,
            f"{leg.buy_from.name} ({leg.buy_from.owner})",
            f"{leg.buy_price:.2f}",
            f"{leg.sell_to.name} ({leg.sell_to.owner})",
            f"{leg.sell_price:.2f}",
            paint(f"+{leg.profit:.2f}", GREEN),
            f"{leg.roi * 100:.0f}%",
            activity_cell(label),
        ]
        if show_cash:
            row.append(money(step.cash_after))
        rows.append(row)
    return table(rows, headers)


def plan_summary(plan: Plan, stats: Dict[str, float], currency: str) -> str:
    """Bloc de synthese d'un plan."""
    lines = [
        f"  devise            : {currency}",
        f"  etapes            : {int(stats['steps'])}"
        f" ({int(stats['units'])} unites)",
        f"  achats cumules    : {money(stats['invested'])}"
        f"  (mise max d'un coup: {money(stats['peak_outlay'])})",
        f"  profit            : "
        f"{paint('+' + money(stats['profit']), GREEN, BOLD)}"
        f"  ({stats['roi'] * 100:.0f}% du capital engage)",
    ]
    if plan.start_cash != float("inf"):
        lines.append(
            f"  caisse            : {money(plan.start_cash)}"
            f" -> {money(plan.end_cash)}"
        )
    if plan.skipped_for_cash:
        lines.append(paint(
            f"  {plan.skipped_for_cash} leg(s) ecarte(s) faute de "
            "tresorerie ou de solde acheteur", DIM,
        ))
    return "\n".join(lines)


def _cycle_path(cycle: Cycle) -> str:
    return " -> ".join([*cycle.currencies, cycle.currencies[0]])


def cycles_table(cycles: Sequence[Cycle]) -> str:
    """Boucles de change entre devises."""
    rows = []
    for cycle in cycles:
        path = _cycle_path(cycle)
        items = " / ".join(leg.item for leg in cycle.legs)
        rows.append([
            path,
            items,
            f"x{cycle.rate:.3f}",
            paint(f"+{cycle.gain_pct:.1f}%", GREEN),
            money(cycle.volume),
        ])
    return table(
        rows,
        ["Boucle", "Items", "Taux", "Gain", "Volume engageable"],
    )


def activity_table(rows: Sequence[Dict[str, Any]]) -> str:
    """Rapport d'activite des joueurs."""
    table_rows = []
    for row in rows:
        table_rows.append([
            row["player"],
            row.get("city") or "-",
            activity_cell(row["label"]),
            row.get("stores", 0),
            money(row.get("balance", 0.0)),
            f"{row.get('history_days', 0):.0f}j / "
            f"{row.get('snapshots', 0)} obs.",
        ])
    return table(
        table_rows,
        ["Joueur", "Ville", "Activite", "Boutiques", "Solde", "Historique"],
    )


def warn(text: str) -> str:
    return paint(f"! {text}", YELLOW)


def error(text: str) -> str:
    return paint(f"Erreur: {text}", RED)


def info(text: str) -> str:
    return paint(text, CYAN)


# ---------------------------------------------------------------- HTML

_HTML_CSS = """
:root { color-scheme: dark; }
body { margin: 0; padding: 24px; background: #14161a; color: #e7e9ee;
       font: 14px/1.5 -apple-system, Segoe UI, Roboto, sans-serif; }
h1 { font-size: 20px; margin: 0 0 4px; }
h2 { font-size: 15px; margin: 28px 0 8px; color: #9aa4b2;
     text-transform: uppercase; letter-spacing: .06em; }
.meta { color: #7c8694; font-size: 12px; margin-bottom: 8px; }
.kpis { display: flex; flex-wrap: wrap; gap: 12px; margin: 16px 0; }
.kpi { background: #1c1f26; border: 1px solid #272b34; border-radius: 8px;
       padding: 10px 14px; min-width: 130px; }
.kpi b { display: block; font-size: 19px; font-weight: 600; }
.kpi span { color: #7c8694; font-size: 11px; text-transform: uppercase;
            letter-spacing: .05em; }
.wrap { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th { text-align: left; color: #9aa4b2; font-weight: 600;
     border-bottom: 1px solid #2d323c; padding: 7px 10px;
     white-space: nowrap; }
td { border-bottom: 1px solid #1f232b; padding: 6px 10px; }
tr:hover td { background: #1a1d23; }
.num { text-align: right; font-variant-numeric: tabular-nums; }
.gain { color: #5ed49a; font-weight: 600; }
.alert { color: #e8b84b; }
.muted { color: #7c8694; }
.ok { color: #5ed49a; }
footer { margin-top: 32px; color: #5d6673; font-size: 11px; }
"""


def _cell_activity_html(label: str) -> str:
    css = "alert" if is_alert(label) else (
        "ok" if label == "en ligne" else "muted"
    )
    return f'<span class="{css}">{html.escape(label)}</span>'


def html_report(
    currency: str,
    source: str,
    generated_at: str,
    stats: Dict[str, float],
    steps: Sequence[PlanStep],
    activity: Dict[str, str],
    cycles: Sequence[Cycle] = (),
    alerts: Optional[Sequence[str]] = None,
) -> str:
    """Rapport autonome, un seul fichier, sans dependance externe."""
    kpis = [
        ("Profit", f"+{money(stats['profit'])}", currency),
        ("Etapes", str(int(stats["steps"])), "legs"),
        ("Capital engage", money(stats["invested"]), currency),
        ("ROI", f"{stats['roi'] * 100:.0f}%", "du capital"),
        ("Mise max", money(stats["peak_outlay"]), "d'un coup"),
    ]
    kpi_html = "".join(
        f'<div class="kpi"><span>{html.escape(name)}</span>'
        f'<b>{html.escape(value)}</b>'
        f'<span>{html.escape(unit)}</span></div>'
        for name, value, unit in kpis
    )

    rows = []
    for step in steps:
        leg = step.leg
        label = activity.get(leg.sell_to.owner, "? inconnu")
        rows.append(
            "<tr>"
            f"<td>{html.escape(leg.item)}</td>"
            f'<td class="num">{leg.quantity}</td>'
            f"<td>{html.escape(leg.buy_from.name)}"
            f' <span class="muted">({html.escape(leg.buy_from.owner)})'
            "</span></td>"
            f'<td class="num">{leg.buy_price:.2f}</td>'
            f"<td>{html.escape(leg.sell_to.name)}"
            f' <span class="muted">({html.escape(leg.sell_to.owner)})'
            "</span></td>"
            f'<td class="num">{leg.sell_price:.2f}</td>'
            f'<td class="num gain">+{leg.profit:.2f}</td>'
            f'<td class="num">{leg.roi * 100:.0f}%</td>'
            f"<td>{_cell_activity_html(label)}</td>"
            "</tr>"
        )

    cycle_section = ""
    if cycles:
        cycle_rows = "".join(
            "<tr>"
            f"<td>{html.escape(_cycle_path(c))}</td>"
            f"<td>{html.escape(' / '.join(lg.item for lg in c.legs))}</td>"
            f'<td class="num">x{c.rate:.3f}</td>'
            f'<td class="num gain">+{c.gain_pct:.1f}%</td>'
            f'<td class="num">{money(c.volume)}</td>'
            "</tr>"
            for c in cycles
        )
        cycle_section = (
            "<h2>Boucles de change</h2><div class=\"wrap\"><table>"
            "<thead><tr><th>Boucle</th><th>Items</th><th>Taux</th>"
            "<th>Gain</th><th>Volume</th></tr></thead>"
            f"<tbody>{cycle_rows}</tbody></table></div>"
        )

    alert_section = ""
    if alerts:
        items = "".join(f"<li>{html.escape(a)}</li>" for a in alerts)
        alert_section = (
            f"<h2>Points d'attention</h2><ul class=\"muted\">{items}</ul>"
        )

    return (
        "<!doctype html><html lang=\"fr\"><head>"
        "<meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,"
        "initial-scale=1\">"
        f"<title>Eco - routes {html.escape(currency)}</title>"
        f"<style>{_HTML_CSS}</style></head><body>"
        f"<h1>Routes de trading - {html.escape(currency)}</h1>"
        f'<div class="meta">{html.escape(source)} &middot; '
        f"{html.escape(generated_at)}</div>"
        f'<div class="kpis">{kpi_html}</div>'
        "<h2>Chaine d'execution</h2>"
        '<div class="wrap"><table><thead><tr>'
        "<th>Item</th><th>Qte</th><th>Acheter chez</th><th>Prix</th>"
        "<th>Revendre a</th><th>Prix</th><th>Profit</th><th>ROI</th>"
        "<th>Activite vendeur</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
        f"{cycle_section}{alert_section}"
        "<footer>Genere par ecotrade. Les prix Eco bougent en permanence"
        " : re-generez avant d'aller en jeu.</footer>"
        "</body></html>"
    )
