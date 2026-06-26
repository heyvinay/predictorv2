<script lang="ts">
	/** Group Stage Winner card (v2.181.0).
	 *
	 *  Hero card at the very top of the dashboard once the admin flips
	 *  competitions.group_stage_winner_released. Backend gates the
	 *  payload — the parent only mounts this component when winner is
	 *  non-null. No client-side visibility logic here.
	 *
	 *  Click target navigates to /leaderboard?entry=<id>, opening the
	 *  EntryDrawer via the deep-link wired in v2.180.2.
	 *
	 *  Visual: champagne-gold accent + font-hero name lockup. Story
	 *  line composition mirrors the GROUP_STAGE_FINAL email body so the
	 *  same recipient who reads both sees the same narrative.
	 */
	import type { GroupStageWinner } from '$lib/types/leaderboard';

	export let winner: GroupStageWinner;

	const PRIZE_EUR = 183;

	$: firstName = (winner.user_name ?? '').split(' ')[0] || winner.user_name;
	$: ownerHasMultiple = winner.entry_name && winner.entry_name !== winner.user_name;
</script>

<a
	href="/leaderboard?entry={winner.entry_id}"
	class="group block rounded-box border-2 border-primary/40 bg-gradient-to-br from-base-200 via-base-200 to-base-300/40 p-5 shadow-glow-gold transition-all hover:border-primary/70 hover:shadow-lg sm:p-6"
>
	<!-- Eyebrow row: trophy + label + prize chip -->
	<div class="mb-3 flex items-center justify-between gap-3 flex-wrap">
		<span class="flex items-center gap-2 text-[11px] font-extrabold uppercase tracking-[0.14em] text-primary">
			<span aria-hidden="true" class="text-base">🏆</span>
			Group Stage Champion
		</span>
		<span class="rounded-badge bg-primary/15 px-2.5 py-0.5 text-[11px] font-extrabold uppercase tracking-[0.12em] text-primary">
			€{PRIZE_EUR} prize
		</span>
	</div>

	<!-- Name + total -->
	<div class="mb-4 flex flex-wrap items-end justify-between gap-x-4 gap-y-1">
		<div class="min-w-0">
			<div class="font-hero text-[28px] leading-none tracking-wide text-base-content sm:text-[36px]">
				{winner.user_name}
			</div>
			{#if ownerHasMultiple}
				<div class="mt-1 text-[13px] text-base-content/55">{winner.entry_name}</div>
			{/if}
		</div>
		<div class="text-right">
			<div class="font-display text-[32px] font-extrabold leading-none text-primary sm:text-[40px]">
				{winner.total_points}
				<span class="text-[14px] font-bold text-base-content/55"> pts</span>
			</div>
			<div class="mt-1 text-[11px] font-bold uppercase tracking-wide text-base-content/40">
				Final rank · #{winner.final_rank}
			</div>
		</div>
	</div>

	<!-- 4-part breakdown -->
	<div class="mb-3 rounded-box border border-base-300/60 bg-base-100/40 p-3.5">
		<div class="mb-2 text-[10.5px] font-extrabold uppercase tracking-[0.12em] text-base-content/55">
			Points breakdown
		</div>
		<dl class="space-y-1 text-[14px]">
			<div class="flex items-baseline justify-between gap-3">
				<dt class="text-base-content/75">Points from correct match outcomes</dt>
				<dd class="font-display font-extrabold tabular-nums text-base-content">{winner.outcome_points}</dd>
			</div>
			<div class="flex items-baseline justify-between gap-3">
				<dt class="text-base-content/75">Extra points from exact scores</dt>
				<dd class="font-display font-extrabold tabular-nums text-base-content">{winner.exact_score_extra}</dd>
			</div>
			<div class="flex items-baseline justify-between gap-3">
				<dt class="text-base-content/75">Extra points from rarity</dt>
				<dd class="font-display font-extrabold tabular-nums text-base-content">{winner.rarity_extra}</dd>
			</div>
			<div class="flex items-baseline justify-between gap-3">
				<dt class="text-base-content/75">Points from bonus questions</dt>
				<dd class="font-display font-extrabold tabular-nums text-base-content">{winner.bonus_question_points}</dd>
			</div>
			<div class="mt-2 border-t border-base-300/60 pt-2 flex items-baseline justify-between gap-3">
				<dt class="font-bold text-base-content">Total</dt>
				<dd class="font-display text-[16px] font-extrabold tabular-nums text-primary">{winner.total_points}</dd>
			</div>
		</dl>
	</div>

	<!-- Story line — pre-composed by the backend service so card and
	     email render identical prose. Edit wording in
	     services/group_stage_winner.py:_compose_story_line. -->
	{#if winner.story_line}
		<p class="m-0 text-[13.5px] leading-relaxed text-base-content/75">
			{winner.story_line}
		</p>
	{/if}

	<!-- CTA hint (footer affordance only — whole card is clickable) -->
	<div class="mt-3 flex justify-end">
		<span class="text-[12px] font-extrabold text-primary transition-transform group-hover:translate-x-0.5">
			View {firstName}'s picks →
		</span>
	</div>
</a>
