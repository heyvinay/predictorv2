"""Golden-source validation for thirdPlaceMapping.json.

The FIFA 2026 R32 matchup grid (which 3rd-placed team plays which group
winner) depends on *which 8 of 12 groups* contributed qualifying 3rd-placed
teams. There are C(12, 8) = 495 possible combinations. FIFA publishes the
matchup grid as a table; Wikipedia archives the same table at
https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_knockout_stage

A static copy of that Wikipedia page is committed to the repo at
docs/2026_world_cup_knockout_format.html. This test parses the table from
that page and asserts that frontend/src/lib/config/thirdPlaceMapping.json
matches it byte-for-byte.

If this test fails:
  1. Check whether Wikipedia updated their table (real FIFA rule change?).
  2. If yes, refresh the HTML snapshot in docs/ and re-run.
  3. If no, somebody edited thirdPlaceMapping.json incorrectly — revert.

This is the single highest-stakes asset in the codebase. One wrong entry
silently shifts R32 matchups for the rest of the tournament; predictions
made against a corrupted mapping would scoring against the wrong teams.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path


def _find_file(relative: str) -> Path | None:
    """Walk up from this test file looking for `relative` (e.g. 'docs/foo.html').

    Returns the first match found. The standings tests run under varying mount
    layouts depending on whether they're invoked from the worktree or the main
    repo, so an absolute parent-index would be fragile. Walking up handles both.
    """
    cur = Path(__file__).resolve()
    for parent in [cur.parent, *cur.parents]:
        candidate = parent / relative
        if candidate.exists():
            return candidate
    return None


_WIKIPEDIA_HTML = _find_file("docs/2026_world_cup_knockout_format.html")
_MAPPING_JSON = _find_file("frontend/src/lib/config/thirdPlaceMapping.json")


# Column order of matchups in the Wikipedia table header.
# These are the 8 group-winner positions that play a 3rd-placed team in R32.
_MATCH_ORDER = ("1A", "1B", "1D", "1E", "1G", "1I", "1K", "1L")


def _strip_html(s: str) -> str:
    """Cheap HTML cell flattener: drop tags, decode entities, collapse whitespace."""
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def _parse_fifa_grid(html_text: str) -> dict[str, dict[str, str]]:
    """Extract the 'Combinations of matches in the round of 32' table.

    Returns a dict shaped {<sorted-letters>: {<winner-pos>: <target>}}, matching
    thirdPlaceMapping.json. Raises if the table can't be located or any row
    fails to parse the expected 8 letters + 8 matchups.
    """
    section_start = html_text.index("Combinations of matches in the round of 32")
    table_match = re.search(r"<table[^>]*>.*?</table>", html_text[section_start:], flags=re.S)
    if not table_match:
        raise RuntimeError("Could not find combinations table in Wikipedia HTML")
    table = table_match.group(0)
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table, flags=re.S)

    grid: dict[str, dict[str, str]] = {}
    for row in rows[1:]:  # skip header
        cells = [_strip_html(c) for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row, flags=re.S)]
        letters = [c for c in cells if re.fullmatch(r"[A-L]", c)]
        matchups = [c for c in cells if re.fullmatch(r"3[A-L]", c)]
        if len(letters) != 8 or len(matchups) != 8:
            raise RuntimeError(
                f"Row {cells[0] if cells else '?'} parse failure: "
                f"got {len(letters)} letters and {len(matchups)} matchups"
            )
        key = "".join(sorted(letters))
        grid[key] = dict(zip(_MATCH_ORDER, matchups))
    return grid


def _require(path: Path | None, name: str) -> Path:
    if path is None:
        import pytest
        pytest.skip(f"{name} not found via parent-walk from test file")
    return path


def test_wikipedia_html_snapshot_is_available() -> None:
    """Guard: the golden HTML snapshot must be present where the full repo tree
    is visible (CI / local checkout). The backend-only container mounts just
    `backend/` → `/app`, so the repo-root `docs/` folder isn't reachable there;
    skip rather than fail in that case (matching the `_require`-based skips the
    rest of this cross-cutting file uses). When the snapshot IS visible, assert
    it really exists."""
    if _WIKIPEDIA_HTML is None:
        import pytest

        pytest.skip(
            "Wikipedia HTML snapshot not visible from this mount "
            "(expected at <repo>/docs/2026_world_cup_knockout_format.html; "
            "present in full-repo runs). The file is committed — this is a "
            "mount-layout skip, not a missing file."
        )
    assert _WIKIPEDIA_HTML.exists()


def test_mapping_json_present_and_parses() -> None:
    json_path = _require(_MAPPING_JSON, "thirdPlaceMapping.json")
    data = json.loads(json_path.read_text())
    assert isinstance(data, dict)
    assert len(data) == 495, f"expected 495 mapping entries, got {len(data)}"


def test_mapping_matches_fifa_wikipedia_grid_byte_for_byte() -> None:
    """The 495-entry grid in our JSON must equal the FIFA-published grid.

    This is the load-bearing assertion for the entire knockout bracket logic.
    """
    html_path = _require(_WIKIPEDIA_HTML, "Wikipedia HTML snapshot")
    json_path = _require(_MAPPING_JSON, "thirdPlaceMapping.json")

    fifa_grid = _parse_fifa_grid(html_path.read_text())
    our_mapping = json.loads(json_path.read_text())

    assert set(fifa_grid) == set(our_mapping), (
        f"Key-set mismatch: only in FIFA={sorted(set(fifa_grid) - set(our_mapping))[:5]}, "
        f"only in ours={sorted(set(our_mapping) - set(fifa_grid))[:5]}"
    )

    mismatches = [(k, fifa_grid[k], our_mapping[k]) for k in fifa_grid if fifa_grid[k] != our_mapping[k]]
    if mismatches:
        sample = "\n".join(
            f"  {k}: FIFA={fifa} OURS={ours}" for k, fifa, ours in mismatches[:5]
        )
        raise AssertionError(
            f"{len(mismatches)} mapping entries diverge from FIFA. Sample:\n{sample}"
        )


def test_mapping_keys_are_alphabetically_sorted_letters() -> None:
    """Every key must be 8 distinct uppercase letters from A-L in ascending order."""
    data = json.loads(_require(_MAPPING_JSON, "thirdPlaceMapping.json").read_text())
    for key in data:
        assert len(key) == 8, f"key {key!r} has {len(key)} letters, expected 8"
        assert all(c in "ABCDEFGHIJKL" for c in key), f"key {key!r} has non-group letters"
        assert key == "".join(sorted(key)), f"key {key!r} is not in alphabetical order"
        assert len(set(key)) == 8, f"key {key!r} has duplicate letters"


def test_mapping_entries_have_the_8_winner_positions() -> None:
    """Each entry must map exactly the 8 group-winner positions that play a 3rd-placed team."""
    expected_sub_keys = set(_MATCH_ORDER)
    data = json.loads(_require(_MAPPING_JSON, "thirdPlaceMapping.json").read_text())
    for key, entry in data.items():
        assert set(entry.keys()) == expected_sub_keys, (
            f"entry {key!r} has sub-keys {set(entry)}, expected {expected_sub_keys}"
        )


def test_mapping_targets_are_valid_third_place_codes_within_key() -> None:
    """Every target must be '3X' where X is one of the qualifying groups in that entry's key."""
    data = json.loads(_require(_MAPPING_JSON, "thirdPlaceMapping.json").read_text())
    for key, entry in data.items():
        for winner_pos, target in entry.items():
            assert re.fullmatch(r"3[A-L]", target), (
                f"entry {key!r}[{winner_pos!r}] = {target!r} is not a valid 3X code"
            )
            target_group = target[1]
            assert target_group in key, (
                f"entry {key!r}[{winner_pos!r}] = {target!r} but group {target_group!r} not in key"
            )


def test_mapping_no_duplicate_targets_within_entry() -> None:
    """Each qualifying 3rd-placed team plays in exactly one R32 match — no group appears twice."""
    data = json.loads(_require(_MAPPING_JSON, "thirdPlaceMapping.json").read_text())
    for key, entry in data.items():
        targets = list(entry.values())
        assert len(targets) == len(set(targets)), (
            f"entry {key!r} has duplicate targets: {targets}"
        )
