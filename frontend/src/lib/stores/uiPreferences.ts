/**
 * UI preferences — small, device-local flags that persist via
 * localStorage. Keys live under `predictor.ui.*` to keep them grouped
 * and distinguishable from theme / auth keys.
 *
 * Currently only houses the live-standings panel open/closed state
 * for `/entries/[id]`. As more reversible UI flags appear (e.g., a
 * "compact match-card" mode), they should join this file rather than
 * sprinkling new stores around the codebase.
 */

import { writable } from 'svelte/store';
import { browser } from '$app/environment';

const STANDINGS_KEY = 'predictor.ui.standings_panel_open';

function readStandingsInitial(): boolean {
	if (!browser) return false;
	const stored = localStorage.getItem(STANDINGS_KEY);
	if (stored === null) {
		// First-load default: open on wide screens, closed on narrow.
		// 1280px = Tailwind `xl` and the threshold where split layout is
		// comfortable; below that we fall back to drawer-on-demand.
		return window.matchMedia('(min-width: 1280px)').matches;
	}
	return stored === 'true';
}

/** Whether the live-standings side panel is open on the wizard page. */
export const standingsPanelOpen = writable<boolean>(readStandingsInitial());

if (browser) {
	standingsPanelOpen.subscribe((v) => {
		try {
			localStorage.setItem(STANDINGS_KEY, String(v));
		} catch {
			// localStorage unavailable (private mode etc.) — preference still
			// applies for this session; just won't persist across reloads.
		}
	});
}
