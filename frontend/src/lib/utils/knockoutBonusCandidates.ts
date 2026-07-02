import type { Fixture } from '$types';
import type { BonusMeta } from '$api/bonus';
import { isRealTeam, seededByStage } from '$lib/utils/leaderboardV4';

const STAGE_ORDER = [
	'group',
	'round_of_32',
	'round_of_16',
	'quarter_final',
	'semi_final',
	'final'
];

export interface DarkHorseCandidates {
	candidates: string[];
	valLabel: string;
	note: string;
	topN: number;
}

export interface BottlersCandidates {
	candidates: string[];
	valLabel: string;
	note: string;
	topN: number;
}

export interface KnockoutBonusCandidates {
	groupStageComplete: boolean;
	/** null until the group stage finishes and bonus meta has loaded. */
	darkHorse: DarkHorseCandidates | null;
	bottlers: BottlersCandidates | null;
}

/**
 * Bonus Q3 (Dark Horse) / Q4 (Bottlers) candidate seeding.
 *
 *   Q3 Dark Horse — team OUTSIDE FIFA top N progressing furthest.
 *   Q4 Bottlers   — team INSIDE FIFA top N eliminated earliest
 *                   (including not making the knockout stage).
 *
 * Both become meaningful once the group stage finishes: Q4's
 * candidates seed from top-N sides that didn't qualify (or all top-N
 * sides if every favourite qualified — they're tied earliest until a
 * KO match knocks one out). Q3's candidates seed from outside-top-N
 * sides that did qualify (all tied for "furthest" at R32 until KO
 * matches narrow the field).
 *
 * Single source of truth for the Insights tab (Tournament
 * Superlatives card) and the Winner tab's Q3/Q4 bonus cards — do not
 * duplicate this computation at either call site.
 */
export function knockoutBonusCandidates(
	fixtures: Fixture[],
	bonusMeta: BonusMeta | null
): KnockoutBonusCandidates {
	const groupFixtures = fixtures.filter((f) => f.stage === 'group');
	const groupStageComplete =
		groupFixtures.length > 0 && groupFixtures.every((f) => f.status === 'finished');

	if (!groupStageComplete || !bonusMeta) {
		return { groupStageComplete, darkHorse: null, bottlers: null };
	}

	const topN = new Set(bonusMeta.fifa_top_teams);
	// Teams seeded into ANY knockout fixture = qualified from groups.
	const seeded = seededByStage(fixtures);
	const qualified = new Set<string>();
	for (const set of seeded.values()) for (const t of set) qualified.add(t);

	const allGroupTeams = new Set<string>();
	for (const f of groupFixtures) {
		if (isRealTeam(f.home_team)) allGroupTeams.add(f.home_team);
		if (isRealTeam(f.away_team)) allGroupTeams.add(f.away_team);
	}

	// Q3: outside-top-N teams that progressed. Once the tournament
	// runs further, this narrows to whoever's still alive deepest.
	const eliminated = new Set<string>();
	for (const f of fixtures) {
		if (
			f.stage !== 'group' &&
			f.status === 'finished' &&
			f.score &&
			isRealTeam(f.home_team) &&
			isRealTeam(f.away_team)
		) {
			if (f.score.outcome === '1') eliminated.add(f.away_team);
			else if (f.score.outcome === '2') eliminated.add(f.home_team);
		}
	}
	const darkHorseCandidates = [...allGroupTeams]
		.filter((t) => !topN.has(t) && qualified.has(t) && !eliminated.has(t))
		.sort((a, b) => a.localeCompare(b));
	const darkHorse: DarkHorseCandidates = {
		candidates: darkHorseCandidates,
		valLabel: darkHorseCandidates.length === 1 ? 'still standing' : 'still in contention',
		note: 'Bonus Q3 — outsider running furthest',
		topN: bonusMeta.top_n
	};

	// Q4: top-N teams eliminated earliest. After group stage that's
	// "didn't qualify"; once KO is running, also top-N KO losers from
	// the earliest round to have any (the question rewards the
	// EARLIEST exit, so eliminating from the latest survivors downward
	// is wrong — pick the lowest stage in which any top-N side has
	// been knocked out).
	const topNNotQualified = [...topN].filter((t) => allGroupTeams.has(t) && !qualified.has(t));
	let bottlerCandidates: string[];
	let bottlerNote: string;
	if (topNNotQualified.length > 0) {
		bottlerCandidates = topNNotQualified.sort((a, b) => a.localeCompare(b));
		bottlerNote = 'Bonus Q4 — top FIFA side failed to qualify';
	} else {
		// Every top-N side qualified — find the earliest KO round any
		// top-N team lost in, list everyone tied at that depth.
		let earliest: string | null = null;
		const koLosers = new Map<string, string>(); // team → stage of loss
		for (const f of fixtures) {
			if (
				f.stage === 'group' ||
				f.status !== 'finished' ||
				!f.score ||
				!isRealTeam(f.home_team) ||
				!isRealTeam(f.away_team)
			)
				continue;
			const loser =
				f.score.outcome === '1' ? f.away_team : f.score.outcome === '2' ? f.home_team : null;
			if (loser && topN.has(loser)) {
				koLosers.set(loser, f.stage);
				if (earliest === null || STAGE_ORDER.indexOf(f.stage) < STAGE_ORDER.indexOf(earliest)) {
					earliest = f.stage;
				}
			}
		}
		bottlerCandidates =
			earliest === null
				? []
				: [...koLosers.entries()]
						.filter(([, s]) => s === earliest)
						.map(([t]) => t)
						.sort((a, b) => a.localeCompare(b));
		if (earliest === null) {
			bottlerNote = 'Bonus Q4 — every top-FIFA side still alive';
		} else {
			const stageLbl = earliest.replace(/_/g, ' ');
			bottlerNote =
				bottlerCandidates.length === 1
					? `Bonus Q4 — top FIFA side out at ${stageLbl}`
					: `Bonus Q4 — top FIFA sides tied · all out at ${stageLbl}`;
		}
	}
	const bottlers: BottlersCandidates = {
		candidates: bottlerCandidates,
		valLabel:
			bottlerCandidates.length === 0
				? 'TBD'
				: bottlerCandidates.length === 1
					? 'eliminated'
					: 'all eliminated',
		note: bottlerNote,
		topN: bonusMeta.top_n
	};

	return { groupStageComplete, darkHorse, bottlers };
}
