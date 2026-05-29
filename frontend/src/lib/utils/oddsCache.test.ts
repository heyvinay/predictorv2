import { describe, expect, it } from 'vitest';

import { mergeCaches, getCacheInfo, type OddsApiMatch, type CachePayload } from './oddsCache';

function makeMatch(id: string, overrides: Partial<OddsApiMatch> = {}): OddsApiMatch {
	return {
		id,
		sport_key: 'soccer_fifa_world_cup',
		commence_time: '2026-06-15T12:00:00Z',
		home_team: 'England',
		away_team: 'Brazil',
		bookmakers: [],
		...overrides
	};
}

describe('mergeCaches — durability contract', () => {
	const now = '2026-05-29T12:00:00Z';

	it('new overrides old by id', () => {
		const oldMs = [makeMatch('A', { home_team: 'OldHome', _cachedAt: '2026-05-28T00:00:00Z' })];
		const newMs = [makeMatch('A', { home_team: 'NewHome' })];
		const merged = mergeCaches(oldMs, newMs, now);
		expect(merged).toHaveLength(1);
		expect(merged[0].home_team).toBe('NewHome');
		expect(merged[0]._cachedAt).toBe(now);
	});

	it('CRITICAL: missing-in-new is preserved from old', () => {
		// API dropped fixture C; our cache must keep it.
		const oldMs = [
			makeMatch('A', { _cachedAt: '2026-05-28T00:00:00Z' }),
			makeMatch('B', { _cachedAt: '2026-05-28T00:00:00Z' }),
			makeMatch('C', { _cachedAt: '2026-05-28T00:00:00Z' })
		];
		const newMs = [makeMatch('A'), makeMatch('B')]; // C dropped
		const merged = mergeCaches(oldMs, newMs, now);
		expect(merged).toHaveLength(3);
		const ids = merged.map((m) => m.id).sort();
		expect(ids).toEqual(['A', 'B', 'C']);
		const cFromMerged = merged.find((m) => m.id === 'C')!;
		expect(cFromMerged._cachedAt).toBe('2026-05-28T00:00:00Z'); // old timestamp preserved
	});

	it('new-only fixtures get _cachedAt = now', () => {
		const oldMs = [makeMatch('A', { _cachedAt: '2026-05-28T00:00:00Z' })];
		const newMs = [makeMatch('A'), makeMatch('B')];
		const merged = mergeCaches(oldMs, newMs, now);
		const bFromMerged = merged.find((m) => m.id === 'B')!;
		expect(bFromMerged._cachedAt).toBe(now);
	});

	it('CRITICAL: empty new does NOT wipe old', () => {
		// Catastrophic upstream — every fixture dropped from the API. We
		// must keep the entire old cache.
		const oldMs = [makeMatch('A'), makeMatch('B'), makeMatch('C')];
		const merged = mergeCaches(oldMs, [], now);
		expect(merged).toHaveLength(3);
		expect(merged.map((m) => m.id).sort()).toEqual(['A', 'B', 'C']);
	});

	it('empty old falls through — all new entries get stamped', () => {
		const merged = mergeCaches(undefined, [makeMatch('A'), makeMatch('B')], now);
		expect(merged).toHaveLength(2);
		expect(merged.every((m) => m._cachedAt === now)).toBe(true);
	});

	it('null/undefined old behaves identically to empty array', () => {
		const newMs = [makeMatch('A')];
		const a = mergeCaches(undefined, newMs, now);
		const b = mergeCaches([], newMs, now);
		expect(a).toEqual(b);
	});

	it('_cachedAt refreshed for overlapping match, preserved for old-only match', () => {
		const oldStamp = '2026-05-25T00:00:00Z';
		const oldMs = [
			makeMatch('A', { _cachedAt: oldStamp }),
			makeMatch('B', { _cachedAt: oldStamp })
		];
		const newMs = [makeMatch('A')]; // B dropped
		const merged = mergeCaches(oldMs, newMs, now);
		const a = merged.find((m) => m.id === 'A')!;
		const b = merged.find((m) => m.id === 'B')!;
		expect(a._cachedAt).toBe(now); // refreshed
		expect(b._cachedAt).toBe(oldStamp); // preserved
	});
});

describe('getCacheInfo', () => {
	it('returns fetchedAt, matchCount, remaining from the payload', () => {
		const payload: CachePayload = {
			fetchedAt: '2026-05-29T12:00:00Z',
			remaining: 487,
			matches: [makeMatch('A'), makeMatch('B'), makeMatch('C')]
		};
		expect(getCacheInfo(payload)).toEqual({
			fetchedAt: '2026-05-29T12:00:00Z',
			matchCount: 3,
			remaining: 487
		});
	});

	it('handles zero matches gracefully', () => {
		const payload: CachePayload = {
			fetchedAt: '2026-05-29T12:00:00Z',
			remaining: 500,
			matches: []
		};
		expect(getCacheInfo(payload).matchCount).toBe(0);
	});
});
