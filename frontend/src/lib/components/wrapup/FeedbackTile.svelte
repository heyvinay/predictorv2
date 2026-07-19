<script lang="ts">
	import { sendFeedback } from '$lib/api/feedback';
	import { markRatingAsked } from '$stores/ratingPrompt';
	import { track } from '$lib/analytics';

	const STARS = [1, 2, 3, 4, 5];
	// Mirrors backend ALLOWED_FEATURES in backend/app/api/feedback.py (max 6
	// chips accepted; anything outside this set is silently dropped there).
	const FEATURES: { id: string; label: string }[] = [
		{ id: 'leaderboard', label: 'Leaderboard' },
		{ id: 'insights', label: 'Insights' },
		{ id: 'match_detail', label: 'Match detail' },
		{ id: 'compare', label: 'Compare' },
		{ id: 'smart_fill', label: 'Smart Fill' },
		{ id: 'results', label: 'Results' }
	];

	let rating = 0;
	let selected = new Set<string>();
	let message = '';
	let status: 'idle' | 'sending' | 'sent' | 'error' = 'idle';

	function rate(n: number) {
		rating = n;
		markRatingAsked();
		track('app_rating_submitted', { rating: n });
	}

	function toggle(id: string) {
		const next = new Set(selected);
		if (next.has(id)) next.delete(id);
		else next.add(id);
		selected = next;
		track('feature_rated', { feature: id, direction: selected.has(id) ? 'up' : 'off' });
	}

	async function send() {
		if (!rating || status === 'sending') return;
		status = 'sending';
		try {
			await sendFeedback(rating, message.trim() || '(no message)', [...selected]);
			status = 'sent';
			track('feedback_submitted', { rating, has_message: !!message.trim() });
		} catch {
			status = 'error';
		}
	}
</script>

<div class="grid h-full content-start gap-2 rounded-box border border-primary/50 bg-gradient-to-br from-primary/15 to-primary/[.02] p-4 text-center">
	<h2 class="font-display font-extrabold">How was The Predictor?</h2>
	{#if status === 'sent'}
		<p class="m-auto text-sm text-success">Thank you — that shapes the next one. 🙌</p>
	{:else}
		<div class="text-xl leading-none tracking-[.18em]">
			{#each STARS as s}
				<button
					class="px-0.5 {s <= rating ? 'text-primary' : 'text-base-content/25'}"
					on:click={() => rate(s)}
					aria-label={`Rate ${s} stars`}>★</button
				>
			{/each}
		</div>
		<p class="text-[11px] text-base-content/40">tap a star — your rating is recorded instantly</p>
		{#if rating > 0}
			<div class="flex flex-wrap justify-center gap-1.5">
				{#each FEATURES as f (f.id)}
					<button
						class="rounded-badge border px-2.5 py-0.5 text-[11px] font-semibold
							{selected.has(f.id)
							? 'border-primary/50 bg-primary/15 text-primary'
							: 'border-base-300/60 text-base-content/55'}"
						on:click={() => toggle(f.id)}
					>{f.label}</button>
				{/each}
			</div>
			<textarea
				class="textarea textarea-bordered textarea-sm w-full text-left"
				rows="2"
				maxlength="2000"
				placeholder="Tell us what to build (or fix) for the next one…"
				bind:value={message}
			></textarea>
			<button
				class="btn btn-primary btn-sm justify-self-center"
				on:click={send}
				disabled={status === 'sending'}
			>
				{status === 'sending' ? 'Sending…' : 'Send feedback'}
			</button>
			{#if status === 'error'}<p class="text-xs text-error">Couldn't send — try again.</p>{/if}
		{/if}
	{/if}
</div>
