"""ecotrade -- recherche de routes et de chaines de trading sur Eco.

Le package est decoupe par responsabilite, une seule par module :

    client.py     acces aux donnees (HTTP ou snapshots locaux)
    market.py     JSON brut -> carnet d'ordres propre
    blacklist.py  filtrage joueurs / boutiques / items
    routes.py     arbitrage direct, par appariement du carnet
    planner.py    mise en ordre sous contrainte de capital
    chains.py     boucles de change multi-devises
    presence.py   historique d'activite et warnings d'absence
    render.py     affichage console et rapport HTML
    config.py     configuration (CLI > env > config.toml)
    cli.py        options communes et bootstrap des scripts

Regle de dependance : render.py et cli.py peuvent tout importer, les
moteurs n'importent que models.py (et blacklist.py). Personne
n'importe client.py a part cli.py -- c'est ce qui permet de tester les
moteurs sans serveur ni token.
"""

__version__ = "0.1.0"
