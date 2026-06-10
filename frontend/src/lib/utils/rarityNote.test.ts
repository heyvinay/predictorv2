import { describe, expect, it } from 'vitest';
import { rarityNote } from './rarityNote';

describe('rarityNote — the four locked D.4 templates', () => {
	it('default variant (live/pending, shared call)', () => {
		expect(rarityNote({ n: 3, total: 31, pts: 6, finished: false })).toBe(
			"Only 3 of 31 entries called this outcome (9.7%) — you'd earn +6 rarity if it holds."
		);
	});

	it('solo variant', () => {
		expect(rarityNote({ n: 1, total: 31, pts: 10, finished: false })).toBe(
			"Only you out of 31 entries called this outcome — you'd earn +10 rarity if it holds."
		);
	});

	it('banked variant (finished)', () => {
		expect(rarityNote({ n: 3, total: 31, pts: 6, finished: true })).toBe(
			'Only 3 of 31 entries called this outcome (9.7%) — banked +6 rarity.'
		);
	});

	it('solo + banked', () => {
		expect(rarityNote({ n: 1, total: 31, pts: 10, finished: true })).toBe(
			'Only you out of 31 entries called this outcome — banked +10 rarity.'
		);
	});

	it('consensus variant (no rarity)', () => {
		expect(rarityNote({ n: 18, total: 31, pts: 0, finished: false })).toBe(
			'Your outcome was the popular call (18 of 31, 58.1%) — no rarity bonus on consensus picks.'
		);
	});

	it('whole percentages drop the decimal', () => {
		expect(rarityNote({ n: 2, total: 4, pts: 0, finished: false })).toContain('(2 of 4, 50%)');
	});

	it('null guards: empty pool or no matching callers', () => {
		expect(rarityNote({ n: 0, total: 31, pts: 5, finished: false })).toBeNull();
		expect(rarityNote({ n: 3, total: 0, pts: 5, finished: false })).toBeNull();
	});
});
