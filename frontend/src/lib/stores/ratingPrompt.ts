/**
 * Rating-prompt gating. Shows a one-time "rate the app" card once the user
 * has engaged a few times in a session — never nags, asks once per device.
 *
 * The prompt itself (`RatingPrompt.svelte`) fires the `app_rating_submitted`
 * PostHog event and can hand off to the Tally feedback panel. This module
 * owns only the WHEN: count meaningful page views, reveal after a threshold,
 * and remember that we've asked. Same localStorage idiom as `uiPreferences.ts`.
 */

import { writable } from 'svelte/store';
import { browser } from '$app/environment';

const ASKED_KEY = 'predictor:rating:asked';
const VIEWS_KEY = 'predictor:rating:views';
/** Show after this many meaningful page views in the user's history. */
const VIEW_THRESHOLD = 4;

export const ratingPromptVisible = writable<boolean>(false);

function alreadyAsked(): boolean {
	try {
		return localStorage.getItem(ASKED_KEY) === '1';
	} catch {
		return false;
	}
}

function markAsked(): void {
	try {
		localStorage.setItem(ASKED_KEY, '1');
	} catch {
		// localStorage unavailable — worst case the prompt shows again next
		// session; acceptable for a friendly one-off ask.
	}
}

/**
 * Register a page view toward the rating gate. Reveals the prompt once the
 * threshold is crossed (and it hasn't been asked before). Call from
 * `afterNavigate`. No-op after the user has been asked once.
 */
export function registerViewForRating(): void {
	if (!browser || alreadyAsked()) return;
	let n = 0;
	try {
		n = Number(localStorage.getItem(VIEWS_KEY) ?? '0') + 1;
		localStorage.setItem(VIEWS_KEY, String(n));
	} catch {
		return;
	}
	if (n >= VIEW_THRESHOLD) {
		ratingPromptVisible.set(true);
	}
}

/**
 * Persist "asked" WITHOUT hiding the prompt. Call the moment a star is
 * tapped so a user who rates and then closes the tab is never re-prompted
 * (and never double-counted) — the follow-up "tell us more" step stays
 * visible until they act on it.
 */
export function markRatingAsked(): void {
	markAsked();
}

/**
 * Force-open the rating card regardless of the "asked" gate — for the manual
 * footer "Feedback" entry point. The automatic view-threshold gate above is
 * unaffected.
 */
export function openRatingPrompt(): void {
	ratingPromptVisible.set(true);
}

/** Hide the prompt and mark it asked — no further prompts on this device. */
export function dismissRatingPrompt(): void {
	markAsked();
	ratingPromptVisible.set(false);
}
