<!--
	GroupAccordion — collapsible section for one group's fixtures.

	Header:
	    Group X   [flag][flag][flag][flag]   [⚠ Tie break needed]   N/M   ▾
	    └─ chevron rotates 180° on open
	    └─ tie-break chip appears only when the parent says so
	       (all games predicted AND standings have an unresolved tie)
	    └─ progress badge: ghost (0), warning (1..N-1), success (N/N)
	    └─ flag cluster hides on mobile (<sm:640px) to make room; the
	       tie chip stays visible since it's an actionable alert

	Body (rendered only when `open` is true):
	    [tied-teams warning if any]
	    <FixtureCard ... />  × all fixtures, sorted by kickoff time
	    ...

	Date subheaders were removed when fixtures became self-describing
	cards (each card carries its own date + time + match # in the header).

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
	import type { FixturesByGroup } from '$lib/types';
	import FixtureCard from './FixtureCard.svelte';

	export let group: FixturesByGroup;
	export let open: boolean = false;
	export let editable: boolean = false;
	export let getPrediction: (fixtureId: string) => { home: number; away: number } | null = () =>
		null;
	export let onScore: (fixtureId: string, home: number, away: number) => void = () => {};
	export let onToggle: () => void = () => {};
	/**
	 * True when the parent has detected an unresolved tie in this group's
	 * standings AND every fixture has a (saved or unsaved) prediction.
	 * Renders a small "⚠ Tie break needed" chip in the header so the user
	 * sees the call-to-action even when the accordion is collapsed.
	 */
	export let tieBreakNeeded: boolean = false;
	/**
	 * Called when the user taps the tie-chip or the "View live standings"
	 * link inside the accordion body. The parent opens the StandingsPanel
	 * drawer focused on this group. Mobile-only path (the docked desktop
	 * panel is always visible at ≥xl viewports).
	 */
	export let onOpenStandings: () => void = () => {};

	// Unique home teams (in fixture order). In a 4-team group's 6 matches,
	// the four teams each appear as "home" in ~3 of the 6, so the
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

	// Tri-state progress badge. Ghost for untouched, warning while in
	// progress, success once every fixture has a prediction.
	$: badgeClass =
		totalCount > 0 && predictedCount === totalCount
			? 'badge-success'
			: predictedCount > 0
				? 'badge-warning'
				: 'badge-ghost';

	// Fixtures sorted by kickoff time. Single flat list — date subheaders
	// were removed when fixtures became self-describing FixtureCards.
	$: sortedFixtures = [...group.fixtures].sort(
		(a, b) => new Date(a.kickoff).getTime() - new Date(b.kickoff).getTime()
	);
</script>

<div class="group-accordion rounded-xl bg-base-200/30 overflow-hidden">
	<!-- Header row. Non-button wrapper so the chip CAN be a sibling button
	     (nested <button> is invalid HTML). Three click regions inside:
	       1. Main toggle (group name + flag cluster + spacer)
	       2. Tie-chip (when present) — opens the standings drawer
	       3. Trailing toggle (badge + chevron) — also toggles the body -->
	<div class="flex items-center gap-3 w-full px-4 py-3 hover:bg-base-300/30 min-h-12">
		<!-- 1. Main toggle: group name + flag cluster + mobile spacer -->
		<button
			type="button"
			class="flex-1 flex items-center gap-3 min-w-0 text-left"
			on:click={onToggle}
			aria-expanded={open}
			aria-controls="group-{group.group}-body"
		>
			<span class="font-display font-bold text-base sm:text-lg whitespace-nowrap">
				Group {group.group}
			</span>

			<!-- Flag cluster: deduplicated home teams. `flex-1` claims the
			     middle of the header so trailing content sits right. Hidden
			     below sm: (640px) so the chip + badge still fit on phones. -->
			<div class="hidden sm:flex items-center gap-1 flex-1 min-w-0 overflow-hidden">
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

			<!-- Mobile-only spacer. Takes over the `flex-1` role when the
			     flag cluster is hidden, so badge + chevron stay right-aligned. -->
			<span class="flex-1 sm:hidden" aria-hidden="true"></span>
		</button>

		<!-- 2. Standings-trigger chip. Single slot, two label variants:
		       - Tied  → yellow "⚠ Tie break needed" (visible on all
		                  viewports; on desktop the docked panel also
		                  shows the warning, so the tap is a no-op there)
		       - Not tied → neutral "View Table" (mobile only — desktop
		                    has the docked panel so a per-group trigger
		                    would be redundant)
		     Both call onOpenStandings; the parent opens the drawer
		     focused on this group via activeGroupPill. -->
		{#if tieBreakNeeded}
			<button
				type="button"
				class="badge badge-warning badge-sm gap-1 font-medium whitespace-nowrap hover:brightness-110 transition-[filter]"
				on:click={onOpenStandings}
				title="View standings — at least two teams tied on points, GD, GF + head-to-head"
			>⚠ Tie break needed</button>
		{:else}
			<button
				type="button"
				class="badge badge-ghost badge-sm gap-1 font-medium whitespace-nowrap xl:hidden hover:brightness-110 transition-[filter]"
				on:click={onOpenStandings}
				title="View live standings for this group"
			>View Table</button>
		{/if}

		<!-- 3. Trailing toggle: badge + chevron. Also toggles the body so
		     the chevron remains a natural tap target. `tabindex="-1"` so
		     keyboard users don't hit two tabs for the same toggle action. -->
		<button
			type="button"
			class="flex items-center gap-3"
			on:click={onToggle}
			aria-label="Toggle Group {group.group}"
			tabindex="-1"
		>
			<!-- Tri-state completion badge: ghost (0/M), warning (1..M-1/M),
			     success (M/M). -->
			<span class="badge badge-sm {badgeClass} font-mono tabular-nums">
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
	</div>

	<!-- Body (only when open) -->
	{#if open}
		<div id="group-{group.group}-body" transition:slide={{ duration: 200, easing: cubicOut }}>
			<!-- Tied-teams warning moved to the StandingsPanel sidebar, where
			     it sits next to the table whose ordering it explains. The
			     accordion is now strictly a fixture editor. -->

			<!-- Fixture cards. Each carries its own date + time + match # in
			     the card header, so no surrounding date subheaders are
			     needed. Responsive grid: 1 column on small screens, 2
			     columns from md: (≥768px) up — at that width the wizard
			     column is wide enough that side-by-side cards stop
			     looking sparse and don't compress the stepper. `gap-3`
			     instead of `space-y-3` so column gap works too. -->
			<div class="px-3 pt-1 pb-3 grid grid-cols-1 md:grid-cols-2 gap-2">
				{#each sortedFixtures as f (f.id)}
					<FixtureCard
						fixture={f}
						prediction={getPrediction(f.id)}
						editable={editable && !f.is_locked}
						onScore={(home, away) => onScore(f.id, home, away)}
					/>
				{/each}
			</div>

			<!-- Body link removed — the standings trigger now lives in the
			     accordion header as a "View Table" / "⚠ Tie break needed"
			     chip (single slot, two label variants). Single CTA, one
			     spatial home. -->
		</div>
	{/if}
</div>
