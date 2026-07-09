<!--
	RatingPrompt — a one-time, well-timed "rate the app" card (see
	stores/ratingPrompt.ts for the timing gate). A star tap fires
	`app_rating_submitted` to PostHog (measurable, no backend) and then reveals
	an inline feedback box; on Send, the rating + message is emailed to the
	pool owner via the backend (POST /api/feedback/). Asks once per device;
	also force-openable from the footer "Feedback" link.
	Anchored above the mobile bottom nav so it clears the sticky bar.
-->
<script lang="ts">
	import { ratingPromptVisible, dismissRatingPrompt, markRatingAsked } from '$stores/ratingPrompt';
	import { sendFeedback } from '$lib/api/feedback';
	import { track } from '$lib/analytics';

	const STARS = [1, 2, 3, 4, 5];
	let hovered = 0;
	let submitted = 0;
	let message = '';
	let status: 'idle' | 'sending' | 'sent' | 'error' = 'idle';

	// Reset to a clean card whenever it (re)opens — a footer-triggered open
	// should never inherit a half-filled state from a previous session.
	let wasVisible = false;
	$: if ($ratingPromptVisible && !wasVisible) {
		wasVisible = true;
		hovered = 0;
		submitted = 0;
		message = '';
		status = 'idle';
	} else if (!$ratingPromptVisible && wasVisible) {
		wasVisible = false;
	}

	function rate(n: number) {
		submitted = n;
		track('app_rating_submitted', { rating: n });
		// Persist "asked" immediately so a rate-then-leave user is never
		// re-prompted or double-counted; the feedback step stays visible.
		markRatingAsked();
	}

	async function send() {
		const trimmed = message.trim();
		if (!trimmed || status === 'sending') return;
		status = 'sending';
		try {
			await sendFeedback(submitted, trimmed);
			status = 'sent';
			track('feedback_submitted', { rating: submitted, has_message: true });
			setTimeout(() => dismissRatingPrompt(), 1500);
		} catch {
			status = 'error';
		}
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
			class="rating-prompt-in pointer-events-auto w-full max-w-xs bg-base-200 border border-primary/40 rounded-2xl shadow-glow-gold p-4 text-center relative"
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
				<h3 class="font-semibold text-sm">Enjoying the Predictor App?</h3>
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
			{:else if status === 'sent'}
				<h3 class="font-semibold text-sm">Thanks! 🙏</h3>
				<p class="text-xs text-base-content/60 mt-0.5">Your feedback is on its way.</p>
			{:else}
				<div class="flex justify-center gap-1.5 mb-2">
					{#each STARS as s}
						<span class="text-xl leading-none {submitted >= s ? 'text-primary' : 'text-base-content/25'}"
							>★</span
						>
					{/each}
				</div>
				<p class="text-xs text-base-content/60 mb-2">Anything you'd like to tell us?</p>
				<textarea
					class="textarea textarea-bordered textarea-sm w-full text-sm resize-none"
					rows="3"
					maxlength="2000"
					placeholder="What's working, what's not, what you'd like next…"
					bind:value={message}
					disabled={status === 'sending'}
				></textarea>
				{#if status === 'error'}
					<p class="text-xs text-error mt-1.5">Couldn't send — please try again.</p>
				{/if}
				<button
					class="btn btn-primary btn-sm w-full mt-2"
					on:click={send}
					disabled={!message.trim() || status === 'sending'}
				>
					{status === 'sending' ? 'Sending…' : 'Send'}
				</button>
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

<style>
	.rating-prompt-in {
		animation: rating-prompt-in 0.32s cubic-bezier(0.22, 1, 0.36, 1);
	}
	@keyframes rating-prompt-in {
		from {
			opacity: 0;
			transform: translateY(18px) scale(0.97);
		}
		to {
			opacity: 1;
			transform: none;
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.rating-prompt-in {
			animation: none;
		}
	}
</style>
