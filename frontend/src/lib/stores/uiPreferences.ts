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

// ─── Simulator discoverability nudge (v2.194.x) ─────────────────────────────
// One-per-user localStorage flag flipped the first time the user lands on
// the Results → Bracket tab AFTER the admin has enabled the simulator.
// Consumed by: the "NEW" dot on the Results rail-nav item (+layout.svelte),
// the "NEW" dot on the Bracket tab pill (RoundTabs), and the one-time hint
// tooltip on the Simulate toggle (SimulatorPanel). Once seen, all three
// nudges vanish permanently for that user on that device.
const SIMULATOR_SEEN_KEY = 'predictor.ui.simulator_seen';

function readSimulatorSeen(): boolean {
	if (!browser) return false;
	try {
		return localStorage.getItem(SIMULATOR_SEEN_KEY) === '1';
	} catch {
		return false;
	}
}

export const simulatorSeen = writable<boolean>(readSimulatorSeen());

/** Mark the simulator as discovered — call once when the user opens the
 *  Bracket tab (or dismisses the intro tooltip). Idempotent; safe to call
 *  from multiple surfaces. */
export function markSimulatorSeen(): void {
	if (!browser) return;
	try {
		localStorage.setItem(SIMULATOR_SEEN_KEY, '1');
	} catch {
		// localStorage unavailable — the nudge will keep showing until it
		// works or the user upgrades their browser; harmless either way.
	}
	simulatorSeen.set(true);
}
