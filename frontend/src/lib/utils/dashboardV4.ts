/**
 * V4 Dashboard pure derivations (v2.165.0).
 *
 * Everything here is a pure function over server data — unit-tested in
 * dashboardV4.test.ts. No stores, no fetches, no DOM. Mirrors the
 * leaderboardV4.ts pattern.
 *
 * third_place fixtures are excluded from EVERY dashboard surface (the
 * ★ invariant from v2.164.0 — the prediction game neither collects picks
 * for the bronze-medal playoff nor scores it).
 */

import type { BracketPrediction, Fixture } from '$types';
import type { MatchPredictionWithPoints, ScoringRules } from '$lib/types/results';
import type { LbEntryV4 } from '$lib/types/leaderboard';
import type {
	DashCall,
	DashPick,
	DashRoundChip,
	MatchdayStripItem,
	MoverRow
} from '$lib/types/dashboard';
import {
	NEXT_ROUND,
	ROUND_STAGE,
	deriveGroupMatchdays,
	roundIdForFixture
} from './resultsRounds';
import { bracketPicksForRound } from './koPoints';
import { displayRank, isRealTeam, multiEntryUserIds, rowDisplayName } from './leaderboardV4';
import { koFinalScore } from './matchDetailV4';
import { teamCode } from './teamCodes';

// ── Fixture bucketing ────────────────────────────────────────────────────

export interface DashBuckets {
	/** Live now + scheduled today (local calendar day), kickoff asc. */
	matchday: Fixture[];
	/** Next scheduled beyond today, kickoff asc, capped. */
	upcoming: Fixture[];
	/** Finished, most recent kickoff first, capped. */
	recent: Fixture[];
	/** Matchday strip contents: up to 1 most-recent finished game from
	 *  before today ('context'), all of today's fixtures ('today'), then
	 *  up to 2 of tomorrow's scheduled fixtures ('context'). Kickoff asc
	 *  within each flank. Empty when there's nothing to show at all. */
	strip: MatchdayStripItem[];
}

function isLive(f: Fixture): boolean {
	return f.status === 'live' || f.status === 'halftime';
}

function sameLocalDay(a: Date, b: Date): boolean {
	return (
		a.getFullYear() === b.getFullYear() &&
		a.getMonth() === b.getMonth() &&
		a.getDate() === b.getDate()
	);
}

/** Local midnight for `d`, optionally offset by whole days — used to bound
 *  "strictly before today" / "tomorrow" windows for the Matchday strip. */
function startOfLocalDay(d: Date, offsetDays = 0): Date {
	return new Date(d.getFullYear(), d.getMonth(), d.getDate() + offsetDays);
}

/** Split fixtures into the three dashboard tables plus the Matchday strip.
 *  `now` is a parameter (not Date.now()) so tests are deterministic. */
export function bucketDashboardFixtures(
	fixtures: Fixture[],
	now: Date,
	limits: { upcoming?: number; recent?: number } = {}
): DashBuckets {
	const upcomingCap = limits.upcoming ?? 5;
	const recentCap = limits.recent ?? 6;
	const eligible = fixtures.filter((f) => f.stage !== 'third_place');
	const asc = [...eligible].sort(
		(a, b) => new Date(a.kickoff).getTime() - new Date(b.kickoff).getTime()
	);

	// "Today" now includes finished-earlier-today matches too — the strip
	// gives users context on what already happened today, not just what's
	// live/upcoming.
	const matchday = asc.filter(
		(f) =>
			isLive(f) ||
			((f.status === 'scheduled' || f.status === 'finished') &&
				sameLocalDay(new Date(f.kickoff), now))
	);
	const matchdayIds = new Set(matchday.map((f) => f.id));

	// Left flank: the single most recent finished game from BEFORE today
	// (strictly, to avoid double-showing a finished-today match that's
	// already in `matchday`).
	const todayStart = startOfLocalDay(now);
	const recentBeforeToday = asc.filter(
		(f) => f.status === 'finished' && new Date(f.kickoff) < todayStart
	);
	const recentContext = recentBeforeToday.length
		? recentBeforeToday[recentBeforeToday.length - 1]
		: null;

	// Right flank: up to 2 of tomorrow's scheduled games, kickoff asc.
	const tomorrowStart = startOfLocalDay(now, 1);
	const nextDayContext = asc
		.filter((f) => f.status === 'scheduled' && sameLocalDay(new Date(f.kickoff), tomorrowStart))
		.slice(0, 2);
	const nextDayIds = new Set(nextDayContext.map((f) => f.id));

	const strip: MatchdayStripItem[] = [
		...(recentContext ? [{ fixture: recentContext, variant: 'context' as const }] : []),
		...matchday.map((f) => ({ fixture: f, variant: 'today' as const })),
		...nextDayContext.map((f) => ({ fixture: f, variant: 'context' as const }))
	];

	// Upcoming table excludes anything already promoted into the strip
	// (today's own fixtures, and the tomorrow flank) to avoid double-listing.
	const upcoming = asc
		.filter(
			(f) =>
				f.status === 'scheduled' &&
				!matchdayIds.has(f.id) &&
				!nextDayIds.has(f.id) &&
				new Date(f.kickoff).getTime() > now.getTime()
		)
		.slice(0, upcomingCap);
	const recent = asc
		.filter((f) => f.status === 'finished')
		.reverse()
		.slice(0, recentCap);

	return { matchday, upcoming, recent, strip };
}

// ── Row chrome ───────────────────────────────────────────────────────────

const STAGE_CHIP: Record<string, string> = {
	round_of_32: 'R32',
	round_of_16: 'R16',
	quarter_final: 'QF',
	semi_final: 'SF',
	final: 'F'
};

/** "9 Jul" — short local date for a kickoff ISO string. */
export function shortDate(iso: string): string {
	return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
}

/** Round chip + context label. Group rows: matchday chip + group name.
 *  KO rows: stage chip + short date. */
export function roundChipForFixture(
	f: Fixture,
	derivedMatchdays: Map<string, 1 | 2 | 3>
): DashRoundChip {
	if (f.stage === 'group') {
		const rid = roundIdForFixture(f, derivedMatchdays);
		return {
			chip: rid ? rid.toUpperCase() : 'GRP',
			sub: f.group ? `Group ${f.group}` : 'Group',
			isGroup: true
		};
	}
	return {
		chip: STAGE_CHIP[f.stage] ?? f.stage.toUpperCase(),
		sub: shortDate(f.kickoff),
		isGroup: false
	};
}

/** "Today · 21:00" / "Tomorrow · 18:00" / "Sat 14 Jun · 21:00" (local). */
export function kickoffLabel(iso: string, now: Date): string {
	const ko = new Date(iso);
	const time = ko.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
	if (sameLocalDay(ko, now)) return `Today · ${time}`;
	const tomorrow = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
	if (sameLocalDay(ko, tomorrow)) return `Tomorrow · ${time}`;
	const date = ko.toLocaleDateString('en-GB', {
		weekday: 'short',
		day: 'numeric',
		month: 'short'
	});
	return `${date} · ${time}`;
}

/** Scoreline + penalty values when the tie went to penalties. Null before
 *  any score exists. Primary home/away numbers are AET-inclusive (via
 *  koFinalScore) — a match won in extra time shows the AET score (e.g.
 *  3–2) rather than the misleading 90-min regulation score (2–2). */
export function scorelineOf(
	f: Fixture
): { home: number; away: number; pens: boolean; home_pen: number | null; away_pen: number | null } | null {
	if (!f.score) return null;
	const final = koFinalScore(f.score);
	if (!final) return null;
	return {
		home: final.home,
		away: final.away,
		pens: f.score.home_penalties != null && f.score.away_penalties != null,
		home_pen: f.score.home_penalties,
		away_pen: f.score.away_penalties
	};
}

// ── Picks & calls (selected entry) ───────────────────────────────────────

/** The bracket round whose picks pay on this fixture: the NEXT stage for
 *  R32..SF (advancement is "reaches stage X"), the champion pick for the
 *  final. Null for group / third_place / unknown. */
function payingPicksFor(f: Fixture, bracket: BracketPrediction | null): Set<string> | null {
	if (f.stage === 'group' || f.stage === 'third_place') return null;
	const rid = roundIdForFixture(f);
	if (!rid) return null;
	const nextId = NEXT_ROUND[rid];
	if (nextId) return bracketPicksForRound(bracket, nextId);
	// Final — the paying pick is the champion call.
	return bracket?.winner ? new Set([bracket.winner]) : new Set();
}

/** Points the paying pick is worth on this fixture (next-stage value for
 *  R32..SF, the winner credit for the final). */
export function koCallValue(f: Fixture, rules: ScoringRules): number {
	const rid = roundIdForFixture(f);
	if (!rid) return 0;
	const nextId = NEXT_ROUND[rid];
	if (nextId) {
		const stage = ROUND_STAGE[nextId];
		return stage ? rules.advancement[stage] ?? 0 : 0;
	}
	return rules.advancement.winner;
}

/** Winner of a finished fixture, null otherwise (or for draws — a
 *  finished knockout always resolves via ET/pens). */
export function winnerOf(f: Fixture): string | null {
	if (f.status !== 'finished' || !f.score) return null;
	if (f.score.outcome === '1') return f.home_team;
	if (f.score.outcome === '2') return f.away_team;
	return null;
}

/** The selected entry's pick for an unfinished fixture. Group → score
 *  chip; KO → the team (of the two playing) the entry picked to advance.
 *  When both teams are in the entry's next-round picks (possible with a
 *  different predicted pairing) the home side is shown — one of the two
 *  is guaranteed to pay either way. */
export function dashPickFor(
	f: Fixture,
	prediction: MatchPredictionWithPoints | undefined,
	bracket: BracketPrediction | null
): DashPick {
	if (f.stage === 'group') {
		if (!prediction) return { kind: 'none' };
		return { kind: 'score', label: `${prediction.home_score}–${prediction.away_score}` };
	}
	const picks = payingPicksFor(f, bracket);
	if (!picks || picks.size === 0) return { kind: 'none' };
	const team = picks.has(f.home_team)
		? f.home_team
		: picks.has(f.away_team)
		? f.away_team
		: null;
	if (!team || !isRealTeam(team)) return { kind: 'none' };
	return { kind: 'team', team, tla: teamCode(team) };
}

/** The selected entry's graded call + points for a FINISHED fixture. */
export function dashCallFor(
	f: Fixture,
	prediction: MatchPredictionWithPoints | undefined,
	bracket: BracketPrediction | null,
	rules: ScoringRules
): DashCall {
	if (f.stage === 'group') {
		if (!prediction) return { kind: 'none', pts: 0 };
		const grade = prediction.points?.base_kind ?? 'miss';
		return {
			kind: 'score',
			label: `${prediction.home_score}–${prediction.away_score}`,
			grade,
			pts: prediction.points?.total ?? 0
		};
	}
	const picks = payingPicksFor(f, bracket);
	if (!picks || picks.size === 0) return { kind: 'none', pts: 0 };
	const winner = winnerOf(f);
	// Prefer the side that won when both teams were picked to advance.
	const team =
		winner && picks.has(winner)
			? winner
			: picks.has(f.home_team)
			? f.home_team
			: picks.has(f.away_team)
			? f.away_team
			: null;
	if (!team || !isRealTeam(team)) return { kind: 'none', pts: 0 };
	const hit = winner != null && team === winner;
	return {
		kind: 'team',
		team,
		tla: teamCode(team),
		hit,
		pts: hit ? koCallValue(f, rules) : 0
	};
}

// ── Entry bar totals ─────────────────────────────────────────────────────

/** Group column total = sum of banked match points (group fixtures are
 *  the only score predictions in this competition). */
export function groupTotalFromPredictions(predictions: MatchPredictionWithPoints[]): number {
	return predictions.reduce((sum, p) => sum + (p.points?.total ?? 0), 0);
}

/** Knockout total — lineup-banked: every pick seeded into a KO round's
 *  real-team lineup pays that round's stage value, plus the winner credit
 *  once the final is finished. Mirrors the V4 Results top-card maths. */
export function koTotalFromFixtures(
	fixtures: Fixture[],
	bracket: BracketPrediction | null,
	rules: ScoringRules | null
): number {
	if (!rules || !bracket) return 0;
	let total = 0;
	let finalFixture: Fixture | null = null;
	for (const f of fixtures) {
		if (f.stage === 'group' || f.stage === 'third_place') continue;
		const rid = roundIdForFixture(f);
		if (!rid) continue;
		if (f.stage === 'final') finalFixture = f;
		if (!isRealTeam(f.home_team) || !isRealTeam(f.away_team)) continue;
		const picks = bracketPicksForRound(bracket, rid);
		const stage = ROUND_STAGE[rid];
		const stagePts = stage ? rules.advancement[stage] ?? 0 : 0;
		if (picks.has(f.home_team)) total += stagePts;
		if (picks.has(f.away_team)) total += stagePts;
	}
	if (finalFixture) {
		const champion = winnerOf(finalFixture);
		if (champion && bracket.winner === champion) total += rules.advancement.winner;
	}
	return total;
}

// ── Leaderboard panels ───────────────────────────────────────────────────

/** Mini-leaderboard split: the user's own rows (rank order) + the global
 *  top N. Own rows keep their server positions. */
export function miniLbRows(
	rows: LbEntryV4[],
	userId: string | null | undefined,
	topN = 10,
	live = false
): { yours: LbEntryV4[]; top: LbEntryV4[] } {
	const yours = userId
		? rows
				.filter((r) => r.user_id === userId)
				.sort((a, b) => displayRank(a, live) - displayRank(b, live))
		: [];
	return { yours, top: rows.slice(0, topN) };
}

/** Movers since yesterday: top `cap` climbers and sliders by
 *  |daily_movement|, zero/null excluded. Labels follow THE naming rule
 *  (rowDisplayName over the unfiltered board). */
export function moversOf(rows: LbEntryV4[], cap = 5): { climbing: MoverRow[]; sliding: MoverRow[] } {
	const multiOwners = multiEntryUserIds(rows);
	const moved = rows.filter((r) => (r.daily_movement ?? 0) !== 0);
	const toRow = (r: LbEntryV4): MoverRow => ({
		entry_id: r.entry_id,
		label: rowDisplayName(r, multiOwners),
		move: r.daily_movement ?? 0
	});
	const climbing = moved
		.filter((r) => (r.daily_movement ?? 0) > 0)
		.sort((a, b) => (b.daily_movement ?? 0) - (a.daily_movement ?? 0))
		.slice(0, cap)
		.map(toRow);
	const sliding = moved
		.filter((r) => (r.daily_movement ?? 0) < 0)
		.sort((a, b) => (a.daily_movement ?? 0) - (b.daily_movement ?? 0))
		.slice(0, cap)
		.map(toRow);
	return { climbing, sliding };
}

// ── Greeting ─────────────────────────────────────────────────────────────

/** "Thu 11 Jun 2026" — live-formatted en-GB date for the greeting line. */
export function greetingDate(now: Date): string {
	return now.toLocaleDateString('en-GB', {
		weekday: 'short',
		day: 'numeric',
		month: 'short',
		year: 'numeric'
	});
}

/** First name for "Welcome back, X" — first whitespace-separated word. */
export function firstNameOf(name: string | null | undefined): string {
	const trimmed = (name ?? '').trim();
	if (!trimmed) return 'there';
	return trimmed.split(/\s+/)[0];
}

export { deriveGroupMatchdays };
