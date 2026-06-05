/**
 * Odds proxy — now a thin pass-through to the FastAPI server-side cache.
 *
 * Plan §9 (2026-06-05): the actual cache + The Odds API integration moved
 * to backend/app/services/odds_cache.py. This SvelteKit endpoint stays at
 * `/odds` (NOT `/api/odds` — the `/api/*` namespace is reserved for the
 * FastAPI proxy) but now just forwards to the backend's `/api/odds`. The
 * frontend response shape is unchanged so no caller code needs touching.
 *
 * Why proxy through here at all (vs the client hitting `/api/odds` directly):
 *   - Keeps the frontend's network calls on the same origin (no CORS).
 *   - Matches the existing convention used by every other backend call —
 *     SvelteKit's `fetch` server-side handles cookies, retries, etc.
 *   - One-line revert path if we ever need to fall back to client-side
 *     fetching: re-point this handler at api.the-odds-api.com.
 *
 * Returns (200-always, body-encoded errors per §9 contract):
 *   - { fetchedAt, remainingRequests, usedRequests, matches } on success
 *   - { error: 'not_configured', matches: [] }  when ODDS_API_KEY is unset
 *   - { error: 'fetch_failed', matches: [] }    on backend failure
 *
 * Fallback (defense in depth): if the backend itself is unreachable, return
 * the existing graceful-degradation shape rather than 500'ing — Smart Fill
 * stays usable on the FIFA path even if the backend cache is down.
 */
import { json, type RequestHandler } from '@sveltejs/kit';

// In dev, Vite proxies /api → http://backend:8000 via the docker-compose
// network. In prod, nginx terminates /api at the FastAPI container. Both
// paths resolve relative to the SvelteKit server-side fetch.
const BACKEND_ODDS_URL = 'http://backend:8000/api/odds/';

export const GET: RequestHandler = async ({ fetch }) => {
	try {
		const res = await fetch(BACKEND_ODDS_URL);
		if (!res.ok) {
			return json({ error: 'fetch_failed', matches: [] });
		}
		const body = await res.json();
		return json(body);
	} catch {
		// Backend unreachable — graceful degradation. Body matches the
		// existing failure shape so client code unchanged.
		return json({ error: 'fetch_failed', matches: [] });
	}
};
