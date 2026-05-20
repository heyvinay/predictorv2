import { describe, expect, it } from 'vitest';

import {
	stubRankTrajectory,
	stubSocialSignal,
	stubHotPick,
	stubBracketExposure,
	stubUnderdogStats,
	stubSteepestClimb,
	stubBonusHaul,
	sparklinePath
} from './widgetFallbacks';

describe('stubRankTrajectory', () => {
	it('is deterministic for the same seed', () => {
		const a = stubRankTrajectory('user-1', 8, 32);
		const b = stubRankTrajectory('user-1', 8, 32);
		expect(a).toEqual(b);
	});

	it('anchors the final point to the current rank', () => {
		const t = stubRankTrajectory('user-9', 14, 32);
		expect(t.ranks[6]).toBe(14);
	});

	it('produces 7 values', () => {
		expect(stubRankTrajectory('x', 1, 50).ranks).toHaveLength(7);
	});

	it('keeps ranks within [1, maxRank]', () => {
		const t = stubRankTrajectory('edge', 1, 5);
		for (const r of t.ranks) {
			expect(r).toBeGreaterThanOrEqual(1);
			expect(r).toBeLessThanOrEqual(5);
		}
	});

	it('yields different outputs for different users', () => {
		const a = stubRankTrajectory('alpha', 10, 32);
		const b = stubRankTrajectory('beta', 10, 32);
		// They share the anchor (index 6) — earlier days should differ.
		expect(a.ranks.slice(0, 6)).not.toEqual(b.ranks.slice(0, 6));
	});
});

describe('stubSocialSignal', () => {
	it('is deterministic', () => {
		const a = stubSocialSignal('fixt-42', 32);
		const b = stubSocialSignal('fixt-42', 32);
		expect(a).toEqual(b);
	});

	it('keeps agreesExact ≤ agreesOutcome ≤ total', () => {
		for (let i = 0; i < 20; i++) {
			const s = stubSocialSignal(`f${i}`, 32);
			expect(s.agreesExact).toBeLessThanOrEqual(s.agreesOutcome);
			expect(s.agreesOutcome).toBeLessThanOrEqual(s.total);
			expect(s.agreesExact).toBeGreaterThanOrEqual(1);
		}
	});
});

describe('stubHotPick', () => {
	it('returns null on empty candidates', () => {
		expect(stubHotPick([])).toBeNull();
	});

	it('picks the rarest candidate', () => {
		const candidates = [
			{ fixtureId: 'a', homeCode: 'ARG', awayCode: 'CRO', yourScore: [2, 1] as [number, number] },
			{ fixtureId: 'b', homeCode: 'BRA', awayCode: 'SUI', yourScore: [2, 0] as [number, number] },
			{ fixtureId: 'c', homeCode: 'FRA', awayCode: 'POL', yourScore: [1, 0] as [number, number] }
		];
		const hp = stubHotPick(candidates);
		expect(hp).not.toBeNull();
		expect(candidates.map((c) => c.fixtureId)).toContain(hp!.fixtureId);
		expect(hp!.multiplier).toBeGreaterThanOrEqual(1);
		expect(hp!.potentialPoints).toBe(15);
	});
});

describe('stubBracketExposure', () => {
	it('returns the fixed mock', () => {
		const e = stubBracketExposure('any-user');
		expect(e.pointsAvailable).toBe(235);
		expect(e.picksLocked).toBe(22);
		expect(e.picksTotal).toBe(22);
		expect(e.finalPick?.winnerCode).toBe('ARG');
	});
});

describe('stubUnderdogStats', () => {
	it('is deterministic', () => {
		const a = stubUnderdogStats('user-1');
		const b = stubUnderdogStats('user-1');
		expect(a).toEqual(b);
	});

	it('returns 1–3 example codes', () => {
		const stats = stubUnderdogStats('user-2');
		expect(stats.exampleCodes.length).toBeGreaterThanOrEqual(1);
		expect(stats.exampleCodes.length).toBeLessThanOrEqual(3);
		expect(stats.count).toBe(stats.exampleCodes.length);
	});
});

describe('stubSteepestClimb', () => {
	it('uses currentMovement as yourPlaces', () => {
		expect(stubSteepestClimb('u', 4, 32).yourPlaces).toBe(4);
	});

	it('puts strong climbers in the top 5', () => {
		const s = stubSteepestClimb('u', 6, 32);
		expect(s.rankAmongClimbers).toBeLessThanOrEqual(5);
	});
});

describe('stubBonusHaul', () => {
	it('sums underdog and exact contributions', () => {
		const h = stubBonusHaul('u-1', 3);
		expect(h.total).toBe(h.fromUnderdogs + h.fromExact);
		expect(h.fromExact).toBe(3 * 5);
	});
});

describe('sparklinePath', () => {
	it('returns empty paths for < 2 points', () => {
		expect(sparklinePath([5], 32, { width: 100, height: 20 })).toEqual({
			linePath: '',
			fillPath: '',
			points: []
		});
	});

	it('starts with M and uses L for subsequent points', () => {
		const { linePath, points } = sparklinePath([1, 2, 3], 5, { width: 100, height: 20 });
		expect(linePath.startsWith('M')).toBe(true);
		expect(linePath.split('L').length).toBe(3); // "M..L..L.."
		expect(points).toHaveLength(3);
	});

	it('places the first x at 0 and last x at width', () => {
		const { points } = sparklinePath([1, 2, 3, 4], 10, { width: 100, height: 20 });
		expect(points[0][0]).toBe(0);
		expect(points[3][0]).toBe(100);
	});

	it('closes the fill path back to the origin', () => {
		const { fillPath } = sparklinePath([1, 5], 10, { width: 100, height: 20 });
		expect(fillPath.endsWith('Z')).toBe(true);
		expect(fillPath).toContain('L100,20');
		expect(fillPath).toContain('L0,20');
	});
});
