# Euro 2028 — prize split & scoring rebalance proposal

**Status:** proposal for discussion with the promoters. Nothing here is
implemented; WC26 rules are untouched.
**Date:** 2026-07-20
**Basis:** every claim below was simulated against the real, final WC26
production data (183 entries) — not estimated. Simulation method in the
appendix.

---

## 1. Why change anything

WC26 feedback: "winner takes all" leaves engagement thin in the
knockout weeks for anyone outside the top handful. WC26 paid exactly
two entries (overall winner ~65%, group-stage leader ~20%, charity
15%). Two goals for Euro 2028:

1. **More entries walk away having won something** — without making any
   single prize meaningless.
2. **Engagement stays high to the last kick** — the pool winner should
   ideally be decided BY the final, and should ideally have picked the
   actual champion.

---

## 2. Proposed prize split

Nine prizes, 100% of the pot. Euro-amounts shown against the WC26 pot
(€915) for scale; the shares are what's proposed.

| Prize | Share | ~€ @ 915 | WC26 winner (simulated) |
|---|---|---|---|
| 1st overall | 30% | €275 | Matthew Ellul — Entry 1 |
| 2nd | 13% | €119 | James Vella — 2nd Entry |
| 3rd | 10% | €92 | Dean Bonello — Entry 1 |
| 4th | 7% | €64 | Carlo Brincau |
| 5th | 5% | €46 | Jonathan Schembri — Entry A |
| Group-stage leader | 10% | €92 | James Vella — 3rd Entry |
| **Sniper** — most exact scores | 5% | €46 | John Sammut *(via cascade)* |
| **Knockout King** — best combined knockout points | 5% | €46 | Edward Camilleri *(via cascade)* |
| Charity | 15% | €137 | Soup Kitchen |

Nine distinct winning entries on WC26 data, versus two under the
current rules. The floor for winning anything (€46) is ~9× a €5 entry.

### 2.1 One prize per entry (the cascade rule)

An entry can win **at most one** prize. If an entry tops a side-prize
metric but already holds a higher prize, the side prize cascades to the
next eligible entry. Prize precedence: overall ladder (1st–5th) →
group-stage leader → Sniper → Knockout King.

This is the rule that spreads the money. On WC26 data it worked twice:

- **Knockout King:** best KO totals belonged to Matthew (1st overall —
  skipped) and Carlo (4th — skipped), so it cascades to **Edward
  Camilleri at #7** — an excellent knockout bracket that would
  otherwise have won nothing.
- **Sniper:** most exacts was Jonathan Schembri (5th — skipped), then a
  13-exact tie between John Sammut and an entry already holding the
  group-stage prize — resolving cleanly to **John Sammut at #39**.

Eligibility is per **entry**, not per person — consistent with the
WC26 Trionda ruling (confirmed 2026-07-20): one person's second entry
can win a prize even if their first entry already holds one.

### 2.2 Ties (simulated)

**Rule: tied entries at a prize boundary split the combined money of
the positions they span.** (Two entries tied for 2nd split
2nd + 3rd = 23% → 11.5% each; the next entry is 4th.) For the
single-winner side prizes (Sniper / Knockout King / group-stage
leader), tied entries split that prize equally.

What the WC26 data says about how often this fires:

- The **final top 10 had zero ties** — every prize position resolved
  cleanly this year.
- Pool-wide, 58 of 183 entries shared a total with at least one other
  entry, so boundary ties WILL eventually happen — the split rule is
  cheap insurance, not a dead letter.
- Under the rebalanced scoring below, one simulated variant produced a
  2-way tie at 3rd/4th — the split rule handled it without judgement
  calls: both take (10% + 7%) / 2 = 8.5%.

Why split rather than tie-break: money should follow the scoreboard.
Tie-breaks (group-stage points, then lots) stay reserved for prizes
that are physically indivisible — per the Trionda convention.

---

## 3. Scoring rebalance

### 3.1 The problem, measured

On final WC26 data, points came **19% from the group stage and 81%
from the knockouts** (the champion's own split: 16/84). Worse, the
knockout weight is front-loaded: the Round of 32 alone offers 640
points — a third of all knockout points — and it's the least skilled
round (21 entries tied its maximum; 28/32 correct was routine). The
table effectively froze early, and the Final was worth only 100.

That the WC26 pool WAS decided by the Final (19 entries alive, Matthew
jumped 4th → 1st on the Spain pick) was genuinely lucky: the top four
happened to sit within 100 points. The target is to make that the
designed outcome, not a coincidence.

**Targets:** ~30% group / ~70% knockout; the Final decides the pool;
the pool winner should (almost) have to pick the actual champion.

### 3.2 Proposed values

| | WC26 | Euro 2028 proposed |
|---|---|---|
| Group match — correct outcome | 5 | **15** |
| Group match — exact score | 10 | **30** |
| First KO round team (R32 → last-16 for a Euro) | 20 | **20** |
| Next round (R16 → QF) | 30 | **40** |
| Quarter-finalist → semi-finalist equivalent | 40 | **80** |
| Semi-finalist → finalist equivalent | 50 | **120** |
| Finalist | 75 | **160** |
| Champion | 100 | **300** |

Three moves:

1. **Group ×3** — lifts group play to ~31% of realized points. The
   five group-stage weeks matter again, and the Sniper prize gains
   teeth.
2. **Back-loaded knockout curve** — first-round weight roughly halves
   in relative terms; the semis and final steepen. The table keeps
   reshuffling in the last two weeks instead of freezing after the
   first knockout round.
3. **Champion credit 100 → 300** — deliberately larger than realistic
   pre-final gaps. This single lever produces both remaining goals.

Rarity bonus and bonus-question values: unchanged (they're small
enough not to move the shares; simulated as-is).

### 3.3 Simulated on real WC26 data

Re-scoring all 183 real entries under the proposed values:

| Metric | WC26 actual | Proposed scheme |
|---|---|---|
| Group / KO share | 19% / 81% | **31% / 69%** |
| Entries mathematically alive for #1 entering the Final | 19 | **30** |
| Pool winner picked the world champion | yes (luckily) | **yes — the entire new top 5 had picked Spain** |
| Ties in the top 5 | 0 | **0** |
| Podium | Matthew, James, Dean | **Matthew, James, Dean** (unchanged) |

The last row matters for fairness optics: the rebalance doesn't
retroactively crown different people — the same skill still wins — it
changes *when* the race is decided and *what kind* of skill each phase
rewards.

---

## 4. Caveats

- **n = 1.** Everything is calibrated on one tournament. The shape
  (group ×3, back-loaded KO, oversized champion credit) transfers; the
  exact integers should be re-derived for the Euro 2028 format (24
  teams, last-16 as the first KO round, ~51 matches vs 104 — fewer
  group matches means the group multiplier may need to go higher than
  ×3 to hold 30%).
- **"Alive at the Final" counts mathematical overtakes**, not likely
  ones. 30 alive ≈ top sixth of the pool with a real reason to watch.
- **Winner's prize drops from ~65% to 30%** of the pot. That is the
  consciously accepted price of nine winners. If it feels flat at the
  top later, the agreed one-line fix: trim group-stage leader to 8%
  and each side prize to 4%, pushing 1st to 34%.
- All four prize metrics were tie-tested on real data. The one metric
  that FAILED simulation — "best points per KO round" — is explicitly
  excluded: rounds produced 21/7/2/27/32/50-way ties at the max,
  because round points are (correct teams) × (fixed value) with only
  ~10–30 possible scores per round. Any per-round prize is a raffle.

---

## Appendix — simulation method

All numbers computed 2026-07-20 against the live production database
(183 eligible entries, final post-tournament state), via the same
scoring breakdown the leaderboard serves (`calculate_leaderboard`,
per-stage advancement points, `exact_scores`, bonus splits). The
rebalance simulation recomputed each entry's total as:

```
new_total = 3 × (outcome_pts + exact_pts)          # group base ×3
          + rarity_pts + group_bonus + ko_bonus     # unchanged
          + Σ per-stage: (stage_pts / old_value) × new_value
```

"Alive at the Final" = entries whose pre-final total (total minus any
champion credit) plus the champion credit would reach the pre-final
leader. Tie counts are exact-total collisions on the final board.
