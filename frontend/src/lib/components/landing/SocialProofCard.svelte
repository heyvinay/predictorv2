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

	// Hoisted as a reactive so the template can branch on it. `{@const}`
	// inside a plain element is a compile error in Svelte (must be the
	// immediate child of a block tag), so we declare it here per the
	// codebase's documented gotcha.
	$: hasPot = (stats?.prize_pot_eur ?? 0) > 0;

	function isDigit(c: string): boolean {
		return c >= '0' && c <= '9';
	}
</script>

<!--
	Prize-pot helpers — formatting only. Whole-euro display feels right
	for a pool counter; sub-euro decimals would imply a precision the
	pool doesn't carry. `Intl.NumberFormat` honours the user's locale
	separator (1,250 in en, 1.250 in de) and renders the € currency
	symbol attached to the figure.
-->
<script lang="ts" context="module">
	const EUR_FMT = new Intl.NumberFormat(undefined, {
		style: 'currency',
		currency: 'EUR',
		maximumFractionDigits: 0
	});
</script>

{#if stats && !loadFailed}
	<div class="stadium-card no-glow p-6 mb-4">
		<!--
			Two-column layout when there's a prize pot to show; falls back
			to single-column ("Who's in" only) when entry_fee or submitted
			count is zero (e.g. brand-new competition before anyone
			submits). The split uses a thin vertical divider so the two
			stats read as siblings, not as one big number. `hasPot` is a
			$: reactive declared in the script — see gotcha note there.
		-->
		<div class={hasPot ? 'grid grid-cols-2 gap-4 sm:gap-6 divide-x divide-base-300/40' : ''}>
			<!-- ─── Left column: Who's in ─────────────────────────────────── -->
			<div>
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
								class="inline-flex justify-center items-center min-w-[1.2em] px-1.5 py-1 rounded-md bg-base-300/40 border border-base-300/60 font-display font-extrabold text-3xl sm:text-4xl text-primary tabular-nums tracking-tight"
							>
								{token}
							</span>
						{:else}
							<!-- Commas / separators — narrower, no panel border. -->
							<span class="font-display font-extrabold text-3xl sm:text-4xl text-primary px-1">
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

				<!--
					Cohort-aware tagline. Sits INSIDE the left column (not
					below the grid) so the left column mirrors the right
					column's rhythm: eyebrow → number → small italic text.
					Without this, the grid stretched the left column to
					match the right column's height and the tagline drifted
					to the bottom, leaving the "2" digit orphaned with a
					big empty gap below it.
				-->
				<p class="text-[10px] leading-snug text-base-content/40 italic mt-1.5">
					{TAGLINES[tagline]}
				</p>
			</div>

			<!-- ─── Right column: Prize pot (only when > 0) ───────────────── -->
			{#if hasPot}
				<div class="pl-4 sm:pl-6">
					<!-- Eyebrow with gold dot — different colour to "Who's in" so
					     the two stats are visually distinct at a glance.
					     Label is "Pot so far" (not "Prize pot") because the
					     figure is built on submissions, not paid-confirmed
					     entries. The label carries the "in progress" caveat
					     so the disclaimer below doesn't have to do all the
					     rhetorical work. -->
					<p class="text-xs font-mono uppercase tracking-[0.18em] text-base-content/60 mb-3 flex items-center gap-2">
						<span class="inline-block w-2 h-2 rounded-full bg-primary"></span>
						Pot so far
					</p>

					<!-- Single big gold number, no flip-counter chrome — the pot is
					     a sum, not a count of bodies, so it reads as one figure. -->
					<p class="font-display font-extrabold text-3xl sm:text-4xl text-primary tabular-nums tracking-tight mb-2">
						{EUR_FMT.format(stats.prize_pot_eur)}
					</p>

					<!-- Fine print — the headline figure is an INDICATIVE
					     pot based on SUBMITTED entries (intentional, to
					     build social proof / FOMO). The actual prize
					     depends on paid entries, which lag submissions.
					     Disclaimer keeps us honest without dampening the
					     headline.

					     Formula breakdown ("X entries × €5") was
					     removed deliberately — showing it would expose
					     small submission counts and undercut the
					     headline. The disclaimer carries enough context
					     for the honest read. -->
					<p class="text-[10px] leading-snug text-base-content/40 italic">
						Indicative. Final pot confirmed once entry fees are collected — may vary.
					</p>
				</div>
			{/if}
		</div>
	</div>
{/if}
