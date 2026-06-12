/**
 * Visibility-aware polling for live-tournament surfaces.
 *
 * `startLivePoll(tick)` runs `tick` every `intervalMs` while the tab is
 * visible. When the tab is hidden the interval stops entirely (no wasted
 * backend load or phone battery); when the user returns, `tick` fires
 * immediately as a catch-up and the interval restarts — so nobody comes
 * back to a minutes-old live score.
 *
 * The initial call does NOT tick (callers have just loaded their data).
 * Returns a stop() that callers must invoke from onDestroy. SSR-safe:
 * a no-op stop is returned when `document` is unavailable.
 */
export function startLivePoll(tick: () => void, intervalMs = 60_000): () => void {
	if (typeof document === 'undefined') return () => {};

	let timer: ReturnType<typeof setInterval> | null = null;

	const start = () => {
		if (!timer) timer = setInterval(tick, intervalMs);
	};
	const stop = () => {
		if (timer) {
			clearInterval(timer);
			timer = null;
		}
	};
	const onVisibility = () => {
		if (document.hidden) {
			stop();
		} else {
			tick();
			start();
		}
	};

	document.addEventListener('visibilitychange', onVisibility);
	if (!document.hidden) start();

	return () => {
		stop();
		document.removeEventListener('visibilitychange', onVisibility);
	};
}
