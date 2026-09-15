# Le warning d'absence

## Le probleme

Vendre a une boutique dont le proprietaire a quitte le serveur
fonctionne techniquement : dans Eco, une boutique paie toute seule
depuis le compte de son proprietaire, sans que celui-ci soit connecte.

Le probleme est ailleurs :

- son compte ne se rechargera jamais -- on vide un stock d'argent mort ;
- ses prix sont figes, donc souvent faux (un prix d'achat genereux
  laisse par un joueur parti n'est pas une bonne affaire, c'est un
  vestige) ;
- les marchandises y restent inutilisees, alors qu'un joueur actif les
  consommerait et continuerait a commercer avec vous.

D'ou le warning : on n'interdit pas la route, on signale que la
contrepartie n'a pas l'air active et qu'il y a peut-etre mieux a faire.

## Pourquoi un historique local

L'API GoodPrice ne fournit **aucune** date de derniere connexion.
`/players` renvoie un `IsOnline` booleen et instantane, `/stores` n'a
pas d'horodatage, et il n'existe pas d'endpoint d'activite. Verifie
endpoint par endpoint : voir `api-goodprice.md`, section "Ce qui
n'existe pas".

L'information n'est donc pas a lire, elle est a **construire**. L'app
enregistre un instantane a chaque execution -- de n'importe lequel des
trois scripts -- dans `data/presence_<serveur>.json`. Un fichier par
serveur : deux serveurs n'ont ni les memes joueurs ni les memes
boutiques, melanger les historiques ferait passer un absent pour un
actif.

Le fichier ne garde par joueur que le dernier etat connu et les dates
cles, pas la serie complete : il reste de l'ordre du kilo-octet apres
des mois, et se lit a la main.

## Les deux signaux temporels

**`last_online`** -- derniere fois ou `/players` a renvoye `IsOnline:
true`. Precis, mais dependant d'un endpoint facultatif, et aveugle aux
connexions qui tombent entre deux executions.

**`last_change`** -- derniere fois ou l'empreinte de ses boutiques a
change. L'empreinte couvre le solde, et pour chaque offre l'item, le
sens, le prix, le stock et la quantite voulue. Elle bouge donc des qu'un
prix est ajuste, que du stock est ajoute, ou qu'une vente est encaissee
-- y compris si c'est vous qui l'avez declenchee.

Le second est le plus robuste : il fonctionne sans `/players`, et une
boutique dont rien n'a bouge en trois semaines est un signal fort, meme
si son proprietaire se connecte pour jouer sans toucher a son commerce.

## Les signaux immediats

Un historique tout neuf ne dit rien, et afficher "absent 0 j" pour tout
le monde serait du bruit qui decredibiliserait les vraies alertes. En
dessous d'un jour d'historique, on se replie donc sur ce qu'un
instantane unique permet d'affirmer :

| Signal | Ce que ca veut dire |
|---|---|
| `solde 0` | le compte est vide, la boutique ne paiera rien |
| `boutique vide` | **toutes** ses boutiques sont sans stock et sans demande |
| `offres non configurees` | la moitie au moins de ses emplacements sont restes au prix sentinelle |

Ce sont des faits, pas des extrapolations. Le cas "une boutique vide sur
trois" est volontairement **ignore** : un joueur actif garde souvent une
boutique de reserve, et le signaler generait plus de faux positifs que
d'informations.

## Les etiquettes

| Etiquette | Signification | Alerte |
|---|---|---|
| `en ligne` | connecte a l'instant | non |
| `vu il y a 2j` | vu en ligne recemment | non |
| `! absent 11j` | pas vu en ligne depuis 11 jours (seuil `absent_days`) | oui |
| `! figee 20j` | rien n'a bouge dans ses boutiques depuis 20 jours (seuil `stale_days`) | oui |
| `! solde 0` | signal immediat, faute d'historique | oui |
| `? jamais vu (10j)` | 10 jours d'historique, jamais vu en ligne | oui |
| `? inconnu` | pas assez d'historique, et aucun signal immediat | non |

Format volontairement tres court : le tableau de routes est deja large,
et l'etiquette doit juste attirer l'oeil. Le detail vit dans
`Presence.py`.

## Les seuils

Defauts : `absent_days = 7`, `stale_days = 14`.

Sept jours parce qu'en dessous on attrape les joueurs en week-end.
Quatorze pour la boutique figee parce que c'est un signal plus lent :
un joueur actif peut tres bien ne pas retoucher ses prix pendant dix
jours, mais trois semaines sans qu'aucun stock ni aucun solde ne bouge
est difficile a expliquer autrement que par un depart.

Ces valeurs sont des points de depart, pas des verites : un serveur
tres actif justifie de descendre a 3 et 7. Reglable dans `config.toml`
(section `[activity]`) ou en ligne de commande (`--absent-days`,
`--stale-days`).

## Faire murir l'historique

Rien a faire de particulier : chaque execution de `Routes.py`,
`Chains.py` ou `Presence.py` enregistre un instantane. Un usage normal
suffit. `--no-record` pour consulter sans ecrire.

Pour un rythme regulier independant de son propre usage, une tache
planifiee sur `Presence.py` fait le travail (elle n'affiche rien
d'utile au debut, mais elle date les observations) :

```bash
# crontab : un releve par jour a midi
0 12 * * * cd /chemin/vers/app && .venv/bin/python src/Presence.py \
           --json data/activite.json > /dev/null
```
