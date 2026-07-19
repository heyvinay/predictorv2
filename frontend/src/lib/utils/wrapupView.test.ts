import { describe, expect, it } from 'vitest';
import { resolveHomeView } from './wrapupView';

describe('resolveHomeView', () => {
	const base = {
		isAuthenticated: false,
		isAdmin: false,
		adminPreviewPool: false,
		phaseOverride: 'auto' as const,
		deadlinePassed: true,
		postDeadlineLive: true,
		tournamentConcluded: false
	};

	it('guest pre-conclusion → landing', () => {
		expect(resolveHomeView({ ...base })).toBe('landing');
	});
	it('guest post-conclusion → wrapup (public page)', () => {
		expect(resolveHomeView({ ...base, tournamentConcluded: true })).toBe('wrapup');
	});
	it('member during tournament → dash', () => {
		expect(resolveHomeView({ ...base, isAuthenticated: true })).toBe('dash');
	});
	it('member post-conclusion → wrapup', () => {
		expect(
			resolveHomeView({ ...base, isAuthenticated: true, tournamentConcluded: true })
		).toBe('wrapup');
	});
	it('admin phase override forces post preview', () => {
		expect(
			resolveHomeView({ ...base, isAuthenticated: true, isAdmin: true, phaseOverride: 'post' })
		).toBe('wrapup');
	});
	it('admin override pre shows the marketing landing', () => {
		expect(
			resolveHomeView({ ...base, isAuthenticated: true, isAdmin: true, phaseOverride: 'pre' })
		).toBe('landing');
	});
	it('override is ignored for non-admins', () => {
		expect(
			resolveHomeView({ ...base, isAuthenticated: true, phaseOverride: 'post' })
		).toBe('dash');
	});
});
