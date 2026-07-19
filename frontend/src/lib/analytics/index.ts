/**
 * Analytics wrapper — single source of truth for event tracking.
 *
 * v2.155.0 migrated this from Umami Cloud to PostHog (browser SDK +
 * optional server-side path for ad-block resistance). The public API
 * — `track()` and `identify()` — is unchanged so the 12+ existing
 * call sites work without modification.
 *
 * Architecture:
 *   USER ACTION → track('event_name', {props}, { alsoServer?: true })
 *      │
 *      ├─► posthog.capture() ─────────► PostHog EU (browser path)
 *      │                                 ├─ Autocapture
 *      │                                 ├─ Heatmaps (derived)
 *      │                                 └─ Custom events
 *      │
 *      └─► POST /api/telemetry/event ─► Backend → PostHog EU
 *           (only when alsoServer=true; ad-block-resistant)
 *
 * Privacy:
 *   - Honours navigator.doNotTrack — DNT users produce ZERO events
 *     (both browser and server paths skip).
 *   - Session recording is explicitly disabled (privacy concern with
 *     typed predictions / paid_to / score inputs).
 *   - Autocapture records element selectors + visible text, NOT typed
 *     input contents. Sensitive inputs additionally carry
 *     `data-ph-no-capture` to be excluded even from element-identity
 *     capture.
 *   - distinct_id is the user's UUID — never name/email.
 *
 * SSR-safe: every public function short-circuits when `window` is
 * undefined (i.e. during server `load`).
 *
 * Cloudflare Web Analytics continues to run via app.html's separate
 * script tag for Core Web Vitals + edge-level pageview counts — it's
 * independent of this module.
 */

import posthog from 'posthog-js';
import { browser } from '$app/environment';
import { env as publicEnv } from '$env/dynamic/public';

/** Discriminated event names used across the app. Adding a new event?
 *  Add it here first so call sites get autocomplete and the build
 *  catches typos. Backend's ALLOWED_EVENTS set in api/telemetry.py
 *  mirrors this list for any event fired with `alsoServer: true`. */
export type EventName =
	// Landing-page funnels (pre-existing — kept verbatim from v2.154.x)
	| 'landing_view'
	| 'section_viewed'
	| 'cta_clicked'
	| 'signin_email_focused'
	| 'signin_email_submitted'
	| 'signin_google_clicked'
	| 'signin_abandoned'
	| 'news_card_clicked'
	| 'rules_link_clicked'
	| 'countdown_phase'
	// SmartFill (v2.154.3 — now flow through this wrapper)
	| 'smartfill_opened'
	| 'smartfill_applied'
	// Navigation (v2.155.0)
	| 'page_viewed'
	| 'nav_clicked'
	// V4 Dashboard (v2.165.0)
	| 'dashboard_view'
	// v2.176.2 — feature-usage signals for the Site Pulse panel.
	// match_detail_opened fires when a user clicks a fixture row to
	// open /results/{id}; carries fixture_id so PostHog UI can break
	// it down by match. leaderboard_view_changed fires when the
	// /leaderboard view tab is switched; carries view = table/race/
	// insights so PostHog UI can break it down by view choice.
	| 'match_detail_opened'
	| 'leaderboard_view_changed'
	// v2.178.0 — sheet button click on /leaderboard. Pairs with the
	// UTM-tagged email link to give email→app and email→sheet
	// attribution. No backend mirroring (frontend-fired only).
	| 'view_all_entries_clicked'
	// Reserved for future server-side fires (declared in advance so
	// allow-list and dashboards stay aligned). Add backend
	// analytics.capture() call sites for these as they get wired.
	| 'entry_created'
	| 'entry_submitted'
	| 'entry_unlocked'
	| 'user_signed_in'
	| 'user_onboarded'
	| 'prediction_saved'
	// v2.194.x — what-if bracket simulator funnel (Results → Bracket tab):
	// bracket_tab_opened (funnel entry) → simulator_gate_opened (game show
	// launched) → simulator_challenge_submitted {result, used_5050} →
	// simulator_unlocked → simulator_toggled_on → simulator_run_committed
	// {picks_count, champion_set}. All browser-fired; the unlock is also
	// audited server-side (feature.simulator_unlocked) for durability, so
	// no alsoServer / ALLOWED_EVENTS mirroring is needed here.
	| 'bracket_tab_opened'
	| 'simulator_gate_opened'
	| 'simulator_challenge_submitted'
	| 'simulator_unlocked'
	| 'simulator_toggled_on'
	| 'simulator_run_committed'
	// Feature awareness + feedback (What's New panel, contextual nudges,
	// rating prompt). All browser-fired; no backend allow-list entry needed.
	// whats_new_feature_clicked / feature_nudge_* carry feature_id;
	// app_rating_submitted carries rating (1-5).
	| 'whats_new_opened'
	| 'whats_new_feature_clicked'
	| 'feature_nudge_shown'
	| 'feature_nudge_clicked'
	| 'app_rating_submitted'
	// Written feedback submitted from the rating card (emailed server-side).
	// Carries rating + has_message. Also fired server-side in api/feedback.py.
	| 'feedback_submitted'
	// Per-feature "Was this useful?" verdict from a What's New card.
	// Carries feature_id + verdict ('up' | 'down').
	| 'feature_rated'
	// /compare head-to-head page. compare_opened carries default_pair
	// (whether ?a=/?b= were absent, i.e. the page picked defaults);
	// compare_pair_changed carries via ('picker' | 'swap');
	// compare_tab_changed carries tab ('matches' | 'bracket' | 'bonus');
	// compare_swings_expanded fires only on collapse→expand (not the
	// reverse), carries total_swings. All browser-fired; no backend
	// allow-list entry needed.
	| 'compare_opened'
	| 'compare_pair_changed'
	| 'compare_tab_changed'
	| 'compare_swings_expanded'
	// Post-tournament wrap-up page (Plan C). wrapup_viewed fires once on
	// mount (auth_state); wrapup_podium_row_clicked carries rank (1-3);
	// wrapup_verified_link_clicked has no props. Registered under the
	// "wrapup" feature group in backend/app/services/usage.py, which also
	// lists wrapup_compare_cta_clicked / wrapup_matrix_compare_clicked /
	// wrapup_leaderboard_full_clicked / wrapup_footer_link_clicked /
	// wrapup_signin_started for later wrap-up tasks — add those here as
	// each is actually wired up.
	| 'wrapup_viewed'
	| 'wrapup_podium_row_clicked'
	| 'wrapup_verified_link_clicked';

/** Event property payload. Flat primitives only — PostHog stores these
 *  as searchable filterable fields. Avoid nested objects (PostHog
 *  flattens via dot-notation but you lose typed filtering). */
export type EventProps = Record<string, string | number | boolean | null | undefined>;

export interface TrackOptions {
	/** Also POST the event to /api/telemetry/event for ad-block-resistant
	 *  capture. Use for events you can't afford to lose to ~25% of
	 *  users running ad-blockers (e.g. `entry_submitted`,
	 *  `smartfill_applied`, `signin_succeeded`). Default false. */
	alsoServer?: boolean;
}

let initialized = false;

/** True when the user has explicitly opted out via navigator.doNotTrack.
 *  Both browser and server paths honour this — DNT users produce zero
 *  events. */
function isDntActive(): boolean {
	if (typeof navigator === 'undefined') return false;
	return navigator.doNotTrack === '1';
}

/** Initialise the PostHog browser SDK. Call once from the root layout's
 *  onMount. Idempotent (safe to call multiple times). No-op when:
 *    - SSR (no `window`)
 *    - Already initialised
 *    - PUBLIC_POSTHOG_KEY empty (dev/local without analytics)
 *    - User has DNT enabled
 *
 *  Init config favours privacy and the user's stated preferences:
 *    - capture_pageview: true     (powers heatmaps + funnels)
 *    - autocapture: true          (click tracking without instrumentation)
 *    - disable_session_recording: true (privacy)
 *    - respect_dnt: true          (belt-and-braces with isDntActive)
 *    - persistence: localStorage  (no third-party cookies)
 */
export function initAnalytics(): void {
	if (!browser || initialized) return;
	const key = publicEnv.PUBLIC_POSTHOG_KEY;
	if (!key) return;
	if (isDntActive()) return;
	try {
		posthog.init(key, {
			api_host: publicEnv.PUBLIC_POSTHOG_HOST || 'https://eu.i.posthog.com',
			capture_pageview: true,
			autocapture: true,
			disable_session_recording: true,
			respect_dnt: true,
			persistence: 'localStorage',
		});
		initialized = true;
	} catch {
		// Analytics init must never break the app.
	}
}

/** Fire a custom event. Browser-side via posthog-js + optionally
 *  server-side via /api/telemetry/event for ad-block resistance. */
export function track(event: EventName, props?: EventProps, opts?: TrackOptions): void {
	if (!browser || isDntActive()) return;

	// Browser-side capture. Silent no-op if posthog-js isn't initialised
	// (e.g. no key configured, init not yet called) or if the call throws.
	if (initialized) {
		try {
			posthog.capture(event, props as Record<string, unknown> | undefined);
		} catch {
			// noop — analytics must never break the app
		}
	}

	// Optional server-side capture for guaranteed delivery. Fire-and-forget;
	// failures (network down, 400 on unknown event) are swallowed.
	if (opts?.alsoServer) {
		void fetch('/api/telemetry/event', {
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({ event, properties: props }),
			credentials: 'include',
		}).catch(() => {
			// noop
		});
	}
}

/** Tag the current session with a stable, anonymous user id (the user's
 *  DB UUID, NOT email). Call from +layout.svelte once auth hydrates so
 *  events get attributed to a user across pageloads / devices.
 *
 *  Per PostHog identify() semantics: subsequent events under this
 *  distinct_id will be associated with this user. No PII passes through —
 *  PostHog only sees the UUID. */
export function identify(userId: string, props?: EventProps): void {
	if (!browser || !initialized || isDntActive()) return;
	try {
		posthog.identify(userId, props as Record<string, unknown> | undefined);
	} catch {
		// noop
	}
}
