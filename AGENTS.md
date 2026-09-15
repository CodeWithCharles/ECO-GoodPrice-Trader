# AGENTS.md

Guide pour les agents de code travaillant sur ce depot (`ecotrade` :
recherche de routes de trading sur un serveur Eco, via l'API du plugin
GoodPrice).

## Commandes

Activer le venv d'abord, ou prefixer par `.venv/bin/`.

```bash
source .venv/bin/activate        # Windows : .venv\Scripts\activate
pip install -r requirements.txt
```

- Norme (doit passer, 79 colonnes, `.venv` et `data` exclus via
  `.flake8`) :
  ```bash
  flake8 .
  ```
- Tests (stdlib `unittest`, aucun acces reseau) :
  ```bash
  cd src && PYTHONPATH=.:../tests python -m unittest \
      discover -s ../tests -t ../tests
  ```
- Lancer un script (**toujours depuis la racine du depot**) :
  ```bash
  python src/Routes.py --offline ../outputs
  python src/Chains.py --capital 40
  python src/Presence.py --alerts-only
  ```

**Ne jamais commiter de token.** `config.toml` et `data/` sont
gitignore. Ne pas ecrire de token dans un test, un fixture, un exemple
de doc ou un message de commit -- utiliser `ECO_AUTH_TOKEN`.

**Ne pas appeler le serveur depuis les tests.** Toute la suite passe par
`OfflineClient` ou par des payloads construits a la main dans
`tests/fixtures.py`. Un test qui a besoin de donnees realistes ajoute un
fixture, il n'ajoute pas un appel reseau.

## Architecture

Scripts CLI fins dans `src/*.py`, logique partagee dans `src/ecotrade/`.
La separation est une regle, pas une preference : un moteur qui
importerait `client.py` ne serait plus testable sans serveur.

```
src/
├── Routes.py     argparse -> routes + planner -> render
├── Chains.py     argparse -> planner + chains  -> render
├── Presence.py   argparse -> presence          -> render
└── ecotrade/
    ├── models.py      dataclasses du domaine. Tout calcul derive
    │                  (profit, roi, cost) vit ICI, en propriete, pas
    │                  dans l'affichage.
    ├── client.py      la SEULE couche qui connait HTTP. ApiClient et
    │                  OfflineClient partagent `fetch(endpoint)`.
    ├── market.py      la SEULE couche qui connait la forme des dicts
    │                  JSON d'Eco. Nettoie, filtre, indexe.
    ├── blacklist.py   filtres joueurs / boutiques / items.
    ├── routes.py      arbitrage direct par appariement du carnet.
    ├── planner.py     ordre d'execution sous contrainte de capital.
    ├── chains.py      boucles de change multi-devises.
    ├── presence.py    historique d'activite + etiquettes de warning.
    ├── render.py      la SEULE couche qui met en forme (console, HTML).
    ├── config.py      CLI > env > config.toml > defaut.
    └── cli.py         options communes + `bootstrap()`.
```

Regle de dependance : `cli.py` et `render.py` peuvent tout importer ;
les moteurs (`routes`, `planner`, `chains`, `presence`) n'importent que
`models.py` et `blacklist.py`. Personne n'importe `client.py` sauf
`cli.py`.

Pourquoi les scripts sont sous `src/` et importent `from ecotrade.x
import ...` et non `from src.ecotrade...` : Python met le dossier *du
script* sur `sys.path[0]`, pas le cwd. `python src/Routes.py` place donc
`src/` sur le path, ce qui fait de `ecotrade` un package importable sans
installation ni manipulation de `sys.path`.

## Modele de donnees Eco (pieges verifies sur snapshots reels)

Ces regles viennent de la lecture du code du plugin (`../source/`) et de
l'observation de `../outputs/stores` (57 boutiques). Les changer sans
preuve casse la justesse des chiffres.

- `Balance` est le compte **du proprietaire**, pas de la boutique. Trois
  boutiques d'un meme joueur renvoient la meme valeur. D'ou la cle
  `wallet = (owner, currency)` dans `models.Store`.
- `Balance` peut valoir la chaine `"Infinity"` (boutiques admin).
- Offre de **vente** (`Buying: false`) : `Quantity` = stock disponible.
  `Price == 999999` est un emplacement jamais configure
  (`../source/store.js:645`), pas une offre.
- Offre d'**achat** (`Buying: true`) : `MaxNumWanted` = ce qu'il reste a
  acheter. `Price == 0` est un emplacement non configure.
- `Limit` est le stock cible du proprietaire, **pas** une contrainte
  d'echange : il est incoherent avec `Quantity` dans les deux sens sur
  les vraies donnees. Traite comme informatif.
- `ItemName` peut etre `null` (emplacement vide) : 73 cas sur 1323.
- Les noms de boutique contiennent des balises `<color=...>`.
- `/players` est **facultatif** (le plugin l'appelle avec un `.catch()`)
  et ne fournit que `Name`, `City`, `IsOnline`. **Aucune date de
  derniere connexion n'existe dans l'API** -- c'est pour ca que
  `presence.py` la reconstruit par observation.

## Points de vigilance

- **Le planner doit rester deterministe.** Deux executions sur les memes
  donnees donnent le meme plan : le tri initial de `remaining` est
  total, et la selection se fait sur un score compare strictement. Tout
  ajout de critere doit conserver cette propriete (un test le verifie).
- **Ne pas remettre de borne de stock dans le planner.**
  `routes.match_item` a deja reparti chaque offre entre ses legs ; en
  rajouter une plafonnerait a tort les executions partielles.
- **Un leg partiellement execute retourne dans la file** avec son
  reliquat. Sans ca, un gros lot inabordable au premier tour serait
  perdu au lieu d'etre termine plus tard.
- **Les etiquettes d'activite passent par `Context.activity_label()`**,
  pas par `warning_for()` directement : c'est ce qui garantit que les
  trois scripts appliquent les memes seuils et le meme repli.
- **`render.py` ne calcule rien.** Si un chiffre manque a l'affichage,
  il s'ajoute dans `models.py` ou dans `planner.summarize()`.

## Documentation

- `docs/api-goodprice.md` -- endpoints, champs, ce qui n'existe pas.
- `docs/modele-economique.md` -- toutes les regles de calcul, et ou
  brancher le craft si on l'ajoute un jour.
- `docs/activite-joueurs.md` -- pourquoi un historique local, comment
  les seuils sont choisis.
- `.ai/decisions.md` -- journal append-only des decisions.
- `.ai/state.md` -- ou en est le projet.

Mettre a jour `.ai/decisions.md` quand une decision structurante change,
plutot que de reecrire l'historique.
