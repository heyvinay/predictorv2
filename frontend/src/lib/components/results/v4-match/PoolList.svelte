<script lang="ts">
	/** "How the pool called it" — banked (sorted by pts) then didn't-score.
	 *  Ranks come from CommunityPrediction.rank (B.3); null renders —. */
	import type { PoolRow } from '$lib/types/results';

	export let banked: PoolRow[];
	export let missed: PoolRow[];
	export let totalPlayers: number;

	function initials(name: string): string {
		return name
			.split(/\s+/)
			.map((w) => w[0])
			.join('')
			.slice(0, 2)
			.toUpperCase();
	}

	const pillTone = (s: PoolRow['status']) =>
		s === 'exact'
			? 'bg-success/15 text-success'
			: s === 'result'
			? 'bg-warning/15 text-warning-text'
			: 'bg-base-300/30 text-base-content/55';
</script>

<div class="rounded-box border border-base-300/60 bg-base-200 p-4">
	<div class="mb-2 flex items-center justify-between">
		<span class="font-display text-[16px]">How the pool called it</span>
		<span class="text-[11px] text-base-content/55">sorted by points</span>
	</div>

	<div class="py-1.5 text-center text-[10px] font-extrabold tracking-[0.1em] text-base-content/40">
		— {banked.length} of {totalPlayers} banked points —
	</div>
	{#each banked as p (p.reference)}
		<div
			class="flex items-center gap-2.5 rounded-btn px-2 py-1.5 {p.you
				? 'bg-primary/10 ring-1 ring-primary/40'
				: ''}"
		>
			<span class="w-5 text-center text-[11px] font-bold text-base-content/55">{p.rank ?? '—'}</span>
			<span
				class="grid h-[26px] w-[26px] flex-none place-items-center rounded-full bg-base-300/50 text-[10px] font-extrabold {p.you
					? 'bg-primary/30 text-primary'
					: 'text-base-content/70'}">{initials(p.name)}</span
			>
			<span class="flex min-w-0 flex-1 items-center gap-2 truncate text-[12.5px] font-semibold">
				{p.name}
				{#if p.you}
					<span
						class="rounded-badge bg-primary/20 px-1.5 py-px text-[9px] font-extrabold tracking-[0.08em] text-primary"
						>YOU</span
					>
				{/if}
			</span>
			<span class="font-display text-[13px]">{p.pick}</span>
			<span class="inline-flex items-center gap-1 rounded-badge px-2 py-0.5 text-[10.5px] font-bold {pillTone(p.status)}">
				<span class="tracking-[0.06em]">{p.status === 'exact' ? 'EXACT' : 'RESULT'}</span>
				<span class="font-display">+{p.pts}</span>
			</span>
		</div>
	{/each}

	{#if missed.length > 0}
		<div class="mt-2 py-1.5 text-center text-[10px] font-extrabold tracking-[0.1em] text-base-content/40">
			— didn't score —
		</div>
		{#each missed as p (p.reference)}
			<div
				class="flex items-center gap-2.5 rounded-btn px-2 py-1.5 opacity-75 {p.you
					? 'bg-primary/10 ring-1 ring-primary/40 opacity-100'
					: ''}"
			>
				<span class="w-5 text-center text-[11px] font-bold text-base-content/40">—</span>
				<span
					class="grid h-[26px] w-[26px] flex-none place-items-center rounded-full bg-base-300/50 text-[10px] font-extrabold text-base-content/70"
					>{initials(p.name)}</span
				>
				<span class="flex min-w-0 flex-1 items-center gap-2 truncate text-[12.5px] font-semibold">
					{p.name}
					{#if p.you}
						<span
							class="rounded-badge bg-primary/20 px-1.5 py-px text-[9px] font-extrabold tracking-[0.08em] text-primary"
							>YOU</span
						>
					{/if}
				</span>
				<span class="font-display text-[13px]">{p.pick}</span>
				<span class="inline-flex items-center gap-1 rounded-badge px-2 py-0.5 text-[10.5px] font-bold {pillTone(p.status)}">
					<span class="tracking-[0.06em]">MISS</span>
					<span class="font-display">0</span>
				</span>
			</div>
		{/each}
	{/if}
</div>
