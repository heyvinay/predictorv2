<script lang="ts">
	/** Group Stage Podium card (v2.183.x; upgrade from v2.181.0).
	 *
	 *  Top-3 podium with the winner row amplified, server-composed
	 *  narrative below, and an audit-verified pill in the corner. Each
	 *  row is clickable → opens that entry's drawer via /leaderboard
	 *  deep-link (same convention as the Standings table). Backend gates
	 *  the payload — parent only mounts this component when podium is
	 *  non-null and has entries.
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
	class="rounded-box border-2 border-primary/40 bg-gradient-to-br from-base-200 via-base-200 to-base-300/40 p-5 shadow-glow-gold sm:p-6"
>
	<!-- Eyebrow row -->
	<div class="mb-4 flex flex-wrap items-center justify-between gap-3">
		<span
			class="flex items-center gap-2 text-[11px] font-extrabold uppercase tracking-[0.14em] text-primary"
		>
			<span aria-hidden="true" class="trophy-pulse text-base">🏆</span>
			Group Stage Champion
		</span>
		<div class="flex items-center gap-2">
			<span
				class="cursor-help inline-flex items-center gap-1 rounded-badge border border-success/40 bg-success/15 px-2 py-0.5 text-[10.5px] font-bold uppercase tracking-[0.08em] text-success"
				title={AUDIT_TOOLTIP}
			>
				<span aria-hidden="true">✓</span>
				Verified
			</span>
			<span
				class="rounded-badge bg-primary/15 px-2.5 py-0.5 text-[11px] font-extrabold uppercase tracking-[0.12em] text-primary"
			>
				€{PRIZE_EUR} prize
			</span>
		</div>
	</div>

	<!-- Top-3 podium table -->
	<div class="overflow-x-auto rounded-box border border-base-300/60 bg-base-100/30">
		<table class="w-full text-[13.5px] tabular-nums">
			<thead>
				<tr class="border-b border-base-300/60">
					<th
						class="w-10 px-3 py-2 text-left text-[9.5px] font-bold uppercase tracking-[0.11em] text-base-content/50"
						>#</th
					>
					<th
						class="px-2 py-2 text-left text-[9.5px] font-bold uppercase tracking-[0.11em] text-base-content/50"
						>Player</th
					>
					<th
						class="px-2 py-2 text-right text-[9.5px] font-bold uppercase tracking-[0.11em] text-base-content/50"
						>Outcomes</th
					>
					<th
						class="px-2 py-2 text-right text-[9.5px] font-bold uppercase tracking-[0.11em] text-base-content/50"
						>Exact</th
					>
					<th
						class="px-2 py-2 text-right text-[9.5px] font-bold uppercase tracking-[0.11em] text-base-content/50"
						>Rarity</th
					>
					<th
						class="px-2 py-2 text-right text-[9.5px] font-bold uppercase tracking-[0.11em] text-base-content/50"
						>Bonus</th
					>
					<th
						class="px-3 py-2 text-right text-[9.5px] font-bold uppercase tracking-[0.11em] text-base-content/50"
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
							class="px-3 py-2.5 text-left text-[15px] font-extrabold text-primary"
							class:winner-rank={isWinner}>{e.final_rank}</td
						>
						<td class="w-full max-w-0 truncate px-2 py-2.5 font-semibold text-base-content">
							{#if isWinner}<span
									aria-hidden="true"
									class="trophy-pulse mr-1.5"
									style="font-size: 16px;">🏆</span
								>{/if}{e.display_name}
						</td>
						<td class="px-2 py-2.5 text-right font-bold text-base-content"
							>{e.outcome_points}</td
						>
						<td class="px-2 py-2.5 text-right font-bold text-base-content"
							>{e.exact_score_extra}</td
						>
						<td class="px-2 py-2.5 text-right font-bold text-base-content"
							>{e.rarity_extra}</td
						>
						<td class="px-2 py-2.5 text-right font-bold text-base-content"
							>{e.bonus_question_points}</td
						>
						<td
							class="px-3 py-2.5 text-right text-[15px] font-extrabold text-primary"
							class:winner-total={isWinner}>{e.total_points}</td
						>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>

	<!-- Story line — pre-composed by services/group_stage_winner.py so
	     card and email render identical prose. -->
	{#if podium.story_line}
		<section
			class="mt-4 rounded-box border border-primary/20 bg-primary/[0.06] px-4 py-3"
		>
			<div
				class="mb-1.5 flex items-center gap-1.5 text-[10px] font-extrabold uppercase tracking-[0.14em] text-primary"
			>
				<span aria-hidden="true" class="text-[12px]">🏆</span>
				How {firstName} won it
			</div>
			<p class="m-0 text-[13.5px] leading-relaxed text-base-content/85">
				{podium.story_line}
			</p>
		</section>
	{/if}

	<!-- Inline audit credibility footnote — same content as the
	     Verified pill's tooltip but visible on every device (the pill
	     tooltip only fires on hover, so mobile/touch users wouldn't
	     see it otherwise). The pill stays as the at-a-glance signal;
	     this paragraph serves the stop-and-read path. -->
	<p
		class="mt-3 flex items-start gap-1.5 text-[11.5px] leading-relaxed text-base-content/55"
	>
		<span aria-hidden="true" class="mt-[1px] text-success">✓</span>
		<span>
			Independently audited against four immutable sources &mdash; the
			database modification log, the deadline-night predictions snapshot,
			submission emails on Resend, and a fresh re-run of the scoring engine.
		</span>
	</p>
</article>

<style>
	/* Winner row halo + gold rail. Cells get an outer glow that overlaps
	   on internal boundaries to read as one continuous halo (negative
	   spread prevents the seam-doubling on internal cell boundaries).
	   First cell adds the gold inset rail via combined box-shadow. */
	:global(tr.winner-row > td) {
		background-color: rgba(212, 175, 55, 0.08);
		box-shadow: 0 0 22px -2px rgba(212, 175, 55, 0.32);
		padding-top: 0.875rem;
		padding-bottom: 0.875rem;
	}
	:global(tr.winner-row > td:first-child) {
		box-shadow:
			0 0 22px -2px rgba(212, 175, 55, 0.32),
			inset 3px 0 0 0 #d4af37;
	}
	:global(tr.winner-row > td.winner-rank) {
		color: #f5d77a;
		font-size: 16.5px;
	}
	:global(tr.winner-row > td.winner-total) {
		color: #ffe08a;
		font-size: 18px;
	}
	:global(tr.winner-row:hover > td) {
		background-color: rgba(212, 175, 55, 0.14);
	}
	:global(tr.winner-row:focus-visible) {
		outline: 2px solid rgba(212, 175, 55, 0.5);
		outline-offset: -2px;
	}

	/* Trophy heartbeat — slow, low-amplitude glow swell. */
	.trophy-pulse {
		display: inline-block;
		filter: drop-shadow(0 0 10px rgba(212, 175, 55, 0.55));
		animation: trophy-pulse 3.2s ease-in-out infinite;
	}
	@keyframes trophy-pulse {
		0%,
		100% {
			filter: drop-shadow(0 0 6px rgba(212, 175, 55, 0.38));
		}
		50% {
			filter: drop-shadow(0 0 16px rgba(212, 175, 55, 0.85));
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.trophy-pulse {
			animation: none;
			filter: drop-shadow(0 0 10px rgba(212, 175, 55, 0.55));
		}
	}
</style>
