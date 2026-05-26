<!--
	CountdownTimer — live "DDd HH:MM:SS" countdown badge.

	Reusable for any deadline (competition start, fixture lock, etc.).
	Takes the deadline as a prop so the component isn't coupled to a
	specific store. Ticks via the existing `currentTime` readable store,
	which is already shared across the app (phase1Countdown,
	phase2Countdown, etc.) — using it here means every visible countdown
	in the UI ticks on the same heartbeat.

	Visual states:
	  - normal       → subtle base-300 badge, base-content text
	  - critical     → error-red bg/border/text when < criticalThresholdSec
	                   remaining (defaults to 6 hours)
	  - past deadline → renders nothing (component disappears entirely)

	Accessibility:
	  - role="timer" (proper ARIA role for a live counter)
	  - aria-live="polite" only when critical — avoids hammering screen
	    readers with 1-Hz announcements for normal long countdowns,
	    surfaces the urgency when it matters
	  - aria-label always carries the human-readable remaining time
-->
<script lang="ts">
	import { currentTime } from '$lib/stores/phase';

	/** ISO 8601 datetime string. `null` → render nothing. */
	export let deadline: string | null = null;

	/**
	 * Below this many seconds remaining, the badge switches to error/red
	 * styling. Default = 6 hours = 21600s.
	 */
	export let criticalThresholdSec: number = 6 * 3600;

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
	$: critical = visible && remainingMs < criticalThresholdSec * 1000;

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
</script>

{#if visible}
	{@const display = formatDdHhMmSs(remainingMs)}
	<div
		role="timer"
		aria-live={critical ? 'polite' : 'off'}
		aria-label="{label}: {display} remaining"
		class="inline-flex items-center {compact ? 'gap-1.5 px-2 py-1' : 'gap-2 px-3 py-1.5'} rounded-lg border font-semibold shadow-sm transition-colors {critical
			? 'bg-error/10 border-error/40 text-error'
			: 'bg-accent border-accent text-accent-content'}"
	>
		{#if !compact}
			<span class="text-[10px] uppercase tracking-wider opacity-80 font-bold">{label}</span>
		{/if}
		<span class="font-mono {compact ? 'text-xs' : 'text-sm'} tabular-nums font-bold">{display}</span>
	</div>
{/if}
