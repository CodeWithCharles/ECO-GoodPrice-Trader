"""Activite des joueurs, deduite par observation repetee.

Pourquoi ce module existe : l'API GoodPrice ne donne *aucune* date de
derniere connexion. `/players` ne renvoie qu'un booleen `IsOnline`
instantane, et `/stores` n'a aucun horodatage. Il n'y a donc pas de
"derniere connexion" a lire -- il faut la construire.

L'app enregistre donc un instantane a chaque execution (fichier
`data/presence.json`) et en deduit deux signaux :

- `last_online_days`  : depuis combien de jours on n'a plus vu le
  joueur en ligne ;
- `last_change_days`  : depuis combien de jours ses boutiques n'ont
  bouge ni en prix, ni en stock, ni en solde. Une boutique figee est
  un bon indicateur de joueur parti, et il est disponible meme si
  `/players` n'existe pas sur le serveur.

Au premier run l'historique est vide. Plutot que d'afficher une
fausse certitude, on se replie alors sur `snapshot_flags()` : les
seuls signaux d'abandon lisibles sur un instantane unique (compte a
zero, boutiques sans stock ni demande, emplacements d'offre jamais
configures). Les signaux temporels se remplissent ensuite tout seuls,
puisque chaque execution de n'importe quel script enregistre un
instantane.

Pourquoi prevenir avant de vendre a un absent : une boutique Eco paie
toute seule, donc la vente *passe* techniquement. Mais le compte d'un
joueur parti ne se recharge jamais : on vide un stock d'argent mort au
lieu d'alimenter quelqu'un qui continuera a commercer, et les prix
figes sont souvent des prix faux.
"""

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .models import SELL_PLACEHOLDER_PRICE, Activity, Store

SECONDS_PER_DAY = 86400.0
DEFAULT_ABSENT_DAYS = 7.0
DEFAULT_STALE_DAYS = 14.0
# En dessous de deux instantanes espaces de cette duree, on refuse de
# conclure quoi que ce soit : sinon le premier run affiche "absent 0 j"
# pour tout le monde, ce qui est du bruit.
MIN_HISTORY_DAYS = 1.0


def store_fingerprint(store: Store) -> str:
    """Empreinte stable d'une boutique : prix, stocks et solde.

    Tout changement visible cote client (un prix ajuste, du stock
    ajoute, un achat encaisse) change l'empreinte. On se contente d'un
    sha1 tronque pour garder le fichier d'historique petit.
    """
    parts = [f"{store.balance:.2f}"]
    for offer in sorted(
        store.offers, key=lambda o: (o.item, o.buying)
    ):
        parts.append(
            f"{offer.item}|{int(offer.buying)}|{offer.price:.2f}"
            f"|{offer.quantity}|{offer.max_num_wanted}"
        )
    digest = hashlib.sha1("\n".join(parts).encode("utf-8"))
    return digest.hexdigest()[:16]


@dataclass
class PresenceStore:
    """Historique persistant, un fichier JSON par serveur.

    Structure volontairement plate et lisible a la main : on ne garde
    par joueur que le dernier etat connu et les dates cles, pas la
    serie complete. Le fichier reste de l'ordre du kilo-octet meme
    apres des mois.
    """

    path: Path
    data: Dict[str, Any] = None

    def __post_init__(self) -> None:
        self.path = Path(self.path)
        self.data = self._load()

    def _load(self) -> Dict[str, Any]:
        if not self.path.is_file():
            return {"version": 1, "first_seen": None, "players": {}}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # Un historique corrompu ne doit jamais bloquer une
            # analyse : on repart de zero, quitte a perdre le passe.
            return {"version": 1, "first_seen": None, "players": {}}
        raw.setdefault("players", {})
        raw.setdefault("first_seen", None)
        return raw

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.data, indent=1, ensure_ascii=False)
        self.path.write_text(payload, encoding="utf-8")

    def record(
        self,
        stores: Iterable[Store],
        players: Optional[Dict[str, Any]] = None,
        now: Optional[float] = None,
    ) -> None:
        """Enregistre un instantane. Idempotent a la seconde pres."""
        now = time.time() if now is None else now
        if self.data["first_seen"] is None:
            self.data["first_seen"] = now

        by_owner: Dict[str, List[Store]] = {}
        for store in stores:
            if store.owner:
                by_owner.setdefault(store.owner, []).append(store)

        names = set(by_owner) | set(players or {})
        for name in names:
            entry = self.data["players"].setdefault(name, {
                "first_seen": now,
                "snapshots": 0,
                "last_online": None,
                "fingerprint": None,
                "last_change": None,
                "city": None,
            })
            entry["snapshots"] = entry.get("snapshots", 0) + 1
            entry["last_seen_at"] = now

            info = (players or {}).get(name) or {}
            if info.get("online") is True:
                entry["last_online"] = now
            if info.get("city"):
                entry["city"] = info["city"]

            owned = by_owner.get(name) or []
            if owned:
                fingerprint = "".join(
                    store_fingerprint(s) for s in sorted(
                        owned, key=lambda s: s.name
                    )
                )
                if entry.get("fingerprint") != fingerprint:
                    entry["fingerprint"] = fingerprint
                    entry["last_change"] = now

    def activity(
        self,
        name: str,
        players: Optional[Dict[str, Any]] = None,
        now: Optional[float] = None,
    ) -> Activity:
        """Ce qu'on sait de ce joueur, sous forme exploitable."""
        now = time.time() if now is None else now
        entry = self.data["players"].get(name) or {}
        info = (players or {}).get(name) or {}

        first = entry.get("first_seen")
        history = (now - first) / SECONDS_PER_DAY if first else 0.0

        def days_since(key: str) -> Optional[float]:
            stamp = entry.get(key)
            if stamp is None:
                return None
            return round((now - stamp) / SECONDS_PER_DAY, 1)

        online = info.get("online")
        if online is None and entry.get("last_online"):
            online = False

        return Activity(
            player=name,
            online=online,
            city=info.get("city") or entry.get("city"),
            last_online_days=0.0 if online else days_since("last_online"),
            last_change_days=days_since("last_change"),
            history_days=round(history, 1),
            snapshots=entry.get("snapshots", 0),
        )


def snapshot_flags(stores: Iterable[Store]) -> List[str]:
    """Signaux d'abandon lisibles sur un *seul* instantane.

    Indispensable au premier run : sans historique, la seule chose
    qu'on puisse encore dire c'est "ce compte n'a pas de quoi payer" ou
    "ces boutiques n'ont jamais rien eu dedans". Ce sont des faits, pas
    des extrapolations.
    """
    owned = [s for s in stores]
    if not owned:
        return []

    flags: List[str] = []
    balance = max(s.balance for s in owned)
    if balance <= 0:
        flags.append("solde 0")

    # Seulement si *toutes* ses boutiques sont vides : un joueur actif
    # a souvent une boutique de reserve inutilisee, la signaler serait
    # du bruit et decredibiliserait les vraies alertes.
    if all(s.looks_abandoned for s in owned):
        flags.append("boutique vide")

    slots = [o for s in owned for o in s.offers]
    unset = [
        o for o in slots
        if (not o.buying and o.price >= SELL_PLACEHOLDER_PRICE)
        or (o.buying and o.price <= 0)
    ]
    if slots and len(unset) >= max(3, len(slots) // 2):
        flags.append("offres non configurees")

    return flags


def warning_for(
    activity: Activity,
    absent_days: float = DEFAULT_ABSENT_DAYS,
    stale_days: float = DEFAULT_STALE_DAYS,
    fallback: Optional[Sequence[str]] = None,
) -> str:
    """Etiquette courte pour la colonne "Activite" d'un tableau.

    Volontairement tres court (une poignee de caracteres) : le tableau
    de routes est deja large, et le message doit juste attirer l'oeil.
    L'explication longue vit dans docs/activite-joueurs.md.

    `fallback` est la sortie de snapshot_flags() : elle prend le relais
    quand l'historique ne permet encore rien de dire.
    """
    if activity.online:
        return "en ligne"

    if activity.history_days < MIN_HISTORY_DAYS:
        return f"! {', '.join(fallback)}" if fallback else "? inconnu"

    absent = activity.last_online_days
    stale = activity.last_change_days

    if absent is None and stale is None:
        return f"! {', '.join(fallback)}" if fallback else "? inconnu"

    # Jamais vu en ligne depuis le debut de l'historique : on ne peut
    # pas dire "absent depuis X", seulement "pas vu depuis au moins X".
    if absent is None:
        if stale is not None and stale >= stale_days:
            return f"! figee {stale:.0f}j"
        return f"? jamais vu ({activity.history_days:.0f}j)"

    if absent >= absent_days:
        return f"! absent {absent:.0f}j"
    if stale is not None and stale >= stale_days:
        return f"! figee {stale:.0f}j"
    return f"vu il y a {absent:.0f}j"


def is_alert(label: str) -> bool:
    """Vrai si l'etiquette merite qu'on propose une autre contrepartie."""
    return label.startswith("!") or label.startswith("? jamais")
