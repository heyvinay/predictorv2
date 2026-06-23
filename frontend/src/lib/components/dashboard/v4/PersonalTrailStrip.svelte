<script lang="ts">
	import { onMount } from 'svelte';
	import { getPersonalTrail } from '$lib/api/leaderboard';
	import type { EntryTrail } from '$lib/types/leaderboard';
	import { firstTwoPlusExpand } from '$lib/utils/leaderboardV4';

	let entries: EntryTrail[] = [];
	let loading = true;
	let expanded = false;

	onMount(async () => {
		try {
			const data = await getPersonalTrail();
			entries = data.entries;
		} catch {
			entries = [];
		} finally {
			loading = false;
		}
	});

	$: split = firstTwoPlusExpand(entries, expanded, 5);

	function pathFor(points: EntryTrail['points'], getter: (p: EntryTrail['points'][number]) => number, w = 800, h = 90): string {
		if (points.length === 0) return '';
		const ys = points.map(getter);
		const min = Math.min(...ys);
		const max = Math.max(...ys);
		const range = Math.max(1, max - min);
		return points
			.map((p, i) => {
				const x = (i / Math.max(1, points.length - 1)) * w;
				const y = h - 5 - ((getter(p) - min) / range) * (h - 10);
				return `${i === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)}`;
			})
			.join(' ');
	}
</script>

{#if !loading && entries.length > 0}
	<section class="rounded-box border border-base-300 bg-base-200 p-4">
		<header class="mb-3 flex items-center gap-2">
			<h3 class="m-0 text-xs font-bold uppercase tracking-wide text-primary">Your Trail — points vs pool average</h3>
		</header>

		<div class="flex flex-col gap-3">
			{#each split.visible as t (t.entry_id)}
				<div class="grid grid-cols-1 md:grid-cols-[1fr_2.5fr_0.8fr] gap-4 items-center">
					<div>
						<div class="font-bold text-sm">{t.entry_name}</div>
						<div class="text-xs text-base-content/40 mt-0.5">#{t.current_rank} · last 30 days</div>
					</div>
					<div>
						{#if t.points.length < 3}
							<div class="text-xs text-base-content/40 italic py-4">It's early — check back tomorrow.</div>
						{:else}
							<svg viewBox="0 0 800 90" class="w-full block">
								<path d={pathFor(t.points, p => p.pool_avg_points)} stroke="currentColor" stroke-width="2.5" fill="none" class="text-base-content/30" />
								<path d={pathFor(t.points, p => p.your_points)} stroke="currentColor" stroke-width="3.5" fill="none" class="text-primary" />
							</svg>
						{/if}
					</div>
					<div class="text-right">
						<div class="font-display text-2xl font-extrabold leading-none {t.current_gap >= 0 ? 'text-success' : 'text-error'}">
							{t.current_gap >= 0 ? '+' : ''}{Math.round(t.current_gap)}
						</div>
						<div class="text-[10px] uppercase tracking-wide text-base-content/40 mt-1">vs pool avg</div>
					</div>
				</div>
			{/each}

			{#if split.remaining > 0 && !expanded}
				<button type="button" class="text-xs text-primary self-start hover:underline" on:click={() => (expanded = true)}>
					+{split.remaining} more {split.remaining === 1 ? 'entry' : 'entries'}
				</button>
			{/if}
			{#if expanded && entries.length > 2}
				<button type="button" class="text-xs text-base-content/55 self-start hover:underline" on:click={() => (expanded = false)}>
					Show less
				</button>
			{/if}
		</div>
	</section>
{/if}
