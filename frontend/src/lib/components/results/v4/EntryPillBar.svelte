<script lang="ts">
	/** Entry switcher pill bar — V4 Results. Parent renders this only for
	 *  multi-entry users (spec: single-entry users never see a switcher).
	 *  Active pill: faint gold outline + tinted fill, NO glow. */
	import { computeDisplayStatus, type Entry } from '$lib/types/entry';
	import type { EntryRankInfo } from '$lib/types/results';

	export let entries: Entry[];
	export let selectedId: string;
	export let rankByEntry: Map<string, EntryRankInfo>;
	export let onSelect: (entryId: string) => void;

	function ordinal(n: number): string {
		const s = ['th', 'st', 'nd', 'rd'];
		const v = n % 100;
		return n + (s[(v - 20) % 10] || s[v] || s[0]);
	}

	function isDraft(e: Entry): boolean {
		return computeDisplayStatus(e, 'phase_1') !== 'submitted';
	}

	function scrollIntoViewAction(node: HTMLElement, active: boolean) {
		function maybeScroll(isActive: boolean) {
			if (isActive)
				node.scrollIntoView({ inline: 'center', block: 'nearest', behavior: 'smooth' });
		}
		maybeScroll(active);
		return { update: maybeScroll };
	}
</script>

<div class="flex items-stretch gap-2 overflow-x-auto pb-1" role="tablist" aria-label="Entries">
	{#each entries as e (e.id)}
		{@const active = e.id === selectedId}
		{@const rank = rankByEntry.get(e.id)}
		<button
			role="tab"
			aria-selected={active}
			use:scrollIntoViewAction={active}
			class="flex min-w-fit flex-col items-start gap-0.5 whitespace-nowrap rounded-full px-3.5 py-1.5 text-left transition-colors border-[1.5px] {active
				? 'border-primary/55 bg-primary/10'
				: 'border-transparent bg-base-300/40 hover:bg-base-300/60'}"
			on:click={() => onSelect(e.id)}
		>
			<span class="flex items-center gap-2">
				<span
					class="font-display text-[13px] leading-tight {active
						? 'text-base-content'
						: 'text-base-content/70'}">{e.display_name}</span
				>
				{#if isDraft(e)}
					<span
						class="rounded-badge bg-primary/20 px-1.5 py-px text-[9.5px] font-bold tracking-[0.08em] text-primary"
						>DRAFT</span
					>
				{/if}
			</span>
			<span class="text-[11px] font-bold">
				{#if rank}
					<span class={active ? 'text-primary' : 'text-base-content/55'}
						>{ordinal(rank.position)}</span
					>
					<span class="text-base-content/55"> · {rank.total_points} pts</span>
				{:else}
					<span class="text-base-content/30">—</span>
				{/if}
			</span>
		</button>
	{/each}
</div>
