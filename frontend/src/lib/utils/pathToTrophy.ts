/**
 * Path to the Trophy — group the flat scenario list (every remaining
 * bracket completion + its pool champion) by champion, and derive, per
 * champion, the exact match results that are INVARIANT across all of their
 * winning scenarios.
 *
 * The invariant is computed structurally, not written by hand: for each
 * match, the result is "fixed" for a champion only if every one of their
 * winning scenarios agrees on it. A match that varies within the group is
 * dropped — it doesn't determine that champion. This is what prevents the
 * class of error where "champion whenever France wins the final" is
 * asserted when the real invariant was "France wins their semi" (the final
 * varied across the group).
 */
import type { MatchMetaEntry, ScenarioOutcome } from '$lib/types/winProbability';

export interface FixedMatch {
	matchNumber: number;
	winningTeam: string;
	homeTeam: string;
	awayTeam: string;
	stage: string;
}

export interface PathGroup {
	entryId: string;
	scenarioCount: number;
	totalScenarios: number;
	/** Summed weight across this champion's winning scenarios = their live
	 *  probability of taking the pool (odds-weighted when the response is). */
	totalWeight: number;
	/** Match results constant across every scenario in the group, ascending
	 *  by match_number. Empty when nothing is invariant. */
	fixedMatches: FixedMatch[];
	/** True only when the group spans >1 scenario yet has zero fixed
	 *  matches — this champion wins no matter how the rest plays out. */
	winsUnconditionally: boolean;
}

export function groupScenariosByChampion(
	scenarios: ScenarioOutcome[],
	matchMeta: MatchMetaEntry[]
): PathGroup[] {
	const metaByMatch = new Map(matchMeta.map((m) => [m.match_number, m]));
	const totalScenarios = scenarios.length;

	// Bucket scenarios by champion. A tie (>1 champion_entry_ids) puts the
	// scenario in every tied champion's bucket.
	const buckets = new Map<string, ScenarioOutcome[]>();
	for (const s of scenarios) {
		for (const entryId of s.champion_entry_ids) {
			const bucket = buckets.get(entryId);
			if (bucket) bucket.push(s);
			else buckets.set(entryId, [s]);
		}
	}

	const groups: PathGroup[] = [];
	for (const [entryId, group] of buckets) {
		// outcomes keys are stringified match numbers in JSON.
		const matchNumbers = Object.keys(group[0].outcomes)
			.map(Number)
			.sort((a, b) => a - b);

		const fixedMatches: FixedMatch[] = [];
		for (const m of matchNumbers) {
			const key = String(m);
			const winner = group[0].outcomes[key];
			// Fixed only if EVERY scenario in the group has the same winner.
			if (!group.every((s) => s.outcomes[key] === winner)) continue;
			const meta = metaByMatch.get(m);
			fixedMatches.push({
				matchNumber: m,
				winningTeam: winner,
				homeTeam: meta?.home_team ?? '',
				awayTeam: meta?.away_team ?? '',
				stage: meta?.stage ?? ''
			});
		}

		groups.push({
			entryId,
			scenarioCount: group.length,
			totalScenarios,
			totalWeight: group.reduce((sum, s) => sum + s.weight, 0),
			fixedMatches,
			winsUnconditionally: fixedMatches.length === 0 && group.length > 1
		});
	}

	// Most likely path to the trophy first; deterministic tie-break on id.
	return groups.sort(
		(a, b) => b.totalWeight - a.totalWeight || a.entryId.localeCompare(b.entryId)
	);
}

/** Human-readable stage label for a fixed-match clause. */
export function stageLabel(stage: string): string {
	switch (stage) {
		case 'round_of_32':
			return 'round of 32';
		case 'round_of_16':
			return 'round of 16';
		case 'quarter_final':
			return 'quarter-final';
		case 'semi_final':
			return 'semi-final';
		case 'final':
			return 'final';
		default:
			return stage.replace(/_/g, ' ');
	}
}
