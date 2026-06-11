import { describe, expect, it } from 'vitest';
import type { BracketPrediction, Fixture } from '$types';
import type { MatchPredictionWithPoints, ScoringRules } from '$lib/types/results';
import type { LbEntryV4 } from '$lib/types/leaderboard';
import {
	bucketDashboardFixtures,
	dashCallFor,
	dashPickFor,
	firstNameOf,
	groupTotalFromPredictions,
	kickoffLabel,
	koCallValue,
	koTotalFromFixtures,
	miniLbRows,
	moversOf,
	roundChipForFixture,
	scorelineOf,
	winnerOf
} from './dashboardV4';
import { deriveGroupMatchdays } from './resultsRounds';

// NOTE: vitest runs in the frontend-dev container (UTC), and every
// "same day" assertion below keeps kickoff and `now` hours away from
// midnight so the local-day comparison can't flip across timezones.

const NOW = new Date('2026-06-28T12:00:00+00:00');

function fx(partial: Partial<Fixture>): Fixture {
	return {
		id: partial.id ?? crypto.randomUUID(),
		home_team: 'Mexico',
		away_team: 'Senegal',
		kickoff: '2026-06-28T18:00:00+00:00',
		stage: 'round_of_32',
		group: null,
		match_number: null,
		status: 'scheduled',
		minute: null,
		is_locked: true,
		time_until_lock: null,
		score: null,
		...partial
	} as Fixture;
}

function finished(partial: Partial<Fixture>, home: number, away: number, pens = false): Fixture {
	return fx({
		status: 'finished',
		score: {
			home_score: home,
			away_score: away,
			home_score_et: null,
			away_score_et: null,
			home_penalties: pens ? 4 : null,
			away_penalties: pens ? 3 : null,
			outcome: home > away ? '1' : away > home ? '2' : pens ? '1' : 'X'
		},
		...partial
	} as Partial<Fixture>);
}

const BRACKET: BracketPrediction = {
	group_winners: {},
	round_of_32: ['Mexico', 'Senegal', 'Brazil', 'Italy'],
	round_of_16: ['Mexico', 'Brazil'],
	quarter_finals: ['Brazil', 'France'],
	semi_finals: ['Brazil', 'France'],
	final: ['Brazil', 'France'],
	winner: 'Brazil'
};

const RULES: ScoringRules = {
	mode: 'logarithmic',
	match: { correct_outcome: 2, exact_score: 3, rarity_cap: 4 },
	advancement: {
		round_of_32: 1,
		round_of_16: 2,
		quarter_final: 4,
		semi_final: 8,
		final: 16,
		winner: 32
	}
};

function pred(
	fixtureId: string,
	home: number,
	away: number,
	points: MatchPredictionWithPoints['points'] = null
): MatchPredictionWithPoints {
	return {
		id: crypto.randomUUID(),
		fixture_id: fixtureId,
		home_score: home,
		away_score: away,
		points
	} as MatchPredictionWithPoints;
}

// ── bucketDashboardFixtures ──────────────────────────────────────────────

describe('bucketDashboardFixtures', () => {
	it('splits live/today vs upcoming vs recent', () => {
		const live = fx({ id: 'live', status: 'live', kickoff: '2026-06-28T11:00:00+00:00' });
		const tonight = fx({ id: 'tonight', kickoff: '2026-06-28T19:00:00+00:00' });
		const tomorrow = fx({ id: 'tomorrow', kickoff: '2026-06-29T18:00:00+00:00' });
		const done = finished({ id: 'done', kickoff: '2026-06-27T18:00:00+00:00' }, 2, 1);

		const b = bucketDashboardFixtures([tomorrow, done, tonight, live], NOW);
		expect(b.matchday.map((f) => f.id)).toEqual(['live', 'tonight']);
		expect(b.upcoming.map((f) => f.id)).toEqual(['tomorrow']);
		expect(b.recent.map((f) => f.id)).toEqual(['done']);
	});

	it('orders recent results most recent first and caps both lists', () => {
		const finishedFixtures = [1, 2, 3, 4, 5, 6, 7].map((d) =>
			finished({ id: `f${d}`, kickoff: `2026-06-${10 + d}T18:00:00+00:00` }, 1, 0)
		);
		const scheduled = [1, 2, 3, 4, 5, 6].map((d) =>
			fx({ id: `s${d}`, kickoff: `2026-07-0${d}T18:00:00+00:00` })
		);
		const b = bucketDashboardFixtures([...finishedFixtures, ...scheduled], NOW, {
			upcoming: 3,
			recent: 4
		});
		expect(b.recent.map((f) => f.id)).toEqual(['f7', 'f6', 'f5', 'f4']);
		expect(b.upcoming.map((f) => f.id)).toEqual(['s1', 's2', 's3']);
	});

	it('excludes third_place from every bucket (★ invariant)', () => {
		const bronzeToday = fx({
			id: 'bronze',
			stage: 'third_place',
			kickoff: '2026-06-28T16:00:00+00:00'
		});
		const bronzeDone = finished(
			{ id: 'bronze2', stage: 'third_place', kickoff: '2026-06-20T18:00:00+00:00' },
			1,
			0
		);
		const b = bucketDashboardFixtures([bronzeToday, bronzeDone], NOW);
		expect(b.matchday).toEqual([]);
		expect(b.upcoming).toEqual([]);
		expect(b.recent).toEqual([]);
	});

	it('does not list past-kickoff scheduled fixtures as upcoming', () => {
		const stale = fx({ id: 'stale', kickoff: '2026-06-27T10:00:00+00:00' });
		const b = bucketDashboardFixtures([stale], NOW);
		expect(b.upcoming).toEqual([]);
	});
});

// ── roundChipForFixture ──────────────────────────────────────────────────

describe('roundChipForFixture', () => {
	it('labels group fixtures with derived matchday + group', () => {
		const g1 = fx({
			id: 'g1',
			stage: 'group',
			group: 'D',
			home_team: 'USA',
			away_team: 'Paraguay',
			kickoff: '2026-06-12T18:00:00+00:00'
		});
		const g2 = fx({
			id: 'g2',
			stage: 'group',
			group: 'D',
			home_team: 'USA',
			away_team: 'Haiti',
			kickoff: '2026-06-18T18:00:00+00:00'
		});
		const md = deriveGroupMatchdays([g1, g2]);
		expect(roundChipForFixture(g1, md)).toEqual({ chip: 'R1', sub: 'Group D', isGroup: true });
		expect(roundChipForFixture(g2, md)).toEqual({ chip: 'R2', sub: 'Group D', isGroup: true });
	});

	it('labels knockout fixtures with stage chip + short date', () => {
		const qf = fx({ stage: 'quarter_final', kickoff: '2026-07-09T19:00:00+00:00' });
		const chip = roundChipForFixture(qf, new Map());
		expect(chip.chip).toBe('QF');
		expect(chip.isGroup).toBe(false);
		expect(chip.sub).toMatch(/9 Jul/);
	});
});

// ── kickoffLabel ─────────────────────────────────────────────────────────

describe('kickoffLabel', () => {
	it('says Today / Tomorrow / full date', () => {
		expect(kickoffLabel('2026-06-28T19:00:00+00:00', NOW)).toMatch(/^Today · /);
		expect(kickoffLabel('2026-06-29T12:00:00+00:00', NOW)).toMatch(/^Tomorrow · /);
		expect(kickoffLabel('2026-07-04T12:00:00+00:00', NOW)).toMatch(/^Sat 4 Jul · /);
	});
});

// ── scoreline / winner ───────────────────────────────────────────────────

describe('scorelineOf / winnerOf', () => {
	it('returns null without a score', () => {
		expect(scorelineOf(fx({}))).toBeNull();
		expect(winnerOf(fx({}))).toBeNull();
	});

	it('marks penalty shootouts', () => {
		const f = finished({ home_team: 'France', away_team: 'Germany' }, 1, 1, true);
		expect(scorelineOf(f)).toEqual({ home: 1, away: 1, pens: true });
		expect(winnerOf(f)).toBe('France'); // outcome '1' via pens
	});

	it('resolves the winner from the outcome', () => {
		const f = finished({ home_team: 'Brazil', away_team: 'Argentina' }, 2, 1);
		expect(winnerOf(f)).toBe('Brazil');
	});
});

// ── dashPickFor ──────────────────────────────────────────────────────────

describe('dashPickFor', () => {
	it('returns the score chip for group fixtures', () => {
		const g = fx({ id: 'g', stage: 'group', group: 'A' });
		expect(dashPickFor(g, pred('g', 2, 2), BRACKET)).toEqual({ kind: 'score', label: '2–2' });
		expect(dashPickFor(g, undefined, BRACKET)).toEqual({ kind: 'none' });
	});

	it('returns the next-round bracket call for KO fixtures', () => {
		// QF fixture: paying picks are the SEMI-final picks.
		const qf = fx({ stage: 'quarter_final', home_team: 'Brazil', away_team: 'Argentina' });
		expect(dashPickFor(qf, undefined, BRACKET)).toEqual({
			kind: 'team',
			team: 'Brazil',
			tla: 'BRA'
		});
	});

	it('uses the champion pick on the final', () => {
		const final = fx({ stage: 'final', home_team: 'Brazil', away_team: 'France' });
		expect(dashPickFor(final, undefined, BRACKET)).toEqual({
			kind: 'team',
			team: 'Brazil',
			tla: 'BRA'
		});
	});

	it('returns none when neither team was picked', () => {
		const qf = fx({ stage: 'quarter_final', home_team: 'Ghana', away_team: 'Japan' });
		expect(dashPickFor(qf, undefined, BRACKET)).toEqual({ kind: 'none' });
	});
});

// ── dashCallFor ──────────────────────────────────────────────────────────

describe('dashCallFor', () => {
	it('grades group calls from server points', () => {
		const g = finished({ id: 'g', stage: 'group', group: 'C' }, 2, 1);
		const exact = pred('g', 2, 1, { base: 5, base_kind: 'exact', rarity: 2, total: 7 });
		expect(dashCallFor(g, exact, BRACKET, RULES)).toEqual({
			kind: 'score',
			label: '2–1',
			grade: 'exact',
			pts: 7
		});
		const miss = pred('g', 0, 1, { base: 0, base_kind: 'miss', rarity: 0, total: 0 });
		expect(dashCallFor(g, miss, BRACKET, RULES)).toMatchObject({ grade: 'miss', pts: 0 });
	});

	it('pays the next-stage value when the KO call wins', () => {
		const qf = finished(
			{ stage: 'quarter_final', home_team: 'Brazil', away_team: 'Argentina' },
			2,
			1
		);
		// Brazil is in the SF picks → hit pays advancement.semi_final.
		expect(dashCallFor(qf, undefined, BRACKET, RULES)).toEqual({
			kind: 'team',
			team: 'Brazil',
			tla: 'BRA',
			hit: true,
			pts: RULES.advancement.semi_final
		});
	});

	it('shows the losing call with zero points', () => {
		const qf = finished(
			{ stage: 'quarter_final', home_team: 'Argentina', away_team: 'Brazil' },
			2,
			1
		);
		// Brazil picked for SF but Argentina won.
		expect(dashCallFor(qf, undefined, BRACKET, RULES)).toMatchObject({
			team: 'Brazil',
			hit: false,
			pts: 0
		});
	});

	it('prefers the winning side when both teams were picked to advance', () => {
		const qf = finished(
			{ stage: 'quarter_final', home_team: 'France', away_team: 'Brazil' },
			0,
			2
		);
		// Both France and Brazil sit in the SF picks; Brazil won.
		expect(dashCallFor(qf, undefined, BRACKET, RULES)).toMatchObject({
			team: 'Brazil',
			hit: true
		});
	});

	it('pays the winner credit on the final', () => {
		const final = finished({ stage: 'final', home_team: 'Brazil', away_team: 'France' }, 1, 0);
		expect(dashCallFor(final, undefined, BRACKET, RULES)).toMatchObject({
			team: 'Brazil',
			hit: true,
			pts: RULES.advancement.winner
		});
	});
});

// ── koCallValue ──────────────────────────────────────────────────────────

describe('koCallValue', () => {
	it('uses the NEXT stage value for R32..SF and winner for the final', () => {
		expect(koCallValue(fx({ stage: 'round_of_32' }), RULES)).toBe(RULES.advancement.round_of_16);
		expect(koCallValue(fx({ stage: 'semi_final' }), RULES)).toBe(RULES.advancement.final);
		expect(koCallValue(fx({ stage: 'final' }), RULES)).toBe(RULES.advancement.winner);
	});
});

// ── totals ───────────────────────────────────────────────────────────────

describe('groupTotalFromPredictions / koTotalFromFixtures', () => {
	it('sums banked match points', () => {
		const preds = [
			pred('a', 1, 0, { base: 2, base_kind: 'result', rarity: 1, total: 3 }),
			pred('b', 2, 2, null),
			pred('c', 0, 3, { base: 5, base_kind: 'exact', rarity: 0, total: 5 })
		];
		expect(groupTotalFromPredictions(preds)).toBe(8);
	});

	it('banks lineup-seeded KO picks at stage value', () => {
		const fixtures = [
			// Both R16 picks seeded into R16 fixtures → 2 × advancement.round_of_16.
			fx({ stage: 'round_of_16', home_team: 'Mexico', away_team: 'Ghana' }),
			fx({ stage: 'round_of_16', home_team: 'Brazil', away_team: 'Japan' }),
			// Placeholder lineup → no banking yet.
			fx({ stage: 'quarter_final', home_team: 'Winner of Match 49', away_team: '1A' })
		];
		expect(koTotalFromFixtures(fixtures, BRACKET, RULES)).toBe(2 * RULES.advancement.round_of_16);
	});

	it('adds the winner credit once the final is finished', () => {
		const fixtures = [
			finished({ stage: 'final', home_team: 'Brazil', away_team: 'France' }, 2, 0)
		];
		// Brazil + France both in final picks (2 × 16) + winner credit 32.
		expect(koTotalFromFixtures(fixtures, BRACKET, RULES)).toBe(
			2 * RULES.advancement.final + RULES.advancement.winner
		);
	});

	it('ignores third_place and returns 0 without a bracket', () => {
		const bronze = fx({ stage: 'third_place', home_team: 'Mexico', away_team: 'Brazil' });
		expect(koTotalFromFixtures([bronze], BRACKET, RULES)).toBe(0);
		expect(koTotalFromFixtures([], null, RULES)).toBe(0);
	});
});

// ── leaderboard panels ───────────────────────────────────────────────────

function lbRow(partial: Partial<LbEntryV4>): LbEntryV4 {
	return {
		entry_id: partial.entry_id ?? crypto.randomUUID(),
		entry_name: 'Entry 1',
		user_id: 'u1',
		user_name: 'Sam',
		position: 1,
		total_points: 100,
		movement: 0,
		correct_outcomes: 0,
		exact_scores: 0,
		daily_movement: 0,
		...partial
	} as LbEntryV4;
}

describe('miniLbRows', () => {
	it('pins own rows and slices the global top N', () => {
		const rows = [
			lbRow({ entry_id: 'e1', position: 1, user_id: 'other1', user_name: 'Ana' }),
			lbRow({ entry_id: 'e2', position: 2, user_id: 'me', user_name: 'Sam' }),
			lbRow({ entry_id: 'e3', position: 3, user_id: 'other2', user_name: 'Bo' }),
			lbRow({ entry_id: 'e4', position: 4, user_id: 'me', user_name: 'Sam' })
		];
		const { yours, top } = miniLbRows(rows, 'me', 3);
		expect(yours.map((r) => r.entry_id)).toEqual(['e2', 'e4']);
		expect(top.map((r) => r.entry_id)).toEqual(['e1', 'e2', 'e3']);
	});

	it('handles a missing user id', () => {
		const { yours, top } = miniLbRows([lbRow({})], null, 10);
		expect(yours).toEqual([]);
		expect(top).toHaveLength(1);
	});
});

describe('moversOf', () => {
	it('splits climbers and sliders, sorted by |move|, capped', () => {
		const rows = [
			lbRow({ entry_id: 'a', user_id: 'ua', user_name: 'A', daily_movement: 4 }),
			lbRow({ entry_id: 'b', user_id: 'ub', user_name: 'B', daily_movement: -2 }),
			lbRow({ entry_id: 'c', user_id: 'uc', user_name: 'C', daily_movement: 9 }),
			lbRow({ entry_id: 'd', user_id: 'ud', user_name: 'D', daily_movement: 0 }),
			lbRow({ entry_id: 'e', user_id: 'ue', user_name: 'E', daily_movement: null }),
			lbRow({ entry_id: 'f', user_id: 'uf', user_name: 'F', daily_movement: -7 })
		];
		const { climbing, sliding } = moversOf(rows, 1);
		expect(climbing).toEqual([{ entry_id: 'c', label: 'C', move: 9 }]);
		expect(sliding).toEqual([{ entry_id: 'f', label: 'F', move: -7 }]);
	});

	it('labels multi-entry owners with the entry name (THE naming rule)', () => {
		const rows = [
			lbRow({ entry_id: 'a', user_id: 'me', user_name: 'Sam', entry_name: 'Samba', daily_movement: 3 }),
			lbRow({ entry_id: 'b', user_id: 'me', user_name: 'Sam', entry_name: 'Wildcard', daily_movement: 1 })
		];
		const { climbing } = moversOf(rows);
		expect(climbing.map((r) => r.label)).toEqual(['Sam — Samba', 'Sam — Wildcard']);
	});
});

// ── greeting ─────────────────────────────────────────────────────────────

describe('firstNameOf', () => {
	it('takes the first word, with a fallback', () => {
		expect(firstNameOf('Vinay Mistry')).toBe('Vinay');
		expect(firstNameOf('  Cher ')).toBe('Cher');
		expect(firstNameOf(null)).toBe('there');
		expect(firstNameOf('')).toBe('there');
	});
});
