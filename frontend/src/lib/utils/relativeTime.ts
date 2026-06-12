/**
 * Compact relative-time formatter for freshness cues ("Updated 23s ago").
 *
 * Snaps to the largest reasonable unit so callers can re-render every
 * second without thrashing the DOM with verbose strings. Returns
 * `"just now"` under 5 seconds and `"a while ago"` past 24 hours — the
 * leaderboard polls every 60 s, so the long tail is for backstopped
 * paths (failed poll, tab returning after sleep).
 */
export function relativeAgo(fromIso: string, now = Date.now()): string {
	const t = new Date(fromIso).getTime();
	if (Number.isNaN(t)) return '';
	const secs = Math.max(0, Math.floor((now - t) / 1000));
	if (secs < 5) return 'just now';
	if (secs < 60) return `${secs}s ago`;
	const mins = Math.floor(secs / 60);
	if (mins < 60) return `${mins}m ago`;
	const hrs = Math.floor(mins / 60);
	if (hrs < 24) return `${hrs}h ago`;
	return 'a while ago';
}
