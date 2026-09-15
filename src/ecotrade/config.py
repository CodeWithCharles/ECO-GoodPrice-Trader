"""Chargement de la configuration.

Ordre de priorite, du plus fort au plus faible :

    argument CLI  >  variable d'environnement  >  config.toml  >  defaut

Le token est traite a part : il ne doit pas finir dans un depot Git.
On le cherche donc d'abord dans `--token`, puis dans `ECO_AUTH_TOKEN`,
puis dans config.toml (qui est gitignore), et en dernier recours on le
demande en saisie masquee. Il n'est jamais reecrit sur disque par
l'app, et jamais affiche.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

ENV_TOKEN = "ECO_AUTH_TOKEN"
ENV_URL = "ECO_SERVER_URL"

DEFAULTS: Dict[str, Any] = {
    "currency": None,          # None = devise la plus repandue
    "capital": 0.0,            # 0 = illimite
    "min_profit": 0.0,
    "top": 25,
    "absent_days": 7.0,
    "stale_days": 14.0,
}


class ConfigError(RuntimeError):
    """Configuration inutilisable, avec un message pour l'utilisateur."""


def _load_toml(path: Path) -> Dict[str, Any]:
    try:
        import tomllib as toml_reader
    except ImportError:  # Python < 3.11
        try:
            import tomli as toml_reader  # type: ignore
        except ImportError as exc:
            raise ConfigError(
                "lecture de config.toml impossible sur ce Python: "
                "installez 'tomli' (pip install -r requirements.txt) "
                "ou passez a Python 3.11+"
            ) from exc
    try:
        with path.open("rb") as handle:
            return toml_reader.load(handle)
    except OSError as exc:
        raise ConfigError(f"config illisible: {exc}") from exc
    except Exception as exc:  # erreur de syntaxe TOML
        raise ConfigError(f"config.toml invalide: {exc}") from exc


@dataclass
class Config:
    """Configuration effective d'une execution."""

    url: Optional[str] = None
    token: Optional[str] = None
    offline: Optional[Path] = None
    data_dir: Path = Path("data")

    currency: Optional[str] = None
    capital: float = 0.0
    min_profit: float = 0.0
    top: int = 25

    absent_days: float = DEFAULTS["absent_days"]
    stale_days: float = DEFAULTS["stale_days"]

    players: List[str] = field(default_factory=list)
    stores: List[str] = field(default_factory=list)
    items: List[str] = field(default_factory=list)
    include_own: bool = False

    @property
    def server_key(self) -> str:
        """Identifiant de serveur, pour ne pas melanger les historiques.

        Deux serveurs differents n'ont ni les memes joueurs ni les
        memes boutiques : leurs fichiers de presence doivent etre
        separes, sinon un joueur absent ici passerait pour actif la-bas.
        """
        source = str(self.offline) if self.offline else (self.url or "local")
        safe = "".join(c if c.isalnum() else "_" for c in source)
        return safe.strip("_").lower() or "local"

    @property
    def presence_path(self) -> Path:
        return self.data_dir / f"presence_{self.server_key}.json"


def load(args: Any) -> Config:
    """Fabrique la config a partir des arguments CLI et du fichier.

    `args` est le Namespace d'argparse produit par cli.base_parser().
    """
    path = Path(getattr(args, "config", None) or "config.toml")
    raw: Dict[str, Any] = _load_toml(path) if path.is_file() else {}

    server = raw.get("server") or {}
    trading = raw.get("trading") or {}
    activity = raw.get("activity") or {}
    blacklist = raw.get("blacklist") or {}

    offline = getattr(args, "offline", None)
    config = Config(
        url=(
            getattr(args, "url", None)
            or os.environ.get(ENV_URL)
            or server.get("url")
        ),
        token=(
            getattr(args, "token", None)
            or os.environ.get(ENV_TOKEN)
            or server.get("token")
        ),
        offline=Path(offline) if offline else None,
        data_dir=Path(getattr(args, "data_dir", None) or "data"),
        currency=(
            getattr(args, "currency", None)
            or trading.get("currency")
            or DEFAULTS["currency"]
        ),
        capital=_number(
            getattr(args, "capital", None),
            trading.get("capital"),
            DEFAULTS["capital"],
        ),
        min_profit=_number(
            getattr(args, "min_profit", None),
            trading.get("min_profit"),
            DEFAULTS["min_profit"],
        ),
        top=int(_number(
            getattr(args, "top", None), trading.get("top"), DEFAULTS["top"]
        )),
        absent_days=_number(
            getattr(args, "absent_days", None),
            activity.get("absent_days"),
            DEFAULTS["absent_days"],
        ),
        stale_days=_number(
            getattr(args, "stale_days", None),
            activity.get("stale_days"),
            DEFAULTS["stale_days"],
        ),
        players=_strings(blacklist.get("players")),
        stores=_strings(blacklist.get("stores")),
        items=_strings(blacklist.get("items")),
        include_own=bool(getattr(args, "include_own", False)),
    )

    # Les exclusions passees en CLI s'ajoutent au fichier, elles ne le
    # remplacent pas : le fichier est la liste durable, le CLI le
    # coup de pouce du moment.
    config.players += _strings(getattr(args, "block_player", None))
    config.stores += _strings(getattr(args, "block_store", None))
    config.items += _strings(getattr(args, "block_item", None))

    if config.offline is None and not config.url:
        raise ConfigError(
            "aucune source de donnees: donnez --url (ou ECO_SERVER_URL, "
            "ou [server].url dans config.toml), ou bien --offline DOSSIER"
        )
    return config


def resolve_token(config: Config, interactive: bool = True) -> str:
    """Renvoie le token, en le demandant en saisie masquee si besoin."""
    if config.token:
        return config.token
    if not interactive:
        raise ConfigError(
            f"token absent: passez --token, ou exportez {ENV_TOKEN}"
        )
    import getpass
    try:
        token = getpass.getpass("X-Auth-Token (saisie masquee): ").strip()
    except (EOFError, KeyboardInterrupt):
        raise ConfigError("saisie du token interrompue")
    if not token:
        raise ConfigError("token vide")
    config.token = token
    return token


def _number(*candidates: Any) -> float:
    for value in candidates:
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def _strings(value: Any) -> List[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    return [str(v) for v in value]
