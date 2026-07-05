/**
 * Contextual feature nudges — the "interrupt" layer that fires a single
 * toast the first time a user lands where a new feature lives, then never
 * again. Sits on top of the passive What's New badge.
 *
 * Frequency caps (both must pass):
 *   - once per feature, per device  → localStorage `predictor:nudge:{id}`
 *   - at most one nudge per session → sessionStorage session flag
 *
 * Wired into `+layout.svelte`'s `afterNavigate`. Add a new nudge by pushing
 * to NUDGES with a fresh `featureId` (bumping the id re-arms it for everyone).
 */

import { browser } from '$app/environment';
import { pushToast } from '$lib/stores/toast';
import { track } from '$lib/analytics';

interface FeatureNudge {
	/** Stable per-feature id; also the localStorage key suffix. */
	featureId: string;
	/** Does the current path host this feature? */
	matchPath: (path: string) => boolean;
	title: string;
	message: string;
	href?: string;
	cta?: string;
}

const NUDGES: FeatureNudge[] = [
	{
		featureId: 'bracket-simulator-2194',
		matchPath: (p) => p.startsWith('/results'),
		title: 'New: What-if Bracket Simulator',
		message: 'Play out the rest of the knockouts and see how the pool would re-rank.',
		href: '/results',
		cta: 'Show me →'
	},
	{
		featureId: 'leaderboard-race-2164',
		matchPath: (p) => p.startsWith('/leaderboard'),
		title: 'New: the Race view',
		message: 'Watch how your rank has moved across the tournament.',
		href: '/leaderboard',
		cta: 'Show me →'
	}
];

const SESSION_FIRED_KEY = 'predictor:nudge:session-fired';
const seenKey = (id: string) => `predictor:nudge:${id}`;

function alreadySeen(id: string): boolean {
	try {
		return localStorage.getItem(seenKey(id)) === '1';
	} catch {
		return false;
	}
}

function markSeen(id: string): void {
	try {
		localStorage.setItem(seenKey(id), '1');
	} catch {
		// localStorage unavailable — nudge may repeat; harmless.
	}
}

function firedThisSession(): boolean {
	try {
		return sessionStorage.getItem(SESSION_FIRED_KEY) === '1';
	} catch {
		return false;
	}
}

function markFiredThisSession(): void {
	try {
		sessionStorage.setItem(SESSION_FIRED_KEY, '1');
	} catch {
		// no session cap available — the per-feature cap still holds.
	}
}

/**
 * Fire at most one contextual nudge for the given path. No-op on the server,
 * when a nudge already fired this session, or when the matching feature has
 * already been seen on this device.
 */
export function maybeFireNudge(path: string): void {
	if (!browser || firedThisSession()) return;
	const nudge = NUDGES.find((n) => n.matchPath(path) && !alreadySeen(n.featureId));
	if (!nudge) return;

	markSeen(nudge.featureId);
	markFiredThisSession();

	pushToast({
		title: nudge.title,
		message: nudge.message,
		href: nudge.href,
		cta: nudge.cta,
		onCta: () => track('feature_nudge_clicked', { feature_id: nudge.featureId })
	});
	track('feature_nudge_shown', { feature_id: nudge.featureId });
}
