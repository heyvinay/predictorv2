<!--
	SimulatorPanel — orchestrator for the what-if bracket simulator.
	Mounted in place of ResultsBracket under the Results page's Bracket tab.

	Flow:
	  1. On mount, fetch simulator status. If the feature is off (and the
	     viewer isn't an admin), render the existing read-only
	     ResultsBracket unchanged — the simulator is fully invisible.
	  2. Otherwise render the read-only wallchart PLUS a "Simulate" toggle.
	     Turning it on switches straight into the interactive bracket — no
	     per-user unlock gate, no daily run cap.
	  3. In interactive mode the user can click open matches to set a
	     hypothetical winner (free, no run spent — `resolveScenario` reruns
	     locally on every pick), use "Fill with my picks" to seed from
	     their own bracket entry, or "Reset to live" to clear overrides.
	  4. "See standings" commits a run (`recordSimulatorRun`, for auditing
	     only) and renders the projected standings table underneath,
	     pinning the viewer's own row.

	Bonus-question scoring, the ceiling readout, and pivotal-match
	highlighting are explicitly OUT of scope for this stage (see task
	description / simulateBracket.ts module docstring).
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import type { BracketPrediction, Fixture } from '$types';
	import type { ScoringRules } from '$lib/types/results';
	import type {
		HypoWinners,
		ProjectedRow,
		SimulatorEntryPicks,
		SimulatorStatus
	} from '$lib/types/simulator';
	import { track } from '$lib/analytics';
	import { ApiResponseError } from '$lib/api/client';
	import {
		getSimulatorBracketPicks,
		getSimulatorStatus,
		recordSimulatorRun
	} from '$lib/api/simulator';
	import { fillFromMyPicks, projectStandings, resolveScenario } from '$lib/utils/simulateBracket';
	// Reuse the leaderboard's canonical naming helpers so the projected
	// standings surface the same "Person — Entry name" (multi-owner) /
	// "Person" (single-owner) rule as /leaderboard's StandingsTable, per
	// the ★ naming-rule invariant in CLAUDE.md.
	import { multiEntryUserIds, rowDisplayName } from '$lib/utils/leaderboardV4';
	import { markSimulatorSeen, simulatorSeen } from '$stores/uiPreferences';
	import ResultsBracket from '$lib/components/results/v4/ResultsBracket.svelte';
	import SimulatorBracket from '$lib/components/results/v4/SimulatorBracket.svelte';

	export let fixtures: Fixture[];
	export let bracketPrediction: BracketPrediction | null;
	export let rules: ScoringRules | null;
	/** The signed-in user's active entry id, used to pin their row in the
	 *  projected-standings table. */
	export let myEntryId: string | null = null;

	// ── Status / gating ────────────────────────────────────────────────────
	let status: SimulatorStatus | null = null;
	let statusLoading = true;
	let simulateOn = false;

	// One-time tooltip on the Simulate toggle. Shown iff the feature is on
	// AND this user hasn't discovered it yet (same `simulatorSeen` flag the
	// rail-nav + Bracket-pill nudges use). Dismissed on any click — either
	// by pressing Simulate (which counts as "found it") or the tooltip's
	// own Got-it button.
	let showTooltip = false;

	onMount(async () => {
		try {
			status = await getSimulatorStatus();
		} catch {
			status = null;
		} finally {
			statusLoading = false;
		}
		// Reaching the Bracket tab IS the discovery event — clear the
		// rail-nav + Bracket-pill nudges immediately, but keep the
		// tooltip visible until they click something so they get one
		// deliberate explainer. Guard on feature visibility so we don't
		// consume the flag when the feature isn't actually surfaced.
		if (status && (status.feature_enabled || status.is_admin)) {
			if (!$simulatorSeen) {
				showTooltip = true;
				markSimulatorSeen();
			}
		}
	});

	function dismissTooltip() {
		showTooltip = false;
	}

	$: featureVisible = !!status && (status.feature_enabled || status.is_admin);

	// ── Bracket picks (lazy — only fetched once Simulate actually turns on) ──
	let picksEntries: SimulatorEntryPicks[] = [];
	let picksLoaded = false;
	let picksLoading = false;
	let picksError: string | null = null;

	async function ensurePicksLoaded() {
		if (picksLoaded || picksLoading) return;
		picksLoading = true;
		picksError = null;
		try {
			const resp = await getSimulatorBracketPicks();
			picksEntries = resp.entries;
			picksLoaded = true;
		} catch (e) {
			picksError = e instanceof Error ? e.message : 'Could not load pool picks.';
		} finally {
			picksLoading = false;
		}
	}

	function handleToggleSimulate() {
		dismissTooltip();
		if (simulateOn) {
			simulateOn = false;
			return;
		}
		activateSimulator();
	}

	function activateSimulator() {
		simulateOn = true;
		track('simulator_toggled_on');
		void ensurePicksLoaded();
	}

	// ── Hypothetical winners + live scenario resolution ─────────────────────
	let hypoWinners: HypoWinners = new Map();

	$: scenario = resolveScenario(fixtures, hypoWinners);

	$: myPicksByMatch = bracketPrediction
		? (() => {
				const m = new Map<number, string>();
				const allPicks: string[] = [
					...bracketPrediction.round_of_32,
					...bracketPrediction.round_of_16,
					...bracketPrediction.quarter_finals,
					...bracketPrediction.semi_finals,
					...bracketPrediction.final
				];
				// Map each pick to whichever match(es) it currently sits in as
				// a resolved participant, so the chip can show "matches your
				// pick" regardless of what round that team has reached so far.
				for (const [num, match] of scenario.matches) {
					const candidates = [match.home, match.away];
					for (const team of candidates) {
						if (team && allPicks.includes(team)) m.set(num, team);
					}
				}
				return m;
			})()
		: new Map<number, string>();

	function handlePick(e: CustomEvent<{ matchNumber: number; team: string }>) {
		const { matchNumber, team } = e.detail;
		const next = new Map(hypoWinners);
		next.set(matchNumber, team);
		hypoWinners = next;
		// Editing invalidates any previously committed standings snapshot —
		// the user must press "See standings" again to re-commit a run.
		standings = null;
	}

	function handleFillFromMyPicks() {
		if (!bracketPrediction) return;
		hypoWinners = fillFromMyPicks(fixtures, bracketPrediction);
		standings = null;
	}

	function handleResetToLive() {
		hypoWinners = new Map();
		standings = null;
	}

	// ── Commit run + projected standings ─────────────────────────────────────
	let standings: ProjectedRow[] | null = null;
	let commitLoading = false;
	let commitError: string | null = null;

	async function handleSeeStandings() {
		if (!rules) return;
		commitLoading = true;
		commitError = null;
		try {
			await ensurePicksLoaded();
			const freshStatus = await recordSimulatorRun();
			status = freshStatus;
			const adv = rules.advancement;
			standings = projectStandings(picksEntries, scenario.reached, scenario.champion, adv);
			track('simulator_run_committed', {
				picks_count: hypoWinners.size,
				champion_set: !!scenario.champion
			});
		} catch (e) {
			if (e instanceof ApiResponseError && e.status === 403) {
				commitError = "The bracket simulator isn't available right now.";
			} else {
				commitError = e instanceof Error ? e.message : 'Could not run that scenario.';
			}
		} finally {
			commitLoading = false;
		}
	}

	// User's row stays in its natural rank position (no pin at top).
	// It's flagged as `isMine` in the render so the row picks up the gold
	// tint + "You" tag in place — you can see your immediate neighbours
	// on the leaderboard rather than being lifted out of context.
	function isMine(row: ProjectedRow): boolean {
		return row.entry_id === myEntryId;
	}

	// User_ids of anyone owning >1 entry. Reactive on `standings` so it
	// stays valid across commits; computed from the FULL projected board
	// (never a filtered view) so a user's display name can't flip between
	// scenarios — same discipline as the main leaderboard.
	$: multiOwners = standings ? multiEntryUserIds(standings) : new Set<string>();

	function movementSymbol(deltaPos: number): string {
		if (deltaPos > 0) return '▲';
		if (deltaPos < 0) return '▼';
		return '—';
	}

	function movementClass(deltaPos: number): string {
		if (deltaPos > 0) return 'text-success';
		if (deltaPos < 0) return 'text-error';
		return 'text-base-content/50';
	}
</script>

{#if statusLoading}
	<div class="flex justify-center py-16">
		<span class="loading loading-spinner loading-lg text-primary"></span>
	</div>
{:else if !featureVisible}
	<!-- Feature fully hidden — render the existing read-only wallchart. -->
	<ResultsBracket {fixtures} {bracketPrediction} {rules} knockoutScoringEnabled={true} />
{:else}
	<div class="mt-3 flex flex-wrap items-center justify-between gap-3">
		<h2 class="font-display text-lg tracking-wide">
			KNOCKOUT <span class="text-primary">BRACKET</span>
		</h2>
		<div class="flex items-center gap-3">
			<div class="relative">
				<button
					type="button"
					class="btn btn-sm {simulateOn ? 'btn-primary' : 'btn-outline'}"
					on:click={handleToggleSimulate}
				>
					🔮 {simulateOn ? 'Simulating' : 'Simulate'}
				</button>
				{#if showTooltip}
					<!-- One-time intro tooltip. Absolutely positioned so the row
					     layout above stays untouched; a small triangle points at
					     the Simulate button. Dismissed automatically when the
					     user clicks Simulate, or via the ✕ button here. Shown
					     once per user per device (see markSimulatorSeen in
					     onMount). -->
					<div
						class="absolute right-0 top-full z-20 mt-2 w-72 rounded-xl border border-primary/45 bg-base-100 p-3 text-sm shadow-lg"
						role="dialog"
						aria-label="What is Simulate?"
					>
						<span
							class="absolute -top-1.5 right-6 h-3 w-3 rotate-45 border-l border-t border-primary/45 bg-base-100"
							aria-hidden="true"
						></span>
						<div class="flex items-start gap-2">
							<div class="flex-1">
								<div class="font-display text-xs uppercase tracking-[0.14em] text-primary">New</div>
								<p class="mt-1 leading-snug text-base-content/85">
									Play the rest of the bracket — pick winners of unplayed matches and see how
									the pool re-ranks.
								</p>
							</div>
							<button
								type="button"
								class="btn btn-ghost btn-xs -mt-1 -mr-1"
								on:click={dismissTooltip}
								aria-label="Dismiss"
							>✕</button>
						</div>
					</div>
				{/if}
			</div>
		</div>
	</div>

	<!-- Helper strip — mirrors the group-standings OverlayBanner pattern:
	     gold-tinted primer when the tool is on, muted teaser when it's off.
	     Gives the user a one-sentence read on what the toggle does before
	     they touch it, and reassures them nothing they do here is permanent. -->
	{#if simulateOn}
		<div
			class="mt-3 flex flex-wrap items-center gap-3 rounded-xl border border-primary/30 bg-primary/10 px-4 py-2.5 text-sm"
			role="status"
		>
			<span class="inline-flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-md bg-primary/20 text-xs font-bold text-primary" aria-hidden="true">
				🔮
			</span>
			<p class="flex-1 text-base-content/90">
				<strong class="text-primary">What-if mode.</strong> Pick winners of the unplayed
				matches — they'll flow through to the next round. Hit <strong>See standings</strong> to
				re-rank the pool under your scenario. Nothing you do here changes your entry.
				<span class="mt-1 block text-base-content/60"
					>This is a rough estimate for fun, not an official projection — it can be wrong.
					Don't rely on it.</span
				>
			</p>
		</div>
	{:else}
		<div
			class="mt-3 flex flex-wrap items-center gap-3 rounded-xl border border-base-300 bg-base-200 px-4 py-2 text-sm"
			role="status"
		>
			<p class="flex-1 text-base-content/60">
				<strong class="text-base-content/80">Play out the rest of the bracket.</strong>
				Hit <em>Simulate</em> to pick winners for the unplayed matches and see how the pool
				re-ranks. Read-only until you turn it on.
			</p>
		</div>
	{/if}

	{#if !simulateOn}
		<ResultsBracket {fixtures} {bracketPrediction} {rules} knockoutScoringEnabled={true} />
	{:else}
		<div class="stadium-card no-glow mt-3 p-4 lg:p-6">
			<div class="mb-4 flex flex-wrap items-center gap-2">
				<button
					type="button"
					class="btn btn-outline btn-sm"
					disabled={!bracketPrediction}
					on:click={handleFillFromMyPicks}
				>
					Fill with my picks
				</button>
				<button type="button" class="btn btn-ghost btn-sm" on:click={handleResetToLive}>
					Reset to live
				</button>
				<div class="flex-1"></div>
				<button
					type="button"
					class="btn btn-primary btn-sm"
					disabled={commitLoading}
					on:click={handleSeeStandings}
				>
					{commitLoading ? 'Crunching…' : 'See standings'}
				</button>
			</div>

			{#if picksError}
				<div class="alert alert-warning text-sm mb-3">{picksError}</div>
			{/if}

			<SimulatorBracket {fixtures} resolved={scenario} {myPicksByMatch} on:pick={handlePick} />

			{#if commitError}
				<div
					class="mt-4 rounded-xl border border-error/40 bg-error/10 px-4 py-3 text-sm text-error"
					role="status"
				>
					{commitError}
				</div>
			{/if}

			{#if standings}
				<!-- Projected standings — visual grammar mirrors StandingsTable
				     from the main /leaderboard page (rounded base-200 shell,
				     sticky uppercase column-header band, thin border-t grid
				     rows, "your entry" pin section) so users recognise the
				     scoreboard idiom. Columns are simpler here — rank / entry /
				     points (with was) / move — since the simulator only touches
				     KO advancement. -->
				<div class="mt-6 border-t border-base-content/10 pt-5">
					<h3 class="font-display text-base tracking-wide mb-1">
						PROJECTED <span class="text-primary">STANDINGS</span>
					</h3>
					<p class="text-xs text-base-content/55 mb-3">
						Includes group-stage points, bonus questions, and knockout advancement under this
						scenario. It's a rough estimate for fun, not an official projection — it can be
						wrong, so don't rely on it.
					</p>

					<div
						class="overflow-hidden rounded-xl border border-base-300/60 bg-base-200"
						role="table"
						aria-label="Projected pool standings"
					>
						<!-- Sticky column-header band, matching StandingsTable. -->
						<div
							class="sticky top-0 z-10 grid items-center gap-2 bg-base-300/40 px-3 py-2 backdrop-blur
								grid-cols-[44px_minmax(0,1fr)_92px_60px] min-[880px]:gap-3 min-[880px]:px-4 min-[880px]:grid-cols-[64px_minmax(0,1.6fr)_120px_80px]"
							role="row"
						>
							<span class="sp-head" role="columnheader">#</span>
							<span class="sp-head text-left" role="columnheader">Entry</span>
							<span class="sp-head text-right" role="columnheader">Points</span>
							<span class="sp-head text-right" role="columnheader">Move</span>
						</div>

						<!-- Rows stay in their natural rank order — the user's row is
						     NOT pinned to the top. It's flagged via `isMine()` so the
						     row picks up a soft gold tint + "You" chip in place, so
						     the user can see the entries immediately above and below
						     them in the same view. -->
						{#each standings as row, i (row.entry_id)}
							{@const mine = isMine(row)}
							<div
								class="grid items-center gap-2 px-3 py-2 border-t transition-colors min-[880px]:gap-3 min-[880px]:px-4
									grid-cols-[44px_minmax(0,1fr)_92px_60px] min-[880px]:grid-cols-[64px_minmax(0,1.6fr)_120px_80px]
									{mine ? 'border-primary/50 bg-primary/10' : 'border-base-300/40 hover:bg-base-300/25'}"
								role="row"
								aria-label={mine ? 'Your entry' : undefined}
							>
								<span
									class="font-mono text-sm tabular-nums {mine ? 'font-bold text-primary' : 'font-semibold text-base-content/75'}"
									role="cell"
								>
									#{row.newPos}
								</span>
								<span class="flex items-center gap-2 min-w-0" role="cell">
									<span class="text-sm truncate {mine ? 'font-semibold' : ''}"
									>{rowDisplayName(row, multiOwners)}</span
								>
									{#if mine}
										<span
											class="flex-shrink-0 rounded-full bg-primary/25 px-1.5 py-0.5 text-[9px] font-mono font-bold uppercase tracking-[0.14em] text-primary"
											aria-hidden="true"
										>You</span>
									{/if}
								</span>
								<div class="text-right font-mono tabular-nums" role="cell">
									<span class="text-sm {mine ? 'font-bold' : ''}">{row.newTotal}</span>
									<span class="text-[10.5px] text-base-content/40 ml-1">was {row.oldTotal}</span>
								</div>
								<div class="text-right font-mono text-xs tabular-nums {movementClass(row.deltaPos)}" role="cell">
									{movementSymbol(row.deltaPos)} {Math.abs(row.deltaPos)}
								</div>
							</div>
						{/each}
					</div>
				</div>
			{/if}
		</div>
	{/if}
{/if}

<style>
	/* Column-header cell — mirrors StandingsTable's HEAD_CLASS token. */
	:global(.sp-head) {
		font-size: 9.5px;
		font-weight: 800;
		letter-spacing: 0.12em;
		text-transform: uppercase;
		color: hsl(var(--bc) / 0.55);
	}

	@media (prefers-reduced-motion: reduce) {
		:global(.sim-chip) {
			transition: none !important;
		}
	}
</style>
