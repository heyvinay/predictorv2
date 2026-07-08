<script lang="ts">
	/**
	 * Per-entry win-probability card — the inline panel that expands below a
	 * row in the Win Probability tab. Answers "what has to happen for THIS
	 * entry to win the pool", using the conditional breakdown the simulator
	 * ships alongside each entry's marginal Win%:
	 *
	 *  - Title Worlds: for each team that could still lift the cup, the
	 *    team's trophy odds and P(this entry wins | that team is champion).
	 *  - Decisive Matches: the next real-vs-real matches, with this entry's
	 *    win odds conditioned on each side advancing — sorted (server-side)
	 *    by how much the result swings them.
	 *
	 * All data arrives pre-computed on the joined row; this component is pure
	 * presentation (no fetch, no derivation beyond formatting + sorting the
	 * title-worlds by trophy odds for display).
	 */
	import type { LbEntryV4 } from '$lib/types/leaderboard';
	import type { WinProbabilityRow } from '$lib/utils/winProbability';
	import { displayRank, displayTotal, rowDisplayName } from '$lib/utils/leaderboardV4';
	import FlagCode from './FlagCode.svelte';
	import YouTag from './YouTag.svelte';

	export let entry: WinProbabilityRow;
	export let multiOwners: Set<string>;
	export let isOwn = false;
	export let live = false;

	// Match the Win Probability table's own precision: 1dp at/above 10%,
	// 2dp below so sub-1% odds don't collapse to "0.0%".
	function pct(v: number): string {
		return `${(v * 100).toFixed(v >= 0.1 ? 1 : 2)}%`;
	}

	const STAGE_LABEL: Record<string, string> = {
		round_of_32: 'Round of 32',
		round_of_16: 'Round of 16',
		quarter_final: 'Quarter-finals',
		semi_final: 'Semi-finals',
		final: 'Final'
	};
	function stageLabel(stage: string): string {
		return STAGE_LABEL[stage] ?? stage;
	}

	$: row = entry.row as LbEntryV4;
	$: ptsNow = displayTotal(row, live);
	$: proj = Math.round(entry.projected_points ?? 0);
	$: rank = displayRank(row, live);
	// Title worlds arrive sorted by trophy odds already, but re-sort defensively.
	$: worlds = [...(entry.title_worlds ?? [])].sort((a, b) => b.trophy_odds - a.trophy_odds);
	$: matches = entry.decisive_matches ?? [];
	// Win% bar fill — absolute (a 20% shot fills a fifth of the track), clamped.
	$: barPct = Math.max(0, Math.min(100, entry.p_win * 100));
	$: hasPath = worlds.length > 0 || matches.length > 0;
</script>

<div class="flex flex-col gap-3">
	<!-- header: rank · name · PTS/PROJ · big Win% + bar -->
	<div class="flex items-start gap-3">
		<span
			class="grid h-8 w-8 flex-none place-items-center rounded-lg font-display text-sm font-extrabold {isOwn
				? 'bg-primary/15 text-primary ring-[1.5px] ring-primary'
				: 'bg-base-300/70 text-base-content/70'}">{rank}</span
		>
		<div class="min-w-0 flex-1">
			<div class="flex items-center gap-1.5 font-display text-sm font-extrabold">
				<span class="truncate">{rowDisplayName(row, multiOwners)}</span>
				{#if isOwn}<YouTag />{/if}
			</div>
			<div class="mt-0.5 font-mono text-[10.5px] uppercase tracking-[0.08em] text-base-content/55">
				{ptsNow.toLocaleString()} pts now · proj {proj.toLocaleString()}
			</div>
		</div>
		<div class="flex flex-none flex-col items-end">
			<span class="font-display text-2xl font-extrabold leading-none text-primary">{pct(entry.p_win)}</span>
			<span class="mt-0.5 text-[9px] font-bold uppercase tracking-[0.1em] text-base-content/45"
				>win chance</span
			>
		</div>
	</div>

	<!-- win% track -->
	<div class="h-1.5 w-full overflow-hidden rounded-full bg-base-300/60">
		<div class="h-full rounded-full bg-primary transition-[width]" style="width: {barPct}%"></div>
	</div>

	{#if !hasPath}
		<p class="rounded-lg bg-base-300/30 px-3 py-2.5 text-[11.5px] text-base-content/55">
			No realistic path to first from here — this entry doesn't win the pool in any of the simulated
			outcomes above the noise floor.
		</p>
	{/if}

	<!-- title worlds -->
	{#if worlds.length}
		<section>
			<h4 class="mb-1.5 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-base-content/45">
				Title worlds
			</h4>
			<div class="flex flex-col">
				{#each worlds as w (w.team)}
					<div
						class="flex items-center justify-between gap-3 border-t border-base-300/40 py-1.5 first:border-t-0"
					>
						<span class="flex min-w-0 items-center gap-1.5 text-[12px] text-base-content/80">
							<FlagCode team={w.team} size="sm" />
							<span class="truncate"
								>lift the cup
								<span class="text-base-content/45">({pct(w.trophy_odds)})</span></span
							>
						</span>
						<span class="flex-none font-mono text-[12px] font-bold tabular-nums text-success">
							wins {pct(w.p_win_given_champion)}
						</span>
					</div>
				{/each}
			</div>
		</section>
	{/if}

	<!-- decisive matches -->
	{#if matches.length}
		<section>
			<h4 class="mb-1.5 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-base-content/45">
				Decisive matches <span class="text-base-content/30">(win% if home / away wins)</span>
			</h4>
			<div class="flex flex-col">
				{#each matches as m (m.match_number)}
					{@const homeBigger = m.p_win_if_home >= m.p_win_if_away}
					<div
						class="flex items-center justify-between gap-3 border-t border-base-300/40 py-1.5 first:border-t-0"
					>
						<span class="flex min-w-0 flex-col text-[12px] text-base-content/80">
							<span class="text-[9.5px] font-bold uppercase tracking-[0.08em] text-base-content/45"
								>{stageLabel(m.stage)}</span
							>
							<span class="flex items-center gap-1 truncate">
								<FlagCode team={m.home_team} size="sm" />
								<span class="text-base-content/40">v</span>
								<FlagCode team={m.away_team} size="sm" />
							</span>
						</span>
						<span class="flex-none font-mono text-[12px] tabular-nums">
							<span class={homeBigger ? 'font-bold text-base-content' : 'text-base-content/55'}
								>{pct(m.p_win_if_home)}</span
							>
							<span class="text-base-content/30"> / </span>
							<span class={!homeBigger ? 'font-bold text-base-content' : 'text-base-content/55'}
								>{pct(m.p_win_if_away)}</span
							>
						</span>
					</div>
				{/each}
			</div>
		</section>
	{/if}
</div>
