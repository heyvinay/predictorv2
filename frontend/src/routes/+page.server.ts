/**
 * Landing-page server load. Fetches in parallel with each request
 * isolated by try/catch — any single failure produces a sensible
 * fallback rather than 500-ing the whole page.
 *
 * Sources:
 *   - /api/competition/info → totalPlayers, phase1Deadline
 *   - /api/fixtures/        → firstKickoff (min kickoff)
 *   - lib/server/news       → BBC + Guardian RSS, aggregated + deduped
 *
 * The response is cached at the edge for 5 minutes via cache-control —
 * marketing page content doesn't need request-level freshness, and the
 * RSS aggregator is the most expensive bit by far. 5 min balances
 * "fresh-ish news" against "don't hammer the feeds".
 */
import type { PageServerLoad } from './$types';
import { fetchAllNews, type NewsItem } from '$lib/server/news';

interface CompetitionInfo {
	total_players?: number | null;
	phase1_deadline?: string | null;
}

interface FixtureRow {
	kickoff?: string;
}

export const load: PageServerLoad = async ({ fetch, setHeaders }) => {
	setHeaders({
		'cache-control': 'public, max-age=300'
	});

	const [info, fixtures, news] = await Promise.all([
		fetchCompetitionInfo(fetch),
		fetchFixtures(fetch),
		fetchNewsSafely()
	]);

	return {
		totalPlayers: info?.total_players ?? null,
		phase1Deadline: info?.phase1_deadline ?? null,
		firstKickoff: computeFirstKickoff(fixtures),
		news
	};
};

async function fetchCompetitionInfo(
	fetch: typeof globalThis.fetch
): Promise<CompetitionInfo | null> {
	try {
		const res = await fetch('/api/competition/info');
		if (!res.ok) return null;
		return (await res.json()) as CompetitionInfo;
	} catch {
		return null;
	}
}

async function fetchFixtures(
	fetch: typeof globalThis.fetch
): Promise<FixtureRow[] | null> {
	try {
		const res = await fetch('/api/fixtures/');
		if (!res.ok) return null;
		const data = (await res.json()) as FixtureRow[] | { fixtures: FixtureRow[] };
		// Endpoint returns a bare array in v1 of the API; defensively
		// handle a wrapped shape too in case the contract changes.
		return Array.isArray(data) ? data : data?.fixtures ?? null;
	} catch {
		return null;
	}
}

async function fetchNewsSafely(): Promise<NewsItem[]> {
	try {
		return await fetchAllNews();
	} catch {
		return [];
	}
}

function computeFirstKickoff(fixtures: FixtureRow[] | null): string | null {
	if (!fixtures || fixtures.length === 0) return null;
	let earliest: number = Number.POSITIVE_INFINITY;
	let earliestIso: string | null = null;
	for (const f of fixtures) {
		if (!f?.kickoff) continue;
		const t = new Date(f.kickoff).getTime();
		if (!Number.isNaN(t) && t < earliest) {
			earliest = t;
			earliestIso = f.kickoff;
		}
	}
	return earliestIso;
}
