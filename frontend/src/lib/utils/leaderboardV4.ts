/**
 * V4 Leaderboard pure derivations (v2.164.0).
 *
 * Everything here is a pure function over server data — unit-tested in
 * leaderboardV4.test.ts. No stores, no fetches, no DOM.
 */

import type { Fixture, PointBreakdown } from '$types';
import type { ScoringRules } from '$lib/types/results';
import type {
	BonusFold,
	BonusPredictionRead,
	DnaSplit,
	EntryTrajectory,
	LbEntryV4,
	LbPool,
	LbStage,
	MinimapMarker,
	RaceSliceDescriptor,
	RaceViewMode
} from '$lib/types/leaderboard';

// ── Pools ────────────────────────────────────────────────────────────────

/** Map a User.employer value onto a pool pill. Unknown/missing → Guests. */
export function poolOf(employer: string | null | undefined): Exclude<LbPool, 'All'> {
	if (employer === 'atlas') return 'Atlas';
	if (employer === 'jmfa') return 'JMFA';
	return 'Guests';
}

/** Filter rows to a pool. Server `position` values are NOT recomputed —
 *  the spec requires global ranks to survive filtering. */
export function filterByPool(rows: LbEntryV4[], pool: LbPool): LbEntryV4[] {
	if (pool === 'All') return rows;
	return rows.filter((r) => poolOf(r.employer) === pool);
}

/** Pill badge counts, computed once per leaderboard load. */
export function poolCounts(rows: LbEntryV4[]): Record<LbPool, number> {
	const counts: Record<LbPool, number> = { All: rows.length, Atlas: 0, JMFA: 0, Guests: 0 };
	for (const r of rows) counts[poolOf(r.employer)] += 1;
	return counts;
}

// ── Stage ────────────────────────────────────────────────────────────────

// "slot:round_of_32:537430:home" is OUR ingest placeholder format (the
// production DB stores exactly this until Football-Data seeds real
// teams) — its absence here made deriveStage report 'knockout' before
// the tournament even started (Final column + trophy what-ifs showed
// pre-kickoff, caught 2026-06-11).
const PLACEHOLDER_RE = /^(winner|loser|runner|slot:|1[a-l]|2[a-l]|3[a-l])\b/i;

/** True when a fixture lineup slot holds a real team rather than a
 *  placeholder ("Winner of Match 12", "1A", "slot:…", empty). */
export function isRealTeam(name: string | null | undefined): boolean {
	return !!name && name.trim() !== '' && !PLACEHOLDER_RE.test(name.trim());
}

/** Knockout stage begins when any non-group fixture has a real team seeded
 *  (lineup-based, consistent with the scoring engine's advancement timing). */
export function deriveStage(fixtures: Fixture[]): LbStage {
	for (const f of fixtures) {
		if (f.stage === 'group') continue;
		if (isRealTeam(f.home_team) || isRealTeam(f.away_team)) return 'knockout';
	}
	return 'group';
}

// ── Bracket chip derivations (drawer) ────────────────────────────────────

/** Teams provably out — client-side mirror of the backend's
 *  get_eliminated_teams (same conservative rules): KO-match losers, plus
 *  group non-qualifiers once every R32 fixture holds real teams. */
export function eliminatedTeams(fixtures: Fixture[]): Set<string> {
	const groupTeams = new Set<string>();
	const koLineup = new Set<string>();
	const out = new Set<string>();
	const r32: Fixture[] = [];

	for (const f of fixtures) {
		if (f.stage === 'group') {
			if (isRealTeam(f.home_team)) groupTeams.add(f.home_team);
			if (isRealTeam(f.away_team)) groupTeams.add(f.away_team);
			continue;
		}
		if (isRealTeam(f.home_team)) koLineup.add(f.home_team);
		if (isRealTeam(f.away_team)) koLineup.add(f.away_team);
		if (f.stage === 'round_of_32') r32.push(f);

		if (f.status === 'finished' && f.score) {
			if (f.score.outcome === '1' && isRealTeam(f.away_team)) out.add(f.away_team);
			else if (f.score.outcome === '2' && isRealTeam(f.home_team)) out.add(f.home_team);
		}
	}

	const r32Real =
		r32.length > 0 &&
		r32.every(
			(f) =>
				isRealTeam(f.home_team) &&
				isRealTeam(f.away_team) &&
				groupTeams.has(f.home_team) &&
				groupTeams.has(f.away_team)
		);
	if (r32Real) {
		for (const t of groupTeams) if (!koLineup.has(t)) out.add(t);
	}
	return out;
}

/** stage → set of real teams credited with reaching that stage. Mirrors
 *  the backend's get_actual_advancement: (a) being seeded into a stage's
 *  fixture lineup counts, AND (b) winning a FINISHED knockout match
 *  credits the winner with the NEXT stage — even before Football-Data
 *  updates the next round's lineups. The pseudo-stage "winner" holds the
 *  champion once the final is finished. */
export function seededByStage(fixtures: Fixture[]): Map<string, Set<string>> {
	const NEXT_STAGE: Record<string, string> = {
		round_of_32: 'round_of_16',
		round_of_16: 'quarter_final',
		quarter_final: 'semi_final',
		semi_final: 'final',
		final: 'winner'
	};
	const map = new Map<string, Set<string>>();
	const add = (stage: string, team: string) => {
		if (!map.has(stage)) map.set(stage, new Set());
		map.get(stage)?.add(team);
	};
	for (const f of fixtures) {
		if (f.stage === 'group') continue;
		if (isRealTeam(f.home_team)) add(f.stage, f.home_team);
		if (isRealTeam(f.away_team)) add(f.stage, f.away_team);
		if (f.status === 'finished' && f.score) {
			const next = NEXT_STAGE[f.stage];
			if (!next) continue;
			if (f.score.outcome === '1' && isRealTeam(f.home_team)) add(next, f.home_team);
			else if (f.score.outcome === '2' && isRealTeam(f.away_team)) add(next, f.away_team);
		}
	}
	return map;
}

export type ChipState = 'hit' | 'out' | 'pend';

/** Bracket chip state for "predicted `team` reaches `stage`":
 *  hit  — team actually seeded into that stage (lineup-banked credit)
 *  out  — eliminated before reaching it
 *  pend — still possible. */
export function chipState(
	team: string,
	stage: string,
	seeded: Map<string, Set<string>>,
	eliminated: Set<string>
): ChipState {
	if (seeded.get(stage)?.has(team)) return 'hit';
	if (eliminated.has(team)) return 'out';
	return 'pend';
}

// ── Points DNA ───────────────────────────────────────────────────────────

/** Where an entry's points come from. exact + result + rarity + the six
 *  per-round bracket fields + bonus === breakdown.total (server fields).
 *  Bracket is broken out per knockout round (R32 → winner) so the DNA bar
 *  can shade each round distinctly instead of one undifferentiated block. */
export function dnaOf(breakdown: PointBreakdown): DnaSplit {
	return {
		exact: breakdown.exact_score_points,
		result: breakdown.match_outcome_points,
		rarity: breakdown.hybrid_bonus_points,
		roundOf32: breakdown.round_of_32_points,
		roundOf16: breakdown.round_of_16_points,
		quarterFinal: breakdown.quarter_final_points,
		semiFinal: breakdown.semi_final_points,
		final: breakdown.final_points,
		winner: breakdown.winner_points,
		bonus: breakdown.bonus_question_points
	};
}

// ── Bonus folding ────────────────────────────────────────────────────────

/** Fold per-question bonus reads into Group / Knockout column extras.
 *  category group_stage → Group; top_flop (and any future awards) → KO. */
export function foldBonus(reads: BonusPredictionRead[]): BonusFold {
	const fold: BonusFold = {
		group: 0,
		knockout: 0,
		groupHits: 0,
		knockoutHits: 0,
		hits: 0,
		answered: reads.length
	};
	for (const r of reads) {
		if (r.hit !== true || !r.points) continue;
		fold.hits += 1;
		if (r.category === 'group_stage') {
			fold.group += r.points;
			fold.groupHits += 1;
		} else {
			fold.knockout += r.points;
			fold.knockoutHits += 1;
		}
	}
	return fold;
}

// ── Column totals ────────────────────────────────────────────────────────

/** Group column = group-stage match points + group bracket credits +
 *  group-category bonus. Phase 2 is dormant; phase1 carries everything. */
export function groupPtsOf(row: LbEntryV4, bonusGroup: number): number {
	const p1 = row.breakdown.phase1;
	return p1.match_total + p1.group_advance_points + p1.group_position_points + bonusGroup;
}

/** Knockout column = KO bracket credits + knockout-category bonus.
 *  (Group matches are the only score predictions in this competition —
 *  match_total is all group.) */
export function koPtsOf(row: LbEntryV4, bonusKnockout: number): number {
	const p1 = row.breakdown.phase1;
	return (
		p1.round_of_32_points +
		p1.round_of_16_points +
		p1.quarter_final_points +
		p1.semi_final_points +
		p1.final_points +
		p1.winner_points +
		bonusKnockout
	);
}

// ── Live projection display ──────────────────────────────────────────────

/** Rank to render: projected when the live board is armed and a projected
 *  value exists, else the banked position. `live` gates on the response's
 *  live_projection_active flag — callers pass that through, not a store. */
export function displayRank(row: LbEntryV4, live: boolean): number {
	return live && row.projected_position != null ? row.projected_position : row.position;
}

/** Points to render: projected when live + present, else banked total. */
export function displayTotal(row: LbEntryV4, live: boolean): number {
	return live && row.projected_total != null ? row.projected_total : row.total_points;
}

// ── Ceiling (Points still on the table) ──────────────────────────────────

/** Max theoretical points still winnable by one entry.
 *
 *  banked total
 *  + champion alive & winner credit unpaid → advancement.winner
 *  + alive-but-uncredited finalist picks   → advancement.final each
 *  + shared remaining match points (identical for every entry)
 */
export function ceilingOf(
	row: LbEntryV4,
	rules: ScoringRules,
	remainingShared: number
): number {
	const winnerVal = rules.advancement.winner;
	const finalVal = rules.advancement.final;
	const b = row.breakdown;
	const championUpside = row.champion_alive && b.winner_points === 0 ? winnerVal : 0;
	const creditedFinalists = finalVal > 0 ? Math.round(b.final_points / finalVal) : 0;
	const uncreditedAlive = Math.max(0, (row.finalists_alive ?? 0) - creditedFinalists);
	return row.total_points + championUpside + uncreditedAlive * finalVal + remainingShared;
}

/** Max match points still on the table from unfinished score-predicted
 *  fixtures (group stage only — KO fixtures take no score predictions).
 *  Identical for every entry. */
export function remainingMatchPoints(fixtures: Fixture[], rules: ScoringRules): number {
	const perFixture =
		rules.match.correct_outcome + rules.match.exact_score + rules.match.rarity_cap;
	const remaining = fixtures.filter(
		(f) => f.stage === 'group' && f.status !== 'finished'
	).length;
	return remaining * perFixture;
}

// ── Row chrome helpers ───────────────────────────────────────────────────

/** Minimal shape shared by leaderboard rows and race trajectories. */
export interface NamedEntryRow {
	user_id: string;
	user_name: string;
	entry_name: string;
}

/** Users holding more than one entry on the board — drives whether the
 *  entry name is appended to the owner's name in row labels. Computed
 *  from the FULL row set (pool filtering must not change naming). */
export function multiEntryUserIds(rows: NamedEntryRow[]): Set<string> {
	const counts = new Map<string, number>();
	for (const r of rows) counts.set(r.user_id, (counts.get(r.user_id) ?? 0) + 1);
	return new Set([...counts.entries()].filter(([, n]) => n > 1).map(([id]) => id));
}

/** THE display-name rule, used by every leaderboard surface (standings,
 *  insights cards, race chart, drawer): "Person — Entry name" when the
 *  person holds several entries, otherwise just the person's name. */
export function rowDisplayName(row: NamedEntryRow, multiOwners: Set<string>): string {
	return multiOwners.has(row.user_id)
		? `${row.user_name} — ${row.entry_name}`
		: row.user_name;
}

// ── Column sorting (v2.168.0) ────────────────────────────────────────────

export type LbSortKey = 'entry' | 'group' | 'knockout' | 'total';

export interface LbSort {
	key: LbSortKey;
	dir: 'asc' | 'desc';
}

/** Default: highest total first, alphabetical on ties. */
export const DEFAULT_LB_SORT: LbSort = { key: 'total', dir: 'desc' };

function sortValue(row: LbEntryV4, key: LbSortKey): number {
	if (key === 'group') return groupPtsOf(row, row.bonus_group_points ?? 0);
	if (key === 'knockout') return koPtsOf(row, row.bonus_knockout_points ?? 0);
	return row.total_points;
}

/** Sort rows for the standings table. The `total` column ties-break on
 *  `position` ascending — the backend already resolved that tie via
 *  exact_scores (services/leaderboard.py) to assign position numbers,
 *  so re-breaking it alphabetically here would visually contradict the
 *  # column (e.g. #22 rendering above #21 because its name sorts
 *  earlier). `group`/`knockout` are derived sums the backend never
 *  ranks, so they still fall back to the display name; the Entry
 *  column sorts on the same rowDisplayName the cell renders. */
export function sortRows(
	rows: LbEntryV4[],
	sort: LbSort,
	multiOwners: Set<string>
): LbEntryV4[] {
	const flip = sort.dir === 'desc' ? -1 : 1;
	const byName = (a: LbEntryV4, b: LbEntryV4) =>
		rowDisplayName(a, multiOwners).localeCompare(rowDisplayName(b, multiOwners), undefined, {
			sensitivity: 'base'
		});
	return [...rows].sort((a, b) => {
		if (sort.key === 'entry') return flip * byName(a, b);
		const diff = sortValue(a, sort.key) - sortValue(b, sort.key);
		if (diff !== 0) return flip * diff;
		if (sort.key === 'total') return a.position - b.position; // backend's own tiebreak, direction-independent
		return byName(a, b); // ties always read A→Z
	});
}

/** Case- and accent-insensitive needle match (è≈e, ü≈u …). */
function foldText(s: string): string {
	return s
		.normalize('NFD')
		.replace(/[̀-ͯ]/g, '')
		.toLowerCase();
}

/** Filter rows on person OR entry name. Empty query returns rows as-is;
 *  global positions are never recomputed (same rule as pool filtering). */
export function searchRows(rows: LbEntryV4[], query: string): LbEntryV4[] {
	const q = foldText(query.trim());
	if (!q) return rows;
	return rows.filter(
		(r) => foldText(r.user_name).includes(q) || foldText(r.entry_name).includes(q)
	);
}

/** Two-character avatar initials from an entry name. */
export function initialsOf(name: string): string {
	const words = name.trim().split(/\s+/).filter(Boolean);
	if (words.length === 0) return '??';
	if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
	return (words[0][0] + words[1][0]).toUpperCase();
}

/** One-sentence drawer story line. */
export function storyLine(row: LbEntryV4): string {
	const parts: string[] = [];
	const move = row.daily_movement;
	if (move == null || move === 0) parts.push('Held steady since yesterday');
	else if (move > 0) parts.push(`Climbed ${move} since yesterday`);
	else parts.push(`Slipped ${Math.abs(move)} since yesterday`);

	if (row.champion_pick) {
		parts.push(
			row.champion_alive
				? `${row.champion_pick} title pick alive`
				: `${row.champion_pick} title pick out`
		);
	}
	const picks = row.finalist_picks?.length ?? 0;
	if (picks > 0) parts.push(`${row.finalists_alive ?? 0} of ${picks} finalists standing`);
	return parts.join(' · ');
}

/** "best is #n · m pts off the lead" inputs for the your-entries strip. */
export function bestOwnSummary(
	rows: LbEntryV4[],
	userId: string | null | undefined
): { bestRank: number; ptsOffLead: number } | null {
	if (!userId || rows.length === 0) return null;
	const own = rows.filter((r) => r.user_id === userId);
	if (own.length === 0) return null;
	const best = own.reduce((a, b) => (b.position < a.position ? b : a));
	const leadPts = Math.max(...rows.map((r) => r.total_points));
	return { bestRank: best.position, ptsOffLead: leadPts - best.total_points };
}

// ── Race-tab slicing ─────────────────────────────────────────────────────

const NEIGHBOURHOOD_RADIUS = 3;

/**
 * Selects the subset of trajectories that should render on the race chart for
 * the given view mode. The minimap markers are also returned so the chart's
 * minimap strip can render in a single derivation pass.
 *
 * - around_me: user's best-ranked entry ± 3 + all other user entries + leader (ghost if outside)
 * - top10 / top25: top N + all user entries (if outside top N)
 * - atlas / jmfa / guests: cohort filter ∪ user entries
 *
 * Signed-out (userId === null) or signed-in with zero entries: around_me
 * silently falls back to top10.
 */
export function selectRaceSlice(
	trajectories: EntryTrajectory[],
	mode: RaceViewMode,
	userId: string | null
): RaceSliceDescriptor {
	const all = trajectories
		.slice()
		.sort((a, b) => (a.points.at(-1)?.position ?? 0) - (b.points.at(-1)?.position ?? 0));
	const userEntries = userId ? all.filter((t) => t.user_id === userId) : [];

	// around_me falls back to top15 if user has no entries (signed-out OR zero entries)
	let effective = mode;
	if (mode === 'around_me' && userEntries.length === 0) {
		effective = 'top15';
	}

	let included: EntryTrajectory[];
	switch (effective) {
		case 'around_me': {
			const best = userEntries[0]; // sorted, so first is the best-ranked
			const bestRank = best!.points.at(-1)!.position;
			// Maintain a 7-line window (2 * radius + 1) — shift right when clamped at 1.
			const windowSize = NEIGHBOURHOOD_RADIUS * 2 + 1;
			const minR = Math.max(1, bestRank - NEIGHBOURHOOD_RADIUS);
			const maxR = minR + windowSize - 1;
			const slice = all.filter((t) => {
				const r = t.points.at(-1)?.position ?? Number.POSITIVE_INFINITY;
				return r >= minR && r <= maxR;
			});
			for (const ue of userEntries) {
				if (!slice.some((s) => s.entry_id === ue.entry_id)) slice.push(ue);
			}
			const leader = all[0];
			if (leader && !slice.some((s) => s.entry_id === leader.entry_id)) {
				slice.push(leader);
			}
			included = slice;
			break;
		}
		case 'top15': {
			const top = all.slice(0, 15);
			const merged = [...top];
			for (const ue of userEntries) {
				if (!merged.some((s) => s.entry_id === ue.entry_id)) merged.push(ue);
			}
			included = merged;
			break;
		}
	}

	const ranks = included
		.map((t) => t.points.at(-1)?.position)
		.filter((r): r is number => typeof r === 'number')
		.sort((a, b) => a - b);
	const minR = ranks[0] ?? 1;
	const maxR = ranks.at(-1) ?? 1;

	const minimapMarkers: MinimapMarker[] = [];
	const leader = all[0];
	if (leader) minimapMarkers.push({ rank: 1, kind: 'leader' });
	for (const ue of userEntries) {
		minimapMarkers.push({ rank: ue.points.at(-1)!.position, kind: 'you' });
	}

	return { included, minimapMarkers, rankRange: [minR, maxR] };
}

/** Renders a rank-delta as a string with ▲/▼ glyph. Zero → em-dash. */
export function composeRankDelta(delta: number): string {
	if (delta > 0) return `▲ ${delta}`;
	if (delta < 0) return `▼ ${-delta}`;
	return '—';
}

/** Personal Trail multi-entry helper — show first N entries by default
 *  (N defaults to 2 for back-compat with the existing test suite), with a
 *  "+N more" link to expand. The name is kept stale-but-stable rather than
 *  churning every call site. */
export function firstTwoPlusExpand<T>(
	items: T[],
	expanded: boolean,
	n: number = 2
): { visible: T[]; remaining: number } {
	if (expanded || items.length <= n) {
		return { visible: items, remaining: 0 };
	}
	return { visible: items.slice(0, n), remaining: items.length - n };
}
