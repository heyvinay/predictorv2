<!--
	GroupAccordion — collapsible section for one group's fixtures.

	Header:
	    [▾] Group X   [flag] [flag] [flag] [flag]   N/M
	    └─ chevron rotates 180° on open

	Body (rendered only when `open` is true):
	    [muted "Mon 15 Jun" label]
	    <FixtureRow ... />  × n fixtures on that date
	    [subtle top border]
	    [muted "Tue 16 Jun" label]
	    <FixtureRow ... />
	    ...

	The flag cluster is the *deduplicated home teams* of the group. In a
	4-team round-robin (6 matches), each team is home in ~3 matches, so
	this gives all 4 group teams in their FIFA-draw order.

	The completion badge `N/M` turns success/green when N === M and
	M > 0. Empty groups (M === 0) stay ghost.

	State:
	  - `open` is controlled by the parent so multiple accordions can
	    open simultaneously (per the resolved decision). Parent
	    typically holds a Set<string> of open group letters and toggles
	    membership on header click.

	Per the spec, no standings or third-place markup lives here.
-->
<script lang="ts">
	import { slide } from 'svelte/transition';
	import { cubicOut } from 'svelte/easing';
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';
	import type { Fixture, FixturesByGroup } from '$lib/types';
	import type { TeamStanding } from '$lib/utils/standings';
	import FixtureRow from './FixtureRow.svelte';

	export let group: FixturesByGroup;
	export let open: boolean = false;
	export let editable: boolean = false;
	export let getPrediction: (fixtureId: string) => { home: number; away: number } | null = () =>
		null;
	export let onScore: (fixtureId: string, home: number, away: number) => void = () => {};
	export let onToggle: () => void = () => {};

	/**
	 * Optional predicted standings for this group. When provided, renders
	 * a compact 4-row table at the top of the body (above the fixtures).
	 * Top 2 = advances (success), 3rd = best-third candidate (warning),
	 * 4th = out (error). Mirrors the legacy `.standings-table-v2` semantics.
	 */
	export let standings: TeamStanding[] = [];

	/**
	 * Tied-teams groups (alphabetical fallback in effect). Each inner array
	 * is the alphabetically-sorted set of tied team names. When non-empty,
	 * a warning alert appears above the standings.
	 */
	export let tiedTeams: string[][] = [];

	// Unique home teams (in fixture order). In a 4-team group's 6 matches,
	// the four group teams each appear as "home" in 3 of the 6, so the
	// deduplicated home set typically covers all four teams.
	$: uniqueHomeTeams = (() => {
		const seen = new Set<string>();
		const out: string[] = [];
		for (const f of group.fixtures) {
			if (!seen.has(f.home_team)) {
				seen.add(f.home_team);
				out.push(f.home_team);
			}
		}
		return out;
	})();

	$: predictedCount = group.fixtures.filter((f) => getPrediction(f.id) !== null).length;
	$: totalCount = group.fixtures.length;
	$: complete = totalCount > 0 && predictedCount === totalCount;

	// Group fixtures by their local kickoff date for the date sub-groups.
	// Sort each date's fixtures by kickoff time, then sort the date groups
	// themselves chronologically.
	$: fixturesByDate = (() => {
		const byKey = new Map<string, Fixture[]>();
		for (const f of group.fixtures) {
			const d = new Date(f.kickoff);
			const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
			if (!byKey.has(key)) byKey.set(key, []);
			byKey.get(key)!.push(f);
		}
		const sections = Array.from(byKey.values()).map((fxs) => {
			const sorted = [...fxs].sort(
				(a, b) => new Date(a.kickoff).getTime() - new Date(b.kickoff).getTime()
			);
			return { date: new Date(sorted[0].kickoff), fixtures: sorted };
		});
		sections.sort((a, b) => a.date.getTime() - b.date.getTime());
		return sections;
	})();

	// Static class lookup for standings position highlighting. Tailwind's JIT
	// can't see dynamic class strings (`bg-${tone}/15`) so we materialize all
	// three variants here as full class strings.
	const POS_CLASS = {
		advance: 'bg-success/15 text-success',
		best3rd: 'bg-warning/15 text-warning',
		out: 'bg-error/15 text-error'
	} as const;
	function posTone(i: number): 'advance' | 'best3rd' | 'out' {
		if (i < 2) return 'advance';
		if (i === 2) return 'best3rd';
		return 'out';
	}

	function fmtDate(d: Date): string {
		// "Mon 15 Jun" — short weekday + day + month
		return d.toLocaleDateString('en-GB', {
			weekday: 'short',
			day: 'numeric',
			month: 'short'
		});
	}
</script>

<div class="rounded-xl border border-base-content/10 bg-base-200/30 overflow-hidden">
	<!-- Header (always rendered) -->
	<button
		type="button"
		class="flex items-center gap-3 w-full px-4 py-3 hover:bg-base-300/30 min-h-12 text-left"
		on:click={onToggle}
		aria-expanded={open}
		aria-controls="group-{group.group}-body"
	>
		<span class="font-display font-bold text-base sm:text-lg whitespace-nowrap">
			Group {group.group}
		</span>

		<!-- Flag cluster: deduplicated home teams -->
		<div class="flex items-center gap-1 flex-1 min-w-0 overflow-hidden">
			{#each uniqueHomeTeams as team (team)}
				{#if hasFlag(team)}
					<img
						src={getFlagUrl(team, 'sm')}
						alt=""
						class="w-5 h-auto rounded-sm flex-shrink-0"
						title={team}
					/>
				{/if}
			{/each}
		</div>

		<!-- Completion badge -->
		<span
			class="badge badge-sm {complete ? 'badge-success' : 'badge-ghost'} font-mono tabular-nums"
		>
			{predictedCount}/{totalCount}
		</span>

		<!-- Chevron (rotates on open) -->
		<svg
			class="w-4 h-4 opacity-60 flex-shrink-0 transition-transform"
			class:rotate-180={open}
			viewBox="0 0 20 20"
			fill="currentColor"
			aria-hidden="true"
		>
			<path
				fill-rule="evenodd"
				d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z"
				clip-rule="evenodd"
			/>
		</svg>
	</button>

	<!-- Body (only when open) -->
	{#if open}
		<div id="group-{group.group}-body" transition:slide={{ duration: 200, easing: cubicOut }}>
			<!-- Tied-teams warning(s) (if any) -->
			{#if tiedTeams.length > 0}
				<div class="px-4 pt-3 pb-1">
					<div class="alert alert-warning text-xs py-2">
						<div>
							<div class="font-semibold mb-0.5">⚠ Tied teams in Group {group.group}</div>
							{#each tiedTeams as set (set.join('-'))}
								<p class="text-[11px] opacity-90">
									{set.join(', ')} — tied on points, GD, GF + head-to-head; ranked
									alphabetically as fallback. Adjust scores to break the tie.
								</p>
							{/each}
						</div>
					</div>
				</div>
			{/if}

			<!-- Predicted standings (compact, scoped to this group) -->
			{#if standings.length > 0}
				<div class="px-4 pt-3">
					<div class="text-[10px] uppercase tracking-wider text-base-content/50 font-semibold mb-1.5">
						Predicted standings
					</div>
					<div class="overflow-x-auto">
						<table class="w-full text-xs">
							<thead class="text-base-content/40 uppercase tracking-wider">
								<tr>
									<th class="text-left font-normal pb-1 w-6">#</th>
									<th class="text-left font-normal pb-1">Team</th>
									<th class="text-center font-normal pb-1">P</th>
									<th class="text-center font-normal pb-1">W</th>
									<th class="text-center font-normal pb-1">D</th>
									<th class="text-center font-normal pb-1">L</th>
									<th class="text-center font-normal pb-1">GD</th>
									<th class="text-center font-normal pb-1">Pts</th>
								</tr>
							</thead>
							<tbody>
								{#each standings as t, i (t.team)}
									<tr class="border-t border-base-content/5">
										<td class="py-1">
											<span
												class="inline-flex items-center justify-center w-5 h-5 rounded-full text-[10px] font-mono {POS_CLASS[
													posTone(i)
												]}">{i + 1}</span
											>
										</td>
										<td class="py-1">
											<span class="flex items-center gap-1.5">
												{#if hasFlag(t.team)}
													<img
														src={getFlagUrl(t.team, 'sm')}
														alt=""
														class="w-4 h-auto rounded-sm flex-shrink-0"
													/>
												{/if}
												<span class="truncate">{t.team}</span>
											</span>
										</td>
										<td class="text-center font-mono tabular-nums py-1">{t.played}</td>
										<td class="text-center font-mono tabular-nums py-1">{t.won}</td>
										<td class="text-center font-mono tabular-nums py-1">{t.drawn}</td>
										<td class="text-center font-mono tabular-nums py-1">{t.lost}</td>
										<td class="text-center font-mono tabular-nums py-1">
											<span
												class={t.goalDifference > 0
													? 'text-success'
													: t.goalDifference < 0
														? 'text-error'
														: 'opacity-60'}
												>{t.goalDifference > 0 ? '+' : ''}{t.goalDifference}</span
											>
										</td>
										<td class="text-center font-mono tabular-nums font-bold py-1">{t.points}</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
					<div class="flex gap-3 text-[10px] text-base-content/50 mt-2 mb-1 flex-wrap">
						<span class="flex items-center gap-1"
							><span class="w-1 h-2.5 bg-success rounded"></span>Advances (top 2)</span
						>
						<span class="flex items-center gap-1"
							><span class="w-1 h-2.5 bg-warning rounded"></span>Best 3rd candidate</span
						>
						<span class="flex items-center gap-1"
							><span class="w-1 h-2.5 bg-error rounded"></span>Out</span
						>
					</div>
				</div>
			{/if}

			<!-- Date-grouped fixtures -->
			{#each fixturesByDate as section, idx (section.date.getTime())}
				<div class:border-t={idx > 0} class="border-base-content/10">
					<div
						class="text-xs text-base-content/50 px-4 pt-2 pb-1 font-mono uppercase tracking-wider"
					>
						{fmtDate(section.date)}
					</div>
					{#each section.fixtures as f (f.id)}
						<FixtureRow
							fixture={f}
							prediction={getPrediction(f.id)}
							editable={editable && !f.is_locked}
							onScore={(home, away) => onScore(f.id, home, away)}
						/>
					{/each}
				</div>
			{/each}
		</div>
	{/if}
</div>
