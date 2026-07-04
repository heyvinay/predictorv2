"""Pinned cross-reference: R16/QF/SF/Final ext_id ↔ FIFA match number
(v2.195.x).

Companion to test_r32_ext_id_mapping.py — same shape, downstream stages.

Backstory: v2.184.x fixed the R32 layer with a hand-verified ext_id map
but kept a kickoff-sorted fallback in ko_lineup_resolver.py for R16+
stages, on the assumption that FIFA schedules match numbers in
chronological order. That assumption held for M91-M96 but broke for
exactly one pair — Match 89 (Paraguay vs France, Philadelphia,
21:00Z Sat 4 Jul) kicks off FOUR HOURS AFTER Match 90 (Canada vs
Morocco, Houston, 17:00Z Sat 4 Jul). Kickoff-sort therefore labelled
the Houston fixture as M89, then walked ROUND_OF_16_SOURCES[89] and
painted "winner-of-M74-vs-winner-of-M77" (Paraguay + France) onto the
Canada–Morocco row. Downstream QF/SF/F derivations that pulled from
those R16 winners also came out with swapped teams.

The v2.195.x fix extends EXT_ID_TO_MATCH_NUMBER to cover R16 through
Final and deletes the kickoff-sort fallback. This test pins that map
so the class of bug can't recur: any Football-Data ext_id reshuffle
OR any FIFA schedule change that would previously have shifted the
kickoff-based label will now fail the test at CI time, not in production.

Source of truth:
  * FIFA 2026 knockout schedule (Wikipedia + multiple sports outlets
    cross-verified — beIN SPORTS, ESPN, olympics.com)
  * backend/data/wc2026_fixtures.json UTC kickoffs
  * ROUND_OF_16_SOURCES / QUARTER_FINAL_SOURCES / SEMI_FINAL_SOURCES /
    FINAL_SOURCES bracket structure
"""

from __future__ import annotations

from app.services.bracket_seeding import (
    EXT_ID_TO_MATCH_NUMBER,
    FINAL_SOURCES,
    QUARTER_FINAL_SOURCES,
    ROUND_OF_16_SOURCES,
    SEMI_FINAL_SOURCES,
)


# Kickoff cross-reference for downstream stages. Format:
#   ext_id  →  (FIFA match number, kickoff ISO-UTC, expected structural label)
PINNED_KO: dict[str, tuple[int, str, str]] = {
    # ── R16 ───────────────────────────────────────────────────────────
    # The M89/M90 pair is the swap fix — Paraguay–France kicks off LATER
    # than Canada–Morocco despite carrying the lower FIFA match number.
    "537375": (89, "2026-07-04T21:00:00+00:00", "M74w vs M77w"),   # Paraguay–France (Philadelphia)
    "537376": (90, "2026-07-04T17:00:00+00:00", "M73w vs M75w"),   # Canada–Morocco (Houston)
    "537377": (91, "2026-07-05T20:00:00+00:00", "M76w vs M78w"),
    "537378": (92, "2026-07-06T00:00:00+00:00", "M79w vs M80w"),
    "537379": (93, "2026-07-06T19:00:00+00:00", "M83w vs M84w"),
    "537380": (94, "2026-07-07T00:00:00+00:00", "M81w vs M82w"),
    "537381": (95, "2026-07-07T16:00:00+00:00", "M86w vs M88w"),
    "537382": (96, "2026-07-07T20:00:00+00:00", "M85w vs M87w"),
    # ── QF ────────────────────────────────────────────────────────────
    "537383": (97, "2026-07-09T20:00:00+00:00", "M89w vs M90w"),
    "537384": (98, "2026-07-10T19:00:00+00:00", "M93w vs M94w"),
    "537385": (99, "2026-07-11T21:00:00+00:00", "M91w vs M92w"),
    "537386": (100, "2026-07-12T01:00:00+00:00", "M95w vs M96w"),
    # ── SF ────────────────────────────────────────────────────────────
    "537387": (101, "2026-07-14T19:00:00+00:00", "M97w vs M98w"),
    "537388": (102, "2026-07-15T19:00:00+00:00", "M99w vs M100w"),
    # ── Final ─────────────────────────────────────────────────────────
    # Third-place (M103, ext_id 537389) intentionally absent — unscored.
    "537390": (104, "2026-07-19T19:00:00+00:00", "M101w vs M102w"),
}


def test_pinned_r16_map_matches_implementation():
    """The R16 slice of the implementation's map MUST match the pinned
    cross-reference — the case that broke in v2.195.x."""
    for ext_id, (expected_match_num, _kickoff, _label) in PINNED_KO.items():
        if 89 <= expected_match_num <= 96:
            actual = EXT_ID_TO_MATCH_NUMBER.get(ext_id)
            assert actual == expected_match_num, (
                f"ext_id {ext_id}: expected M{expected_match_num}, got M{actual}. "
                f"This is the class of bug that swapped Paraguay–France ↔ "
                f"Canada–Morocco in v2.194.x."
            )


def test_paraguay_france_row_is_m89_not_m90():
    """The exact swap fix in v2.195.x — pinned so it can never regress.

    ROUND_OF_16_SOURCES[89] = (M74w, M77w) = (Paraguay-side, France-side).
    The DB fixture that MUST carry match number 89 is the one played at
    21:00Z on Sat 4 Jul in Philadelphia (ext_id 537375). Under the buggy
    kickoff-sort, 537375 got labelled M90 (because it kicks off LATER
    than the 17:00Z Houston game), and its row displayed the wrong teams.
    """
    assert EXT_ID_TO_MATCH_NUMBER["537375"] == 89
    assert EXT_ID_TO_MATCH_NUMBER["537376"] == 90


def test_pinned_qf_sf_final_map_matches_implementation():
    """Extending coverage to QF/SF/Final: hand-verified so we're not
    one FIFA schedule quirk away from the same class of bug re-appearing
    when Football-Data backfills those stages after R16 concludes."""
    for ext_id, (expected_match_num, _kickoff, _label) in PINNED_KO.items():
        if expected_match_num >= 97:
            actual = EXT_ID_TO_MATCH_NUMBER.get(ext_id)
            assert actual == expected_match_num, (
                f"ext_id {ext_id}: expected M{expected_match_num}, got M{actual}"
            )


def test_every_ko_ext_id_has_bracket_source():
    """Every downstream match number in the map must have a matching
    entry in ROUND_OF_16_SOURCES / QUARTER_FINAL_SOURCES / etc. —
    otherwise the resolver would fail silently."""
    downstream_sources: dict[int, tuple[dict, dict]] = {
        **ROUND_OF_16_SOURCES,
        **QUARTER_FINAL_SOURCES,
        **SEMI_FINAL_SOURCES,
        **FINAL_SOURCES,
    }
    for ext_id, (match_num, _kickoff, _label) in PINNED_KO.items():
        assert match_num in downstream_sources, (
            f"ext_id {ext_id} pinned to M{match_num} but no bracket source "
            f"defines that match"
        )


def test_no_ko_match_number_appears_twice():
    """Sanity: each FIFA match number appears at most once across the
    entire (R32 + R16 + QF + SF + Final) map."""
    values = list(EXT_ID_TO_MATCH_NUMBER.values())
    assert len(values) == len(set(values)), (
        f"Duplicate match numbers in EXT_ID_TO_MATCH_NUMBER: {values}"
    )


def test_downstream_match_numbers_cover_89_to_104_except_103():
    """All 15 downstream FIFA match numbers must appear: M89..M102 + M104.
    M103 (third_place playoff) is intentionally OMITTED — unscored per
    CLAUDE.md invariant."""
    ko_nums = {v for v in EXT_ID_TO_MATCH_NUMBER.values() if v >= 89}
    expected = set(range(89, 103)) | {104}
    assert ko_nums == expected, (
        f"Downstream match number coverage drift: expected {sorted(expected)}, "
        f"got {sorted(ko_nums)}"
    )
