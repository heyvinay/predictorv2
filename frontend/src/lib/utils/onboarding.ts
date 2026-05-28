import type { User } from '$types';

/**
 * Whether a user still needs to complete onboarding.
 *
 * Mandatory fields: full name and employer; plus a company contact when
 * employer is "neither". Existing/Google accounts (which already have a
 * name) are caught by the missing-employer check, so they're routed
 * through onboarding to back-fill the new fields.
 */
export function needsOnboarding(u: User | null | undefined): boolean {
	if (!u) return false;
	if (!u.name) return true;
	if (!u.employer) return true;
	if (u.employer === 'neither' && !u.company_contact) return true;
	return false;
}

/**
 * What value to pre-fill the "Name of the person you paid the fee to"
 * input with on a fresh edit.
 *
 * Rule (R10.4): if the user already has an explicit paid_to, use that.
 * Otherwise, when their employer is "neither", default to the
 * company_contact they recorded — most users in that situation paid
 * their Atlas/JMFA contact, so it's a useful nudge. The user can always
 * override before submitting. We never silently persist this default —
 * it's display-only until the user submits/saves.
 */
export function defaultPaidTo(u: User | null | undefined): string {
	if (!u) return '';
	if (u.paid_to) return u.paid_to;
	if (u.employer === 'neither' && u.company_contact) return u.company_contact;
	return '';
}
