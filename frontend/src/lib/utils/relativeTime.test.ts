import { describe, expect, it } from 'vitest';
import { relativeAgo } from './relativeTime';

const NOW = new Date('2026-06-15T12:00:00Z').getTime();
const ago = (s: number) => new Date(NOW - s * 1000).toISOString();

describe('relativeAgo', () => {
	it('reports just-now under 5 seconds', () => {
		expect(relativeAgo(ago(0), NOW)).toBe('just now');
		expect(relativeAgo(ago(4), NOW)).toBe('just now');
	});

	it('reports seconds up to a minute', () => {
		expect(relativeAgo(ago(23), NOW)).toBe('23s ago');
		expect(relativeAgo(ago(59), NOW)).toBe('59s ago');
	});

	it('snaps to minutes between 1 minute and an hour', () => {
		expect(relativeAgo(ago(60), NOW)).toBe('1m ago');
		expect(relativeAgo(ago(120), NOW)).toBe('2m ago');
		// floor(3599 / 60) = 59 — we never report "60m"; the next tier kicks in at 3600s.
		expect(relativeAgo(ago(3599), NOW)).toBe('59m ago');
	});

	it('snaps to hours past an hour', () => {
		expect(relativeAgo(ago(3600), NOW)).toBe('1h ago');
		// floor((86_399 / 60) / 60) = 23 — 24h is the cutoff for "a while ago".
		expect(relativeAgo(ago(86_399), NOW)).toBe('23h ago');
	});

	it('returns "a while ago" past a day', () => {
		expect(relativeAgo(ago(86_400), NOW)).toBe('a while ago');
		expect(relativeAgo(ago(86_400 * 2), NOW)).toBe('a while ago');
	});

	it('handles unparseable input safely', () => {
		expect(relativeAgo('not a date', NOW)).toBe('');
	});
});
