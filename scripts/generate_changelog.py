"""
One-shot generator for frontend/src/lib/data/changelog.json.

Walks May 2026 commits chronologically, classifies each by its
conventional-commit prefix, assigns sequential semver bumps starting
at 2.0.0 (minor for feat/refactor/merge, patch for fix/chore/style/
docs/test/revert/build), produces a user-friendly summary, and writes
the JSON the admin Release Notes panel consumes.

Re-run safely: deterministic given the same git history. The output
file is the source of truth; hand-edits to individual summaries are
preserved by editing the JSON directly (this script is the bootstrap,
not the ongoing authoring tool).

Run:
    docker compose exec backend python /app/scripts/generate_changelog.py
or natively (anywhere git is on PATH and you're in the repo root):
    python scripts/generate_changelog.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SINCE = "2026-05-01"
UNTIL = "2026-06-01"
BASELINE = (2, 0, 0)  # first commit gets this exact version
OUTPUT = Path("frontend/src/lib/data/changelog.json")

# Conventional-commit type → category for the UI + bump tier.
# Tiers: 'minor' (feat/refactor/merge) or 'patch' (everything else).
TYPE_MAP: dict[str, tuple[str, str]] = {
    "feat": ("feature", "minor"),
    "refactor": ("internal", "minor"),
    "perf": ("improvement", "minor"),
    "fix": ("fix", "patch"),
    "style": ("improvement", "patch"),
    "ui": ("improvement", "patch"),
    "docs": ("internal", "patch"),
    "test": ("internal", "patch"),
    "chore": ("internal", "patch"),
    "build": ("internal", "patch"),
    "ci": ("internal", "patch"),
    "revert": ("fix", "patch"),
}

# Sub-scope → friendly label for user-facing copy.
SCOPE_LABELS: dict[str, str] = {
    "predictions": "Predictions wizard",
    "wizard": "Predictions wizard",
    "bracket": "Knockout bracket",
    "entries": "Entries",
    "auth": "Sign-in",
    "magic-login": "Magic-link sign-in",
    "panini": "Panini redesign",
    "theme": "Theme",
    "rules": "Rules page",
    "landing": "Landing page",
    "privacy": "Privacy page",
    "admin": "Admin console",
    "results": "Results page",
    "bonus": "Bonus questions",
    "smartfill": "Smart Fill",
    "scoring": "Scoring",
    "scheduler": "Background jobs",
    "snapshots": "Leaderboard snapshots",
    "agreements": "Agreement signals",
    "exposure,bonus": "Exposure + bonus",
    "exposure": "Bracket exposure",
    "scoring-copy": "Scoring copy",
    "timing-copy": "Deadline copy",
    "live-scores": "Live scores",
    "competition": "Competition",
    "ui": "UI polish",
    "deps": "Dependencies",
    "shell": "App shell",
    "match-detail": "Match detail page",
    "themes": "Themes",
    "compose": "Docker compose",
    "alembic": "Database migrations",
    "migration": "Database migration",
    "gitignore": "Internal",
    "scripts": "Internal scripts",
    "db": "Database",
    "leaderboard": "Leaderboard",
    "profile": "Profile",
    "fixtures": "Fixtures",
    "wallchart": "Wallchart",
    "regulations": "Regulations docs",
    "backend": "Backend",
    "deps": "Dependencies",
    "widgets": "Dashboard widgets",
    "standings": "Standings",
    "api": "API",
    "rules-page": "Rules page",
    "snapshot": "Snapshot",
    "claude+agents": "Internal docs",
    "claude": "Internal docs",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
COMMIT_RE = re.compile(
    r"^(?P<type>feat|fix|refactor|perf|style|ui|docs|test|chore|build|ci|revert)"
    r"(?:\((?P<scope>[^)]+)\))?:\s*(?P<rest>.+)$",
    re.IGNORECASE,
)


def fetch_commits() -> list[tuple[str, str, str]]:
    """Return [(hash, ISO date, subject), ...] in chronological order."""
    out = subprocess.check_output(
        [
            "git",
            "log",
            "--reverse",
            "--pretty=format:%h\x1f%ad\x1f%s",
            "--date=short",
            f"--since={SINCE}",
            f"--until={UNTIL}",
        ],
        text=True,
    )
    commits: list[tuple[str, str, str]] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("\x1f", 2)
        if len(parts) != 3:
            continue
        commits.append((parts[0], parts[1], parts[2]))
    return commits


def classify(subject: str) -> tuple[str, str, str, str]:
    """Return (category, bump_tier, scope_label, body).

    `body` is the cleaned message minus the type/scope prefix.
    `scope_label` is "" when the commit has no scope.
    """
    m = COMMIT_RE.match(subject)
    if m:
        kind = m.group("type").lower()
        scope = (m.group("scope") or "").lower().strip()
        body = m.group("rest").strip()
        category, tier = TYPE_MAP.get(kind, ("internal", "patch"))
        scope_label = SCOPE_LABELS.get(scope, scope) if scope else ""
        return category, tier, scope_label, body
    # No conventional prefix — fall back to heuristic.
    lower = subject.lower()
    if lower.startswith("merge"):
        return "merge", "minor", "", subject
    # User-facing improvements / features without conventional prefix.
    if lower.startswith(("refine ", "polish ", "improve ")):
        return "improvement", "minor", "", subject
    if lower.startswith(("mobile ", "desktop ", "profile page", "dashboard ")):
        return "feature", "minor", "", subject
    # Plan / spec / docs.
    if "design spec" in lower or "implementation plan" in lower or lower.startswith(
        ("plan ", "spec ")
    ):
        return "internal", "patch", "", subject
    # Internal additions (backend modules, helpers, schemas).
    if lower.startswith("add ") and any(
        kw in lower
        for kw in (
            "skeleton",
            "client",
            "helpers",
            "method",
            "schema",
            "column",
            "table",
            "record",
            "result",
            "cli",
            "wrapper",
            "alias",
        )
    ):
        return "internal", "minor", "", subject
    # User-visible additions / wiring.
    if lower.startswith(("add ", "wire ", "render ", "pivot ", "make ", "expose ")):
        return "feature", "minor", "", subject
    if lower.startswith(("fix ", "drop ", "rename ", "block ", "ignore ", "skip ")):
        return "fix", "patch", "", subject
    if lower.startswith(("refactor", "reconcile", "squash", "update ", "seed ")):
        return "internal", "patch", "", subject
    # default
    return "internal", "patch", "", subject


# Hand-crafted overrides for the most user-facing milestones.
# Indexed by short-hash; overrides the auto-generated summary and/or
# category. `tier` is also overridable — `None` means keep auto-bump.
# Keep entries terse and friendly for end users.
SUMMARY_OVERRIDES: dict[str, dict[str, str | None]] = {
    "8b92deb": {"type": "improvement", "summary": "Results scatter chart now colors matches by outcome and highlights your own predictions."},
    "bb93c78": {"type": "feature", "summary": "Knockout bracket on mobile now swipes between two-round pages for easier navigation."},
    "ea9f703": {"type": "feature", "summary": "Profile page now shows Phase 1 and Phase 2 bracket predictions separately."},
    "353a6e9": {"type": "improvement", "summary": "Unfilled team slots now show as 'TBD' everywhere team names appear."},
    "396ee26": {"type": "feature", "summary": "Live scores now update via a background scheduler with smarter match-window polling."},
    "bf59aee": {"type": "feature", "summary": "Admin dashboard: user management and manual score sync added."},
    "fc65ebf": {"type": "feature", "summary": "Unsaved predictions now survive page refresh — drafts mirror to your browser's local storage."},
    "c6089cc": {"type": "internal", "summary": "Internal: every date/time across the app is now timezone-aware UTC — eliminates a class of off-by-N-hours bugs."},
    "980b1ca": {"type": "fix", "summary": "When another tab saves predictions, this tab now refreshes its view so it doesn't show stale data."},
    "7eded48": {"type": "feature", "summary": "Production-ready: deployment stack hardened for VPS hosting."},
    "3e86d0e": {"type": "feature", "summary": "Daily automated backups of the production database to Cloudflare R2."},
    "a394d92": {"type": "feature", "summary": "Search engines no longer index the site — your pool stays private."},
    "5e17cbc": {"type": "feature", "summary": "Daily leaderboard snapshots + trajectory data for dashboard charts."},
    "89ab8b8": {"type": "feature", "summary": "Real social-signal counts per fixture + 'Hot Pick' widget powered by actual data."},
    "19af054": {"type": "feature", "summary": "Real bracket exposure + bonus-haul breakdowns on the dashboard."},
    "6281786": {"type": "feature", "summary": "Bonus questions: schema, save/load endpoints, and wizard wiring."},
    "6a35f20": {"type": "feature", "summary": "Bonus questions: admin can manage answers; leaderboard scores bonus picks."},
    "6f213e3": {"type": "feature", "summary": "Public /rules page explaining scoring, phases, and buy-in."},
    "a01bd17": {"type": "feature", "summary": "Live scores now appear on fixture data + dashboard."},
    "6fc0165": {"type": "feature", "summary": "Group standings: full FIFA tiebreaker chain with alphabetical-tie warnings."},
    "6d1e54c": {"type": "feature", "summary": "Predictions wizard: tie-warning banner when alphabetical fallback decides standings."},
    "63a634d": {"type": "feature", "summary": "Predictions wizard: cross-tab and cross-refresh draft persistence restored."},
    "604ec90": {"type": "feature", "summary": "Multi-entry foundation: users can now have multiple prediction entries per competition."},
    "e09f9bb": {"type": "feature", "summary": "Multi-entry: frontend wizard, selector, and entry-scoped APIs."},
    "8fc947f": {"type": "feature", "summary": "Multi-entry: leaderboard hides other players' predictions until the deadline (blind pool)."},
    "4fbc705": {"type": "feature", "summary": "Multi-entry: admin panels for entry settings, Phase II open, and the entries table."},
    "675fb76": {"type": "feature", "summary": "Multi-entry: lifecycle actions wired — Mark Ready, Submit, Reopen, Withdraw + bonus gate."},
    "dae70d9": {"type": "feature", "summary": "Bonus + bracket: multi-answer ties, auto-resolver, and bracket alignment."},
    "6fdc0c2": {"type": "feature", "summary": "Theme picker added to the user avatar dropdown."},
    "1cba18e": {"type": "feature", "summary": "Magic-link (passwordless) sign-in added."},
    "287cf2b": {"type": "feature", "summary": "Onboarding overhaul + submit flow + email rebrand."},
    "c292b0c": {"type": "feature", "summary": "New app icons and PWA manifest installed."},
    "74c2cc9": {"type": "improvement", "summary": "New premium-night / premium-day themes with Manrope + Inter typography."},
    "45e72f9": {"type": "feature", "summary": "Landing page (/) built from the predictorv3 design handoff."},
    "ffcd3d2": {"type": "improvement", "summary": "Landing page: mobile polish, FAQ section, news + auth-aware chrome fixes."},
    "9c6682e": {"type": "feature", "summary": "Smart Fill: scoreline suggestions from real betting odds."},
    "cf4960c": {"type": "improvement", "summary": "Smart Fill: method radio, cache info, and help text in the modal."},
    "aef60bf": {"type": "improvement", "summary": "Rules page refreshed with new content and tone; single-deadline framing."},
    "74407dc": {"type": "feature", "summary": "Public /privacy route with the privacy statement."},
    "75597e2": {"type": "feature", "summary": "Per-match drill-down page with bubble plot and scrolling leaderboard."},
    "4f0b244": {"type": "improvement", "summary": "Entry lifecycle simplified from 6 statuses to 3: draft, submitted, withdrawn."},
    "a42ce51": {"type": "feature", "summary": "Background job auto-withdraws DRAFT entries past the competition deadline."},
    "1582f82": {"type": "feature", "summary": "Logarithmic rarity-bonus scoring mode (default); legacy hybrid mode retired."},
    "c2af978": {"type": "feature", "summary": "Per-match breakdown cards + Results page rebuild."},
    "394f54c": {"type": "feature", "summary": "Rules page: per-pool-size rarity bonus table."},
    "00c8f17": {"type": "fix", "summary": "Group standings tiebreak now applies head-to-head before overall goal difference per FWC2026 Article 13."},
    "6c85476": {"type": "feature", "summary": "New /entries hub: list of all your entries, plus admin table refactor."},
    "9c7a230": {"type": "improvement", "summary": "/entries: visual redesign — clean table, naming dialog, inline edit, completion chips, kebab menu."},
    "6e2afae": {"type": "feature", "summary": "Bracket wallchart: symmetric desktop 9-column layout + mobile 4-page carousel."},
    "fc552e2": {"type": "fix", "summary": "Predictions wizard: drafts isolated per tab — sibling tabs no longer overwrite each other."},
    "89a9a51": {"type": "feature", "summary": "Predictions wizard: save / submit errors now surface via clear modals, with strict completeness checks front + back."},
    "acf6496": {"type": "feature", "summary": "Predictions wizard: warns you when the same entry is open in another tab of this browser."},
    "ed14e05": {"type": "internal", "summary": "Internal: version bump policy documented in CLAUDE.md."},
}


def humanize(body: str) -> str:
    """Light cleanup: ensure first char is uppercase + trailing period."""
    if not body:
        return ""
    s = body.strip()
    if not s:
        return ""
    s = s[0].upper() + s[1:]
    if s[-1] not in ".!?":
        s += "."
    return s


def build_summary(scope_label: str, body: str, category: str) -> str:
    body_clean = humanize(body)
    if scope_label and not body_clean.lower().startswith(scope_label.lower()):
        return f"{scope_label}: {body_clean[0].lower()}{body_clean[1:]}"
    return body_clean


def bump(
    minor: int, patch: int, tier: str, first: bool
) -> tuple[int, int, str]:
    if first:
        return 0, 0, "2.0.0"
    if tier == "minor":
        minor += 1
        patch = 0
    else:
        patch += 1
    return minor, patch, f"2.{minor}.{patch}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    commits = fetch_commits()
    if not commits:
        print("No commits found in window.", file=sys.stderr)
        sys.exit(1)

    entries: list[dict[str, str]] = []
    minor = 0
    patch = 0

    for idx, (sha, date, subject) in enumerate(commits):
        category, tier, scope_label, body = classify(subject)
        minor, patch, version = bump(minor, patch, tier, first=(idx == 0))
        summary = build_summary(scope_label, body, category)

        # Hand-crafted override for major user-facing milestones.
        ov = SUMMARY_OVERRIDES.get(sha)
        if ov:
            if ov.get("type"):
                category = ov["type"]  # type: ignore[assignment]
            if ov.get("summary"):
                summary = ov["summary"]  # type: ignore[assignment]

        entries.append(
            {
                "version": version,
                "date": date,
                "type": category,
                "summary": summary,
                "commit": sha,
            }
        )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(
            {
                "baseline": "2.0.0",
                "generated_from": f"git log --since={SINCE} --until={UNTIL}",
                "entries": entries,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(f"Wrote {len(entries)} entries to {OUTPUT}")
    print(f"Final version: {entries[-1]['version']}")


if __name__ == "__main__":
    main()
