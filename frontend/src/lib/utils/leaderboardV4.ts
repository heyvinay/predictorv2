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
	LbEntryV4,
	LbPool,
	LbStage
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

const PLACEHOLDER_RE = /^(winner|loser|runner|1[a-l]|2[a-l]|3[a-l])\b/i;

/** True when a fixture lineup slot holds a real team rather than a
 *  Football-Data placeholder ("Winner of Match 12", "1A", empty). */
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

/** Where an entry's points come from. exact + result + rarity + bracket +
 *  bonus === breakdown.total (server-computed fields). */
export function dnaOf(breakdown: PointBreakdown): DnaSplit {
	return {
		exact: breakdown.exact_score_points,
		result: breakdown.match_outcome_points,
		rarity: breakdown.hybrid_bonus_points,
		bracket: breakdown.bracket_total,
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

/** Sort rows for the standings table. Numeric columns tie-break on the
 *  display name (A→Z regardless of direction); the Entry column sorts on
 *  the same rowDisplayName the cell renders. Server `position` values
 *  ride along untouched — global ranks must survive any sort order. */
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
