<script lang="ts">
	import SignInCard from '$lib/components/SignInCard.svelte';
	import { track } from '$lib/analytics';
</script>

<div
	class="grid items-center gap-4 rounded-box border border-dashed border-primary/45 bg-primary/5 p-4 min-[760px]:grid-cols-[1.1fr_1fr]"
	on:pointerdown={() => track('wrapup_signin_started', {})}
>
	<div class="grid gap-1">
		<h2 class="font-display font-extrabold">In the pool?</h2>
		<p class="text-[13px] text-base-content/55">
			Sign in to see your personal wrap — your final rank, superlatives, and how you compared to
			the champion.
		</p>
		<p class="text-[11px] text-base-content/40">Not in the pool? Keep scrolling — the whole story is below.</p>
	</div>
	<SignInCard id="wrapup-signin" placement="wrapup" />
</div>
