/**
 * News aggregator orchestrator — the only public entry-point for the
 * landing page's `+page.server.ts`. Fetches every feed in parallel,
 * parses each one, merges + dedupes the result, sorts by recency, and
 * marks the first item as `featured` for the larger landing card.
 *
 * Failure model:
 *   - Per-feed: any fetch / parse failure is swallowed (logged once)
 *     and the feed contributes zero items. The other feeds still
 *     populate the strip.
 *   - All-feeds: returns `[]` rather than throwing. The caller's
 *     `+page.server.ts` already has `?? []` fallback, but defence in
 *     depth here keeps the contract simple.
 *
 * Caching is delegated to the caller via SvelteKit's `setHeaders` —
 * we don't memoize results in-process because the dev server reloads
 * the module on every request anyway.
 */
import { FEEDS } from './feeds';
import { parseFeed } from './parser';
import { dedupeByTitle } from './dedupe';
import type { NewsItem, FeedSource } from './types';

/** Max items returned to the landing page. The handoff layout shows 1
 *  featured + 5 grid + 1 "all headlines" tile = 6 actual cards; we
 *  return a few extra so dedupe doesn't leave us under-stocked. */
const MAX_ITEMS = 12;

/** Per-feed fetch timeout. RSS feeds usually return in <500ms; anything
 *  past 5s is almost certainly dead. */
const FEED_TIMEOUT_MS = 5_000;

export async function fetchAllNews(): Promise<NewsItem[]> {
	const results = await Promise.allSettled(FEEDS.map((feed) => fetchAndParseFeed(feed)));

	const allItems: NewsItem[] = [];
	for (let i = 0; i < results.length; i++) {
		const result = results[i];
		if (result.status === 'fulfilled') {
			allItems.push(...result.value);
		} else {
			console.warn(`[news] feed "${FEEDS[i].name}" failed:`, result.reason);
		}
	}

	if (allItems.length === 0) return [];

	const deduped = dedupeByTitle(allItems);

	deduped.sort((a, b) => toEpoch(b.publishedAt) - toEpoch(a.publishedAt));

	const top = deduped.slice(0, MAX_ITEMS);
	if (top.length > 0) {
		// Don't mutate the array entries directly — return a copy with
		// `featured` set on the first item only. Caller may render the
		// array more than once during SSR; immutability avoids surprises.
		top[0] = { ...top[0], featured: true };
	}

	return top;
}

/** Fetch + parse one feed. Failures throw to the caller; the
 *  `Promise.allSettled` upstream catches them. */
async function fetchAndParseFeed(feed: FeedSource): Promise<NewsItem[]> {
	const xml = await fetchWithTimeout(feed.url, FEED_TIMEOUT_MS);
	return parseFeed(xml, feed.name, feed.format);
}

/** `fetch` with an AbortController-backed timeout. Native `fetch` has
 *  no built-in timeout — without one, a hung feed would block the
 *  page-server `load` for as long as the OS TCP timeout allows. */
async function fetchWithTimeout(url: string, ms: number): Promise<string> {
	const controller = new AbortController();
	const timer = setTimeout(() => controller.abort(), ms);
	try {
		const res = await fetch(url, {
			signal: controller.signal,
			headers: {
				// Some feeds (Guardian especially) gate XML responses on
				// User-Agent looking browser-ish. Identify ourselves
				// transparently — feed publishers prefer a real UA over
				// the default `node`.
				'User-Agent': 'PredictorBot/1.0 (+landing-news-aggregator)',
				Accept: 'application/rss+xml, application/xml, text/xml'
			}
		});
		if (!res.ok) {
			throw new Error(`HTTP ${res.status} ${res.statusText}`);
		}
		return await res.text();
	} finally {
		clearTimeout(timer);
	}
}

function toEpoch(iso: string): number {
	const t = new Date(iso).getTime();
	return Number.isNaN(t) ? 0 : t;
}
