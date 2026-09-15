# Modele economique

Toutes les regles de calcul, avec leur justification. Chacune est
couverte par un test : si une regle change ici, un test doit changer
aussi.

## Vocabulaire

- **ask** : une offre ou une boutique **vend** (`Buying: false`). C'est
  la qu'on achete.
- **bid** : une offre ou une boutique **achete** (`Buying: true`). C'est
  la qu'on revend.
- **leg** : un aller-retour sur un item -- acheter chez A, revendre chez
  B. L'unite atomique de tout le reste.
- **wallet** : `(proprietaire, devise)`. L'unite de budget cote
  acheteur.
- **chaine** : une suite ordonnee de legs, ou la revente de l'un
  finance l'achat du suivant.

## Ce qui est echangeable

Un ask est exploitable si : `Buying == false`, `Enabled`,
`Quantity > 0`, et `0 < Price < 999999`.

Un bid est exploitable si : `Buying == true`, `Enabled`,
`MaxNumWanted > 0`, `Price > 0`, **et le wallet du proprietaire n'est
pas a zero**.

Les bornes de prix ne sont pas de la coquetterie : le plugin ecrit
`Price: isBuying ? 0 : 999999` quand on cree un emplacement d'offre
vide (`../source/store.js:645`). Une "offre" a 999999 est donc un
formulaire jamais rempli, pas un prix.

## Pourquoi dérouler le carnet, et pas comparer les extremes

L'approche naive prend le `min(prix de vente)` et le `max(prix
d'achat)` et s'arrete la. Elle rate tout le reste du carnet.

Exemple : Alice vend 100 bois a 1.00. Bob en achete 60 a 1.50, Carol en
achete 100 a 1.20.

- Naif : 1 route, 60 unites, profit 30.00. Les 40 bois restants sont
  ignores.
- Reel : Bob prend 60 (profit 30.00), Carol prend les 40 restants
  (profit 8.00). **Profit total 38.00.**

`routes.match_item` avance donc dans les deux carnets tant que le
prochain acheteur paie plus cher que le prochain vendeur ne demande.
Comme les deux listes sont triees, la premiere paire non rentable est
aussi la derniere : on peut s'arreter la.

Effet mesure sur le snapshot de reference, a perimetre egal (memes
filtres, memes exclusions, seule la strategie d'appariement change) :

| Approche | Routes | Profit |
|---|---|---|
| Naive, telle que le vieux script la faisait | 50 | 218.46 |
| Naive, boutiques du joueur exclues | 49 | 252.21 |
| Carnet deroule | 59 | 274.21 |

L'ecart d'appariement pur est donc **+8.7 %** (252.21 -> 274.21). Les
25.02 restants ne sont pas un gain d'algorithme mais une erreur retiree
— du profit qui n'existait pas (voir plus bas).

## Le solde des acheteurs est partage par joueur

Observation sur les vraies donnees : Tec possede trois boutiques, toutes
avec `Balance: 550.20`. Askardius deux, toutes a `573.96`. Onze joueurs
sont dans ce cas. `Balance` est donc le compte du **proprietaire**.

Consequence : un joueur dont deux boutiques veulent acheter pour 20
chacune alors qu'il a 10 en banque ne paiera 10, pas 40. Le budget se
suit par `wallet = (owner, currency)`, et il est decremente au fil du
plan.

On agrege par `max` et non par somme : deux boutiques renvoyant la meme
valeur, sommer reviendrait a doubler le compte.

## Les comptes a zero sortent du carnet

Cas reel rencontre en test : Frank affiche un prix d'achat de 5.00 sur
la pierre mais a 0 en banque. S'il reste dans le carnet, il rafle les 20
unites du vendeur au premier tour d'appariement... puis se fait retirer
au moment du plafonnement par solde. Resultat : zero route, alors
qu'Eve, qui paie 1.00 et peut payer, etait disponible.

Un bid insolvable n'est pas un bid. Il est donc ecarte a la
construction du carnet (`market.build_market`, `skip_broke_bids`), pas
apres.

## Ses propres boutiques sont exclues

Acheter dans sa propre boutique et revendre dans sa propre boutique ne
cree aucun profit : l'argent change de poche. Sur le snapshot de
reference, la version naive annoncait 25.02 de profit sur la farine...
achetee dans la boutique du joueur lui-meme.

L'identification se fait sur `Owner == UserName` **ou** `UserName` dans
`FullAccessUsers` (une boutique co-geree est aussi la sienne). La
comparaison est **exacte**, contrairement aux blacklists : un pseudo est
une identite, et un motif partiel "Tec" ecarterait "Tecumseh".

`--include-own` pour les reintegrer.

## Le meme joueur des deux cotes

Different du cas precedent : acheter 0.10 chez Merle et revendre 0.18 a
une autre boutique de Merle **est** un profit reel pour nous (et une
perte pour lui). C'est garde par defaut mais signale
(`meme joueur des deux cotes`), et `--no-same-owner` l'ecarte pour qui
prefere ne pas exploiter une erreur de prix.

## L'ordre d'execution : glouton iteratif

Le capital se recycle -- on revend juste apres avoir achete, donc chaque
leg rembourse sa mise plus le profit. La question est l'ordre.

Un tri fige ne marche pas, parce que la faisabilite depend de la
tresorerie du moment. Avec 25 calories :

- tri par ROI : enchaine des legs a 0.10 de mise et 900 % de ROI. Six
  etapes plus tard, on a gagne 4.32.
- glouton iteratif : choisit a chaque etape le **meilleur coup jouable
  maintenant**. Etape 1, la betterave (200 unites, 20 de mise, +20 de
  profit) est abordable. Six etapes plus tard : **+108.28**.

A chaque tour on recalcule donc, pour chaque leg restant, la quantite
reellement finançable (bornee par la tresorerie et par le solde de
l'acheteur), et on retient le meilleur score. Un leg trop gros
aujourd'hui reste candidat : il redeviendra jouable quand la caisse
aura grossi.

Un leg execute partiellement **retourne dans la file avec son
reliquat**. C'est ce qui permet d'acheter 300 farines en deux passages
de 150 quand la bourse ne suit pas au premier tour. Sur le snapshot de
reference, 25 calories de depart suffisent a extraire les 274.21 de
profit total du serveur, en 60 etapes.

Ce n'est pas un optimum exact -- le probleme est un sac a dos ordonne
avec budgets partages, donc NP-difficile. Mais le choix "meilleur coup
jouable maintenant" est celui qu'un joueur fait de toute facon, il est
deterministe, et chaque etape est verifiable a la main.

`Routes.py` trie par profit (c'est un classement a lire), `Chains.py`
par le meme glouton (c'est un plan a executer).

## Les boucles de change

A devise constante, l'argent est fongible : enchainer deux legs n'a pas
d'autre effet que de recycler la caisse, ce que le planner fait deja. La
seule chaine **structurelle** vient du multi-devises.

Un item achete en calories et revendu a une boutique qui paie en credits
definit un taux de change implicite :

    taux(A -> B) = prix_de_vente_en_B / prix_d_achat_en_A

Pour chaque couple de devises, on garde l'item au meilleur taux, puis on
cherche les boucles dont le produit des taux depasse 1 : elles rendent
plus de devise de depart qu'elles n'en consomment. Les boucles de
longueur 1 sont exclues -- ce serait de l'arbitrage simple, deja traite.

Recherche exhaustive sur les cycles de longueur 2 a 4. Avec une poignee
de devises par serveur c'est instantane, et bien plus lisible qu'un
Bellman-Ford sur `-log(taux)`.

Sur le serveur de reference, aucune boucle : 52 boutiques sur 57 sont en
calories et les trois boutiques `Barter` ont un solde nul. C'est le
resultat normal d'un serveur mono-devise, et l'app le dit explicitement
plutot que d'afficher un tableau vide.

## Ce qui est hors modele

- **`Limit`.** Sur les vraies donnees il est incoherent avec `Quantity`
  dans les deux sens (56 fois inferieur, 51 fois superieur) : c'est le
  stock cible du proprietaire, pas une contrainte d'echange. Le plugin
  lui-meme ne fait que l'afficher (`../source/store.js:130`).
- **`MinDurability`.** Lu et conserve, jamais applique. Il ne concerne
  que les outils, et un outil achete en boutique est generalement neuf.
- **Distance et poids.** L'API ne donne ni position de boutique ni poids
  d'item. Un leg de 999 unites demande plusieurs allers-retours que le
  plan ne compte pas.
- **Volume d'echange reel.** Aucun historique de transactions dans
  l'API : on ne voit que l'offre affichee, pas ce qui s'echange
  vraiment.

## Craft : pourquoi c'est absent, et ou le brancher

Acheter des ingredients, fabriquer, revendre le produit est une vraie
chaine rentable -- et la plus rentable dans Eco. Elle n'est pas dans ce
POC, volontairement.

Le cout d'un craft depend de : la recette choisie parmi les variantes,
le niveau de competence, les talents de reduction de ressources, les
modules de l'atelier (`BasicModule` 10 %, `AdvancedModule` 10 %,
`ModernModule` 15 %), le labor, les produits secondaires et les
dechets. Le plugin y consacre ~170 ko de JavaScript
(`../source/calculator.js`). Un modele a moitie juste donnerait des
profits faux, ce qui est pire que pas de fonctionnalite.

Pour l'ajouter proprement :

1. `client.fetch("recipes")` -- forme documentee dans
   `api-goodprice.md`, attention au champ `Ammount` (deux `m`).
2. `client.fetch("user")["UserSkills"]` donne les niveaux, deja
   recupere par `cli.bootstrap()`.
3. Nouveau module `ecotrade/craft.py`, qui n'importe que `models.py` :
   il produit des `Leg` synthetiques (achat = somme des ingredients au
   meilleur ask, vente = meilleur bid du produit) et le planner les
   ordonne sans rien savoir de leur origine.
4. Commencer par les recettes sans talent ni module (facteur 1), et
   afficher le cout du labor separement plutot que de l'estimer.
