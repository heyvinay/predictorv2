<!--
	SocialProofCard — sits above WelcomeBackCard in the landing hero's
	right column. Shows:

	  • a flip-counter-styled total of signed-up predictors
	  • a green "▲ N joined in the last hour" delta line (hidden when 0)
	  • a cohort-aware italic tagline that nudges the user's current state

	Why this card exists (v2.160.x):
	  • Visually balances the Atlas prize panel on the left so the right
	    column isn't just a single card floating in space.
	  • Adds urgency / social proof without alarmism — "your friends are
	    already in" framing rather than "submit or else."
	  • Tagline rotates by user state so the card stays relevant whether
	    you've submitted, have drafts in flight, or haven't started.

	Hides itself if the backend call fails — better than rendering a card
	with zero values that might be wrong rather than absent.
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import { editableEntries, submittedEntries } from '$stores/entries';
	import { getLandingStats, type LandingStats } from '$lib/api/landing';

	let stats: LandingStats | null = null;
	let loadFailed = false;

	onMount(async () => {
		try {
			stats = await getLandingStats();
		} catch {
			loadFailed = true;
		}
	});

	type Tagline = 'drafts' | 'all_submitted' | 'no_entries';

	const TAGLINES: Record<Tagline, string> = {
		drafts: "don't be the friend who left it as a draft",
		all_submitted: "you're all in. drag a friend across the line?",
		no_entries: 'your friends are already in. where are you?'
	};

	$: draftCount = $editableEntries.length;
	$: submittedCount = $submittedEntries.length;

	function pickTagline(draft: number, submitted: number): Tagline {
		if (draft > 0) return 'drafts';
		if (submitted > 0) return 'all_submitted';
		return 'no_entries';
	}

	$: tagline = pickTagline(draftCount, submittedCount);

	// Render the total as individual digit boxes for the flip-counter
	// aesthetic. Each digit becomes a small navy panel with the gold
	// numeral inside. Commas (thousand separators) become their own
	// narrower box so the rhythm stays consistent.
	$: digitTokens = (stats?.predictors_signed_up ?? 0)
		.toLocaleString()
		.split('');

	function isDigit(c: string): boolean {
		return c >= '0' && c <= '9';
	}
</script>

{#if stats && !loadFailed}
	<div class="stadium-card no-glow p-6 mb-4">
		<!-- Eyebrow with green status dot -->
		<p class="text-xs font-mono uppercase tracking-[0.18em] text-base-content/60 mb-3 flex items-center gap-2">
			<span class="inline-block w-2 h-2 rounded-full bg-success"></span>
			Who's in
		</p>

		<!-- Flip-counter digits -->
		<div class="flex gap-1 mb-2 items-baseline">
			{#each digitTokens as token}
				{#if isDigit(token)}
					<span
						class="inline-flex justify-center items-center min-w-[1.4em] px-2 py-1 rounded-md bg-base-300/40 border border-base-300/60 font-display font-extrabold text-4xl sm:text-5xl text-primary tabular-nums tracking-tight"
					>
						{token}
					</span>
				{:else}
					<!-- Commas / separators — narrower, no panel border. -->
					<span class="font-display font-extrabold text-4xl sm:text-5xl text-primary px-1">
						{token}
					</span>
				{/if}
			{/each}
		</div>

		<!-- Delta line — hidden when zero so the card stays calm in quiet hours. -->
		{#if stats.joined_in_last_hour > 0}
			<p class="text-xs text-success font-semibold mb-1 flex items-center gap-1">
				<span aria-hidden="true">▲</span>
				{stats.joined_in_last_hour}
				{stats.joined_in_last_hour === 1 ? 'joined' : 'joined'} in the last hour
			</p>
		{/if}

		<!-- Cohort-aware tagline. Italic + muted to read as a quiet aside. -->
		<p class="text-xs text-base-content/55 italic mt-2">
			{TAGLINES[tagline]}
		</p>
	</div>
{/if}
