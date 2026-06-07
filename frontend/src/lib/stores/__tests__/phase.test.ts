import { describe, it, expect } from 'vitest';
import { deriveUxPhase } from '../phase';
import type { PhaseStatus } from '$types';

const baseStatus: PhaseStatus = {
	current_phase: 'phase_1',
	phase1_deadline: '2026-06-10T00:00:00Z',
	phase1_locked: false,
	is_phase2_active: false,
	phase2_bracket_deadline: null,
	phase2_bracket_locked: false
};

describe('deriveUxPhase', () => {
	it('returns pre_tournament when phaseStatus is null and final not finished', () => {
		expect(deriveUxPhase(null, false)).toBe('pre_tournament');
	});
	it('returns pre_tournament when phase1 is not locked', () => {
		expect(deriveUxPhase(baseStatus, false)).toBe('pre_tournament');
	});
	it('returns during_tournament once phase1 is locked', () => {
		expect(deriveUxPhase({ ...baseStatus, phase1_locked: true }, false)).toBe('during_tournament');
	});
	it('returns post_competition when finalFinished overrides any lock state', () => {
		expect(deriveUxPhase({ ...baseStatus, phase1_locked: true }, true)).toBe('post_competition');
	});
	it('returns post_competition when finalFinished is true even with null phaseStatus', () => {
		expect(deriveUxPhase(null, true)).toBe('post_competition');
	});
});
