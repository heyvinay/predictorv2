/**
 * Odds proxy — hides ODDS_API_KEY from the client.
 *
 * Path is `/odds`, NOT `/api/odds` — the `/api/*` namespace is reserved
 * for the FastAPI proxy via nginx in prod and Vite's dev proxy locally.
 * Using `/odds` keeps this SvelteKit endpoint cleanly separate.
 *
 * Returns:
 *   - { fetchedAt, remainingRequests, usedRequests, matches } on success
 *   - { error: 'not_configured' } when ODDS_API_KEY is unset
 *   - { error: 'upstream_error', status } if the-odds-api.com is unhappy
 *   - { error: 'fetch_failed' } on network failure
 *
 * Status is always 200 — the UI inspects the body to decide how to react.
 * This keeps the graceful-degradation path simple in the client (no need
 * to differentiate "key unset" from "network died" by status code).
 */
import { env } from '$env/dynamic/private';
import { json, type RequestHandler } from '@sveltejs/kit';

const ODDS_URL =
	'https://api.the-odds-api.com/v4/sports/soccer_fifa_world_cup/odds' +
	'?regions=eu&markets=h2h&oddsFormat=decimal';

export const GET: RequestHandler = async ({ fetch }) => {
	const apiKey = env.ODDS_API_KEY;
	if (!apiKey) {
		return json({ error: 'not_configured' });
	}

	try {
		const res = await fetch(`${ODDS_URL}&apiKey=${encodeURIComponent(apiKey)}`);
		if (!res.ok) {
			return json({ error: 'upstream_error', status: res.status });
		}
		const matches = await res.json();
		const remainingRequests = Number(res.headers.get('x-requests-remaining') ?? 0);
		const usedRequests = Number(res.headers.get('x-requests-used') ?? 0);
		return json({
			fetchedAt: new Date().toISOString(),
			remainingRequests,
			usedRequests,
			matches
		});
	} catch {
		return json({ error: 'fetch_failed' });
	}
};
