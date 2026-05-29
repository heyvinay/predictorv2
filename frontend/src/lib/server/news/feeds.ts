/**
 * Registry of RSS / Atom news feeds the landing page aggregates.
 *
 * v1 ships with two reliable, CORS-friendly sources. Adding more is a
 * one-line addition here — `aggregate.ts` fetches in parallel via
 * `Promise.allSettled`, so adding a feed that's slow or flaky doesn't
 * break the others. See the plan's "Deferred" section for the v2 sources
 * already scoped (Sky Sports, ESPN, Goal.com).
 */
import type { FeedSource } from './types';

export const FEEDS: readonly FeedSource[] = [
	{
		// NOTE on URL: BBC migrated two things at once around 2024:
		//   1. Hostname `feeds.bbc.co.uk` → `feeds.bbci.co.uk`. The old
		//      host silently kills TLS handshakes (ECONNRESET).
		//   2. Path separator from underscore to hyphen in the WC URL
		//      (`/world_cup/` → `/world-cup/`). The old path returns 404.
		// Both legacy variants are dead; this is the only working route
		// to BBC's World Cup feed today.
		name: 'BBC Sport',
		url: 'https://feeds.bbci.co.uk/sport/football/world-cup/rss.xml',
		format: 'rss2'
	},
	{
		// Guardian follows a "<topic-page>/rss" convention; appending /rss
		// to the WC-2026 hub page exposes the WC-only segment. The wider
		// `/football/rss` is the general football firehose — we're using
		// the tournament-scoped variant to keep the strip on-topic with
		// BBC's equivalent WC feed.
		name: 'Guardian Football',
		url: 'https://www.theguardian.com/football/world-cup-2026/rss',
		format: 'rss2'
	}
] as const;
