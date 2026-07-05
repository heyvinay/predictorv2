<!--
	RatingPrompt — a one-time, well-timed "rate the app" card (see
	stores/ratingPrompt.ts for the timing gate). A star tap fires
	`app_rating_submitted` to PostHog (measurable, no backend); "Tell us more"
	hands off to the Tally feedback panel. Asks once per device.
	Anchored above the mobile bottom nav so it clears the sticky bar.
-->
<script lang="ts">
	import { ratingPromptVisible, dismissRatingPrompt, markRatingAsked } from '$stores/ratingPrompt';
	import { feedbackOpen } from '$stores/feedbackPanel';
	import { track } from '$lib/analytics';

	const STARS = [1, 2, 3, 4, 5];
	let hovered = 0;
	let submitted = 0;

	function rate(n: number) {
		submitted = n;
		track('app_rating_submitted', { rating: n });
		// Persist "asked" immediately so a rate-then-leave user is never
		// re-prompted or double-counted; the follow-up step stays visible.
		markRatingAsked();
	}

	function openFeedback() {
		dismissRatingPrompt();
		feedbackOpen.set(true);
	}

	function dismiss() {
		dismissRatingPrompt();
	}
</script>

{#if $ratingPromptVisible}
	<div
		class="fixed z-[65] inset-x-0 bottom-[calc(4rem+env(safe-area-inset-bottom)+0.5rem)] min-[700px]:bottom-4 min-[700px]:inset-x-auto min-[700px]:right-4 flex justify-center min-[700px]:justify-end px-3 pointer-events-none"
	>
		<div
			class="pointer-events-auto w-full max-w-xs bg-base-200 border border-base-300/60 rounded-2xl shadow-card p-4 text-center relative"
			role="dialog"
			aria-label="Rate the app"
		>
			<button
				class="absolute top-2 right-2 btn btn-ghost btn-xs btn-circle text-base-content/40"
				on:click={dismiss}
				aria-label="Dismiss"
			>
				✕
			</button>

			{#if submitted === 0}
				<h3 class="font-semibold text-sm">Enjoying the Predictor?</h3>
				<p class="text-xs text-base-content/60 mt-0.5 mb-3">Tap to rate — takes a second.</p>
				<!-- svelte-ignore a11y-mouse-events-have-key-events -->
				<div class="flex justify-center gap-1.5" on:mouseleave={() => (hovered = 0)}>
					{#each STARS as s}
						<button
							class="text-2xl leading-none transition-transform hover:scale-110 {(hovered ||
								submitted) >= s
								? 'text-primary'
								: 'text-base-content/25'}"
							on:mouseenter={() => (hovered = s)}
							on:click={() => rate(s)}
							aria-label="{s} star{s > 1 ? 's' : ''}"
						>
							★
						</button>
					{/each}
				</div>
				<button
					class="mt-3 text-xs text-base-content/50 hover:text-base-content"
					on:click={dismiss}
				>
					Maybe later
				</button>
			{:else}
				<h3 class="font-semibold text-sm">Thanks! 🙏</h3>
				<p class="text-xs text-base-content/60 mt-0.5 mb-3">Anything you'd like to tell us?</p>
				<div class="flex justify-center gap-1.5 mb-3">
					{#each STARS as s}
						<span class="text-2xl leading-none {submitted >= s ? 'text-primary' : 'text-base-content/25'}"
							>★</span
						>
					{/each}
				</div>
				<button class="btn btn-primary btn-sm w-full" on:click={openFeedback}>Tell us more</button>
				<button
					class="mt-2 text-xs text-base-content/50 hover:text-base-content"
					on:click={dismiss}
				>
					No thanks
				</button>
			{/if}
		</div>
	</div>
{/if}
