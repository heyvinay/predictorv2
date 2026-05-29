/**
 * Client-side cache for The Odds API responses.
 *
 * TTL: 24 hours. Stored as a single JSON blob under
 * `localStorage['worldcup_odds_cache_v1']`.
 *
 * The non-obvious bit is the **merge-on-refresh contract**:
 *
 *   When refreshing odds, the new API response is MERGED into the existing
 *   cache by fixture `id` — NOT replaced wholesale. If a fixture present in
 *   the OLD cache is missing from the new response (the API occasionally
 *   drops fixtures when a bookmaker quote is temporarily withdrawn), we
 *   KEEP the old version. Blind overwrite would silently destroy known-good
 *   odds and break Smart Fill for that fixture until the next successful
 *   refresh days later.
 *
 * Each cached match is augmented with `_cachedAt` (ISO datetime) so the
 * cache can later surface per-fixture staleness if needed.
 */

const CACHE_KEY = 'worldcup_odds_cache_v1';
const TTL_MS = 24 * 60 * 60 * 1000;

export type OddsApiMatch = {
	id: string;
	sport_key: string;
	commence_time: string;
	home_team: string;
	away_team: string;
	bookmakers: Array<{
		key: string;
		title: string;
		last_update: string;
		markets: Array<{
			key: string;
			outcomes: Array<{ name: string; price: number }>;
		}>;
	}>;
	/** Set by the cache layer on write — not part of the API response. */
	_cachedAt?: string;
};

export type CachePayload = {
	/** Wall-clock ISO datetime of the most recent successful refresh. */
	fetchedAt: string;
	/** `x-requests-remaining` from the most recent API response. */
	remaining: number;
	/** Union of new + preserved-from-old matches. */
	matches: OddsApiMatch[];
};

/**
 * Merge a fresh API response into an existing cache. PURE — no I/O.
 *
 * Contract:
 *   - For each fixture in `newMatches` → use the new version (with
 *     `_cachedAt` set to `now`).
 *   - For each fixture in `oldMatches` whose `id` is NOT in `newMatches`
 *     → keep the old version unchanged (its `_cachedAt` stays at whatever
 *     it was when last successfully fetched).
 *   - Empty `newMatches` does NOT wipe the cache. This is the critical
 *     durability case — a catastrophic upstream that returns `[]` should
 *     leave clients still functioning off their last-good data.
 */
export function mergeCaches(
	oldMatches: OddsApiMatch[] | undefined,
	newMatches: OddsApiMatch[],
	now: string
): OddsApiMatch[] {
	const stampedNew = newMatches.map((m) => ({ ...m, _cachedAt: now }));
	if (!oldMatches || oldMatches.length === 0) return stampedNew;
	const newIds = new Set(stampedNew.map((m) => m.id));
	const preservedOld = oldMatches.filter((m) => !newIds.has(m.id));
	return [...stampedNew, ...preservedOld];
}

function readCache(): CachePayload | null {
	if (typeof localStorage === 'undefined') return null;
	try {
		const raw = localStorage.getItem(CACHE_KEY);
		if (!raw) return null;
		return JSON.parse(raw) as CachePayload;
	} catch {
		return null;
	}
}

function writeCache(payload: CachePayload): void {
	if (typeof localStorage === 'undefined') return;
	try {
		localStorage.setItem(CACHE_KEY, JSON.stringify(payload));
	} catch {
		// Quota exceeded etc. — ignore; next refresh tries again.
	}
}

/** Manual reset — useful for testing or DevTools rescue. */
export function clearCache(): void {
	if (typeof localStorage === 'undefined') return;
	localStorage.removeItem(CACHE_KEY);
}

export function getCacheInfo(payload: CachePayload): {
	fetchedAt: string;
	matchCount: number;
	remaining: number;
} {
	return {
		fetchedAt: payload.fetchedAt,
		matchCount: payload.matches.length,
		remaining: payload.remaining
	};
}

function isFresh(fetchedAt: string, nowMs: number): boolean {
	const fetchedMs = new Date(fetchedAt).getTime();
	if (Number.isNaN(fetchedMs)) return false;
	return nowMs - fetchedMs < TTL_MS;
}

/**
 * Get odds, fetching + merging if the cache is stale.
 *
 * Returns:
 *   - The cached payload if it's fresh (< 24h old) — NO fetch.
 *   - A merged payload (new + preserved-old) on successful refresh.
 *   - The existing stale cache on network failure or proxy error
 *     (graceful offline — stale > nothing).
 *   - `null` when there's no cache AND the proxy says `not_configured`
 *     or the fetch failed outright.
 */
export async function getOdds(): Promise<CachePayload | null> {
	const nowMs = Date.now();
	const nowIso = new Date(nowMs).toISOString();
	const existing = readCache();

	if (existing && isFresh(existing.fetchedAt, nowMs)) {
		return existing;
	}

	try {
		const res = await fetch('/odds');
		if (!res.ok) {
			return existing ?? null;
		}
		const body = await res.json();
		if (body.error) {
			return existing ?? null;
		}
		const merged: CachePayload = {
			fetchedAt: nowIso,
			remaining: Number(body.remainingRequests ?? 0),
			matches: mergeCaches(existing?.matches, body.matches ?? [], nowIso)
		};
		writeCache(merged);
		return merged;
	} catch {
		return existing ?? null;
	}
}
