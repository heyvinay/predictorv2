<!--
	FeedbackPrompt — one-tap star rating + optional details (v2.174.0).

	Bottom-right card, same chrome as FeatureToast, chained LAST in the
	popup sequence: it waits until the welcome tour has been seen AND
	the current feature toast has been dismissed, so users only ever
	see one floating prompt per visit. Shown once per device, keyed by
	FEEDBACK_ID — re-run the pulse later (e.g. after the group stage)
	by bumping the ID. Retire via FEEDBACK_PROMPT_ENABLED.

	Flow: tap a star → the rating is captured IMMEDIATELY (PostHog via
	the analytics wrapper, alsoServer for ad-block resistance) and the
	device is marked done → card expands with one-tap aspect chips +
	an optional comment → Send fires a second event with the details.
	Closing at any point keeps whatever was already captured.

	Storage is PostHog-only by design (no DB table): read responses in
	PostHog → Activity, filtered to feedback_rating / feedback_details.
	Because the wrapper honours Do-Not-Track (DNT users produce zero
	events), the prompt doesn't render for them at all — we never ask
	for feedback we can't record.
-->
<script lang="ts" context="module">
	export const FEEDBACK_PROMPT_ENABLED = true;
	export const FEEDBACK_ID = '2026-06-group-stage';
	export const FEEDBACK_DONE_KEY = `predictor:feedback:${FEEDBACK_ID}:done`;
</script>

<script lang="ts">
	import { onMount } from 'svelte';
	import { fly } from 'svelte/transition';
	import { page } from '$app/stores';
	import { isAuthenticated } from '$stores/auth';
	import { track } from '$lib/analytics';
	import Star from 'lucide-svelte/icons/star';
	import { TOUR_ENABLED, TOUR_SEEN_KEY } from '$lib/components/WelcomeTourModal.svelte';
	import {
		FEATURE_TOAST_ENABLED,
		FEATURE_DISMISS_KEY
	} from '$lib/components/FeatureToast.svelte';

	const STAR_VALUES = [1, 2, 3, 4, 5];
	const ASPECTS = [
		{ id: 'picks', label: 'Making picks' },
		{ id: 'leaderboard', label: 'Leaderboard' },
		{ id: 'results', label: 'Results' },
		{ id: 'ease', label: 'Ease of use' }
	];
	const COMMENT_MAX = 600;

	// Hidden until onMount so a device that already answered never
	// sees a flash; the gates below all resolve from localStorage.
	let done = true;
	let tourPending = false;
	let toastPending = false;
	let dntActive = false;

	let stage: 'rate' | 'details' | 'thanks' = 'rate';
	let rating = 0;
	let selectedAspects = new Set<string>();
	let comment = '';
	let detailsSent = false;

	onMount(() => {
		try {
			done = localStorage.getItem(FEEDBACK_DONE_KEY) === '1';
			tourPending = TOUR_ENABLED && localStorage.getItem(TOUR_SEEN_KEY) !== '1';
			toastPending =
				FEATURE_TOAST_ENABLED && localStorage.getItem(FEATURE_DISMISS_KEY) !== '1';
		} catch {
			done = true; // storage unavailable → never show
		}
		dntActive = typeof navigator !== 'undefined' && navigator.doNotTrack === '1';
	});

	function markDone() {
		done = true;
		try {
			localStorage.setItem(FEEDBACK_DONE_KEY, '1');
		} catch {
			/* storage unavailable — prompt still hides for this session */
		}
	}

	function rate(value: number) {
		rating = value;
		// Capture immediately — the one-tap rating must survive the user
		// closing the card without engaging with the follow-up.
		track(
			'feedback_rating',
			{ rating: value, feedback_id: FEEDBACK_ID },
			{ alsoServer: true }
		);
		try {
			localStorage.setItem(FEEDBACK_DONE_KEY, '1');
		} catch {
			/* noop */
		}
		stage = 'details';
	}

	function toggleAspect(id: string) {
		if (selectedAspects.has(id)) {
			selectedAspects.delete(id);
		} else {
			selectedAspects.add(id);
		}
		selectedAspects = selectedAspects; // reassign for reactivity
	}

	function sendDetails() {
		const trimmed = comment.trim().slice(0, COMMENT_MAX);
		if (selectedAspects.size > 0 || trimmed) {
			track(
				'feedback_details',
				{
					rating,
					aspects: [...selectedAspects].sort().join(','),
					comment: trimmed,
					feedback_id: FEEDBACK_ID
				},
				{ alsoServer: true }
			);
			detailsSent = true;
			stage = 'thanks';
			setTimeout(() => {
				done = true;
			}, 1800);
		} else {
			done = true;
		}
	}

	function dismiss() {
		// Closing mid-details still salvages any tapped chips (comment
		// drafts are deliberately NOT sent — unsubmitted text stays local).
		if (stage === 'details' && !detailsSent && selectedAspects.size > 0) {
			track(
				'feedback_details',
				{
					rating,
					aspects: [...selectedAspects].sort().join(','),
					comment: '',
					feedback_id: FEEDBACK_ID
				},
				{ alsoServer: true }
			);
		}
		markDone();
	}

	$: show =
		FEEDBACK_PROMPT_ENABLED &&
		$isAuthenticated &&
		!done &&
		!tourPending &&
		!toastPending &&
		!dntActive &&
		!$page.url.pathname.startsWith('/admin') &&
		$page.url.pathname !== '/onboarding';
	$: aspectsLabel = rating >= 4 ? "What's working well?" : 'What could be better?';
</script>

{#if show}
	<div
		class="fixed bottom-[4.5rem] right-3 min-[700px]:bottom-6 min-[700px]:right-6 z-40
			w-[calc(100%-1.5rem)] max-w-sm min-[700px]:w-96
			bg-base-200 rounded-2xl shadow-2xl border border-base-content/10 p-4"
		aria-label="Rate The Predictor"
		transition:fly={{ x: 24, duration: 200 }}
	>
		{#if stage === 'rate'}
			<div class="flex items-start gap-3">
				<div class="flex-1 min-w-0">
					<p class="text-sm font-display font-bold">How are you finding The Predictor?</p>
					<div class="mt-2 flex gap-1.5">
						{#each STAR_VALUES as value}
							<button
								class="p-1 text-base-content/40 hover:text-primary hover:scale-110 transition-all"
								aria-label="Rate {value} out of 5"
								on:click={() => rate(value)}
							>
								<Star size={26} strokeWidth={1.75} />
							</button>
						{/each}
					</div>
				</div>
				<button
					class="btn btn-ghost btn-xs shrink-0 px-1.5 text-base-content/60 hover:text-base-content"
					aria-label="Dismiss feedback prompt"
					title="Dismiss"
					on:click={dismiss}
				>
					✕
				</button>
			</div>
		{:else if stage === 'details'}
			<div class="flex items-start gap-3">
				<div class="flex-1 min-w-0">
					<p class="text-sm font-display font-bold">
						Thanks!
						<span class="ml-1 text-primary" aria-label="{rating} of 5 stars">
							{'★'.repeat(rating)}<span class="text-base-content/20"
								>{'★'.repeat(5 - rating)}</span
							>
						</span>
					</p>
					<p class="mt-2 text-[12.5px] font-semibold text-base-content/70">{aspectsLabel}</p>
					<div class="mt-1.5 flex flex-wrap gap-1.5">
						{#each ASPECTS as aspect (aspect.id)}
							<button
								class="badge badge-lg cursor-pointer border transition-colors {selectedAspects.has(
									aspect.id
								)
									? 'bg-primary/20 border-primary/50 text-primary'
									: 'bg-base-300/40 border-base-content/10 text-base-content/70'}"
								aria-pressed={selectedAspects.has(aspect.id)}
								on:click={() => toggleAspect(aspect.id)}
							>
								{aspect.label}
							</button>
						{/each}
					</div>
					<textarea
						class="textarea textarea-bordered textarea-sm w-full mt-2.5 leading-snug"
						rows="2"
						maxlength={COMMENT_MAX}
						placeholder="Anything else? (optional)"
						bind:value={comment}
					></textarea>
					<div class="mt-2 flex justify-end">
						<button class="btn btn-primary btn-xs" on:click={sendDetails}>
							{selectedAspects.size > 0 || comment.trim() ? 'Send' : 'Done'}
						</button>
					</div>
				</div>
				<button
					class="btn btn-ghost btn-xs shrink-0 px-1.5 text-base-content/60 hover:text-base-content"
					aria-label="Close"
					title="Close"
					on:click={dismiss}
				>
					✕
				</button>
			</div>
		{:else}
			<p class="text-sm font-display font-bold text-center py-1" role="status">
				Feedback sent — thank you! 🙌
			</p>
		{/if}
	</div>
{/if}
