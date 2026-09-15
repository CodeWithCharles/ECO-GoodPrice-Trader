"""Acces aux donnees du serveur : la seule couche qui connait HTTP.

Deux implementations derriere la meme interface `fetch(endpoint)` :

- `ApiClient`      : le vrai serveur, via /api/v1/plugins/GoodPrice.
- `OfflineClient`  : un dossier de snapshots sur disque.

Le mode offline n'est pas un gadget de test : il permet de rejouer une
analyse sans re-solliciter le serveur, et c'est ce qui rend les tests
possibles sans token. Il accepte aussi bien du JSON pur que les dumps
"requete HTTP complete" du dossier outputs/ (en-tetes puis ligne vide
puis corps), parce que c'est sous cette forme que les captures
arrivent.
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional

API_PATH = "/api/v1/plugins/GoodPrice"
DEFAULT_TIMEOUT = 20

# Nom de fichier offline accepte pour chaque endpoint (casse libre).
OFFLINE_ALIASES = {
    "stores": ("stores", "Stores"),
    "user": ("user", "User"),
    "players": ("players", "Players"),
    "tags": ("tags", "Tags"),
    "allItems": ("allitems", "allItems", "AllItems"),
}


class ApiError(RuntimeError):
    """Echec d'appel API, avec un message exploitable par l'utilisateur."""


def _strip_http_headers(raw: str) -> str:
    """Retire les en-tetes d'un dump HTTP si le fichier en contient.

    On detecte le cas par la premiere ligne (verbe HTTP) plutot que par
    la presence d'une ligne vide : un JSON indente en contient aussi.
    """
    head = raw.lstrip()[:8].upper()
    if not head.startswith(("GET ", "POST ", "PUT ", "HTTP")):
        return raw
    for separator in ("\r\n\r\n", "\n\n"):
        if separator in raw:
            return raw.split(separator, 1)[1]
    return raw


class OfflineClient:
    """Lit les snapshots depuis un dossier local."""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        if not self.directory.is_dir():
            raise ApiError(f"dossier de snapshots introuvable: "
                           f"'{self.directory}'")

    @property
    def label(self) -> str:
        return f"offline:{self.directory}"

    def _locate(self, endpoint: str) -> Optional[Path]:
        names = OFFLINE_ALIASES.get(endpoint, (endpoint,))
        for name in names:
            for candidate in (name, f"{name}.json"):
                path = self.directory / candidate
                if path.is_file():
                    return path
        return None

    def fetch(self, endpoint: str) -> Dict[str, Any]:
        path = self._locate(endpoint)
        if path is None:
            raise ApiError(
                f"snapshot '{endpoint}' absent de '{self.directory}'"
            )
        raw = path.read_text(encoding="utf-8", errors="replace")
        try:
            return json.loads(_strip_http_headers(raw))
        except json.JSONDecodeError as exc:
            raise ApiError(f"snapshot '{path.name}' illisible: {exc}") from exc


class ApiClient:
    """Client HTTP du plugin GoodPrice.

    Le token voyage en en-tete `X-Auth-Token` : c'est le "world ticket"
    que le plugin lit dans le localStorage du navigateur (api.js:1290).
    Il expire au bout de 24 h, d'ou le message explicite sur un 401.
    """

    def __init__(self, base_url: str, token: str,
                 timeout: int = DEFAULT_TIMEOUT) -> None:
        try:
            import requests
        except ImportError as exc:  # pragma: no cover - depend de l'env
            raise ApiError(
                "le module 'requests' est requis: pip install -r "
                "requirements.txt"
            ) from exc
        self._requests = requests
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "X-Auth-Token": token,
            "Content-Type": "application/json",
            "Accept": "*/*",
        })

    @property
    def label(self) -> str:
        return self.base_url

    def fetch(self, endpoint: str) -> Dict[str, Any]:
        url = f"{self.base_url}{API_PATH}/{endpoint}"
        try:
            response = self.session.get(url, timeout=self.timeout)
        except self._requests.exceptions.RequestException as exc:
            raise ApiError(f"{endpoint}: serveur injoignable ({exc})") from exc

        if response.status_code in (401, 403):
            raise ApiError(
                f"{endpoint}: token refuse (HTTP {response.status_code}). "
                "Le X-Auth-Token expire au bout de 24 h, il faut le "
                "recopier depuis le navigateur."
            )
        if response.status_code == 404:
            raise ApiError(
                f"{endpoint}: introuvable (HTTP 404). Le plugin GoodPrice "
                "est-il bien installe sur ce serveur ?"
            )
        if not response.ok:
            raise ApiError(f"{endpoint}: HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise ApiError(f"{endpoint}: reponse non JSON") from exc


def fetch_optional(client: Any, endpoint: str) -> Optional[Dict[str, Any]]:
    """Appelle un endpoint facultatif sans faire echouer le programme.

    `players` n'existe pas sur toutes les installations (le plugin
    lui-meme l'appelle avec un `.catch()`), et l'analyse doit rester
    possible sans lui.
    """
    try:
        return client.fetch(endpoint)
    except ApiError:
        return None
