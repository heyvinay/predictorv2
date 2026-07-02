<script lang="ts">
	import type { R32Difference } from '$lib/utils/groupTracker';
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';
	import { displayTeamName } from '$lib/utils/teamName';

	export let differences: R32Difference[];
	export let totalMatches: number;
	export let statusLabel: string;
</script>

<section class="stadium-card mt-6 p-4 sm:p-5" aria-label="R32 pairings that differ from your prediction">
	<header class="mb-3">
		<h2 class="font-display text-xl tracking-wide">
			R32 impact preview · <span class="text-primary">where your bracket shifts</span>
		</h2>
		<p class="mt-1 max-w-prose text-xs text-base-content/55">
			Only pairings that differ from your prediction are shown below. Cleaner opponents on the
			right side mean easier points to bank next round.
		</p>
	</header>

	<div class="mb-3 flex items-center justify-between rounded-lg bg-primary/10 px-3 py-2 text-xs">
		<span>
			<strong class="text-primary">{totalMatches - differences.length} of {totalMatches}</strong>
			R32 pairings match your prediction —
			<strong class="text-primary">{differences.length} shifted</strong>.
		</span>
		<span class="text-base-content/45">{statusLabel}</span>
	</div>

	{#if differences.length === 0}
		<p class="text-sm text-base-content/55">
			Nothing has shifted yet — your predicted R32 lineup still matches the live standings.
		</p>
	{:else}
		<div class="divide-y divide-base-300 rounded-lg border border-base-300">
			{#each differences as diff}
				<div class="grid grid-cols-[auto_1fr_auto] items-center gap-3 px-3 py-2.5 text-xs sm:grid-cols-[70px_1fr_28px_1fr]">
					<span class="hidden text-[10px] font-bold uppercase tracking-wide text-base-content/40 sm:block">
						R32 · M{diff.matchNumber}
					</span>
					<div class="flex items-center gap-2 opacity-50">
						{#if diff.predicted.home && hasFlag(diff.predicted.home)}
							<img src={getFlagUrl(diff.predicted.home, 'sm')} alt="" class="h-3.5 w-5 rounded-sm" />
						{/if}
						<span class="truncate line-through decoration-base-content/30">
							{diff.predicted.home ? displayTeamName(diff.predicted.home) : '—'}
						</span>
						<span class="text-[10px] uppercase text-base-content/40">vs</span>
						{#if diff.predicted.away && hasFlag(diff.predicted.away)}
							<img src={getFlagUrl(diff.predicted.away, 'sm')} alt="" class="h-3.5 w-5 rounded-sm" />
						{/if}
						<span class="truncate line-through decoration-base-content/30">
							{diff.predicted.away ? displayTeamName(diff.predicted.away) : '—'}
						</span>
					</div>
					<span class="hidden text-center font-bold text-primary sm:block">→</span>
					<div class="flex items-center gap-2">
						{#if diff.projected.home && hasFlag(diff.projected.home)}
							<img src={getFlagUrl(diff.projected.home, 'sm')} alt="" class="h-3.5 w-5 rounded-sm" />
						{/if}
						<span class="truncate font-medium">
							{diff.projected.home ? displayTeamName(diff.projected.home) : 'TBD'}
						</span>
						<span class="text-[10px] uppercase text-base-content/40">vs</span>
						{#if diff.projected.away && hasFlag(diff.projected.away)}
							<img src={getFlagUrl(diff.projected.away, 'sm')} alt="" class="h-3.5 w-5 rounded-sm" />
						{/if}
						<span class="truncate font-medium">
							{diff.projected.away ? displayTeamName(diff.projected.away) : 'TBD'}
						</span>
					</div>
				</div>
			{/each}
		</div>
	{/if}
</section>
