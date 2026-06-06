<!--
	TypographicHero — "MAKE EVERY WORLD CUP MATCH MATTER" brand statement
	on the left, live countdown card on the right. Moved out of
	LandingHero in v2.159 so the prize hero can lead; the countdown
	was promoted into this row so the deadline urgency reads alongside
	the brand statement instead of as a separate band below.
-->
<script lang="ts">
	import CountdownBand from './CountdownBand.svelte';

	export let totalPlayers: number | null = null;
	export let phase1Deadline: string | null = null;

	$: daysToLock = computeDays(phase1Deadline);
	$: trustSignals = buildTrustSignals(totalPlayers, daysToLock);

	function computeDays(iso: string | null): number | null {
		if (!iso) return null;
		const t = new Date(iso).getTime();
		if (Number.isNaN(t)) return null;
		const diffMs = t - Date.now();
		if (diffMs <= 0) return 0;
		return Math.floor(diffMs / (1000 * 60 * 60 * 24));
	}

	function buildTrustSignals(players: number | null, days: number | null): string[] {
		const signals: string[] = [];
		if (players !== null && players >= 1) {
			signals.push('€5 per entry');
		}
		signals.push('AI-ASSISTED PICKS');
		if (days !== null) {
			if (days <= 0) signals.push('Kickoff today');
			else if (days === 1) signals.push('Kickoff in 1d');
			else signals.push(`Kickoff in ${days}d`);
		} else {
			signals.push('Free to play');
		}
		return signals;
	}
</script>

<div class="relative overflow-hidden bg-base-100 noise">
	<div
		class="absolute inset-x-0 top-0 h-[60%] bg-[radial-gradient(ellipse_80%_70%_at_50%_0%,rgba(13,151,72,0.15),transparent_70%)] pointer-events-none"
		aria-hidden="true"
	></div>

	<div
		class="relative max-w-[1200px] mx-auto mobile-padding py-10 sm:py-14 lg:py-20
			grid grid-cols-1 lg:grid-cols-[1.5fr_1fr] gap-8 lg:gap-14 items-center"
	>
		<!-- ── Left column — typographic brand statement ─────────────── -->
		<div>
			<h1
				class="font-hero text-[clamp(36px,7.6vw,108px)] leading-[0.9] tracking-[0.01em]
					text-base-content"
			>
				<span class="block lg:hidden">
					<span class="block">MAKE EVERY WORLD CUP</span>
					<span class="block text-primary">MATCH MATTER.</span>
				</span>
				<span class="hidden lg:block" aria-hidden="true">
					<span class="block">MAKE EVERY</span>
					<span class="block">WORLD CUP</span>
					<span class="block text-primary">MATCH MATTER.</span>
				</span>
			</h1>

			<p
				class="mt-4 sm:mt-5 lg:mt-6 text-base sm:text-[18px] lg:text-[20px]
					text-base-content/80 max-w-2xl leading-relaxed"
			>
				Pick scores, build a bracket, watch the World Cup like it matters. Last tournament's pot:
				<strong class="text-base-content font-semibold">€600</strong>. <span class="block text-primary">Some goes to charity.</span> The
				rest goes to whoever calls the final right.
			</p>

			<div
				class="mt-4 sm:mt-5 flex flex-wrap items-center gap-x-2.5 gap-y-1
					text-[10px] sm:text-[11px] font-mono uppercase tracking-[0.16em] text-base-content/60"
			>
				{#each trustSignals as signal, i (signal)}
					{#if i > 0}<span class="text-primary/70" aria-hidden="true">●</span>{/if}
					<span>{signal}</span>
				{/each}
			</div>
		</div>

		<!-- ── Right column — countdown card ──────────────────────── -->
		<div class="w-full">
			<CountdownBand {phase1Deadline} variant="card" />
		</div>
	</div>
</div>
