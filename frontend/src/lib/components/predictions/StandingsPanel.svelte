<!--
	StandingsPanel — live-updating sidebar on /entries/[id] that reflects
	the impact of the user's predictions in real time.

	Three modes driven by the wizard's active section:
	  - 'groups' → 4-row standings table for the currently focused group
	  - 'knockout' → read-only mini bracket (existing KnockoutBracket in
	    locked mode) showing the user's predicted advancement path
	  - 'bonus' → compact list of answered bonus questions

	Layout mode (visual presentation):
	  - 'split' → embedded in a flex row alongside the wizard at ≥1280px
	  - 'drawer' → slides in from the right as an overlay below 1280px

	Reads from existing prediction stores so it updates reactively without
	plumbing changes — Svelte's reactive store subscriptions handle the
	"recompute on every prediction edit" behaviour automatically.
-->
<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import { predictionsByFixture, bracketPrediction, workingBracketPrediction, unsavedChanges } from '$stores/predictions';
	import { groupFixtures } from '$stores/fixtures';
	import {
		computeGroupStandingsMapWithWarnings,
		type TeamStanding
	} from '$lib/utils/standings';
	import type { MatchPrediction } from '$lib/types';
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';
	import KnockoutBracket from '$components/bracket/KnockoutBracket.svelte';
	import type { BonusQuestion } from '$api/bonus';

	export let activeGroup: string = 'A';
	export let activeSection: 'groups' | 'knockout' | 'bonus' = 'groups';
	export let mode: 'split' | 'drawer' = 'split';
	/** Bonus inputs (passed in — they live as page-local state in the wizard). */
	export let bonusQuestions: BonusQuestion[] = [];
	export let bonusAnswers: Map<string, string> = new Map();
	/**
	 * Third-place qualifying standings (top 8 of 12 advance to R32).
	 * Parent computes these via `applyFifaTiebreakers`; we just render
	 * when `activeGroup === 'thirdplace'`. Empty array hides the table.
	 */
	export let thirdPlaceStandings: TeamStanding[] = [];
	/** Warnings filtered for the third-place "group" (alphabetical fallback). */
	export let thirdPlaceWarnings: Array<{ group: string; tiedTeams: string[] }> = [];
	/** True when every fixture in every group has a saved-or-unsaved prediction.
	 * Gates the third-place tie warning since alphabetical-fallback is only
	 * meaningful once all games are in. */
	export let allGroupsComplete: boolean = false;

	const dispatch = createEventDispatcher<{ close: void }>();

	// Effective predictions = saved overlaid with unsaved. The standings
	// util reads only `home_score` / `away_score` from each entry, so for
	// fixtures with an unsaved-only score (no saved row yet) we synthesize
	// a minimal MatchPrediction with placeholder filler for the other
	// fields. This makes the standings TABLE update live as the user
	// types, instead of only refreshing after Save Draft promotes
	// unsavedChanges into predictionsByFixture.
	$: effectivePredictions = (() => {
		const merged = new Map<string, MatchPrediction>($predictionsByFixture);
		for (const fid in $unsavedChanges) {
			const u = $unsavedChanges[fid];
			const existing = merged.get(fid);
			if (existing) {
				merged.set(fid, { ...existing, home_score: u.home_score, away_score: u.away_score });
			} else {
				merged.set(fid, {
					id: '',
					entry_id: '',
					fixture_id: fid,
					home_score: u.home_score,
					away_score: u.away_score,
					phase: 'phase_1',
					locked_at: null,
					is_locked: false,
					created_at: '',
					updated_at: ''
				});
			}
		}
		return merged;
	})();

	// Compute standings for ALL groups using the merged map so the table
	// reflects unsaved edits in real time.
	$: standingsResult = computeGroupStandingsMapWithWarnings(
		$groupFixtures,
		effectivePredictions
	);
	$: standingsMap = standingsResult.standingsMap;
	$: groupStandings = standingsMap[activeGroup] ?? ([] as TeamStanding[]);
	$: groupWarnings = standingsResult.warnings.filter((w) => w.group === activeGroup);

	// Tie warning is suppressed until every fixture in the active group has
	// a score (saved or unsaved). Until then a tie could still be broken
	// by the remaining games, so the alphabetical-fallback warning would
	// be premature noise. `effectivePredictions` already merges both
	// sources — one `.has()` covers both cases.
	$: activeGroupFixtures =
		$groupFixtures.find((g) => g.group === activeGroup)?.fixtures ?? [];
	$: allGroupGamesPredicted =
		activeGroupFixtures.length > 0 &&
		activeGroupFixtures.every((f) => effectivePredictions.has(f.id));

	// Static class lookup for standings position highlighting. Tailwind's
	// JIT can't see dynamic class strings, so we materialize each variant
	// here as full class strings.
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

	// True when at least one fixture in `group` has a (saved or unsaved)
	// prediction. Used inside 'all' mode to gate per-group tie-warning
	// icons in each table header — no point flagging a tie that's
	// computed off an empty group.
	function groupHasAnyPrediction(group: string): boolean {
		const fixtures = $groupFixtures.find((g) => g.group === group)?.fixtures ?? [];
		return fixtures.some((f) => effectivePredictions.has(f.id));
	}

	// In 'all' mode, fetch the warning (if any) for one group. We surface
	// it as a small ⚠ icon next to the group heading rather than as a
	// full alert below the table — the user asked to keep the stack
	// uncluttered.
	function groupHasUnresolvedTie(group: string): boolean {
		return (
			groupHasAnyPrediction(group) &&
			standingsResult.warnings.some((w) => w.group === group)
		);
	}

	// Ordered group letters for 'all' mode. Strips the 'thirdplace'
	// pseudo-group; the cross-group third-place table renders separately
	// at the bottom of the stack.
	$: orderedGroups = $groupFixtures
		.map((g) => g.group)
		.filter((g) => g !== 'thirdplace');
</script>

<aside
	class="bg-base-200 border-l border-base-300/60 flex flex-col h-full overflow-hidden"
	aria-label="Live standings panel"
>
	<header
		class="flex-shrink-0 flex items-center justify-between gap-2 px-4 py-3 border-b border-base-300/60 bg-base-100"
	>
		<div class="min-w-0">
			<div class="text-[10px] uppercase tracking-wider text-base-content/50 font-semibold">
				Live preview
			</div>
			<h3 class="font-display text-2xl leading-tight truncate">
				{#if activeSection === 'groups'}
					{#if activeGroup === 'all'}All Groups{:else if activeGroup === 'thirdplace'}Third Place{:else}Group {activeGroup}{/if}
				{:else if activeSection === 'knockout'}Knockout Path{:else}Bonus Answers{/if}
			</h3>
		</div>
		{#if mode === 'drawer'}
			<button
				type="button"
				class="btn btn-ghost btn-sm flex-shrink-0"
				on:click={() => dispatch('close')}
				aria-label="Close standings panel"
			>
				Done
			</button>
		{/if}
	</header>

	<div class="flex-1 overflow-y-auto px-4 py-3">
		{#if activeSection === 'groups'}
			{#if activeGroup === 'all'}
				<!-- ====== 'all' mode — vertical stack of every group's table ======
				     Triggered from the wizard's Expand-all button. Each group
				     gets a heading (with a ⚠ icon if there's an unresolved tie),
				     the existing single-group table format, and a slim spacer.
				     Tie-warning ALERTS are suppressed inside this stack per
				     the spec; only the cross-group third-place warning survives
				     at the bottom, because that one is genuinely consequential
				     (it can flip qualification across groups). -->
				<div class="space-y-5">
					{#each orderedGroups as g (g)}
						{@const teams = standingsMap[g] ?? []}
						<section>
							<div class="flex items-center gap-2 mb-1.5">
								<span class="font-display text-base tracking-wide">Group {g}</span>
								{#if groupHasUnresolvedTie(g)}
									<span
										class="badge badge-warning badge-xs gap-1 font-medium"
										title="Unresolved tie in this group — open Group {g} for details"
									>
										<svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5" aria-hidden="true">
											<path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
										</svg>
										Tie
									</span>
								{/if}
							</div>
							{#if teams.length === 0}
								<p class="text-xs text-base-content/40 py-1">No predictions yet.</p>
							{:else}
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
											{#each teams as team, i (team.team)}
												<tr class="border-t border-base-content/5">
													<td class="py-1">
														<span
															class="inline-flex items-center justify-center w-5 h-5 rounded-full text-[10px] font-mono {POS_CLASS[posTone(i)]}"
														>{i + 1}</span>
													</td>
													<td class="py-1">
														<span class="flex items-center gap-1.5">
															{#if hasFlag(team.team)}
																<img src={getFlagUrl(team.team, 'sm')} alt="" class="w-4 h-auto rounded-sm flex-shrink-0" />
															{/if}
															<span class="truncate">{team.team}</span>
														</span>
													</td>
													<td class="text-center font-mono tabular-nums py-1">{team.played}</td>
													<td class="text-center font-mono tabular-nums py-1">{team.won}</td>
													<td class="text-center font-mono tabular-nums py-1">{team.drawn}</td>
													<td class="text-center font-mono tabular-nums py-1">{team.lost}</td>
													<td class="text-center font-mono tabular-nums py-1">
														<span class={team.goalDifference > 0 ? 'text-success' : team.goalDifference < 0 ? 'text-error' : 'opacity-60'}>
															{team.goalDifference > 0 ? '+' : ''}{team.goalDifference}
														</span>
													</td>
													<td class="text-center font-mono tabular-nums font-bold py-1">{team.points}</td>
												</tr>
											{/each}
										</tbody>
									</table>
								</div>
							{/if}
						</section>
					{/each}

					<!-- Third-place qualifying table — closes the stack. Kept the
					     existing markup style for parity with the dedicated
					     'thirdplace' mode below. -->
					{#if thirdPlaceStandings.length > 0}
						<section>
							<div class="flex items-center gap-2 mb-1.5">
								<span class="font-display text-base tracking-wide">Third Place</span>
								<span class="text-[10px] text-base-content/40 uppercase tracking-wider">Top 8 advance</span>
							</div>
							<div class="overflow-x-auto">
								<table class="w-full text-xs">
									<thead class="text-base-content/40 uppercase tracking-wider">
										<tr>
											<th class="text-left font-normal pb-1 w-6">#</th>
											<th class="text-center font-normal pb-1 w-8">Grp</th>
											<th class="text-left font-normal pb-1">Team</th>
											<th class="text-center font-normal pb-1">P</th>
											<th class="text-center font-normal pb-1">GD</th>
											<th class="text-center font-normal pb-1">Pts</th>
										</tr>
									</thead>
									<tbody>
										{#each thirdPlaceStandings as t, i (t.team)}
											<tr class="border-t border-base-content/5 {i < 8 ? 'bg-success/5' : ''}">
												<td class="py-1">
													<span class="inline-flex items-center justify-center w-5 h-5 rounded-full text-[10px] font-mono {i < 8 ? 'bg-success/20 text-success' : 'bg-base-300/40 text-base-content/50'}">{i + 1}</span>
												</td>
												<td class="text-center text-[11px] font-mono py-1">{t.group}</td>
												<td class="py-1">
													<span class="flex items-center gap-1.5">
														{#if hasFlag(t.team)}
															<img src={getFlagUrl(t.team, 'sm')} alt="" class="w-4 h-auto rounded-sm flex-shrink-0" />
														{/if}
														<span class="truncate">{t.team}</span>
													</span>
												</td>
												<td class="text-center font-mono tabular-nums py-1">{t.played}</td>
												<td class="text-center font-mono tabular-nums py-1">
													<span class={t.goalDifference > 0 ? 'text-success' : t.goalDifference < 0 ? 'text-error' : 'opacity-60'}>
														{t.goalDifference > 0 ? '+' : ''}{t.goalDifference}
													</span>
												</td>
												<td class="text-center font-mono tabular-nums font-bold py-1">{t.points}</td>
											</tr>
										{/each}
									</tbody>
								</table>
							</div>

							<!-- Cross-group third-place tie warning. The user kept
							     THIS one (and only this one) inside the stacked
							     view because it's the only warning that captures
							     state spanning multiple groups. -->
							{#if thirdPlaceWarnings.length > 0 && allGroupsComplete}
								<div class="alert alert-warning text-xs py-2 mt-3">
									<div>
										<div class="font-semibold mb-0.5">⚠ Tied teams · alphabetical fallback</div>
										{#each thirdPlaceWarnings as w (w.tiedTeams.join('-'))}
											<p class="text-[11px] opacity-90">
												{w.tiedTeams.join(', ')} — tied on points, GD and GF. Third-place teams come from different groups so head-to-head isn't applicable; ranked alphabetically. Adjust scores to change qualification.
											</p>
										{/each}
									</div>
								</div>
							{/if}
						</section>
					{/if}
				</div>
			{:else if activeGroup === 'thirdplace'}
				<!-- Third-place qualifying table. Different shape from the
				     regular group table: 12 teams (3 from each group), an
				     extra "Grp" column, and top-8/bottom-4 highlighting
				     (top 8 advance to R32 per the FIFA 2026 format). -->
				{#if thirdPlaceStandings.length === 0}
					<p class="text-sm text-base-content/50 py-6 text-center">
						Fill in some group predictions to see third-place qualifying.
					</p>
				{:else}
					<div class="overflow-x-auto">
						<table class="w-full text-xs">
							<thead class="text-base-content/40 uppercase tracking-wider">
								<tr>
									<th class="text-left font-normal pb-1 w-6">#</th>
									<th class="text-center font-normal pb-1 w-10">Grp</th>
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
								{#each thirdPlaceStandings as t, i (t.team)}
									<tr class="border-t border-base-content/5 {i < 8 ? 'bg-success/5' : ''}">
										<td class="py-1">
											<span
												class="inline-flex items-center justify-center w-5 h-5 rounded-full text-[10px] font-mono {i < 8
													? 'bg-success/20 text-success'
													: 'bg-base-300/40 text-base-content/50'}">{i + 1}</span
											>
										</td>
										<td class="text-center text-[11px] font-mono py-1">{t.group}</td>
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
					<p class="text-[10px] text-base-content/50 mt-2 uppercase tracking-wider">
						★ Top 8 third-placed teams qualify for the Round of 32 (FIFA 2026 format)
					</p>

					<!-- Third-place tie warning. Gated on `allGroupsComplete`
					     because cross-group ties only crystallise once every
					     group has finished — until then the user could still
					     change the ranking with any group prediction. -->
					{#if thirdPlaceWarnings.length > 0 && allGroupsComplete}
						<div class="alert alert-warning text-xs py-2 mt-3">
							<div>
								<div class="font-semibold mb-0.5">⚠ Tied teams · alphabetical fallback</div>
								{#each thirdPlaceWarnings as w (w.tiedTeams.join('-'))}
									<p class="text-[11px] opacity-90">
										{w.tiedTeams.join(', ')} — tied on points, GD and GF. Third-place
										teams come from different groups so head-to-head isn't applicable;
										ranked alphabetically. Adjust scores to change qualification.
									</p>
								{/each}
							</div>
						</div>
					{/if}
				{/if}
			{:else if groupStandings.length === 0}
				{#if activeGroupFixtures.length === 0}
					<!-- Fixtures still loading — brief skeleton before first fetch -->
					<div class="space-y-2 py-4 animate-pulse">
						{#each Array(4) as _}
							<div class="h-6 bg-base-300/60 rounded w-full"></div>
						{/each}
					</div>
				{:else}
					<p class="text-sm text-base-content/50 py-6 text-center">
						Add a prediction to see the standings update.
					</p>
				{/if}
			{:else}
				<!-- Predicted standings — richer variant migrated from the
				     in-accordion table. Position chip in success/warning/error
				     tone, GD colored by sign, bold Pts. Legend below explains
				     the qualification tones. -->
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
							{#each groupStandings as team, i (team.team)}
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
											{#if hasFlag(team.team)}
												<img
													src={getFlagUrl(team.team, 'sm')}
													alt=""
													class="w-4 h-auto rounded-sm flex-shrink-0"
												/>
											{/if}
											<span class="truncate">{team.team}</span>
										</span>
									</td>
									<td class="text-center font-mono tabular-nums py-1">{team.played}</td>
									<td class="text-center font-mono tabular-nums py-1">{team.won}</td>
									<td class="text-center font-mono tabular-nums py-1">{team.drawn}</td>
									<td class="text-center font-mono tabular-nums py-1">{team.lost}</td>
									<td class="text-center font-mono tabular-nums py-1">
										<span
											class={team.goalDifference > 0
												? 'text-success'
												: team.goalDifference < 0
													? 'text-error'
													: 'opacity-60'}
											>{team.goalDifference > 0 ? '+' : ''}{team.goalDifference}</span
										>
									</td>
									<td class="text-center font-mono tabular-nums font-bold py-1">{team.points}</td>
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

				<!-- Tied-teams warning(s). Migrated from the accordion body so
				     the explanation sits next to the table whose ordering it
				     explains. One alert may contain multiple tied sets when
				     a group has more than one unresolved tie. Gated on
				     `allGroupGamesPredicted` so the warning only appears
				     once every game in the group has a score (saved or
				     unsaved) — until then the user could still break the
				     tie with a future score. -->
				{#if groupWarnings.length > 0 && allGroupGamesPredicted}
					<div class="alert alert-warning text-xs py-2 mt-3">
						<div>
							<div class="font-semibold mb-0.5">⚠ Tied teams in Group {activeGroup}</div>
							{#each groupWarnings as w (w.tiedTeams.join('-'))}
								<p class="text-[11px] opacity-90">
									{w.tiedTeams.join(', ')} — tied on points, GD, GF + head-to-head;
									ranked alphabetically as fallback. Adjust scores to break the tie.
								</p>
							{/each}
						</div>
					</div>
				{/if}
			{/if}
		{:else if activeSection === 'knockout'}
			<KnockoutBracket
				prediction={$workingBracketPrediction}
				groupStandings={standingsMap}
				locked={true}
				phase="phase_1"
			/>
		{:else if activeSection === 'bonus'}
			{@const answered = bonusQuestions.filter((q) => bonusAnswers.get(q.id))}
			<p class="text-sm mb-3">
				You've answered <span class="font-display text-xl text-primary">{answered.length}</span> of
				<span class="font-display text-xl">{bonusQuestions.length}</span> bonus questions.
			</p>
			{#if answered.length === 0}
				<p class="text-sm text-base-content/50">
					Answer your bonus questions on the left for extra points.
				</p>
			{:else}
				<ul class="space-y-2">
					{#each answered as q (q.id)}
						<li class="text-xs">
							<div class="text-base-content/60 truncate">{q.label}</div>
							<div class="font-medium truncate">{bonusAnswers.get(q.id)}</div>
						</li>
					{/each}
				</ul>
			{/if}
		{/if}
	</div>

	<footer
		class="flex-shrink-0 px-4 py-2 border-t border-base-300/60 bg-base-100 text-[10px] text-base-content/40 uppercase tracking-wider"
	>
		Updates live as you predict
	</footer>
</aside>
