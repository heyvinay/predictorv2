<script lang="ts">
	/**
	 * Waterfall — chronological "where the gap was made" chart for /compare.
	 * Replaces the old magnitude-ranked SwingList: same underlying swings,
	 * but ordered by when each element actually resolved (group stage ->
	 * bonus -> knockout rounds) instead of ranked by |delta|, so the bars
	 * read as a real progression rather than a reconnected ranked list.
	 */
	import type { Fixture } from '$types';
	import { buildWaterfall, WATERFALL_PHASE_LABEL, type Swing, type WaterfallPhase } from '$lib/utils/compareEntries';

	export let swings: Swing[];
	export let fixtureById: Map<string, Fixture>;
	export let aName: string;
	export let bName: string;

	$: steps = buildWaterfall(swings, fixtureById);
	$: total = steps.length ? steps[steps.length - 1].cumulative : 0;

	$: allPoints = [0, ...steps.map((s) => s.cumulative)];
	$: lo = Math.min(...allPoints);
	$: hi = Math.max(...allPoints);
	$: span = Math.max(1, hi - lo);
	$: pad = span * 0.12;
	$: scaleLo = lo - pad;
	$: scaleSpan = hi + pad - scaleLo || 1;
	$: pct = (v: number) => ((v - scaleLo) / scaleSpan) * 100;
	$: zeroPct = pct(0);

	type DisplayRow =
		| { type: 'divider'; phase: WaterfallPhase }
		| { type: 'row'; swing: Swing; from: number; to: number; width: number; isPos: boolean; connector: number | null };

	$: rows = ((): DisplayRow[] => {
		const out: DisplayRow[] = [];
		let prev = 0;
		let prevPhase: WaterfallPhase | null = null;
		steps.forEach((step, i) => {
			if (step.phase !== prevPhase) {
				out.push({ type: 'divider', phase: step.phase });
				prevPhase = step.phase;
			}
			const from = pct(Math.min(prev, step.cumulative));
			const to = pct(Math.max(prev, step.cumulative));
			out.push({
				type: 'row',
				swing: step.swing,
				from,
				to,
				width: Math.max(0.6, to - from),
				isPos: step.swing.delta > 0,
				connector: i > 0 ? pct(prev) : null
			});
			prev = step.cumulative;
		});
		return out;
	})();

	$: finalFrom = pct(Math.min(0, total));
	$: finalTo = pct(Math.max(0, total));
	$: finalWidth = Math.max(0.6, finalTo - finalFrom);

	const fmt = (n: number) => (n > 0 ? `+${Math.round(n * 10) / 10}` : `${Math.round(n * 10) / 10}`);
	const GRID = 'grid grid-cols-[6.5rem_1fr_2.75rem] sm:grid-cols-[9rem_1fr_3.25rem] items-center gap-2';
</script>

<p class="mb-3 text-xs text-base-content/55">
	{aName} vs {bName} — every match, knockout call and bonus question, in the order they actually happened.
</p>

<div class="mb-1.5 flex items-center gap-3.5 text-[11px] text-base-content/40">
	<span class="flex items-center gap-1.5"><i class="h-2 w-2 rounded-sm bg-success"></i>{aName} gains ground</span>
	<span class="flex items-center gap-1.5"><i class="h-2 w-2 rounded-sm bg-error"></i>{bName} gains ground</span>
</div>

{#if steps.length === 0}
	<p class="rounded-btn border border-base-300/60 bg-base-100 px-3 py-4 text-center text-sm text-base-content/50">
		No differences yet — every settled pick, call and bonus question matches between these two entries.
	</p>
{:else}
	<!-- shared axis ruler: same grid template as every row below, so its zero
	     tick lines up exactly with 0 inside each row's own track -->
	<div class={GRID}>
		<span></span>
		<div class="relative h-4">
			<div class="absolute inset-x-0 top-1/2 h-px bg-base-300"></div>
			<div class="absolute top-0 bottom-0 w-px bg-base-content/30" style="left: {zeroPct}%"></div>
			<span
				class="absolute -top-0.5 -translate-x-1/2 text-[9px] font-bold uppercase tracking-wider text-base-content/40"
				style="left: {zeroPct}%">even</span
			>
		</div>
		<span></span>
	</div>

	{#each rows as r (r.type === 'divider' ? `d-${r.phase}` : `s-${r.swing.kind}-${r.swing.key}`)}
		{#if r.type === 'divider'}
			<div class="mt-3.5 mb-1 flex items-center gap-2 text-[10px] font-extrabold uppercase tracking-wider text-base-content/40 first:mt-1">
				{WATERFALL_PHASE_LABEL[r.phase]}
				<span class="h-px flex-1 bg-base-300"></span>
			</div>
		{:else}
			<div class="{GRID} border-t border-base-300/40 py-1.5 first:border-t-0">
				<p class="truncate text-[11px] leading-tight sm:text-xs" title={r.swing.label}>{r.swing.label}</p>
				<div class="relative h-[22px] rounded-md border border-base-300/60 bg-base-100">
					{#if r.connector !== null}
						<div class="absolute -top-2 h-2 w-px bg-base-content/30" style="left: {r.connector}%"></div>
					{/if}
					<div
						class="absolute inset-y-[2px] rounded {r.isPos
							? 'bg-gradient-to-r from-success/55 to-success'
							: 'bg-gradient-to-r from-error to-error/55'}"
						style="left: {r.from}%; width: {r.width}%"
					></div>
				</div>
				<span class="text-right font-display text-xs font-extrabold tabular-nums {r.isPos ? 'text-success' : 'text-error'}"
					>{fmt(r.swing.delta)}</span
				>
			</div>
		{/if}
	{/each}

	<div class="{GRID} mt-1 border-t border-base-300/60 pt-2.5">
		<p class="text-xs font-extrabold">Final gap</p>
		<div class="relative h-[22px] rounded-md border border-primary/50 bg-primary/10">
			<div class="absolute inset-y-[2px] rounded bg-gradient-to-r from-primary/55 to-primary" style="left: {finalFrom}%; width: {finalWidth}%"></div>
		</div>
		<span class="text-right font-display text-sm font-extrabold tabular-nums text-primary">{fmt(total)}</span>
	</div>
{/if}
