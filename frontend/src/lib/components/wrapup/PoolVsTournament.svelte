<script lang="ts">
	import type { KoLadderRowOut, PoolRetrospective } from '$lib/types/wrapup';

	export let retro: PoolRetrospective;
	export let poolSize: number;

	const STAGE_LABEL: Record<string, string> = {
		round_of_32: 'Round of 32',
		round_of_16: 'Round of 16',
		quarter_final: 'Quarter-finals',
		semi_final: 'Semi-finals',
		final: 'Final',
		winner: 'Winner'
	};
	const pct = (row: KoLadderRowOut) => (row.of ? Math.round((row.consensus_had / row.of) * 100) : 0);
</script>

<div class="stadium-card no-glow h-full p-4">
	<h2 class="font-display font-extrabold">The pool vs the tournament</h2>
	<p class="mb-2 text-xs text-base-content/50">
		How {poolSize} entries read the tournament collectively — what everyone saw coming, and what
		nobody did.
	</p>

	<div class="grid grid-cols-1 gap-2 min-[560px]:grid-cols-3">
		<div class="rounded-box border border-base-300/60 bg-base-100 px-3 py-2">
			<p class="text-[9px] uppercase tracking-wider text-base-content/40">Group games called right</p>
			<p class="font-display text-xl font-extrabold">
				{retro.group_called_right} <span class="text-xs text-base-content/40">/ {retro.group_total}</span>
			</p>
			<p class="text-[10px] text-base-content/40">pool majority pick vs result</p>
		</div>
		<div class="rounded-box border border-primary/45 bg-primary/5 px-3 py-2">
			<p class="text-[9px] uppercase tracking-wider text-base-content/40">Final called right</p>
			<p class="font-display text-xl font-extrabold">{Math.round(retro.final_called_right_pct * 100)}%</p>
			<p class="text-[10px] text-base-content/40">
				backed <b class="text-primary">🏆 {retro.final_winner_team ?? '—'}</b> — world champions
			</p>
		</div>
		<div class="rounded-box border border-base-300/60 bg-base-100 px-3 py-2">
			<p class="text-[9px] uppercase tracking-wider text-base-content/40">Exact scores landed</p>
			<p class="font-display text-xl font-extrabold">{retro.exact_total}</p>
			<p class="text-[10px] text-base-content/40">across the pool · {retro.exact_avg_per_entry} per entry</p>
		</div>
	</div>

	<div class="mt-3 grid gap-3 min-[720px]:grid-cols-2">
		<div>
			<p class="mb-1 font-display text-[13px] font-extrabold">😱 Biggest collective misses</p>
			{#each retro.misses as m (m.label)}
				<div class="mt-1 flex items-center gap-2 rounded-full border border-error/25 bg-base-100 px-2.5 py-1 text-xs">
					<span class="flex-none rounded-full bg-error/10 px-2 py-0.5 font-display font-extrabold text-error"
						>{Math.round(m.pct * 100)}%</span
					>
					<span class="min-w-0">
						<span class="block truncate">{m.label}</span>
						<span class="block text-[10px] text-base-content/40">only {Math.round(m.pct * 100)}% called it</span>
					</span>
				</div>
			{/each}
		</div>
		<div>
			<p class="mb-1 font-display text-[13px] font-extrabold">🏦 Bankers that landed</p>
			{#each retro.bankers as m (m.label)}
				<div class="mt-1 flex items-center gap-2 rounded-full border border-success/25 bg-base-100 px-2.5 py-1 text-xs">
					<span class="flex-none rounded-full bg-success/10 px-2 py-0.5 font-display font-extrabold text-success"
						>{Math.round(m.pct * 100)}%</span
					>
					<span class="min-w-0">
						<span class="block truncate">{m.label}</span>
						<span class="block text-[10px] text-base-content/40">{m.exact_count} entries had it exact</span>
					</span>
				</div>
			{/each}
		</div>
	</div>

	<p class="mt-3 font-display text-[13px] font-extrabold">How far did the pool's bracket faith hold?</p>
	<p class="text-[11px] text-base-content/40">
		Share of each round's actual line-up the consensus predicted — and the teams it believed in that
		fell.
	</p>
	{#each retro.ko_ladder as row (row.stage)}
		<div
			class="grid grid-cols-[130px_1fr] items-center gap-x-3 gap-y-1 border-b border-base-300/40 py-1.5 last:border-none min-[560px]:grid-cols-[150px_1fr]"
		>
			<span class="flex items-baseline justify-between text-[13px] font-bold">
				{STAGE_LABEL[row.stage] ?? row.stage}
				<span class="font-display">{row.consensus_had}<span class="text-[10px] text-base-content/40">/{row.of}</span></span>
			</span>
			<div class="h-4 overflow-hidden rounded-full border border-base-300/60 bg-base-100">
				<div
					class="flex h-full items-center justify-end rounded-l-full pr-1.5
						{row.stage === 'final' || row.stage === 'winner'
						? 'bg-gradient-to-r from-primary/40 to-primary/80'
						: 'bg-gradient-to-r from-success/35 to-success/75'}"
					style={`width:${pct(row)}%`}
				>
					<span class="font-display text-[9px] font-extrabold text-base-100">{pct(row)}%</span>
				</div>
			</div>
			<span class="col-start-2 flex flex-wrap gap-1">
				{#if row.fallen_teams.length}
					{#each row.fallen_teams.slice(0, 3) as t}
						<span class="rounded-full border border-error/25 bg-error/[.06] px-2 py-0.5 text-[10px] font-semibold text-error/85"
							>✕ {t}</span
						>
					{/each}
					{#if row.fallen_teams.length > 3}
						<span class="rounded-full border border-base-300/60 bg-base-100 px-2 py-0.5 text-[10px] text-base-content/40"
							>+{row.fallen_teams.length - 3} more</span
						>
					{/if}
				{:else}
					<span class="rounded-full border border-success/25 bg-success/[.06] px-2 py-0.5 text-[10px] font-semibold text-success">
						{row.stage === 'winner' ? "🏆 the pool's favourite lifted it ✓" : 'the pool called them all ✓'}
					</span>
				{/if}
			</span>
		</div>
	{/each}
</div>
