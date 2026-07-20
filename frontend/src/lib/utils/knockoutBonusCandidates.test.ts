import { describe, expect, it } from 'vitest';
import type { Fixture } from '$types';
import type { BonusMeta } from '$api/bonus';
import { knockoutBonusCandidates } from './knockoutBonusCandidates';

function fx(partial: Partial<Fixture>): Fixture {
	return {
		id: partial.id ?? crypto.randomUUID(),
		home_team: 'Mexico',
		away_team: 'Senegal',
		kickoff: '2026-06-28T18:00:00+00:00',
		stage: 'group',
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

/** A finished fixture where `winner` ('home' | 'away') took it 1-0. */
function ko(stage: string, home: string, away: string, winner: 'home' | 'away'): Fixture {
	return fx({
		stage,
		home_team: home,
		away_team: away,
		status: 'finished',
		score: {
			home_score: winner === 'home' ? 1 : 0,
			away_score: winner === 'away' ? 1 : 0,
			home_score_et: null,
			away_score_et: null,
			home_penalties: null,
			away_penalties: null,
			outcome: winner === 'home' ? '1' : '2'
		}
	} as Partial<Fixture>);
}

/** A finished group fixture (result irrelevant — only completeness matters). */
function grp(home: string, away: string): Fixture {
	return fx({
		stage: 'group',
		home_team: home,
		away_team: away,
		status: 'finished',
		score: {
			home_score: 1,
			away_score: 0,
			home_score_et: null,
			away_score_et: null,
			home_penalties: null,
			away_penalties: null,
			outcome: '1'
		}
	} as Partial<Fixture>);
}

const META: BonusMeta = { top_n: 10, fifa_top_teams: ['France', 'Spain', 'Argentina'] };

describe('knockoutBonusCandidates — Dark Horse (Q3)', () => {
	it('keeps eliminated outsiders that reached the furthest stage (regression)', () => {
		// Norway & Switzerland (outside the FIFA top-N) reach the quarter-finals
		// and are then knocked out; Croatia (also an outsider) went out a round
		// earlier at R16. The Dark Horse answer must stay Norway + Switzerland
		// even though they're eliminated — the OLD "still alive" filter emptied
		// this to [] the moment every outsider was out, silently dropping the card.
		const fixtures: Fixture[] = [
			grp('France', 'Norway'),
			grp('Spain', 'Switzerland'),
			grp('Argentina', 'Croatia'),
			ko('round_of_16', 'Croatia', 'Spain', 'away'), // Croatia out at R16
			ko('quarter_final', 'Norway', 'France', 'away'), // Norway out at QF
			ko('quarter_final', 'Switzerland', 'Argentina', 'away') // Switzerland out at QF
		];

		const kb = knockoutBonusCandidates(fixtures, META);

		expect(kb.groupStageComplete).toBe(true);
		expect(kb.darkHorse).not.toBeNull();
		// The two furthest outsiders survive as candidates; Croatia (earlier
		// exit) is correctly excluded — furthest-reached, not still-alive.
		expect(kb.darkHorse!.candidates).toEqual(['Norway', 'Switzerland']);
		expect(kb.darkHorse!.valLabel).toBe('reached the quarter-finals');
	});

	it('early on, every qualified outsider is tied at the round they reached', () => {
		// Only R16 fixtures seeded (not yet played): both outsiders reached R16.
		const fixtures: Fixture[] = [
			grp('France', 'Norway'),
			grp('Spain', 'Switzerland'),
			fx({ stage: 'round_of_16', home_team: 'Norway', away_team: 'France' }),
			fx({ stage: 'round_of_16', home_team: 'Switzerland', away_team: 'Spain' })
		];

		const kb = knockoutBonusCandidates(fixtures, META);

		expect(kb.darkHorse).not.toBeNull();
		expect(kb.darkHorse!.candidates).toEqual(['Norway', 'Switzerland']);
		expect(kb.darkHorse!.valLabel).toBe('reached the round of 16');
	});
});

describe('knockoutBonusCandidates — Bottlers (Q4)', () => {
	it('excludes the unscored third_place playoff from the earliest-exit search (regression)', () => {
		// Argentina (top-N) loses at R32 — the true earliest KO exit among
		// top-N sides. France (also top-N) goes much deeper — reaches the
		// semis, loses there, then loses the third-place playoff. Before
		// the fix, 'third_place' wasn't in STAGE_ORDER so indexOf()
		// returned -1, which incorrectly won the "earliest" comparison
		// and picked France (a deep semi-finalist) over Argentina (the
		// real earliest exit). Confirmed against real WC26 prod data:
		// France reached the semis and lost the third-place match, and
		// this bug surfaced it as "top FIFA side out at third place."
		const fixtures: Fixture[] = [
			grp('France', 'Iceland'),
			grp('Spain', 'Wales'),
			grp('Argentina', 'Panama'),
			ko('round_of_32', 'Argentina', 'Panama', 'away'), // Argentina out at R32
			ko('semi_final', 'France', 'Spain', 'away'), // France loses the semis
			ko('third_place', 'France', 'England', 'away') // ...then loses bronze too
		];

		const kb = knockoutBonusCandidates(fixtures, META);

		expect(kb.bottlers).not.toBeNull();
		expect(kb.bottlers!.candidates).toEqual(['Argentina']);
		expect(kb.bottlers!.note).toBe('Bonus Q4 — top FIFA side out at round of 32');
	});
});
