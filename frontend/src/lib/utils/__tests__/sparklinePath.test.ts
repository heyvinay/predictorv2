import { describe, it, expect } from 'vitest';
import { sparklinePath } from '../sparklinePath';

describe('sparklinePath', () => {
	it('returns empty paths for <2 ranks', () => {
		const r = sparklinePath([5], 30, { width: 100, height: 50 });
		expect(r.linePath).toBe('');
		expect(r.fillPath).toBe('');
		expect(r.points).toEqual([]);
	});

	it('produces 4 points for 4 ranks', () => {
		const r = sparklinePath([10, 8, 5, 3], 30, { width: 90, height: 50 });
		expect(r.points).toHaveLength(4);
		expect(r.points[0][0]).toBeCloseTo(0);
		expect(r.points[3][0]).toBeCloseTo(90);
		expect(r.linePath.startsWith('M')).toBe(true);
		expect(r.fillPath).toContain('Z');
	});

	it('maps rank 1 closer to top than rank maxRank', () => {
		const r = sparklinePath([1, 30], 30, { width: 100, height: 100, padTop: 0, padBottom: 0 });
		// rank 1 → y=0 (top); rank 30 → y=100 (bottom)
		expect(r.points[0][1]).toBeLessThan(r.points[1][1]);
	});
});
