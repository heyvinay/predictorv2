<script lang="ts">
	/**
	 * The Race — rank-over-time bump chart (spec §5, adapted to real data:
	 * checkpoints are DAILY leaderboard snapshots, not per-round, because
	 * that's what the backend records).
	 *
	 * Gold = your entries · green = current leader · faint = the field.
	 * Hover a line (or its right-edge label) to trace it; a tip bar below
	 * shows the full rank path.
	 */
	import { onMount } from 'svelte';
	import { getAllTrajectories } from '$api/leaderboard';
	import type { Fixture } from '$types';
	import type { EntryTrajectory, LbEntryV4 } from '$lib/types/leaderboard';
	import type { RaceSliceDescriptor, MatchMarker as ChartMatchMarker } from '$lib/types/leaderboard';
	import { multiEntryUserIds, rowDisplayName } from '$lib/utils/leaderboardV4';
	import RaceMinimap from './RaceMinimap.svelte';
	import MatchMarkerLayer from './MatchMarkerLayer.svelte';

	export let rows: LbEntryV4[];
	export let userId: string | null | undefined;
	/** Fixture list — anchors the x-axis to tournament time, not seed-data
	 *  snapshot dates. Start = first kickoff's UTC date, end = today. */
	export let fixtures: Fixture[] = [];
	export let slice: RaceSliceDescriptor | null = null;
	export let matchMarkers: ChartMatchMarker[] = [];
	export let showMinimap: boolean = false;

	let loading = true;
	let loadError = false;
	let trajectories: EntryTrajectory[] = [];
	let totalParticipants = 0;
	let hoverId: string | null = null;

	async function load() {
		loading = true;
		loadError = false;
		try {
			const res = await getAllTrajectories(30);
			trajectories = res.entries;
			totalParticipants = res.total_participants;
		} catch {
			loadError = true;
		}
		loading = false;
	}
	onMount(load);

	// ── geometry ──
	const PAD_L = 46;
	const PAD_R = 190;
	const PAD_T = 30;
	const PAD_B = 16;
	const W = 1080;

	function utcDate(iso: string): string {
		// Normalize an ISO datetime (or date) to its UTC calendar date.
		return new Date(iso).toISOString().slice(0, 10);
	}

	function dailyRange(start: string, end: string): string[] {
		if (start > end) return [start];
		const out: string[] = [];
		const startMs = Date.UTC(
			Number(start.slice(0, 4)),
			Number(start.slice(5, 7)) - 1,
			Number(start.slice(8, 10))
		);
		const endMs = Date.UTC(
			Number(end.slice(0, 4)),
			Number(end.slice(5, 7)) - 1,
			Number(end.slice(8, 10))
		);
		for (let t = startMs; t <= endMs; t += 86_400_000) {
			out.push(new Date(t).toISOString().slice(0, 10));
		}
		return out;
	}

	// X-axis anchors: tournament timeline, not seed snapshots.
	$: kickoffDates = fixtures.map((f) => utcDate(f.kickoff)).sort();
	$: startDate = kickoffDates[0] ?? new Date().toISOString().slice(0, 10);
	$: todayUtc = new Date().toISOString().slice(0, 10);
	// End grows as days pass — capped at the latest scoring day actually
	// represented in the data so the field doesn't trail off to empty.
	$: latestPointDate = trajectories
		.flatMap((t) => t.points.map((p) => p.captured_date))
		.filter((d) => d >= startDate)
		.sort()
		.at(-1) ?? startDate;
	$: endDate = todayUtc > latestPointDate ? todayUtc : latestPointDate;
	$: dates =
		startDate && endDate && startDate <= endDate ? dailyRange(startDate, endDate) : [];

	$: rankBounds = slice?.rankRange ?? [1, Math.max(totalParticipants, trajectories.length, 2)];
	$: rankSpan = Math.max(1, rankBounds[1] - rankBounds[0]);
	$: n = Math.max(totalParticipants, trajectories.length, 2);  // still needed for label slot count
	$: H = Math.max(360, PAD_T + PAD_B + (rendered.length || n) * 16);
	$: dateIndex = new Map(dates.map((d, i) => [d, i]));
	$: xOf = (d: string) =>
		PAD_L + ((dateIndex.get(d) ?? 0) * (W - PAD_L - PAD_R)) / Math.max(dates.length - 1, 1);
	$: yOf = (rank: number) => PAD_T + ((rank - rankBounds[0]) * (H - PAD_T - PAD_B)) / rankSpan;

	function dateLabel(d: string): string {
		return new Date(d + 'T00:00:00Z').toLocaleDateString(undefined, {
			day: 'numeric',
			month: 'short'
		});
	}

	type Line = {
		id: string;
		name: string;
		owner: string;
		isOwn: boolean;
		isLeader: boolean;
		path: string;
		finalRank: number;
		pts: number;
		points: { date: string; rank: number }[];
	};
	// Same display-name rule as the standings table (consistency).
	$: multiOwners = multiEntryUserIds(trajectories);
	$: sliceIds = slice ? new Set(slice.included.map((s) => s.entry_id)) : null;
	$: rendered = sliceIds ? trajectories.filter((t) => sliceIds!.has(t.entry_id)) : trajectories;
	$: lines = rendered
		.map((t): Line | null => {
			// Drop snapshot points outside the tournament window — pre-kickoff
			// seed data shouldn't pull the axis backwards.
			const pts = t.points
				.filter((p) => p.captured_date >= startDate && p.captured_date <= endDate)
				.map((p) => ({ date: p.captured_date, rank: p.position }));
			if (pts.length === 0) return null;
			const last = pts[pts.length - 1];
			return {
				id: t.entry_id,
				name: rowDisplayName(t, multiOwners),
				owner: t.user_name,
				isOwn: t.user_id === userId,
				isLeader: last.rank === 1,
				path: pts
					.map((p, i) => `${i === 0 ? 'M' : 'L'} ${xOf(p.date).toFixed(1)} ${yOf(p.rank).toFixed(1)}`)
					.join(' '),
				finalRank: last.rank,
				pts:
					t.points.find((p) => p.captured_date === last.date)?.total_points ?? 0,
				points: pts
			};
		})
		.filter((l): l is Line => l !== null)
		.sort((a, b) => a.finalRank - b.finalRank);

	// Right-edge labels get sequential slots so tied ranks don't overlap.
	// Divide by rendered-line count (NOT full-pool n) so the slot
	// spacing matches the actual visible lines — otherwise on a sliced
	// chart (Top 15 = ~16 lines) the labels squash into a tiny band at
	// the top of the chart and overlap each other.
	$: labelSlots = new Map(
		lines.map((l, i) => [
			l.id,
			PAD_T + i * ((H - PAD_T - PAD_B) / Math.max(lines.length - 1, 1))
		])
	);

	// Sparse x-axis tick labels (at most ~8 across the daily timeline).
	$: tickEvery = Math.max(1, Math.ceil(dates.length / 8));
	$: axisDates = dates.filter(
		(_, i) => i === 0 || i === dates.length - 1 || i % tickEvery === 0
	);

	// Sparse rank axis — anchor at slice min/max with a few in between.
	$: rankTicks = (() => {
		const [lo, hi] = rankBounds;
		if (hi - lo <= 8) return Array.from({ length: hi - lo + 1 }, (_, i) => lo + i);
		const candidates = [lo, hi, ...[5, 10, 15, 20, 25, 30, 40, 50, 75, 100]];
		return Array.from(new Set(candidates.filter((r) => r >= lo && r <= hi))).sort((a, b) => a - b);
	})();

	$: hovered = hoverId ? lines.find((l) => l.id === hoverId) ?? null : null;
	$: tipPath = hovered
		? hovered.points
				.slice(-8)
				.map((p) => `${dateLabel(p.date)} #${p.rank}`)
				.join(' → ')
		: '';

	function lineClass(l: Line): string {
		const base = l.isOwn
			? 'stroke-primary'
			: l.isLeader
			? 'stroke-success'
			: 'stroke-base-content/20';
		const dim = hoverId && hoverId !== l.id ? 'opacity-20' : '';
		return `${base} ${dim}`;
	}
	function lineWidth(l: Line): number {
		if (hoverId === l.id) return 3.2;
		return l.isOwn ? 2.6 : l.isLeader ? 2 : 1.4;
	}
	$: hasEnoughData = dates.length > 1 && lines.length > 0;
	$: preKickoff = startDate > todayUtc;
</script>

<div class="rounded-xl border border-base-300/60 bg-base-200 px-4 pb-3 pt-4 sm:px-5">
	<div class="mb-2 flex flex-wrap items-start justify-between gap-4">
		<div>
			<h2 class="font-hero text-2xl tracking-[0.04em]">The Race</h2>
			<p class="mt-1 text-xs text-base-content/55">
				Rank after every scoring day — gold lines are your entries. Hover or tap any line to
				trace it.
			</p>
		</div>
		<div class="flex gap-2">
			<span
				class="inline-flex items-center gap-1.5 rounded-full bg-base-300/40 px-2.5 py-1 text-[10.5px] font-bold text-base-content/70"
				><span class="h-[3px] w-3.5 rounded-sm bg-primary"></span>Your entries</span
			>
			<span
				class="inline-flex items-center gap-1.5 rounded-full bg-base-300/40 px-2.5 py-1 text-[10.5px] font-bold text-base-content/70"
				><span class="h-[3px] w-3.5 rounded-sm bg-success"></span>Leader</span
			>
			<span
				class="inline-flex items-center gap-1.5 rounded-full bg-base-300/40 px-2.5 py-1 text-[10.5px] font-bold text-base-content/70"
				><span class="h-[3px] w-3.5 rounded-sm bg-base-content/30"></span>The field</span
			>
		</div>
	</div>

	{#if loading}
		<div class="grid h-72 place-items-center">
			<span class="loading loading-spinner loading-lg text-primary"></span>
		</div>
	{:else if loadError}
		<div class="rounded-xl border border-error/40 bg-error/10 px-5 py-6 text-center">
			<p class="text-sm text-base-content/80">Couldn't load rank history.</p>
			<button class="btn btn-outline btn-sm mt-3" on:click={load}>Retry</button>
		</div>
	{:else if !hasEnoughData}
		<div class="grid h-56 place-items-center text-center">
			<p class="max-w-sm text-sm text-base-content/55">
				{#if preKickoff}
					The race chart unlocks at kickoff — first match {dateLabel(startDate)}.
				{:else}
					The race chart unlocks after the first full day of scoring.
				{/if}
			</p>
		</div>
	{:else}
		<div class="overflow-x-auto">
			<!-- Tap support (touch devices have no hover): tapping a line or
			     its label toggles the trace; tapping the chart background
			     clears it. svelte-ignore: 183 chart paths must not join the
			     tab order — the standings table is the accessible surface. -->
			<!-- svelte-ignore a11y-click-events-have-key-events a11y-no-noninteractive-element-interactions -->
			<svg
				viewBox="0 0 {W} {H}"
				class="block h-auto w-full min-w-[720px]"
				role="img"
				aria-label="Rank-over-time chart for all entries"
				on:mouseleave={() => (hoverId = null)}
				on:click={() => (hoverId = null)}
			>
				<!-- date columns -->
				{#each axisDates as d (d)}
					<line
						x1={xOf(d)}
						y1={PAD_T - 6}
						x2={xOf(d)}
						y2={H - PAD_B}
						class="stroke-base-300/50"
						stroke-width="1"
					/>
					<text
						x={xOf(d)}
						y={PAD_T - 12}
						text-anchor="middle"
						class="fill-base-content/55 font-display text-[11px] font-extrabold tracking-[0.08em]"
						>{dateLabel(d)}</text
					>
				{/each}
				<!-- rank axis -->
				{#each rankTicks as r (r)}
					<text
						x={PAD_L - 12}
						y={yOf(r) + 3.5}
						text-anchor="end"
						class="fill-base-content/30 text-[10px] font-semibold">{r}</text
					>
				{/each}

				<!-- field lines, then leader, then own (paint order) -->
				{#each lines.filter((l) => !l.isOwn && !l.isLeader) as l (l.id)}
					<path
						d={l.path}
						fill="none"
						stroke-linejoin="round"
						stroke-linecap="round"
						class="transition-opacity {lineClass(l)}"
						stroke-width={lineWidth(l)}
					/>
				{/each}
				{#each lines.filter((l) => l.isLeader && !l.isOwn) as l (l.id)}
					<path
						d={l.path}
						fill="none"
						stroke-linejoin="round"
						stroke-linecap="round"
						class="transition-opacity {lineClass(l)}"
						stroke-width={lineWidth(l)}
					/>
				{/each}
				{#each lines.filter((l) => l.isOwn) as l (l.id)}
					<path
						d={l.path}
						fill="none"
						stroke-linejoin="round"
						stroke-linecap="round"
						class="transition-opacity {lineClass(l)}"
						stroke-width={lineWidth(l)}
					/>
				{/each}

				<!-- invisible fat hit strokes -->
				{#each lines as l (l.id)}
					<!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
					<path
						d={l.path}
						fill="none"
						stroke="transparent"
						stroke-width="12"
						class="cursor-pointer"
						role="presentation"
						on:mouseenter={() => (hoverId = l.id)}
						on:click={(e) => {
							e.stopPropagation();
							hoverId = hoverId === l.id ? null : l.id;
						}}
					/>
				{/each}

				<!-- right-edge labels -->
				{#each lines as l (l.id)}
					<!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
					<text
						x={W - PAD_R + 10}
						y={(labelSlots.get(l.id) ?? 0) + 3.5}
						class="cursor-pointer text-[10px] font-semibold {l.isOwn
							? 'fill-primary font-extrabold'
							: l.isLeader
							? 'fill-success font-extrabold'
							: 'fill-base-content/55'} {hoverId && hoverId !== l.id ? 'opacity-25' : ''}"
						role="presentation"
						on:mouseenter={() => (hoverId = l.id)}
						on:click={(e) => {
							e.stopPropagation();
							hoverId = hoverId === l.id ? null : l.id;
						}}>{l.finalRank}. {l.name}</text
					>
				{/each}

				<!-- hovered checkpoint dots -->
				{#if hovered}
					{#each hovered.points as p (p.date)}
						<circle
							cx={xOf(p.date)}
							cy={yOf(p.rank)}
							r="3.5"
							class={hovered.isOwn
								? 'fill-primary'
								: hovered.isLeader
								? 'fill-success'
								: 'fill-base-content/70'}
						/>
					{/each}
				{/if}

				{#if matchMarkers.length > 0}
					<MatchMarkerLayer
						markers={matchMarkers}
						xScale={xOf}
						yTop={PAD_T}
						yBottom={H - PAD_B}
					/>
				{/if}
			</svg>
		</div>

		{#if showMinimap && slice}
			<RaceMinimap
				markers={slice.minimapMarkers}
				rankRange={slice.rankRange}
				totalParticipants={totalParticipants}
			/>
		{/if}

		{#if hovered}
			<div
				class="mt-1.5 flex flex-wrap items-center gap-2.5 rounded-lg bg-base-300/25 px-3.5 py-2 text-xs"
			>
				<b>{hovered.name}</b>
				{#if hovered.isOwn}<span class="text-base-content/55">· your entry</span>{/if}
				<span class="font-display font-extrabold text-primary">{hovered.pts} pts</span>
				<span class="text-base-content/55">{tipPath}</span>
			</div>
		{:else}
			<div class="mt-1.5 px-1 text-[10.5px] text-base-content/40">
				{rows.length} entries · {dates.length} scoring days
			</div>
		{/if}
	{/if}
</div>
