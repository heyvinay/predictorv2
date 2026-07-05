/**
 * What's New panel state + "unseen" tracking.
 *
 * The panel itself is a pull surface (users open it); the only push is a
 * passive "New" badge on the nav trigger, shown when the newest curated
 * highlight hasn't been seen on this device. Same one-per-device localStorage
 * idiom as `uiPreferences.ts` (SSR-safe, try/catch around every access).
 */

import { writable, derived } from 'svelte/store';
import { browser } from '$app/environment';
import { latestHighlightId } from '$lib/utils/releases';

const LAST_SEEN_KEY = 'predictor:whatsnew:lastSeenId';

export const whatsNewOpen = writable<boolean>(false);

function readLastSeen(): string {
	// SSR: pretend the latest is already seen so the badge never flashes
	// during hydration for users who HAVE seen it. The client re-reads
	// localStorage on import below.
	if (!browser) return latestHighlightId();
	try {
		return localStorage.getItem(LAST_SEEN_KEY) ?? '';
	} catch {
		return '';
	}
}

/** The highlight id the user last saw (persisted per device). */
export const lastSeenHighlightId = writable<string>(readLastSeen());

/** True when the newest highlight hasn't been seen on this device. */
export const hasUnseenHighlights = derived(
	lastSeenHighlightId,
	($seen) => browser && $seen !== latestHighlightId()
);

/** Open the panel and mark the newest highlight as seen (clears the badge). */
export function openWhatsNew(): void {
	const latest = latestHighlightId();
	if (browser) {
		try {
			localStorage.setItem(LAST_SEEN_KEY, latest);
		} catch {
			// localStorage unavailable — badge may re-show next load; harmless.
		}
	}
	lastSeenHighlightId.set(latest);
	whatsNewOpen.set(true);
}

export function closeWhatsNew(): void {
	whatsNewOpen.set(false);
}
