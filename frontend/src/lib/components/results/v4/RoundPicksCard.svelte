<script lang="ts">
	/** Round Picks Card (v2.184.x) — replaces MissedPicksCard at the top of
	 *  each /results KO round tab. Renders the user's full bracket picks
	 *  for the active round, with each pick marked alive ✓ or missed ✗.
	 *
	 *  Three rendering states, picked by the `lineupSeeded` prop:
	 *
	 *  1. lineupSeeded === true → settled. Header reads
	 *     "Round of X · A/N through · +banked · –unrealised". Pills are
	 *     sorted alive-first then missed-last (each group alphabetical).
	 *
	 *  2. lineupSeeded === false → pre-resolution. Header reads
	 *     "Lineup pending · banks +N per alive pick". Pills render
	 *     neutrally without ✓/✗ marks so we don't promise / deny credit
	 *     before the upstream round finishes.
	 *
	 *  3. picks.length === 0 → component shouldn't be rendered (caller
	 *     gates on `picks.length > 0`).
	 *
	 *  Pill density: at R32 (32 picks) and R16 (16 picks) the team-code
	 *  label uses 3-letter FIFA codes (COL/CRO/ESP…) so the row wraps
	 *  cleanly on mobile. At QF/SF/F the simplified `displayTeamName`
	 *  is used since 8/4/2 pills have room for full names.
	 *
	 *  Replaces MissedPicksCard which only surfaced the misses; the new
	 *  card carries both halves of the story so a user doesn't need to
	 *  scan two regions to know "of my N picks, how many made it".
	 */
	import { teamCode } from '$lib/utils/teamCodes';
	import { displayTeamName } from '$lib/utils/teamName';
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';

	export let roundLabel: string;
	/** The user's bracket picks for this round (e.g. all 32 teams for R32). */
	export let picks: string[];
	/** The subset of `picks` that didn't make the actual lineup. Output of
	 *  `missedPicksForRound`. Should be `[]` when `lineupSeeded` is false. */
	export let missedTeams: string[];
	/** Per-pick advancement payout (advancement[stage] from scoring rules). */
	export let stagePoints: number;
	/** True for R32/R16 → use 3-letter FIFA codes; false for QF/SF/F → use
	 *  simplified names. Density compromise rationale documented above. */
	export let compactCodes: boolean = false;
	/** False when the round's lineup still has slot:* placeholders. Drops
	 *  the ✓/✗ marks and the through-count. */
	export let lineupSeeded: boolean = true;

	$: missedSet = new Set(missedTeams);
	$: aliveTeams = picks.filter((t) => !missedSet.has(t));
	$: aliveCount = aliveTeams.length;
	$: missedCount = missedTeams.length;
	$: banked = aliveCount * stagePoints;
	$: unrealised = missedCount * stagePoints;
	$: total = picks.length;

	// Sort: alive-first (alphabetical), missed last (alphabetical). Stable
	// across re-renders because we sort the source arrays before display.
	$: aliveSorted = [...aliveTeams].sort();
	$: missedSorted = [...missedTeams].sort();

	function pillLabel(team: string): string {
		return compactCodes ? teamCode(team) : displayTeamName(team);
	}
</script>

<div class="mt-3 rounded-box border border-base-300/60 bg-base-200 p-3">
	<!-- Header: round label + summary stats (tightened v2.184.x) -->
	<div class="mb-2 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
		<div class="text-[12.5px] font-bold">
			Your <span class="text-primary">{roundLabel}</span> bracket
		</div>
		<div class="font-mono text-[10.5px] tabular-nums text-base-content/55">
			{#if lineupSeeded}
				<strong class="text-base-content">{aliveCount}</strong>/{total} through
				<span class="ml-1 font-bold text-success">+{banked}</span>
				{#if missedCount > 0}
					<span class="ml-1 font-semibold text-error">· –{unrealised}</span>
				{/if}
			{:else}
				Lineup pending · banks
				<span class="font-bold text-primary">+{stagePoints}</span>
				per alive pick
			{/if}
		</div>
	</div>

	<!-- Pills row -->
	<div class="flex flex-wrap gap-1.5">
		{#if lineupSeeded}
			{#each aliveSorted as team (team)}
				<span
					class="inline-flex items-center gap-1 rounded-full border border-success/40 bg-base-300/20 px-2 py-0.5 text-[11px] font-semibold"
				>
					{#if hasFlag(team)}
						<img
							src={getFlagUrl(team, 'sm')}
							alt=""
							class="h-auto w-3.5 rounded-sm"
							style="aspect-ratio: 4 / 3"
						/>
					{/if}
					<span>{pillLabel(team)}</span>
					<span
						class="rounded-badge bg-success/15 px-1 text-[9px] font-bold text-success"
						aria-label="alive">✓</span
					>
				</span>
			{/each}
			{#each missedSorted as team (team)}
				<span
					class="inline-flex items-center gap-1 rounded-full border border-error/40 bg-base-300/20 px-2 py-0.5 text-[11px] font-semibold opacity-65"
				>
					{#if hasFlag(team)}
						<img
							src={getFlagUrl(team, 'sm')}
							alt=""
							class="h-auto w-3.5 rounded-sm"
							style="aspect-ratio: 4 / 3"
						/>
					{/if}
					<span class="line-through decoration-error/80 decoration-1">{pillLabel(team)}</span>
					<span
						class="rounded-badge bg-error/15 px-1 text-[9px] font-bold text-error"
						aria-label="missed">✗</span
					>
				</span>
			{/each}
		{:else}
			<!-- Pre-resolution: neutral pills with no claim either way. -->
			{#each [...picks].sort() as team (team)}
				<span
					class="inline-flex items-center gap-1 rounded-full border border-base-300/50 bg-base-300/20 px-2 py-0.5 text-[11px] font-semibold opacity-80"
				>
					{#if hasFlag(team)}
						<img
							src={getFlagUrl(team, 'sm')}
							alt=""
							class="h-auto w-3.5 rounded-sm"
							style="aspect-ratio: 4 / 3"
						/>
					{/if}
					<span>{pillLabel(team)}</span>
					<span
						class="rounded-badge bg-base-300/30 px-1 text-[9px] font-bold text-base-content/45"
						aria-label="pending">—</span
					>
				</span>
			{/each}
		{/if}
	</div>
</div>
