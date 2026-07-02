import type { Fixture } from '$types';

export interface TiedLeaders<K> {
	keys: K[];
	n: number;
}

/** Returns every key tied for the maximum value, sorted alphabetically. */
export function topTiedBy<K>(map: Map<K, number>): TiedLeaders<K> {
	if (map.size === 0) return { keys: [], n: 0 };
	const n = Math.max(...map.values());
	const keys = [...map.entries()]
		.filter(([, v]) => v === n)
		.map(([k]) => k)
		.sort((a, b) => String(a).localeCompare(String(b)));
	return { keys, n };
}

export interface GroupGoalsMaps {
	gf: Map<string, number>;
	ga: Map<string, number>;
}

/** Goals-for / goals-against totals from finished group-stage fixtures. */
export function buildGroupGoalsMaps(fixtures: Fixture[]): GroupGoalsMaps {
	const gf = new Map<string, number>();
	const ga = new Map<string, number>();
	for (const f of fixtures) {
		if (f.stage !== 'group' || f.status !== 'finished' || !f.score) continue;
		gf.set(f.home_team, (gf.get(f.home_team) ?? 0) + f.score.home_score);
		gf.set(f.away_team, (gf.get(f.away_team) ?? 0) + f.score.away_score);
		ga.set(f.home_team, (ga.get(f.home_team) ?? 0) + f.score.away_score);
		ga.set(f.away_team, (ga.get(f.away_team) ?? 0) + f.score.home_score);
	}
	return { gf, ga };
}

export interface GroupGoalsSuperlatives {
	mostScored: TiedLeaders<string>;
	mostConceded: TiedLeaders<string>;
}

/**
 * Current group-phase "most goals scored" / "most conceded" leaders,
 * including every team tied at the max. Single source of truth for
 * the Insights tab (Tournament Superlatives card) and the Group
 * Standings reality-check overlay (bonus Q1/Q2 mirror) — do not
 * duplicate this computation at either call site.
 */
export function groupGoalsSuperlatives(fixtures: Fixture[]): GroupGoalsSuperlatives {
	const { gf, ga } = buildGroupGoalsMaps(fixtures);
	return {
		mostScored: topTiedBy(gf),
		mostConceded: topTiedBy(ga)
	};
}
