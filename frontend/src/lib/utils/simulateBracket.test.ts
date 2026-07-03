/**
 * What-if bracket simulator — pure engine tests.
 *
 * Mirrors the `fx()` fixture-builder pattern from `koPoints.test.ts`. The
 * headline test is a PARITY check: with an empty hypothetical-winners map,
 * `resolveScenario` + `rescoreEntryKo` must agree with the authoritative
 * fixture-based KO scoring (`fixtureKoHits` + `stagePointsForRound`, the
 * same primitives `computeKoTotal` in `routes/results/+page.svelte` uses)
 * over the same fixtures. If the two ever disagree, the simulator would
 * show a different "current" total than the real Results page before the
 * user has even touched a what-if control — silently eroding trust in the
 * feature. Rather than duplicating `computeKoTotal`'s glue in the test
 * (import boundary — it lives in a `.svelte` route module), the test
 * reimplements the same fixture-walk directly from `fixtureKoHits`, which
 * is the exact function `computeKoTotal` delegates its per-fixture-hit
 * logic to; the only thing `computeKoTotal` adds on top is the `winner`
 * bonus, which is asserted separately.
 */

import { describe, expect, it } from 'vitest';
import type { BracketPrediction, Fixture } from '$types';
import type { RoundId } from '$lib/types/results';
import type { HypoWinners, SimulatorBracketPicks, SimulatorEntryPicks } from '$lib/types/simulator';
import { fixtureKoHits, stagePointsForRound } from './koPoints';
import {
	fillFromMyPicks,
	pivotalMatches,
	projectStandings,
	rankOf,
	rescoreEntryKo,
	resolveScenario
} from './simulateBracket';

const ADV: Record<string, number> = {
	round_of_32: 20,
	round_of_16: 30,
	quarter_final: 40,
	semi_final: 50,
	final: 75,
	winner: 100
};

const KO_ROUNDS: RoundId[] = ['r32', 'r16', 'qf', 'sf', 'f'];

/** `buildMatchNumberIndex` (bracketGeometry.ts) reads `external_id` off
 *  R32 fixtures via a `Fixture & { external_id }` cast, so our R32 fixture
 *  literals must carry that property. We accept it on the builder's partial
 *  and cast through this widened type. */
type FixtureWithExt = Fixture & { external_id?: string | null };

function fx(partial: Partial<FixtureWithExt>): FixtureWithExt {
	return {
		id: partial.id ?? crypto.randomUUID(),
		home_team: 'TeamA',
		away_team: 'TeamB',
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
	} as FixtureWithExt;
}

function finishedScore(outcome: '1' | '2'): Fixture['score'] {
	return {
		home_score: outcome === '1' ? 2 : 0,
		away_score: outcome === '1' ? 0 : 2,
		home_score_et: null,
		away_score_et: null,
		home_penalties: null,
		away_penalties: null,
		outcome
	} as Fixture['score'];
}

/**
 * A partially-played KO bracket:
 *  - M73 (R32) FINISHED: Mexico beats Senegal.
 *  - M74 (R32) FINISHED: Brazil beats Italy.
 *  - M75-88 (R32) still scheduled, real group-stage teams seeded, no score.
 *  - M89 (R16 = winner 74 vs winner 77): home resolved to Brazil (M74
 *    finished), away still a slot placeholder (M77 hasn't been played).
 *    This models what the KO lineup resolver would actually produce.
 *  - M90 (R16 = winner 73 vs winner 75): home resolved to Mexico, away
 *    still a slot placeholder (M75 unplayed).
 *  - Remaining R16 (91-96), QF (97-100), SF (101-102), Final (104): fully
 *    unresolved slot placeholders on both sides.
 */
/** R32 external_id -> FIFA match number, mirrored from
 *  `R32_EXT_ID_TO_MATCH_NUMBER` in `bracketGeometry.ts`.
 *  `buildMatchNumberIndex` resolves R32 fixtures SOLELY via this map, so
 *  each R32 fixture MUST carry the matching `external_id`. */
const R32_MATCH_TO_EXT_ID: Record<number, string> = {
	73: '537417',
	74: '537415',
	75: '537418',
	76: '537423',
	77: '537416',
	78: '537424',
	79: '537425',
	80: '537426',
	81: '537421',
	82: '537422',
	83: '537419',
	84: '537420',
	85: '537429',
	86: '537427',
	87: '537430',
	88: '537428'
};

/** Build an ascending kickoff timestamp so kickoff-sorted index maps to the
 *  intended match number. `buildMatchNumberIndex` sorts each R16+ stage by
 *  `kickoff.localeCompare` (LEXICAL string comparison), then assigns
 *  base+i. We encode the match number as a fixed-width (3-digit) zero-padded
 *  millisecond field on a fixed date/time, so lexical order == numeric order
 *  (fixed width is what makes "089" < "090" < "104" sort correctly, unlike
 *  variable-width "89"/"104" where "104" would sort before "89"). Only
 *  ordering WITHIN a stage matters for the index. */
function kickoffFor(matchNumber: number): string {
	const ms = String(matchNumber).padStart(3, '0'); // 73..104 -> "073".."104"
	return `2026-07-01T18:00:00.${ms}+00:00`;
}

function buildPartialBracketFixtures(): Fixture[] {
	const fixtures: FixtureWithExt[] = [];

	// R32 — matches 73..88. Only 73/74 are finished; rest scheduled with
	// real (non-placeholder) team names since R32 always seeds off group
	// standings directly. Each carries its `external_id` so
	// `buildMatchNumberIndex` can locate it.
	const r32Teams: Record<number, [string, string]> = {
		73: ['Mexico', 'Senegal'],
		74: ['Brazil', 'Italy'],
		75: ['France', 'Japan'],
		76: ['Portugal', 'Morocco'],
		77: ['Argentina', 'Poland'],
		78: ['England', 'Uruguay'],
		79: ['Germany', 'Ghana'],
		80: ['Belgium', 'Canada'],
		81: ['Netherlands', 'Tunisia'],
		82: ['Croatia', 'Iran'],
		83: ['Spain', 'Costa Rica'],
		84: ['Switzerland', 'Cameroon'],
		85: ['USA', 'Wales'],
		86: ['Denmark', 'Qatar'],
		87: ['Serbia', 'Ecuador'],
		88: ['Australia', 'Saudi Arabia']
	};
	for (const [numStr, [home, away]] of Object.entries(r32Teams)) {
		const num = Number(numStr);
		const isFinished = num === 73 || num === 74;
		fixtures.push(
			fx({
				id: `m${num}`,
				external_id: R32_MATCH_TO_EXT_ID[num],
				home_team: home,
				away_team: away,
				kickoff: kickoffFor(num),
				stage: 'round_of_32',
				status: isFinished ? 'finished' : 'scheduled',
				score: isFinished ? finishedScore('1') : null // home always wins when finished
			})
		);
	}

	// R16 — matches 89..96 (singular stage 'round_of_16', kickoff-ordered).
	// Only 89/90 have a resolved home side (from M74/M73 winners); everything
	// else is fully unresolved. The stored home/away must match the engine's
	// config-derived participants for the parity oracle to agree:
	//   M89 = winner(74)=Brazil (home) vs winner(77)=? (away, unplayed -> slot)
	//   M90 = winner(73)=Mexico (home) vs winner(75)=? (away, unplayed -> slot)
	const r16: Array<{ num: number; home: string; away: string }> = [
		{ num: 89, home: 'Brazil', away: 'slot:round_of_16:89:away' },
		{ num: 90, home: 'Mexico', away: 'slot:round_of_16:90:away' },
		{ num: 91, home: 'slot:round_of_16:91:home', away: 'slot:round_of_16:91:away' },
		{ num: 92, home: 'slot:round_of_16:92:home', away: 'slot:round_of_16:92:away' },
		{ num: 93, home: 'slot:round_of_16:93:home', away: 'slot:round_of_16:93:away' },
		{ num: 94, home: 'slot:round_of_16:94:home', away: 'slot:round_of_16:94:away' },
		{ num: 95, home: 'slot:round_of_16:95:home', away: 'slot:round_of_16:95:away' },
		{ num: 96, home: 'slot:round_of_16:96:home', away: 'slot:round_of_16:96:away' }
	];
	for (const { num, home, away } of r16) {
		fixtures.push(
			fx({
				id: `m${num}`,
				home_team: home,
				away_team: away,
				kickoff: kickoffFor(num),
				stage: 'round_of_16'
			})
		);
	}

	// QF 97-100 ('quarter_final'), SF 101-102 ('semi_final'), Final 104
	// ('final') — fully unresolved, kickoff-ordered.
	for (const num of [97, 98, 99, 100]) {
		fixtures.push(
			fx({
				id: `m${num}`,
				home_team: `slot:quarter_final:${num}:home`,
				away_team: `slot:quarter_final:${num}:away`,
				kickoff: kickoffFor(num),
				stage: 'quarter_final'
			})
		);
	}
	for (const num of [101, 102]) {
		fixtures.push(
			fx({
				id: `m${num}`,
				home_team: `slot:semi_final:${num}:home`,
				away_team: `slot:semi_final:${num}:away`,
				kickoff: kickoffFor(num),
				stage: 'semi_final'
			})
		);
	}
	fixtures.push(
		fx({
			id: 'm104',
			home_team: 'slot:final:104:home',
			away_team: 'slot:final:104:away',
			kickoff: kickoffFor(104),
			stage: 'final'
		})
	);

	return fixtures;
}

/** Round -> its fixtures, for the direct fixture-based recomputation. */
function fixturesByRound(fixtures: Fixture[]): Record<RoundId, Fixture[]> {
	const stageOf: Record<string, RoundId> = {
		round_of_32: 'r32',
		round_of_16: 'r16',
		quarter_final: 'qf',
		semi_final: 'sf',
		final: 'f'
	};
	const out: Record<string, Fixture[]> = { r32: [], r16: [], qf: [], sf: [], f: [] };
	for (const f of fixtures) {
		const rid = stageOf[f.stage];
		if (rid) out[rid].push(f);
	}
	return out;
}

/** Direct fixture-based recomputation — same primitives `computeKoTotal`
 *  uses (`fixtureKoHits` per fixture, `stagePointsForRound` per round),
 *  used as the independent oracle for the parity test. */
function directFixtureBasedKoTotal(
	bracket: BracketPrediction,
	fixtures: Fixture[],
	adv: Record<string, number>
): number {
	const byRound = fixturesByRound(fixtures);
	let total = 0;
	for (const roundId of KO_ROUNDS) {
		const picks = new Set(
			roundId === 'r32'
				? bracket.round_of_32
				: roundId === 'r16'
				? bracket.round_of_16
				: roundId === 'qf'
				? bracket.quarter_finals
				: roundId === 'sf'
				? bracket.semi_finals
				: bracket.final
		);
		const stagePts = stagePointsForRound(adv, roundId);
		let hits = 0;
		for (const f of byRound[roundId]) {
			hits += fixtureKoHits(f, picks).hits;
		}
		total += hits * stagePts;
	}
	return total;
}

function toSimulatorPicks(bracket: BracketPrediction): SimulatorBracketPicks {
	return {
		round_of_32: bracket.round_of_32,
		round_of_16: bracket.round_of_16,
		quarter_finals: bracket.quarter_finals,
		semi_finals: bracket.semi_finals,
		final: bracket.final,
		winner: bracket.winner || null
	};
}

describe('resolveScenario / rescoreEntryKo parity with fixture-based scoring', () => {
	const fixtures = buildPartialBracketFixtures();

	// An entry whose picks span every round, mixing hits, misses, and a
	// pick riding on a still-unresolved slot.
	const bracket: BracketPrediction = {
		group_winners: {},
		round_of_32: ['Mexico', 'Senegal', 'Brazil', 'Italy', 'Argentina', 'Poland'],
		round_of_16: ['Mexico', 'Brazil', 'Argentina'], // Argentina hasn't played M77 yet
		quarter_finals: ['Brazil'],
		semi_finals: ['Brazil'],
		final: ['Brazil'],
		winner: 'Brazil'
	};

	it('agrees with the direct fixture-based recomputation when hypoWinners is empty', () => {
		const scenario = resolveScenario(fixtures, new Map());
		const engineTotal = rescoreEntryKo(toSimulatorPicks(bracket), scenario.reached, scenario.champion, ADV);
		const directTotal = directFixtureBasedKoTotal(bracket, fixtures, ADV);
		expect(engineTotal).toBe(directTotal);
	});

	it('the parity total is nonzero and reflects real R32 + partial R16 hits', () => {
		const scenario = resolveScenario(fixtures, new Map());
		const directTotal = directFixtureBasedKoTotal(bracket, fixtures, ADV);
		// R32 picks {Mexico, Senegal, Brazil, Italy, Argentina, Poland} are
		// all seeded R32 participants (M73/M74/M77 hold real names), so all
		// 6 hit: 6 * 20 = 120.
		// R16 picks {Mexico, Brazil, Argentina}: Mexico (M90 home) and Brazil
		// (M89 home) are seeded via the resolved home slots (2 hits * 30 =
		// 60); Argentina does NOT hit — M77 is unplayed so M89's away side is
		// still a slot placeholder.
		// Total: 120 + 60 = 180.
		expect(directTotal).toBe(120 + 60);
		expect(scenario.champion).toBeNull(); // Final unplayed, no hypo winner supplied
	});

	it('champion is null and no winner bonus is paid without a resolved Final', () => {
		const scenario = resolveScenario(fixtures, new Map());
		const total = rescoreEntryKo(toSimulatorPicks(bracket), scenario.reached, scenario.champion, ADV);
		// Total banks 180 (120 R32 + 60 R16); the winner bonus (100) must NOT
		// be included since champion is null.
		expect(total).toBe(120 + 60);
		expect(total).toBeLessThan(120 + 60 + 100);
	});
});

describe('resolveScenario — hypothetical propagation', () => {
	const fixtures = buildPartialBracketFixtures();

	it('propagating a hypothetical QF winner makes that team reach the SF', () => {
		// Chain of hypothetical winners: M77 (R32) -> M89 (R16) -> M97 (QF),
		// each feeding the next round, so Argentina ends up a resolved
		// participant in SF match 101.
		const hypo = new Map<number, string>([
			[77, 'Argentina'], // R32: Argentina beats Poland
			[89, 'Argentina'], // R16: Argentina beats Brazil
			[97, 'Argentina'] // QF: Argentina wins (feeds SF 101)
		]);
		const scenario = resolveScenario(fixtures, hypo);
		expect(scenario.reached.get('Argentina')).toBeGreaterThanOrEqual(rankOf('sf'));
		// SF match 101 should now show Argentina as a resolved participant.
		const sf101 = scenario.matches.get(101);
		expect(sf101?.home === 'Argentina' || sf101?.away === 'Argentina').toBe(true);
	});

	it('a full scenario resolves a champion and awards the winner picker the winner bonus', () => {
		const hypo = new Map<number, string>([
			// R32 winners needed to fill the rest of the bracket
			[75, 'France'],
			[76, 'Portugal'],
			[77, 'Argentina'],
			[78, 'England'],
			[79, 'Germany'],
			[80, 'Belgium'],
			[81, 'Netherlands'],
			[82, 'Croatia'],
			[83, 'Spain'],
			[84, 'Switzerland'],
			[85, 'USA'],
			[86, 'Denmark'],
			[87, 'Serbia'],
			[88, 'Australia'],
			// R16
			[89, 'Brazil'],
			[90, 'Mexico'],
			[91, 'Portugal'],
			[92, 'Germany'],
			[93, 'Spain'],
			[94, 'Netherlands'],
			[95, 'Denmark'],
			[96, 'USA'],
			// QF: 97 = winner(89)Brazil vs winner(90)Mexico; 98 = winner(93)Spain
			// vs winner(94)Netherlands; 99 = winner(91)Portugal vs
			// winner(92)Germany; 100 = winner(95)Denmark vs winner(96)USA.
			[97, 'Brazil'],
			[98, 'Spain'],
			[99, 'Portugal'],
			[100, 'Denmark'],
			// SF: 101 = winner(97)Brazil vs winner(98)Spain; 102 =
			// winner(99)Portugal vs winner(100)Denmark.
			[101, 'Brazil'],
			[102, 'Denmark'],
			// Final: 104 = winner(101)Brazil vs winner(102)Denmark.
			[104, 'Brazil']
		]);
		const scenario = resolveScenario(fixtures, hypo);
		expect(scenario.champion).toBe('Brazil');
		expect(scenario.reached.get('Brazil')).toBe(6); // CHAMPION_RANK

		const pickedBrazil: SimulatorBracketPicks = {
			round_of_32: ['Brazil'],
			round_of_16: ['Brazil'],
			quarter_finals: ['Brazil'],
			semi_finals: ['Brazil'],
			final: ['Brazil'],
			winner: 'Brazil'
		};
		const total = rescoreEntryKo(pickedBrazil, scenario.reached, scenario.champion, ADV);
		// R32 (20) + R16 (30) + QF (40) + SF (50) + Final (75) + winner (100)
		expect(total).toBe(20 + 30 + 40 + 50 + 75 + 100);
	});
});

describe('fillFromMyPicks', () => {
	const fixtures = buildPartialBracketFixtures();

	it('seeds a match when the pick matches a currently-resolved real team', () => {
		const myBracket: BracketPrediction = {
			group_winners: {},
			round_of_32: [],
			round_of_16: ['Brazil'], // picked Brazil to reach QF via M89 (home already resolved)
			quarter_finals: [],
			semi_finals: [],
			final: [],
			winner: ''
		};
		const hypo = fillFromMyPicks(fixtures, myBracket);
		expect(hypo.get(89)).toBe('Brazil');
	});

	it('leaves a slot open when the picked team has been eliminated / never seeded', () => {
		const myBracket: BracketPrediction = {
			group_winners: {},
			round_of_32: [],
			round_of_16: ['Senegal'], // Senegal LOST M73 to Mexico — eliminated, not seeded into M89/M90
			quarter_finals: [],
			semi_finals: [],
			final: [],
			winner: ''
		};
		const hypo = fillFromMyPicks(fixtures, myBracket);
		expect(hypo.has(89)).toBe(false);
		expect(hypo.has(90)).toBe(false);
	});

	it('does not seed matches that are already played (M73/M74)', () => {
		const myBracket: BracketPrediction = {
			group_winners: {},
			round_of_32: ['Senegal'], // Senegal lost — irrelevant, M73 already has a real result
			quarter_finals: [],
			round_of_16: [],
			semi_finals: [],
			final: [],
			winner: ''
		};
		const hypo = fillFromMyPicks(fixtures, myBracket);
		expect(hypo.has(73)).toBe(false);
	});
});

describe('projectStandings', () => {
	const fixtures = buildPartialBracketFixtures();
	const scenario = resolveScenario(fixtures, new Map());

	function entry(
		id: string,
		name: string,
		position: number,
		groupPts: number,
		picks: SimulatorBracketPicks
	): SimulatorEntryPicks {
		return {
			entry_id: id,
			entry_name: name,
			user_id: `u-${id}`,
			user_name: name,
			position,
			total_points: groupPts, // no KO points banked yet in this fixture
			group_points: groupPts,
			picks
		};
	}

	it('re-ranks entries by new KO-inclusive total, tie-breaking alphabetically', () => {
		const entries: SimulatorEntryPicks[] = [
			entry('1', 'Zed', 1, 100, {
				round_of_32: ['Mexico', 'Senegal', 'Brazil', 'Italy'], // 80 pts
				round_of_16: [],
				quarter_finals: [],
				semi_finals: [],
				final: [],
				winner: null
			}),
			entry('2', 'Amy', 2, 150, {
				round_of_32: ['Mexico'], // 20 pts
				round_of_16: [],
				quarter_finals: [],
				semi_finals: [],
				final: [],
				winner: null
			})
		];
		const rows = projectStandings(entries, scenario.reached, scenario.champion, ADV);
		// Zed: 100 + 80 = 180; Amy: 150 + 20 = 170 -> Zed now ranks first.
		expect(rows[0].entry_name).toBe('Zed');
		expect(rows[0].newTotal).toBe(180);
		expect(rows[0].newPos).toBe(1);
		expect(rows[0].deltaPos).toBe(0); // was 1, still 1
		expect(rows[1].entry_name).toBe('Amy');
		expect(rows[1].newTotal).toBe(170);
		expect(rows[1].newPos).toBe(2);
		expect(rows[1].deltaPos).toBe(0); // was 2, still 2
	});

	it('computes deltaPos/deltaPts correctly when ranking flips', () => {
		const entries: SimulatorEntryPicks[] = [
			entry('1', 'Underdog', 5, 50, {
				round_of_32: ['Mexico', 'Senegal', 'Brazil', 'Italy'], // 80 pts -> 130 total
				round_of_16: [],
				quarter_finals: [],
				semi_finals: [],
				final: [],
				winner: null
			}),
			entry('2', 'FrontRunner', 1, 120, {
				round_of_32: [], // 0 pts -> 120 total
				round_of_16: [],
				quarter_finals: [],
				semi_finals: [],
				final: [],
				winner: null
			})
		];
		const rows = projectStandings(entries, scenario.reached, scenario.champion, ADV);
		const underdog = rows.find((r) => r.entry_name === 'Underdog')!;
		const frontRunner = rows.find((r) => r.entry_name === 'FrontRunner')!;
		expect(underdog.newPos).toBe(1);
		expect(underdog.oldPos).toBe(5);
		expect(underdog.deltaPos).toBe(4); // moved up 4 places
		expect(underdog.deltaPts).toBe(80);
		expect(frontRunner.newPos).toBe(2);
		expect(frontRunner.deltaPos).toBe(-1); // moved down 1 place
	});
});

describe('pivotalMatches', () => {
	const fixtures = buildPartialBracketFixtures();

	function entry(
		id: string,
		name: string,
		position: number,
		groupPts: number,
		picks: SimulatorBracketPicks
	): SimulatorEntryPicks {
		return {
			entry_id: id,
			entry_name: name,
			user_id: `u-${id}`,
			user_name: name,
			position,
			total_points: groupPts,
			group_points: groupPts,
			picks
		};
	}

	const emptyPicks: SimulatorBracketPicks = {
		round_of_32: [],
		round_of_16: [],
		quarter_finals: [],
		semi_finals: [],
		final: [],
		winner: null
	};

	// M75 (R32: France vs Japan) and M76 (R32: Portugal vs Morocco) are both
	// still open with two real, non-placeholder participants — exactly the
	// candidate shape `pivotalMatches` looks for. M89/M90 (R16) are NOT
	// candidates: one side is still a slot placeholder in this fixture set.
	//
	// "Me" picked France to reach the R16 (a pick that only hits once France
	// actually WINS M75 — R32 picks bank just for being seeded, but an R16
	// pick requires the team to reach R16, which routes through M75's
	// winner feeding M90's away slot). "Rival" has a fixed 145-point total
	// with no picks riding on M75 or M76 at all.
	//
	// Me: baseline group_points 120, no KO points banked yet.
	//   - France wins M75 -> France reaches R16 -> my R16 pick hits -> +30
	//     -> 150, which crosses Rival's fixed 145 -> I rank 1st.
	//   - Japan wins M75 -> my R16 pick never hits -> stays 120 -> below
	//     Rival's 145 -> I rank 2nd.
	// The 30-point R16 swing is tuned to straddle Rival's total exactly so
	// the match outcome flips my rank.
	const ME_GROUP_PTS = 120;
	const RIVAL_TOTAL = 145;

	function buildEntries(): SimulatorEntryPicks[] {
		return [
			entry('me', 'Me', 2, ME_GROUP_PTS, {
				...emptyPicks,
				round_of_16: ['France']
			}),
			entry('rival', 'Rival', 1, RIVAL_TOTAL, emptyPicks)
		];
	}

	it('ranks the match that flips my position ahead of a no-op match, with correct posIfHome/posIfAway', () => {
		const entries = buildEntries();
		const baseHypo: HypoWinners = new Map();
		const results = pivotalMatches(entries, baseHypo, fixtures, ADV, 'me', 3);

		expect(results.length).toBeGreaterThan(0);
		const top = results[0];
		expect(top.matchNumber).toBe(75);
		expect(top.home).toBe('France');
		expect(top.away).toBe('Japan');

		// France wins M75 -> Me: 120 + 30 = 150 > Rival's 145 -> rank 1.
		// Japan wins M75 -> Me: 120 + 0 = 120 < Rival's 145 -> rank 2.
		expect(top.posIfHome).toBe(1);
		expect(top.posIfAway).toBe(2);
		expect(top.swing).toBe(1);

		// M76 (Portugal vs Morocco) touches nothing I picked anywhere ->
		// my rank is identical under either outcome -> swing 0, ranked
		// below the M75 result (sorted swing DESC).
		const m76 = results.find((r) => r.matchNumber === 76);
		expect(m76).toBeDefined();
		expect(m76!.swing).toBe(0);
		expect(results.indexOf(m76!)).toBeGreaterThan(results.indexOf(top));
	});

	it('respects the limit parameter', () => {
		const entries = buildEntries();
		const results = pivotalMatches(entries, new Map(), fixtures, ADV, 'me', 1);
		expect(results.length).toBe(1);
		expect(results[0].matchNumber).toBe(75);
	});

	it('returns an empty array when myEntryId is not in entries', () => {
		const entries = buildEntries();
		const results = pivotalMatches(entries, new Map(), fixtures, ADV, 'nobody', 3);
		expect(results).toEqual([]);
	});

	it('only considers matches where both sides are already resolved to real teams', () => {
		const entries = buildEntries();
		const results = pivotalMatches(entries, new Map(), fixtures, ADV, 'me', 100);
		// M89/M90 (R16) have one placeholder side in this fixture set and must
		// be excluded; M73/M74 are FINISHED and must be excluded too.
		const numbers = results.map((r) => r.matchNumber);
		expect(numbers).not.toContain(89);
		expect(numbers).not.toContain(90);
		expect(numbers).not.toContain(73);
		expect(numbers).not.toContain(74);
		// Every remaining open, both-sides-real R32 match (75-88 minus 73/74)
		// should be present.
		for (const num of [75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88]) {
			expect(numbers).toContain(num);
		}
	});
});
