<script lang="ts">
	/** Group Stage Podium card (v2.184.x rebuild).
	 *
	 *  Two layouts, one component:
	 *  - Mobile (< sm): three stacked podium cards. Player name + total
	 *    on the top row at full width (no truncation), 4-part breakdown
	 *    in a compact row below. The desktop table was unreadable at
	 *    375px — names truncated to "Kevi..." / "Joh...".
	 *  - Desktop (sm+): compact table with abbreviated headers and a
	 *    wider Player column. Designed to sit inside the dashboard's
	 *    main column (~560px+ wide), not the full page width.
	 *
	 *  Story line moves to a tighter denser block; audit footnote
	 *  collapses to a single inline line with the full text available
	 *  via the Verified pill's tooltip.
	 */
	import { goto } from '$app/navigation';
	import type { GroupStagePodium } from '$lib/types/leaderboard';

	export let podium: GroupStagePodium;

	const PRIZE_EUR = 183;
	const AUDIT_TOOLTIP =
		'Independently verified against the database modification log, ' +
		"the deadline-night predictions snapshot, each player's " +
		'submission email, and a fresh re-run of the scoring engine. ' +
		'All four sources agreed.';

	$: winner = podium.entries[0];
	$: firstName = (winner?.user_name ?? '').split(' ')[0] || winner?.user_name || '';

	function openEntry(entryId: string) {
		void goto(`/leaderboard?entry=${entryId}`);
	}

	function handleRowKeydown(ev: KeyboardEvent, entryId: string) {
		if (ev.key === 'Enter' || ev.key === ' ') {
			ev.preventDefault();
			openEntry(entryId);
		}
	}
</script>

<article
	class="rounded-box border-2 border-primary/40 bg-gradient-to-br from-base-200 via-base-200 to-base-300/40 p-4 shadow-glow-gold sm:p-5"
>
	<!-- Eyebrow row -->
	<div class="mb-3 flex flex-wrap items-center justify-between gap-2">
		<span
			class="flex items-center gap-2 text-[11px] font-extrabold uppercase tracking-[0.14em] text-primary"
		>
			<span aria-hidden="true" class="trophy-pulse text-base">🏆</span>
			Group Stage Champion
		</span>
		<div class="flex items-center gap-1.5">
			<span
				class="cursor-help inline-flex items-center gap-1 rounded-badge border border-success/40 bg-success/15 px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.08em] text-success"
				title={AUDIT_TOOLTIP}
			>
				<span aria-hidden="true">✓</span>
				Verified
			</span>
			<span
				class="rounded-badge bg-primary/15 px-2 py-0.5 text-[10.5px] font-extrabold uppercase tracking-[0.12em] text-primary"
			>
				€{PRIZE_EUR}
			</span>
		</div>
	</div>

	<!-- ── Mobile: stacked podium cards ── -->
	<div class="flex flex-col gap-2 sm:hidden">
		{#each podium.entries as e (e.entry_id)}
			{@const isWinner = e.entry_id === winner.entry_id}
			<div
				class="rounded-box border border-base-300/60 bg-base-100/30 px-3 py-2.5"
				class:winner-card={isWinner}
				on:click={() => openEntry(e.entry_id)}
				on:keydown={(ev) => handleRowKeydown(ev, e.entry_id)}
				tabindex="0"
				role="link"
				aria-label={`Open ${e.display_name}'s picks`}
			>
				<div class="flex items-center justify-between gap-2">
					<span class="flex min-w-0 items-center gap-2">
						<span
							class="font-display text-[16px] font-extrabold leading-none text-primary"
							class:winner-rank={isWinner}>{e.final_rank}</span
						>
						{#if isWinner}
							<span aria-hidden="true" class="trophy-pulse text-[14px]">🏆</span>
						{/if}
						<span class="truncate font-semibold text-base-content">{e.display_name}</span>
					</span>
					<span
						class="font-display text-[18px] font-extrabold leading-none text-primary"
						class:winner-total={isWinner}>{e.total_points}</span
					>
				</div>
				<div
					class="mt-1 flex items-center gap-2 text-[10.5px] tabular-nums text-base-content/65"
				>
					<span><strong class="text-base-content">{e.outcome_points}</strong> outc</span>
					<span class="text-base-content/30">·</span>
					<span><strong class="text-base-content">{e.exact_score_extra}</strong> ex</span>
					<span class="text-base-content/30">·</span>
					<span><strong class="text-base-content">{e.rarity_extra}</strong> rar</span>
					<span class="text-base-content/30">·</span>
					<span><strong class="text-base-content">{e.bonus_question_points}</strong> bn</span>
				</div>
			</div>
		{/each}
	</div>

	<!-- ── Desktop: compact table ── -->
	<div class="hidden overflow-hidden rounded-box border border-base-300/60 bg-base-100/30 sm:block">
		<table class="w-full text-[13px] tabular-nums">
			<thead>
				<tr class="border-b border-base-300/60">
					<th
						class="w-8 px-2 py-1.5 text-left text-[9.5px] font-bold uppercase tracking-[0.1em] text-base-content/50"
						>#</th
					>
					<th
						class="px-2 py-1.5 text-left text-[9.5px] font-bold uppercase tracking-[0.1em] text-base-content/50"
						>Player</th
					>
					<th
						class="px-1.5 py-1.5 text-right text-[9.5px] font-bold uppercase tracking-[0.1em] text-base-content/50"
						title="Outcome points"
						>Outc</th
					>
					<th
						class="px-1.5 py-1.5 text-right text-[9.5px] font-bold uppercase tracking-[0.1em] text-base-content/50"
						title="Exact-score bonus"
						>Ex</th
					>
					<th
						class="px-1.5 py-1.5 text-right text-[9.5px] font-bold uppercase tracking-[0.1em] text-base-content/50"
						title="Rarity bonus"
						>Rar</th
					>
					<th
						class="px-1.5 py-1.5 text-right text-[9.5px] font-bold uppercase tracking-[0.1em] text-base-content/50"
						title="Bonus questions"
						>Bn</th
					>
					<th
						class="w-14 px-2 py-1.5 text-right text-[9.5px] font-bold uppercase tracking-[0.1em] text-base-content/50"
						>Total</th
					>
				</tr>
			</thead>
			<tbody>
				{#each podium.entries as e (e.entry_id)}
					{@const isWinner = e.entry_id === winner.entry_id}
					<tr
						class="cursor-pointer transition-colors hover:bg-base-content/[0.03]"
						class:winner-row={isWinner}
						on:click={() => openEntry(e.entry_id)}
						on:keydown={(ev) => handleRowKeydown(ev, e.entry_id)}
						tabindex="0"
						role="link"
						aria-label={`Open ${e.display_name}'s picks`}
					>
						<td
							class="px-2 py-2 text-left text-[14px] font-extrabold text-primary"
							class:winner-rank={isWinner}>{e.final_rank}</td
						>
						<td
							class="whitespace-nowrap px-2 py-2 font-semibold text-base-content"
							title={e.display_name}
						>
							{#if isWinner}<span
									aria-hidden="true"
									class="trophy-pulse mr-1"
									style="font-size: 14px;">🏆</span
								>{/if}{e.display_name}
						</td>
						<td class="px-1.5 py-2 text-right font-bold text-base-content"
							>{e.outcome_points}</td
						>
						<td class="px-1.5 py-2 text-right font-bold text-base-content"
							>{e.exact_score_extra}</td
						>
						<td class="px-1.5 py-2 text-right font-bold text-base-content"
							>{e.rarity_extra}</td
						>
						<td class="px-1.5 py-2 text-right font-bold text-base-content"
							>{e.bonus_question_points}</td
						>
						<td
							class="px-2 py-2 text-right text-[14px] font-extrabold text-primary"
							class:winner-total={isWinner}>{e.total_points}</td
						>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>

	<!-- Story line — pre-composed by services/group_stage_winner.py.
	     Tighter visual treatment (v2.184.x): smaller text and padding,
	     less vertical chrome. Text content is server-side and unchanged. -->
	{#if podium.story_line}
		<section class="mt-3 rounded-btn border border-primary/20 bg-primary/[0.06] px-3 py-2">
			<div
				class="mb-1 flex items-center gap-1.5 text-[9.5px] font-extrabold uppercase tracking-[0.14em] text-primary"
			>
				<span aria-hidden="true" class="text-[11px]">🏆</span>
				How {firstName} won it
			</div>
			<p class="m-0 text-[12px] leading-snug text-base-content/85">
				{podium.story_line}
			</p>
		</section>
	{/if}

	<!-- Compact audit footnote — full provenance in the Verified pill's
	     tooltip. The single-line form fits on every viewport and the
	     tooltip is the read-when-needed path. -->
	<p
		class="mt-2 inline-flex items-center gap-1 text-[10.5px] text-base-content/55"
		title={AUDIT_TOOLTIP}
	>
		<span aria-hidden="true" class="text-success">✓</span>
		<span>Audited against 4 immutable sources.</span>
	</p>
</article>

<style>
	/* Mobile winner card — gold halo + amplified rank/total. */
	.winner-card {
		background-color: hsl(var(--p) / 0.1);
		box-shadow: 0 0 22px -2px hsl(var(--p) / 0.3), inset 3px 0 0 0 hsl(var(--p));
	}
	.winner-card:hover {
		background-color: hsl(var(--p) / 0.18);
	}
	.winner-card:focus-visible {
		outline: 2px solid hsl(var(--p) / 0.5);
		outline-offset: -2px;
	}

	/* Desktop winner row — same gold halo via cell-level shadows. */
	:global(tr.winner-row > td) {
		background-color: hsl(var(--p) / 0.1);
		box-shadow: 0 0 22px -2px hsl(var(--p) / 0.3);
		padding-top: 0.625rem;
		padding-bottom: 0.625rem;
	}
	:global(tr.winner-row > td:first-child) {
		box-shadow:
			0 0 22px -2px hsl(var(--p) / 0.3),
			inset 3px 0 0 0 hsl(var(--p));
	}
	:global(tr.winner-row > td.winner-rank) {
		font-size: 15.5px;
	}
	:global(tr.winner-row > td.winner-total) {
		font-size: 16.5px;
	}
	:global(tr.winner-row:hover > td) {
		background-color: hsl(var(--p) / 0.18);
	}
	:global(tr.winner-row:focus-visible) {
		outline: 2px solid hsl(var(--p) / 0.5);
		outline-offset: -2px;
	}

	/* Trophy heartbeat — theme-aware via hsl(var(--p)). */
	.trophy-pulse {
		display: inline-block;
		filter: drop-shadow(0 0 10px hsl(var(--p) / 0.55));
		animation: trophy-pulse 3.2s ease-in-out infinite;
	}
	@keyframes trophy-pulse {
		0%,
		100% {
			filter: drop-shadow(0 0 6px hsl(var(--p) / 0.38));
		}
		50% {
			filter: drop-shadow(0 0 16px hsl(var(--p) / 0.85));
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.trophy-pulse {
			animation: none;
			filter: drop-shadow(0 0 10px hsl(var(--p) / 0.55));
		}
	}
</style>
