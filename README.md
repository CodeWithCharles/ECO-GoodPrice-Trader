# ecotrade

Finds profitable trade routes and trade chains on an [Eco](https://play.eco)
server, by reading the API of the **GoodPrice** plugin installed on the
server.

Three tools, one shared core:

| Script | Answers |
|---|---|
| `src/Routes.py` | What is profitable right now? |
| `src/Chains.py` | In what order do I run it with *my* purse? |
| `src/Presence.py` | Who is still active on the server? |

## Installation

Python 3.9+ (3.11+ recommended: `tomllib` is in the stdlib from there on).

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp config.example.toml config.toml   # then fill in url + token
```

`config.toml` is gitignored: it is the only place a token is allowed to
live. Otherwise: `export ECO_AUTH_TOKEN=...`, or nothing at all and the
app asks for it with hidden input.

**Where to find the X-Auth-Token**: in game, open the GoodPrice plugin,
then browser dev tools → Application → Local Storage → key
`worldTicketData`, field `worldTicket`. It expires after 24 h.

## Usage

Always from the repository root (imports rely on `src/` being
`sys.path[0]`, see AGENTS.md).

```bash
# What is profitable, biggest profit first
python src/Routes.py

# Same thing, but playable with 40 calories in your pocket
python src/Chains.py --capital 40

# Who has been gone for a long time
python src/Presence.py --alerts-only

# Without touching the server: replay snapshots
python src/Routes.py --offline ../outputs

# Exports
python src/Routes.py --json routes.json --html report.html
```

```
Profitable routes - Calories
============================
  currency          : Calories
  steps             : 36 (4788 units)
  total purchases   : 583.07  (largest single outlay: 148.12)
  profit            : +262.29  (45% of the capital committed)

Item          Qty  Buy from                       Price  Sell to                        Price  Profit  ROI   Seller activity
------------  ---  -----------------------------  -----  -----------------------------  -----  ------  ----  ------------------
Flour         300  Merle's Store (Merle)           0.30  Penguish Delights (Kowalski)    0.47   51.00   57%  online
Beet          200  GingyGinger's Store             0.10  Lettuce Eat (SG1CSIfan)         0.20   20.00  100%  ! away 11d
Limestone     999  vokial95's Store                0.03  The glass pitt (Pittsy)         0.05   19.98   67%  seen 2d ago
```

*(the "Seller activity" column above is what you get after a few days of
history; on the first run it shows `? unknown` — see below.)*

`python src/<Script>.py -h` for every option.

## What the tool takes into account

The constraints below are the reason this project exists: a plain
`min(sell price)` against `max(buy price)` announces profits that do not
exist.

- **The whole order book**, not just the best pair. If three stores buy
  the same item for more than a fourth one sells it, all three get
  served, until the stock runs out.
- **Buyer balances are shared per player**, not per store: the API
  returns the owner's account, so their three stores all draw from the
  same pocket.
- **Accounts at zero are dropped from the book.** A penniless store
  advertising a generous buy price would otherwise soak up the seller's
  stock inside the computation, hiding the real best buyer.
- **Your own stores are excluded** on both sides: buying from yourself
  does not create profit (`--include-own` to bring them back).
- **Cash is recycled**: `Chains.py` orders the operations so that each
  resale funds the next purchase, and splits a big lot into several
  passes when the purse cannot keep up.
- **API noise is filtered out**: empty offer slots (`ItemName` set to
  null), the `999999` sentinel price, disabled offers, zero stock,
  `<color=...>` tags in names, the `"Infinity"` balance of admin stores.

On the reference snapshot (57 stores, 1323 offers):

| Approach | Routes | Profit |
|---|---|---|
| Naive: best seller against best buyer | 50 | 218.46 |
| … of which fake profit coming from the player's own stores | | −25.02 |
| Naive, corrected (player's own stores excluded) | 49 | 252.21 |
| **ecotrade (order book unrolled)** | **59** | **274.21** |

That is **+8.7 %** against a naive version already cleaned of its fake
profits — and above all numbers you can count on, where the 218.46
announced at the start contained 25.02 of money that does not exist.

## The inactivity warning

The Eco API provides **no** last-login date: `/players` only gives an
instantaneous boolean and `/stores` has no timestamp. So the app rebuilds
the information by recording a snapshot on every run
(`data/presence_<server>.json`, gitignored).

- First run: `? unknown`, or an immediate signal when there is one
  (`! balance 0`, `! empty store`).
- After a few days: `! away 11d` (never seen online for 11 days) or
  `! stale 20d` (no change in price, stock or balance for 20 days).

An Eco store pays by itself, so selling to an absent player technically
*works*. The problem is elsewhere: their account will never be topped up
again, and their frozen prices are often wrong. Better to feed someone
who will keep trading. Thresholds are configurable (`absent_days`,
`stale_days`).

Details and rationale: `docs/activite-joueurs.md`.

## Blacklists

Three independent lists in `config.toml` (`players`, `stores`, `items`),
or on the command line:

```bash
python src/Routes.py --block-player "Spammer" --block-store "Dump" \
                     --block-item "Garbage"
```

Matching is **partial and case-insensitive**: `dump` is enough to rule
out `<color=grey>Twitch's Dumping Grounds</color>`. CLI exclusions add to
the ones from the file.

## Development

```bash
flake8 .                                              # lint, must pass
cd src && PYTHONPATH=.:../tests python -m unittest \
    discover -s ../tests -t ../tests                  # 104 tests
```

Architecture, dependency rules and known pitfalls: `AGENTS.md`.
Economic model: `docs/modele-economique.md`. API reverse engineering:
`docs/api-goodprice.md`.

## Known limitations

- **Crafting is not covered.** Buying ingredients, crafting and reselling
  is a genuinely profitable chain, but its cost depends on talents,
  workshop upgrade modules and labor: the plugin spends ~170 kB of JS on
  it. Doing it halfway would give wrong numbers.
  `docs/modele-economique.md` §Craft says where to plug that in properly.
- **No distance, no weight.** The API gives neither store coordinates nor
  item weight: the plan ignores travel time and carrying capacity. Routes
  of 999 units take several round trips.
- **Prices move.** A plan is a photograph. Regenerate it before going in
  game.
- **`MinDurability`** is read but not used: a tool buy offer requiring
  50 % durability is treated like any other.