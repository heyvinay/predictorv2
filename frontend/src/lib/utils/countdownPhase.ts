/**
 * Shared urgency-tier logic for every "deadline countdown" surface
 * (landing CountdownBand, navbar CountdownTimer pill, future variants).
 *
 * Source of truth so the navbar pill and the body countdown never
 * disagree on what colour to render at a given time-remaining.
 */

export type CountdownPhase =
	| 'calm'
	| 'heads_up'
	| 'urgent'
	| 'critical'
	| 'locked'
	| 'unknown';

/** Phase boundaries in seconds. Change here → both timers update.
 *
 * Note on the `urgent` threshold: we treat the LAST 48 HOURS as urgent
 * (red colour, pulse), not just <24h. Empirically, at 30+ hours out
 * users perceive the deadline as imminent — "Last day(s)" — and the
 * label/copy escalation in `countdownCopy` below mirrors that, so the
 * pill color shouldn't lag behind. Below 24h is still "Last day" but
 * with sharper subline copy.
 */
const ONE_HOUR_SEC = 3600;
const SIX_HOURS_SEC = 6 * 3600;
const ONE_DAY_SEC = 86_400;
const TWO_DAYS_SEC = 2 * 86_400;
const THREE_DAYS_SEC = 3 * 86_400;
const ONE_WEEK_SEC = 604_800;

export function derivePhase(secondsRemaining: number | null): CountdownPhase {
	if (secondsRemaining === null) return 'unknown';
	if (secondsRemaining <= 0) return 'locked';
	if (secondsRemaining < ONE_HOUR_SEC) return 'critical';
	if (secondsRemaining < TWO_DAYS_SEC) return 'urgent';
	if (secondsRemaining < ONE_WEEK_SEC) return 'heads_up';
	return 'calm';
}

/**
 * Headline label + supporting subline for the given time-remaining.
 *
 * Single source of truth so the navbar pill, the body countdown card,
 * and any future variant pull the same wording from one place. Returns
 * granular phrases inside each phase tier (e.g. heads_up tier spans
 * 2–7 days but says "Final days" near the bottom and "Last week" near
 * the top), so the text never lies about how much time is left.
 *
 * Granularity tiers (escalate as deadline approaches):
 *   > 7d              calm        "Pools locks in"   / plenty-of-time copy
 *   3–7d              heads_up    "Last week"        / N days remaining
 *   2–3d              heads_up    "Final days"       / leave-it-now copy
 *   1–2d              urgent      "Last day"         / day-of urgency
 *   6h–24h            urgent      "Last day"         / hours-of-the-day copy
 *   1h–6h             urgent      "Final hours"      / hour-count copy
 *   < 1h              critical    "Minutes left"     / last-chance copy
 *   ≤ 0               locked      "Locked"           / tournament-begins copy
 *   null              unknown     "Pools"            / generic fallback
 */
export function countdownCopy(
	secondsRemaining: number | null
): { label: string; subline: string } {
	if (secondsRemaining === null) {
		return { label: 'Pools', subline: 'Locks in soon.' };
	}
	if (secondsRemaining <= 0) {
		return { label: 'Locked', subline: 'The tournament begins.' };
	}
	if (secondsRemaining < ONE_HOUR_SEC) {
		const mins = Math.max(1, Math.ceil(secondsRemaining / 60));
		return {
			label: 'Minutes left',
			subline: `${mins} ${mins === 1 ? 'minute' : 'minutes'} until lock. AI Smart Fill finishes in 90 seconds.`
		};
	}
	if (secondsRemaining < SIX_HOURS_SEC) {
		const hours = Math.max(1, Math.ceil(secondsRemaining / 3600));
		return {
			label: 'Final hours',
			subline: `${hours} ${hours === 1 ? 'hour' : 'hours'} to lock in. AI Smart Fill takes 2 minutes.`
		};
	}
	if (secondsRemaining < ONE_DAY_SEC) {
		return {
			label: 'Last day',
			subline: 'Lock in your picks now. AI Smart Fill takes 2 minutes.'
		};
	}
	if (secondsRemaining < TWO_DAYS_SEC) {
		return {
			label: 'Last day',
			subline: "Less than 48 hours. Lock in today — don't leave it to the wire."
		};
	}
	if (secondsRemaining < THREE_DAYS_SEC) {
		return {
			label: 'Final days',
			subline: 'A few days left. Lock in now so a busy week doesn’t catch you out.'
		};
	}
	if (secondsRemaining < ONE_WEEK_SEC) {
		const days = Math.ceil(secondsRemaining / ONE_DAY_SEC);
		return {
			label: 'Last week',
			subline: `${days} days until your picks are frozen. Don't be the friend who forgot.`
		};
	}
	return {
		label: 'Pools locks in',
		subline:
			'Plenty of time. But picks stay editable until the deadline — lock in early, tweak later.'
	};
}

/**
 * Pill-style classes for the compact CountdownTimer chip (bg + border +
 * text + optional pulse). Keep in lockstep with CountdownBand's color
 * tokens so both timers escalate together.
 *
 * Naming note: `warning` is a SURFACE color in this design system, so
 * bare `text-warning` renders nearly invisible on dark chrome. The
 * readable amber foreground is `text-warning-text` (see app.css:7-10).
 * `success` and `error` are foreground-safe under both names, so they
 * use the unsuffixed token.
 */
export function phasePillClasses(phase: CountdownPhase): string {
	switch (phase) {
		case 'critical':
			return 'bg-error/10 border-error/40 text-error animate-pulse-soft';
		case 'urgent':
			return 'bg-error/10 border-error/40 text-error';
		case 'heads_up':
			return 'bg-warning/10 border-warning/40 text-warning-text';
		case 'locked':
			return 'bg-success/10 border-success/40 text-success';
		case 'calm':
		case 'unknown':
		default:
			return 'bg-success/10 border-success/40 text-success';
	}
}
