/**
 * Thin integration layer — given a fixture and a pile of API matches,
 * return a deterministic `[home_score, away_score]` or null if no odds
 * are available for that fixture.
 *
 * This deliberately diverges from `smartFillScoreline()`'s sync signature:
 *   - Returns a Promise because team-matching might one day involve
 *     async work (alias-table fetches, etc.); current impl is sync inside
 *     but the wrapper signature future-proofs the async escape hatch.
 *   - Returns `null` when no API odds exist for the fixture. The caller
 *     (`runSmartFill`) treats null as "skip this fixture, count as
 *     unmatched" — different from FIFA which always returns a score.
 */

import { findOddsForFixture, extractH2HOdds } from './teamMatch';
import { buildSeed, hashString, simulateScore } from './simulateScore';
import type { OddsApiMatch } from './oddsCache';

export async function oddsScoreline(
	homeTeam: string,
	awayTeam: string,
	fixtureId: string,
	apiMatches: OddsApiMatch[],
	fetchedAt: string
): Promise<[number, number] | null> {
	const match = findOddsForFixture(
		{ home_team: homeTeam, away_team: awayTeam },
		apiMatches
	);
	if (!match) return null;

	const odds = extractH2HOdds(match);
	if (!odds) return null;

	const seedStr = buildSeed(fixtureId, fetchedAt);
	const seed = hashString(seedStr);
	const { hs, as } = simulateScore(odds.home, odds.draw, odds.away, seed);
	return [hs, as];
}
