# API GoodPrice : ce qu'on utilise, et ce qui n'existe pas

Retro-ingenierie faite depuis le code du plugin (`../source/`) et des
captures de requetes (`../outputs/`). Rien ici n'est devine : chaque
affirmation renvoie soit a une ligne du plugin, soit a une observation
sur les snapshots.

## Acces

Base : `GET <url_serveur>/api/v1/plugins/GoodPrice/<endpoint>`
(`../source/api.js:2`).

En-tetes (`../source/api.js:1287-1302`) :

| En-tete | Valeur |
|---|---|
| `X-Auth-Token` | le "world ticket" JWT |
| `Content-Type` | `application/json` |

Le token est celui que le plugin lit dans le `localStorage` du
navigateur, cle `worldTicketData`, champ `worldTicket`. Sa charge utile
contient `exp` : **24 h de validite**. Un 401 signifie presque toujours
"token perime", d'ou le message explicite dans `client.py`.

Le plugin ajoute `credentials: 'include'`, donc les cookies de session
comptent aussi cote navigateur. En Python on se contente du token, et
ca suffit.

## Endpoints utilises

### `GET /stores` -- la source de tout

```json
{"Stores": [{
  "Name": "Holly's Mining tools",
  "Owner": "Holly",
  "Balance": 357.78,
  "CurrencyName": "Calories",
  "Enabled": true,
  "FullAccessUsers": [],
  "AllOffers": [{
    "ItemName": "Crushed Iron Ore",
    "Buying": false,
    "Price": 0.21,
    "Quantity": 3,
    "Limit": 0,
    "MaxNumWanted": 3,
    "MinDurability": -1.0,
    "Enabled": true
  }]
}]}
```

Pieges verifies sur le snapshot de reference (57 boutiques, 1323
offres) :

| Champ | Piege |
|---|---|
| `Balance` | compte **du proprietaire**, pas de la boutique : 11 joueurs ont plusieurs boutiques, toutes avec la meme valeur |
| `Balance` | peut valoir la chaine `"Infinity"` (1 cas : boutique admin) |
| `ItemName` | peut etre `null` : 73 cas, emplacements vides |
| `Price` | `999999` en vente = emplacement non configure (`../source/store.js:645`) |
| `Price` | `0` en achat = emplacement non configure (meme ligne) |
| `Quantity` | en vente : stock disponible. En achat : identique a `MaxNumWanted` (0 divergence observee) |
| `Limit` | stock cible du proprietaire, incoherent avec `Quantity` dans les deux sens (56 fois inferieur, 51 fois superieur) : **informatif seulement** |
| `Name` | contient des balises `<color=...>` (4 cas) |
| `MinDurability` | `-1` = sans objet, sinon durabilite minimale exigee sur un outil |

Devises observees : `Calories` (52 boutiques), `Barter` (3),
`"Doc" Terror Credit` (1), `Claim Credit` (1). Les boutiques `Barter`
ont un solde a 0 : le troc ne passe pas par un compte.

### `GET /players` -- **facultatif**

```json
{"Players": [{"Name": "Holly", "City": "Mt Isa", "IsOnline": true}]}
```

Le plugin l'appelle avec `.catch(() => null)`
(`../source/pricepolicy.js:61`) : il n'existe pas partout. Champs
reellement utilises par le plugin : `Name`, `City`, `IsOnline`
(`../source/pricepolicy.js:515-516`). L'app fait pareil et tolere
l'absence de l'endpoint.

### `GET /user` -- qui suis-je

```json
{"UserName": "Kiwi Cometaire", "UserId": 1078012, "IsOnline": true,
 "IsAdmin": false, "UserSkills": {"FarmingSkill": 6}}
```

Sert a une seule chose ici : identifier ses propres boutiques pour les
exclure du calcul. `UserSkills` serait la porte d'entree d'un module de
craft.

## Ce qui n'existe pas dans l'API

C'est la partie importante : ces absences expliquent des choix de
conception qui auraient l'air arbitraires sinon.

- **Aucune date de derniere connexion.** Ni dans `/players`, ni dans
  `/stores`, ni ailleurs. `IsOnline` est un booleen instantane. D'ou
  l'historique local reconstruit par `presence.py`
  (voir `activite-joueurs.md`).
- **Aucun horodatage sur les offres.** Impossible de savoir depuis
  quand un prix est affiche -- sauf en le constatant soi-meme d'un
  instantane a l'autre (empreinte de boutique).
- **Aucune position de boutique.** Pas de coordonnees, donc aucun calcul
  de trajet possible.
- **Aucun poids d'item.** `/allItems` ne renvoie que `{"Tags": [...]}`.
  La capacite de transport est donc hors modele.
- **Aucun historique de transactions.** On ne peut pas mesurer le volume
  reel d'echange d'une boutique, seulement l'offre affichee.

## Endpoints existants non utilises

Repertories pour qui voudrait etendre l'outil (liste tiree des appels
`apiFetch` du plugin) : `recipes`, `craftingTables`, `talents`,
`talentDefinitions`, `allItems`, `allTags`, `tags`, `itemImages`,
`priceAlerts`, `pricePolicy`, `priceManagers`, `rawMaterials`,
`storeManifest/<boutique>`, `stomach`, `garbagePrice`.

`recipes` est le seul dont on aurait vraiment besoin pour aller plus
loin : sa forme est `[{CraftingTable, SkillNeeds, Variants: [{Key,
Ingredients: [{Name|Tag, TagDisplayName, Ammount, IsSpecificItem,
IsStatic}], Products: [{Name, Ammount}], Garbages}]}]`
(`../source/utils.js:399-410`, `../source/calculator.js:1597-1620`).
Noter le `Ammount` avec deux `m` -- c'est bien le nom du champ cote Eco.
