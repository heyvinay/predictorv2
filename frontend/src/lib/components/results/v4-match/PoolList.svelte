<script lang="ts">
	/** "How the pool called it" — the user's own row(s) pinned to the top,
	 *  then the rest of the pool grouped by banked / didn't-score. Ranks
	 *  come from CommunityPrediction.rank (B.3); null renders —. */
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

	// Pull the user's row(s) to the top — for multi-entry users every one
	// of their entries surfaces above the rest of the pool. Order within
	// the "yours" group: banked first (by points desc), then missed.
	$: yoursBanked = banked.filter((p) => p.you).sort((a, b) => b.pts - a.pts);
	$: yoursMissed = missed.filter((p) => p.you);
	$: yours = [...yoursBanked, ...yoursMissed];
	$: othersBanked = banked.filter((p) => !p.you);
	$: othersMissed = missed.filter((p) => !p.you);
</script>

<div class="rounded-box border border-base-300/60 bg-base-200 p-4">
	<div class="mb-2 flex items-center justify-between">
		<span class="font-display text-[16px]">How the pool called it</span>
		<span class="text-[11px] text-base-content/55">{totalPlayers} entries</span>
	</div>

	{#if yours.length > 0}
		<div class="py-1.5 text-center text-[10px] font-extrabold tracking-[0.1em] text-primary/80">
			— your {yours.length === 1 ? 'pick' : 'picks'} —
		</div>
		{#each yours as p (p.reference)}
			<div
				class="flex items-center gap-2.5 rounded-btn bg-primary/10 px-2 py-1.5 ring-1 ring-primary/40 {p.status ===
				'miss'
					? ''
					: ''}"
			>
				<span class="w-5 text-center text-[11px] font-bold text-base-content/55"
					>{p.rank ?? '—'}</span
				>
				<span
					class="grid h-[26px] w-[26px] flex-none place-items-center rounded-full bg-primary/30 text-[10px] font-extrabold text-primary"
					>{initials(p.name)}</span
				>
				<span class="flex min-w-0 flex-1 items-center gap-2 truncate text-[12.5px] font-semibold">
					{p.entryName || p.name}
					<span
						class="rounded-badge bg-primary/20 px-1.5 py-px text-[9px] font-extrabold tracking-[0.08em] text-primary"
						>YOU</span
					>
				</span>
				<span class="font-display text-[13px]">{p.pick}</span>
				<span
					class="inline-flex items-center gap-1 rounded-badge px-2 py-0.5 text-[10.5px] font-bold {pillTone(
						p.status
					)}"
				>
					<span class="tracking-[0.06em]"
						>{p.status === 'exact' ? 'EXACT' : p.status === 'result' ? 'RESULT' : 'MISS'}</span
					>
					<span class="font-display">{p.pts > 0 ? `+${p.pts}` : p.pts}</span>
				</span>
			</div>
		{/each}
	{/if}

	{#if othersBanked.length > 0}
		<div class="mt-2 py-1.5 text-center text-[10px] font-extrabold tracking-[0.1em] text-base-content/40">
			— {banked.length} of {totalPlayers} banked points —
		</div>
	{/if}
	{#each othersBanked as p (p.reference)}
		<div class="flex items-center gap-2.5 rounded-btn px-2 py-1.5">
			<span class="w-5 text-center text-[11px] font-bold text-base-content/55">{p.rank ?? '—'}</span>
			<span
				class="grid h-[26px] w-[26px] flex-none place-items-center rounded-full bg-base-300/50 text-[10px] font-extrabold text-base-content/70"
				>{initials(p.name)}</span
			>
			<span class="min-w-0 flex-1 truncate text-[12.5px] font-semibold">{p.name}</span>
			<span class="font-display text-[13px]">{p.pick}</span>
			<span class="inline-flex items-center gap-1 rounded-badge px-2 py-0.5 text-[10.5px] font-bold {pillTone(p.status)}">
				<span class="tracking-[0.06em]">{p.status === 'exact' ? 'EXACT' : 'RESULT'}</span>
				<span class="font-display">+{p.pts}</span>
			</span>
		</div>
	{/each}

	{#if othersMissed.length > 0}
		<div class="mt-2 py-1.5 text-center text-[10px] font-extrabold tracking-[0.1em] text-base-content/40">
			— didn't score —
		</div>
		{#each othersMissed as p (p.reference)}
			<div class="flex items-center gap-2.5 rounded-btn px-2 py-1.5 opacity-75">
				<span class="w-5 text-center text-[11px] font-bold text-base-content/40">—</span>
				<span
					class="grid h-[26px] w-[26px] flex-none place-items-center rounded-full bg-base-300/50 text-[10px] font-extrabold text-base-content/70"
					>{initials(p.name)}</span
				>
				<span class="min-w-0 flex-1 truncate text-[12.5px] font-semibold">{p.name}</span>
				<span class="font-display text-[13px]">{p.pick}</span>
				<span class="inline-flex items-center gap-1 rounded-badge px-2 py-0.5 text-[10.5px] font-bold {pillTone(p.status)}">
					<span class="tracking-[0.06em]">MISS</span>
					<span class="font-display">0</span>
				</span>
			</div>
		{/each}
	{/if}
</div>
