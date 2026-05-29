/**
 * Unit tests for the news deduplicator. Verifies the Jaccard threshold
 * behaviour (catches paraphrases at 0.85, leaves distinct stories
 * alone) and the "keep earliest" tie-breaking rule.
 */
import { describe, it, expect } from 'vitest';
import { dedupeByTitle, tokenize, jaccard, DEFAULT_DEDUPE_THRESHOLD } from './dedupe';
import type { NewsItem } from './types';

function item(title: string, isoTime: string, source = 'BBC Sport'): NewsItem {
	return {
		source,
		title,
		link: `https://example.com/${encodeURIComponent(title)}`,
		publishedAt: isoTime
	};
}

describe('tokenize', () => {
	it('lowercases, drops punctuation, drops short tokens', () => {
		const tokens = tokenize("England beat Brazil 3-2 in WC qualifier");
		expect(tokens.has('england')).toBe(true);
		expect(tokens.has('beat')).toBe(true);
		expect(tokens.has('brazil')).toBe(true);
		// Numbers and short tokens dropped (length ≤ 2).
		expect(tokens.has('3')).toBe(false);
		expect(tokens.has('2')).toBe(false);
		expect(tokens.has('in')).toBe(false);
	});

	it('returns empty set for a title of only short words', () => {
		expect(tokenize('a b c').size).toBe(0);
	});
});

describe('jaccard', () => {
	it('returns 1 for identical token sets', () => {
		const a = new Set(['england', 'beat', 'brazil']);
		const b = new Set(['brazil', 'beat', 'england']);
		expect(jaccard(a, b)).toBe(1);
	});

	it('returns 0 for fully disjoint sets', () => {
		const a = new Set(['england', 'beat']);
		const b = new Set(['france', 'won']);
		expect(jaccard(a, b)).toBe(0);
	});

	it('returns 0 when either set is empty', () => {
		expect(jaccard(new Set(), new Set(['x']))).toBe(0);
		expect(jaccard(new Set(['x']), new Set())).toBe(0);
	});

	it('computes intersection/union correctly', () => {
		const a = new Set(['england', 'beat', 'brazil']);
		const b = new Set(['england', 'beat', 'germany']);
		// intersection = 2 (england, beat), union = 4
		expect(jaccard(a, b)).toBe(2 / 4);
	});
});

describe('dedupeByTitle', () => {
	it('preserves order and content when no duplicates exist', () => {
		const items = [
			item('England beat Brazil', '2026-05-01T10:00:00Z'),
			item('France draw with Germany', '2026-05-01T11:00:00Z'),
			item('Italy lose to Spain', '2026-05-01T12:00:00Z')
		];
		const result = dedupeByTitle(items);
		expect(result).toHaveLength(3);
		expect(result.map((r) => r.title)).toEqual(items.map((i) => i.title));
	});

	it('deduplicates near-identical paraphrases above the default threshold', () => {
		const items = [
			item('England beat Brazil 3-2 in World Cup qualifier', '2026-05-01T10:00:00Z', 'BBC Sport'),
			item(
				'England beat Brazil in World Cup qualifier 3-2',
				'2026-05-01T11:00:00Z',
				'Guardian Football'
			)
		];
		const result = dedupeByTitle(items);
		expect(result).toHaveLength(1);
		// Earlier item wins (the original publication).
		expect(result[0].source).toBe('BBC Sport');
		expect(result[0].publishedAt).toBe('2026-05-01T10:00:00Z');
	});

	it('keeps the earlier item when a later "duplicate" arrives', () => {
		const items = [
			item('Germany name squad for World Cup', '2026-05-02T10:00:00Z', 'Guardian Football'),
			// "earlier" version, but processed second
			item('Germany name squad for the World Cup', '2026-05-02T08:00:00Z', 'BBC Sport')
		];
		const result = dedupeByTitle(items);
		expect(result).toHaveLength(1);
		// The 08:00 version is earlier — should win the tie-break.
		expect(result[0].publishedAt).toBe('2026-05-02T08:00:00Z');
		expect(result[0].source).toBe('BBC Sport');
	});

	it('leaves distinct stories alone (below threshold)', () => {
		const items = [
			item('England beat Brazil in friendly', '2026-05-01T10:00:00Z'),
			// Different teams, completely different story.
			item('France draw with Germany in qualifier', '2026-05-01T11:00:00Z')
		];
		const result = dedupeByTitle(items);
		expect(result).toHaveLength(2);
	});

	it('honours a lower threshold to merge more aggressively', () => {
		const items = [
			// Tokens: {england, beat, brazil, friendly}
			item('England beat Brazil in friendly', '2026-05-01T10:00:00Z'),
			// Tokens: {england, loss, brazil, qualifier}
			//   intersection = {england, brazil} = 2; union = 6;
			//   Jaccard ≈ 0.33 → separate at 0.85, merged at 0.30.
			item('England loss Brazil in qualifier', '2026-05-01T11:00:00Z')
		];
		expect(dedupeByTitle(items, 0.85)).toHaveLength(2);
		expect(dedupeByTitle(items, 0.3)).toHaveLength(1);
	});

	it('handles items with empty / short titles gracefully (no false-dedupes)', () => {
		const items = [
			item('a b', '2026-05-01T10:00:00Z'),
			item('c d', '2026-05-01T11:00:00Z')
		];
		// Both tokenize to empty — algorithm keeps both rather than merging
		// (can't confidently call them duplicates).
		expect(dedupeByTitle(items)).toHaveLength(2);
	});

	it('uses 0.4 as the default threshold', () => {
		// Tuned against real BBC ↔ Guardian paraphrases of the same
		// World Cup story. See comment in dedupe.ts.
		expect(DEFAULT_DEDUPE_THRESHOLD).toBe(0.4);
	});

	it('catches paraphrases that share most content words', () => {
		// Two outlets covering the same story with mostly-shared wording.
		// After stopword filtering, ~4/5 tokens overlap → Jaccard well
		// above 0.4 → merged.
		const items = [
			item('Brazil announce 26-man World Cup squad', '2026-05-01T10:00:00Z', 'BBC Sport'),
			item('Brazil announce their 26-man squad for the World Cup', '2026-05-01T11:00:00Z', 'Guardian Football')
		];
		expect(dedupeByTitle(items)).toHaveLength(1);
	});

	it('leaves heavy-rewrite paraphrases separate (honest limitation)', () => {
		// Both outlets cover the same Messi news with different verbs,
		// different framings — only "messi" and "sixth" overlap after
		// stopword filtering. Jaccard ≈ 0.33, below the 0.4 default.
		// Jaccard at lower thresholds starts merging *different* stories
		// that share a subject, so we accept this as the honest limit.
		// Embedding-based dedupe could catch these; out of scope for v1.
		const items = [
			item('Messi to represent Argentina at sixth World Cup', '2026-05-01T10:00:00Z'),
			item('Messi confirms he will play at sixth World Cup', '2026-05-01T11:00:00Z')
		];
		expect(dedupeByTitle(items)).toHaveLength(2);
	});
});

describe('STOPWORDS filtering', () => {
	it('drops common English connectives', () => {
		const tokens = tokenize('England beat Brazil with goals from the striker');
		expect(tokens.has('with')).toBe(false);
		expect(tokens.has('the')).toBe(false);
		expect(tokens.has('from')).toBe(false);
		// Content words preserved
		expect(tokens.has('england')).toBe(true);
		expect(tokens.has('beat')).toBe(true);
		expect(tokens.has('brazil')).toBe(true);
		expect(tokens.has('goals')).toBe(true);
		expect(tokens.has('striker')).toBe(true);
	});

	it('drops WC-context noise (world, cup, football)', () => {
		const tokens = tokenize('Brazil eye World Cup glory after qualifying for the football tournament');
		expect(tokens.has('world')).toBe(false);
		expect(tokens.has('cup')).toBe(false);
		expect(tokens.has('football')).toBe(false);
		// Content words preserved
		expect(tokens.has('brazil')).toBe(true);
		expect(tokens.has('glory')).toBe(true);
		expect(tokens.has('qualifying')).toBe(true);
		expect(tokens.has('tournament')).toBe(true);
	});
});
