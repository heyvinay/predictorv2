<!--
	LandingHero — the page's opening surface. Split grid: copy on the
	left, an auth-aware card on the right (SignInCard for guests,
	WelcomeBackCard for returning members). Stadium-glow radial behind
	the headline. Trust signals row sits below the subhead.

	The H1's last line ("MATCH MATTER.") is rendered in `text-primary`
	gold per the handoff. Sizing uses `clamp()` so the headline scales
	gracefully from 50px on mobile to 108px on desktop.

	On `lg+` the layout is two columns 1.5fr / 1fr; below that the card
	stacks under the copy, with the email field still anchorable via
	the `#signin` id on SignInCard.
-->
<script lang="ts">
	import { isAuthenticated } from '$stores/auth';
	import SignInCard from '$components/SignInCard.svelte';
	import WelcomeBackCard from '$components/WelcomeBackCard.svelte';

	/** Live count from /api/competition/info for the trust-signals row.
	 *  Null → server load failed; fall back to a generic "Join the pool"
	 *  copy line instead of showing "0+ entries". */
	export let totalPlayers: number | null = null;
	/** ISO datetime when Phase 1 locks. Drives the "First kickoff in Xd"
	 *  trust signal and the WelcomeBackCard's status line. */
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
		// Real player count if we have one and it's worth showing.
		// Otherwise lead with the pot.
		if (players !== null && players >= 30) {
			signals.push(`${players}+ entries`);
		}
		signals.push('€600 pot last year');
		signals.push('A cut to charity');
		if (days !== null) {
			if (days === 0) signals.push('Kickoff today');
			else if (days === 1) signals.push('First kickoff tomorrow');
			else signals.push(`First kickoff in ${days}d`);
		} else {
			signals.push('Free to play');
		}
		return signals;
	}
</script>

<div class="relative overflow-hidden bg-base-100 noise">
	<!-- Stadium-glow radial behind the headline -->
	<div
		class="absolute inset-x-0 top-0 h-[60%] bg-[radial-gradient(ellipse_80%_70%_at_50%_0%,rgba(13,151,72,0.15),transparent_70%)] pointer-events-none"
		aria-hidden="true"
	></div>

	<div
		class="relative max-w-[1200px] mx-auto mobile-padding py-20 lg:py-24
			grid grid-cols-1 lg:grid-cols-[1.5fr_1fr] gap-10 lg:gap-14 items-center"
	>
		<!-- ── Left column — copy ─────────────────────────────────── -->
		<div>
			<h1
				class="font-hero text-[clamp(50px,7.6vw,108px)] leading-[0.9] tracking-[0.01em]
					text-base-content"
			>
				<span class="block">MAKE EVERY</span>
				<span class="block">WORLD CUP</span>
				<span class="block text-primary">MATCH MATTER.</span>
			</h1>

			<p
				class="mt-6 text-[18px] sm:text-[20px] text-base-content/80 max-w-2xl leading-relaxed"
			>
				Pick scores, build a bracket, watch the World Cup like it matters. Last year's pot:
				<strong class="text-base-content font-semibold">€600</strong>. Some goes to charity. The
				rest goes to whoever calls the final right.
			</p>

			<div
				class="mt-7 flex flex-wrap items-center gap-x-3 gap-y-1
					text-[11px] sm:text-xs font-mono uppercase tracking-widest text-base-content/60"
			>
				{#each trustSignals as signal, i (signal)}
					{#if i > 0}<span class="text-primary/70" aria-hidden="true">●</span>{/if}
					<span>{signal}</span>
				{/each}
			</div>
		</div>

		<!-- ── Right column — auth-aware card ─────────────────────── -->
		<div class="w-full max-w-md justify-self-stretch lg:justify-self-end">
			{#if $isAuthenticated}
				<WelcomeBackCard {phase1Deadline} placement="hero" />
			{:else}
				<SignInCard id="signin" placement="hero" />
			{/if}
		</div>
	</div>
</div>
