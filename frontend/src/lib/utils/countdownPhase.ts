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

/** Phase boundaries in seconds. Change here → both timers update. */
const ONE_HOUR_SEC = 3600;
const ONE_DAY_SEC = 86_400;
const ONE_WEEK_SEC = 604_800;

export function derivePhase(secondsRemaining: number | null): CountdownPhase {
	if (secondsRemaining === null) return 'unknown';
	if (secondsRemaining <= 0) return 'locked';
	if (secondsRemaining < ONE_HOUR_SEC) return 'critical';
	if (secondsRemaining < ONE_DAY_SEC) return 'urgent';
	if (secondsRemaining < ONE_WEEK_SEC) return 'heads_up';
	return 'calm';
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
