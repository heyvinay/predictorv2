/**
 * Public surface of the news aggregator. Callers import from
 * `$lib/server/news` and get the orchestrator + types — the internal
 * file split (feeds / parser / dedupe / aggregate) is an implementation
 * detail.
 */
export { fetchAllNews } from './aggregate';
export { FEEDS } from './feeds';
export type { NewsItem, FeedSource } from './types';
