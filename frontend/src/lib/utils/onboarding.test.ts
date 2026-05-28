import { describe, expect, it } from 'vitest';

import type { Employer, User } from '$types';
import { needsOnboarding } from './onboarding';

function makeUser(overrides: Partial<User> = {}): User {
	return {
		id: 'u1',
		email: 'u@example.com',
		name: 'Full Name',
		auth_provider: 'email',
		is_admin: false,
		is_active: true,
		competition_id: null,
		created_at: '2026-01-01T00:00:00Z',
		employer: 'atlas',
		company_contact: null,
		paid_to: null,
		...overrides
	};
}

describe('needsOnboarding', () => {
	it('false for null user (nothing to route yet)', () => {
		expect(needsOnboarding(null)).toBe(false);
	});

	it('true when name is missing', () => {
		expect(needsOnboarding(makeUser({ name: null }))).toBe(true);
	});

	it('true when employer is missing (catches existing/Google accounts)', () => {
		expect(needsOnboarding(makeUser({ employer: null }))).toBe(true);
	});

	it('true when employer is neither but contact is missing', () => {
		expect(needsOnboarding(makeUser({ employer: 'neither', company_contact: null }))).toBe(true);
	});

	it('false when employer is neither and a contact is set', () => {
		expect(
			needsOnboarding(makeUser({ employer: 'neither', company_contact: 'Dana' }))
		).toBe(false);
	});

	it.each(['atlas', 'jmfa'] as Employer[])('false for complete %s profile', (e) => {
		expect(needsOnboarding(makeUser({ employer: e }))).toBe(false);
	});
});
