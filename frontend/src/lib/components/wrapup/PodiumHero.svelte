<script lang="ts">
	/** Final-podium hero: top-3 podium blocks + honours board (Overall
	 *  Champion / Group Stage Champion / Trionda side prize) + story line
	 *  + audit footnote. Group Stage Champion name is fetched live from
	 *  the existing group-stage-winner endpoint (mirrors
	 *  GroupStageWinnerCard.svelte's `podium.entries[0].user_name`
	 *  pattern) — NOT hardcoded, since the plan draft's literal example
	 *  name was a mock artifact. */
	import { onMount } from 'svelte';
	import { track } from '$lib/analytics';
	import { getGroupStagePodium } from '$api/leaderboard';
	import type { FinalPodium } from '$lib/types/wrapup';

	export let podium: FinalPodium;

	$: first = podium.entries.find((e) => e.final_rank === 1) ?? podium.entries[0];
	$: second = podium.entries[1] ?? null;
	$: third = podium.entries[2] ?? null;
	$: trionda = podium.trionda;
	$: ballOn = (entryId: string) => trionda.recipient_entry_id === entryId;

	let groupStageChampionName: string | null = null;
	onMount(async () => {
		try {
			const gsw = await getGroupStagePodium();
			groupStageChampionName = gsw?.entries?.[0]?.user_name ?? null;
		} catch {
			groupStageChampionName = null;
		}
	});
</script>

<div
	class="stadium-card relative h-full overflow-hidden rounded-box border border-primary/40 p-5 text-center"
>
	<div class="relative">
		<p class="text-[10px] uppercase tracking-[.24em] text-base-content/55">
			World Cup 2026 · Final podium
		</p>

		<div class="mx-auto mt-3 grid max-w-[600px] grid-cols-[1fr_1.15fr_1fr] items-end gap-2.5">
			{#each [{ e: second, cls: 'p2', h: 'h-14', medal: '🥈' }, { e: first, cls: 'p1', h: 'h-[86px]', medal: '🏆' }, { e: third, cls: 'p3', h: 'h-10', medal: '🥉' }] as col}
				{#if col.e}
					<div class="grid gap-1.5">
						<span class={col.cls === 'p1' ? 'text-3xl' : 'text-xl'}>{col.medal}</span>
						<span
							class="font-bold leading-tight {col.cls === 'p1'
								? 'font-hero text-3xl tracking-wide text-primary'
								: 'text-sm'}"
						>
							{col.e.user_name}
						</span>
						<span
							class="font-display text-xs font-extrabold {col.cls === 'p1' ? 'text-primary' : ''}"
						>
							{col.e.total_points} pts{col.cls === 'p1' ? ' · €595' : ''}
						</span>
						{#if ballOn(col.e.entry_id)}
							<span
								class="justify-self-center rounded-badge border border-primary/45 bg-primary/10 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider text-primary"
							>
								🏐 Trionda ball
							</span>
						{/if}
						<span class="hidden text-[11px] text-base-content/55 min-[560px]:block">
							Champion pick: {col.e.champion_pick ?? '—'}
							{col.e.champion_hit ? '✓' : '✗'}
							{col.cls === 'p1' && col.e.days_at_top
								? ` · led ${col.e.days_at_top} of ${podium.total_days} days`
								: ''}
						</span>
						<div
							class="grid place-items-center rounded-t-lg border border-b-0 {col.h}
							{col.cls === 'p1'
								? 'border-primary/55 bg-primary/10 text-primary shadow-glow-gold'
								: 'border-base-300 bg-base-100 text-base-content/30'}
							font-display text-xl font-extrabold"
						>
							{col.e.final_rank}
						</div>
					</div>
				{/if}
			{/each}
		</div>

		<!-- honours board -->
		<div class="mx-auto mt-3 grid max-w-[600px] gap-1 border-t border-primary/35 pt-2.5 text-left">
			{#if first}
				<a
					href={`/leaderboard?entry=${first.entry_id}`}
					class="grid grid-cols-[24px_1fr_auto] items-center gap-2 rounded-lg border border-primary/50 bg-primary/5 px-2.5 py-1 text-[13px]"
					on:click={() => track('wrapup_podium_row_clicked', { rank: 1 })}
				>
					<span>🏆</span>
					<span>
						<b>{first.user_name}</b>
						<span class="text-xs text-base-content/55">
							· Overall Champion — highest total after the Final
						</span>
					</span>
					<span class="font-display text-sm font-extrabold text-primary">€595</span>
				</a>
			{/if}
			{#if groupStageChampionName}
				<div
					class="grid grid-cols-[24px_1fr_auto] items-center gap-2 rounded-lg border border-base-300 bg-base-100 px-2.5 py-1 text-[13px]"
				>
					<span>🏅</span>
					<span>
						<b>{groupStageChampionName}</b>
						<span class="text-xs text-base-content/55">
							· Group Stage Champion — led when the groups closed
						</span>
					</span>
					<span class="font-display text-sm font-extrabold text-primary">€183</span>
				</div>
			{/if}
			<div
				class="grid grid-cols-[24px_1fr_auto] items-center gap-2 rounded-lg border border-base-300 bg-base-100 px-2.5 py-1 text-[13px]"
			>
				<span>🏐</span>
				<span>
					{#if trionda.requires_draw}
						<b>Draw pending</b>
						<span class="text-xs text-base-content/55">
							· between {trionda.draw_candidate_names.join(' and ')}
						</span>
					{:else}
						<b>{trionda.recipient_name ?? '—'}</b>
						<span class="text-xs text-base-content/55">
							· Adidas Trionda match ball — {trionda.reason}
						</span>
					{/if}
				</span>
				<span class="font-display text-sm font-extrabold text-primary">Side prize</span>
			</div>
		</div>

		<p class="mx-auto mt-2.5 max-w-[64ch] text-[13px] text-base-content/55">
			{podium.story_line}
		</p>

		<p class="mt-2.5 text-xs text-base-content/40">
			{podium.total_days} matchdays · {podium.audit?.entries_verified ?? '—'} entries · one champion
			·
			<a
				href="/rules#verification"
				class="rounded-badge border border-success/40 bg-success/10 px-2 py-0.5 font-bold uppercase tracking-wide text-success no-underline"
				on:click={() => track('wrapup_verified_link_clicked', {})}
			>
				✓ Verified result — how this was checked →
			</a>
		</p>
	</div>
</div>
