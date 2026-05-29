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
		name: 'BBC Sport',
		url: 'https://feeds.bbc.co.uk/sport/football/world_cup/rss.xml',
		format: 'rss2'
	},
	{
		name: 'Guardian Football',
		url: 'https://www.theguardian.com/football/rss',
		format: 'rss2'
	}
] as const;
