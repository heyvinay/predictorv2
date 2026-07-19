/** Home dispatcher (pre / during / post) — extracted pure from
 * +page.svelte so the fourth state (post-tournament wrap-up) is
 * unit-tested without mounting the whole page. */

export type HomeView = 'landing' | 'holding' | 'dash' | 'wrapup';
export type PhaseOverride = 'auto' | 'pre' | 'during' | 'post';

export interface HomeViewInputs {
	isAuthenticated: boolean;
	isAdmin: boolean;
	adminPreviewPool: boolean;
	phaseOverride: PhaseOverride;
	deadlinePassed: boolean;
	postDeadlineLive: boolean;
	tournamentConcluded: boolean;
}

export function resolveHomeView(i: HomeViewInputs): HomeView {
	// Admin phase override (preview switcher) — admins only, client-side only.
	const effective =
		i.isAdmin && i.phaseOverride !== 'auto'
			? i.phaseOverride
			: i.tournamentConcluded
				? 'post'
				: 'auto';

	if (effective === 'post') return 'wrapup';
	if (effective === 'pre') return 'landing';
	if (effective === 'during') return i.isAuthenticated ? 'dash' : 'landing';

	// auto — the pre-existing v2.166.0 model, unchanged
	if (!i.isAuthenticated) return 'landing';
	if (i.isAdmin && !i.adminPreviewPool) return 'dash';
	if (i.postDeadlineLive) return 'dash';
	if (i.deadlinePassed) return 'holding';
	return 'landing';
}
