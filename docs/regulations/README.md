# FIFA World Cup 2026 — Official Regulations

Authoritative reference for the tournament rules this app implements (group
ranking, third-place qualification, knockout bracket seeding, scoring windows).

| Item | Value |
|------|-------|
| Edition | *Regulations for the FIFA World Cup 26™* — May 2026 |
| Source PDF (canonical) | https://digitalhub.fifa.com/m/636f5c9c6f29771f/original/FWC2026_regulations_EN.pdf |
| Retrieved | 2026-05-27 |

## Files

- **`FWC2026_regulations_EN.pdf`** — the official PDF, verbatim (immutable source of truth).
- **`FWC2026_regulations_EN.txt`** — full UTF-8 text extraction (`pdftotext -enc UTF-8`). Greppable / diff-able; ~10,555 lines. Use it to search rule text without opening the PDF.

## Key articles for this codebase

### Article 13 — Equal points and qualification for knockout stages (group tie-breaks)

When two or more teams in a group are level on points, ranking is determined in this order (verbatim):

**Step 1 — head-to-head (matches between the teams concerned):**
- a) greatest number of points obtained in the group matches between the teams concerned;
- b) superior goal difference resulting from the group matches between the teams concerned;
- c) greatest number of goals scored in all group matches between the teams concerned.

**Step 2:** if teams are still level after a)–c), criteria a)–c) are **re-applied to the matches between the remaining still-level teams only**. If no decision can be made, then:
- d) superior goal difference in **all** group matches;
- e) greatest number of goals scored in **all** group matches;
- f) highest team conduct score (yellow/red card deductions).

**Step 3:**
- g) FIFA/Coca-Cola Men's World Ranking (most recent edition);
- h) the preceding published editions of the FIFA World Ranking, continually, until a decision can be made.

> **Order matters:** head-to-head (Step 1) is applied **before** overall goal difference (Step 2 d). This is the FWC2026 convention and differs from the older (2018/2022) "overall-GD-first" order. Independently corroborated by the Wikipedia 2026 FWC article (Group-stage section).

### Article 13 — Ranking of the eight best third-placed teams

The eight best third-placed teams are determined by (verbatim):
- a) greatest number of points obtained in **all** group matches;
- b) goal difference resulting from **all** group matches;
- c) greatest number of goals scored in **all** group matches;
- d) highest team conduct score;
- e) FIFA/Coca-Cola Men's World Ranking (most recent edition);
- f) the preceding editions of the FIFA World Ranking.

(No head-to-head here — third-placed teams come from different groups and never played each other.)

### Articles 12.6–12.11 — Knockout bracket structure

§12.6 defines the Round of 32 matchups (M73–M88), §12.7–12.11 the Round of 16, quarter-finals, semi-finals, third-place play-off and final. Example: **M73 = Runner-up A (2A) v Runner-up B (2B)**; the eight matches that include a third-placed team specify the candidate group set (e.g. M74 = 1E v "best 3rd of ABCDF").

## How the code implements this

| Rule | Code |
|------|------|
| Group tie-break chain (points → h2h → overall GD/goals → fallback) | `backend/app/services/standings.py`, `frontend/src/lib/utils/standings.ts` |
| Third-place ranking (points → overall GD → goals → fallback) | same files, `third_place_qualifying` context |
| R32→Final bracket seeding (which group position → which match) | `frontend/src/lib/config/bracketConfig.ts` |
| Third-place slot assignment (495 combinations / Annexe C) | `frontend/src/lib/config/thirdPlaceMapping.json` |

**Deliberate deviations:** the unpredictable end-of-chain criteria — team conduct score (cards), FIFA World Ranking, drawing of lots — cannot be predicted in this game, so the code collapses them to a deterministic **alphabetical** ordering that also raises a `TieWarning` ("this tie isn't fully FIFA-resolved — adjust your predictions"). Everything up to and including overall GD/goals is faithful to Article 13.

**Verification status:** the bracket seeding in `bracketConfig.ts` (R32–SF) was cross-checked match-by-match against §12.6–12.10 of this PDF *and* Wikipedia, and matches exactly. The group tie-break order was corrected to head-to-head-first (Article 13) on branch `fix/group-tiebreak-order`, validated against both the PDF and Wikipedia.

## Reference links

- **Official regulations PDF:** https://digitalhub.fifa.com/m/636f5c9c6f29771f/original/FWC2026_regulations_EN.pdf
- **Tournament overview (Wikipedia):** https://en.wikipedia.org/wiki/2026_FIFA_World_Cup
- **Third-place / R32 matchup grid (Wikipedia):** https://en.wikipedia.org/wiki/Template:2026_FIFA_World_Cup_third-place_table — the golden source the `backend/tests/test_third_place_mapping.py` snapshot (`docs/2026_world_cup_knockout_format.html`) is taken from, validating `thirdPlaceMapping.json`.
