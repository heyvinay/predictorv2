/**
 * Per-feature "Was this useful?" verdicts, captured inside the What's New
 * panel. Deliberately low-friction: one 👍/👎 per feature card, only visible
 * to users who chose to open the panel, recorded once and never re-asked.
 *
 * The verdict goes to PostHog (`feature_rated`); we persist per device only
 * to hide the control after answering and to prevent double counting.
 */

import { writable, get } from 'svelte/store';
import { browser } from '$app/environment';
import { track } from '$lib/analytics';

export type FeatureVerdict = 'up' | 'down';

const KEY = 'predictor:whatsnew:feedback';

function readAll(): Record<string, FeatureVerdict> {
	if (!browser) return {};
	try {
		return JSON.parse(localStorage.getItem(KEY) ?? '{}') as Record<string, FeatureVerdict>;
	} catch {
		return {};
	}
}

/** Map of feature id → the verdict this device has already given (if any). */
export const featureVerdicts = writable<Record<string, FeatureVerdict>>(readAll());

/**
 * Record a verdict for a feature. No-op if this device already rated it
 * (keeps the PostHog signal one-per-user and the UI stable).
 */
export function rateFeature(id: string, verdict: FeatureVerdict): void {
	const current = get(featureVerdicts);
	if (current[id]) return;

	const next = { ...current, [id]: verdict };
	if (browser) {
		try {
			localStorage.setItem(KEY, JSON.stringify(next));
		} catch {
			// localStorage unavailable — verdict still applies this session.
		}
	}
	featureVerdicts.set(next);
	track('feature_rated', { feature_id: id, verdict });
}
