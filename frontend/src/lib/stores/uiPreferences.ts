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

/** Whether the mobile standings drawer is open on the wizard page.
 *  The desktop docked panel is always visible at xl+ and does NOT use
 *  this store — it's decoupled so SSR's false default doesn't hide it. */
export const standingsPanelOpen = writable<boolean>(false);

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
