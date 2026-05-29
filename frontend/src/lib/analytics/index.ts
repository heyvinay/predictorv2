/**
 * Analytics wrapper — thin abstraction over Umami Cloud.
 *
 * Loaded globally via the script tag in `frontend/src/app.html`, which
 * attaches `window.umami` when `PUBLIC_UMAMI_WEBSITE_ID` is set. This
 * module hides that global so components don't reach for `window.*`
 * directly — keeps the tool swappable in one file.
 *
 * Cloudflare Web Analytics is also loaded in app.html for Core Web
 * Vitals + simple pageviews; it has no custom-event API and isn't
 * exposed here.
 *
 * SSR-safe: every public function short-circuits when `window` is
 * undefined (i.e. during server `load`). Also honours the browser's
 * Do-Not-Track signal — DNT users produce zero analytics traffic.
 */

/** Discriminated event names used across the landing page. Adding a
 *  new event? Add it here first so callsites get autocomplete and the
 *  build catches typos. */
export type EventName =
	| 'landing_view'
	| 'section_viewed'
	| 'cta_clicked'
	| 'signin_email_focused'
	| 'signin_email_submitted'
	| 'signin_google_clicked'
	| 'signin_abandoned'
	| 'news_card_clicked'
	| 'rules_link_clicked'
	| 'countdown_phase';

/** Umami's track() accepts only flat primitive props. */
export type EventProps = Record<string, string | number | boolean>;

interface UmamiGlobal {
	track?: (event: string, props?: EventProps) => void;
	identify?: (id: string, props?: EventProps) => void;
}

/** Fetch the window-attached `umami` object if present. Returns
 *  `undefined` during SSR or before the script tag has loaded. */
function getUmami(): UmamiGlobal | undefined {
	if (typeof window === 'undefined') return undefined;
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	return (window as any).umami as UmamiGlobal | undefined;
}

/** True when the user has explicitly opted out via `navigator.doNotTrack`.
 *  We honour DNT — Umami events stop firing entirely; Cloudflare's beacon
 *  is similarly minimal and we don't try to suppress it client-side. */
function isDntActive(): boolean {
	if (typeof navigator === 'undefined') return false;
	return navigator.doNotTrack === '1';
}

/** Fire a custom event. No-op during SSR, when Umami isn't loaded yet,
 *  or when DNT is on. Never throws. */
export function track(event: EventName, props?: EventProps): void {
	if (isDntActive()) return;
	const umami = getUmami();
	if (!umami?.track) return;
	try {
		umami.track(event, props ?? {});
	} catch {
		// Swallow — analytics must never break the page.
	}
}

/** Tag the current session with a stable, anonymous user id (typically
 *  the user's DB id, NOT email). Call from `+layout.svelte` once auth
 *  hydrates. Optional — used for cross-session funnels. */
export function identify(userId: string, props?: EventProps): void {
	if (isDntActive()) return;
	const umami = getUmami();
	if (!umami?.identify) return;
	try {
		umami.identify(userId, props);
	} catch {
		// Swallow.
	}
}
