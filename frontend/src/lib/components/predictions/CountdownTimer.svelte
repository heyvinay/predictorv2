<!--
	CountdownTimer — live "DDd HH:MM:SS" countdown badge.

	Reusable for any deadline (competition start, fixture lock, etc.).
	Takes the deadline as a prop so the component isn't coupled to a
	specific store. Ticks via the existing `currentTime` readable store,
	which is already shared across the app (phase1Countdown,
	phase2Countdown, etc.) — using it here means every visible countdown
	in the UI ticks on the same heartbeat.

	Visual states (phase tiers shared with CountdownBand via
	$lib/utils/countdownPhase so the navbar pill and the body countdown
	always agree at every tick):
	  - calm     ( > 7d  )  → green
	  - heads_up ( 1-7d  )  → amber
	  - urgent   ( <24h  )  → red
	  - critical ( <1h   )  → red + pulse
	  - locked   ( ≤0    )  → hidden (component disappears)

	Accessibility:
	  - role="timer" (proper ARIA role for a live counter)
	  - aria-live="polite" only when critical — avoids hammering screen
	    readers with 1-Hz announcements for normal long countdowns,
	    surfaces the urgency when it matters
	  - aria-label always carries the human-readable remaining time
-->
<script lang="ts">
	import { currentTime } from '$lib/stores/phase';
	import { derivePhase, phasePillClasses } from '$lib/utils/countdownPhase';

	/** ISO 8601 datetime string. `null` → render nothing. */
	export let deadline: string | null = null;

	/** Left-side label. Defaults to "Deadline". */
	export let label: string = 'Deadline';

	/**
	 * Compact rendering for tight chrome (mobile navbar, dense topbars).
	 * Hides the label and reduces padding/font, keeping only the timer
	 * digits. The pill background + border stay so the chip is still
	 * visually scannable next to other navbar controls.
	 */
	export let compact: boolean = false;

	$: deadlineMs = deadline ? new Date(deadline).getTime() : 0;
	$: remainingMs = deadlineMs ? deadlineMs - $currentTime.getTime() : -1;
	$: visible = remainingMs > 0;
	$: phase = derivePhase(visible ? Math.floor(remainingMs / 1000) : null);
	$: pillClasses = phasePillClasses(phase);
	$: critical = phase === 'critical';

	function formatDdHhMmSs(ms: number): string {
		if (ms <= 0) return '0d 00:00:00';
		const totalSec = Math.floor(ms / 1000);
		const days = Math.floor(totalSec / 86400);
		const hours = Math.floor((totalSec % 86400) / 3600);
		const mins = Math.floor((totalSec % 3600) / 60);
		const secs = totalSec % 60;
		const pad = (n: number) => n.toString().padStart(2, '0');
		return `${days}d ${pad(hours)}:${pad(mins)}:${pad(secs)}`;
	}

	/**
	 * Compact rendering — shorter formats that scale with how-far-away the
	 * deadline is, so the mobile navbar pill never wraps. When days remain,
	 * seconds are noise (the user has 13 days, not 13 seconds, to act).
	 * Under one day, full precision matters again.
	 *
	 *   ≥ 1 day  → "Nd HH:MM"    (e.g. "13d 01:16",  9 chars)
	 *   < 1 day  → "HH:MM:SS"    (e.g. "23:45:12",   8 chars)
	 *   < 1 hour → "MM:SS"       (e.g. "59:42",      5 chars — last-hour urgency)
	 */
	function formatCompact(ms: number): string {
		if (ms <= 0) return '00:00';
		const totalSec = Math.floor(ms / 1000);
		const days = Math.floor(totalSec / 86400);
		const hours = Math.floor((totalSec % 86400) / 3600);
		const mins = Math.floor((totalSec % 3600) / 60);
		const secs = totalSec % 60;
		const pad = (n: number) => n.toString().padStart(2, '0');
		if (days >= 1) return `${days}d ${pad(hours)}:${pad(mins)}`;
		if (hours >= 1) return `${pad(hours)}:${pad(mins)}:${pad(secs)}`;
		return `${pad(mins)}:${pad(secs)}`;
	}
</script>

{#if visible}
	{@const display = compact ? formatCompact(remainingMs) : formatDdHhMmSs(remainingMs)}
	{@const ariaDisplay = formatDdHhMmSs(remainingMs)}
	<div
		role="timer"
		aria-live={critical ? 'polite' : 'off'}
		aria-label="{label}: {ariaDisplay} remaining"
		class="inline-flex items-center whitespace-nowrap {compact ? 'gap-1.5 px-2 py-1' : 'gap-2 px-3 py-1.5'} rounded-lg border font-semibold shadow-sm transition-colors {pillClasses}"
	>
		{#if !compact}
			<span class="text-[10px] uppercase tracking-wider opacity-80 font-bold">{label}</span>
		{/if}
		<span class="font-mono {compact ? 'text-xs' : 'text-sm'} tabular-nums font-bold whitespace-nowrap">{display}</span>
	</div>
{/if}
