"""Filtrage des contreparties et des items.

Trois listes independantes (joueurs, boutiques, items), toutes en
correspondance *partielle et insensible a la casse* : on ecrit
"Dumping" pour ecarter "<color=grey>Twitch's Dumping Grounds</color>".
C'est volontaire -- les noms de boutique Eco sont longs, changeants et
contiennent des balises de couleur, donc exiger l'exact serait
inutilisable.

Cas particulier : ses propres boutiques. Elles sont exclues par defaut
des deux cotes, parce qu'acheter a soi-meme ou se vendre a soi-meme ne
cree aucun profit -- l'argent change juste de poche.
"""

from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence

from .models import Store


@dataclass
class Blacklist:
    """Motifs a exclure. Listes vides = rien n'est filtre."""

    players: Sequence[str] = field(default_factory=tuple)
    stores: Sequence[str] = field(default_factory=tuple)
    items: Sequence[str] = field(default_factory=tuple)
    own_names: Sequence[str] = field(default_factory=tuple)
    exclude_own: bool = True

    def __post_init__(self) -> None:
        self._players = _normalize(self.players)
        self._stores = _normalize(self.stores)
        self._items = _normalize(self.items)
        self._own = _normalize(self.own_names)

    def blocks_store(self, store: Store) -> Optional[str]:
        """Motif de rejet de la boutique, ou None si elle est gardee."""
        if self.exclude_own and self._is_own(store):
            return "boutique du joueur"
        hit = _match(self._players, store.owner)
        if hit:
            return f"joueur '{hit}'"
        hit = _match(self._stores, store.name)
        if hit:
            return f"boutique '{hit}'"
        return None

    def blocks_item(self, item: str) -> Optional[str]:
        hit = _match(self._items, item)
        return f"item '{hit}'" if hit else None

    def _is_own(self, store: Store) -> bool:
        """Boutique possedee ou pilotee par le joueur.

        Ici la comparaison est *exacte* (au contraire des blacklists) :
        un pseudo est une identite, pas un motif de recherche, et un
        "Tec" partiel ecarterait "Tecumseh".
        """
        if not self._own:
            return False
        names = {store.owner.lower()}
        names.update(u.lower() for u in store.full_access_users if u)
        return bool(names & set(self._own))

    def filter_stores(self, stores: Iterable[Store]) -> List[Store]:
        return [s for s in stores if self.blocks_store(s) is None]

    def rejections(self, stores: Iterable[Store]) -> List[str]:
        """Resume lisible de ce qui a ete ecarte, pour l'afficher."""
        out = []
        for store in stores:
            reason = self.blocks_store(store)
            if reason:
                out.append(f"{store.name} ({store.owner}) -> {reason}")
        return sorted(out)


def _normalize(values: Sequence[str]) -> List[str]:
    return [v.strip().lower() for v in values or () if v and v.strip()]


def _match(patterns: Sequence[str], value: str) -> Optional[str]:
    """Premier motif contenu dans `value`, ou None.

    On renvoie le motif et non un booleen pour pouvoir dire a
    l'utilisateur *quelle* entree de sa blacklist a declenche le rejet.
    """
    if not value:
        return None
    low = value.lower()
    for pattern in patterns:
        if pattern in low:
            return pattern
    return None
