<!--
	SimulatorPanel — orchestrator for the what-if bracket simulator
	(v2.194.x core stage). Mounted in place of ResultsBracket under the
	Results page's Bracket tab.

	Flow:
	  1. On mount, fetch simulator status. If the feature is off (and the
	     viewer isn't an admin), render the existing read-only
	     ResultsBracket unchanged — the simulator is fully invisible.
	  2. Otherwise render the read-only wallchart PLUS a "Simulate" toggle
	     + a run-counter chip.
	  3. Turning Simulate ON while locked (non-admin, not yet unlocked)
	     opens the SimulatorGameShow trivia gate. A correct answer flips
	     `unlocked` and the panel switches into the interactive bracket.
	     Admins and already-unlocked users skip the gate entirely.
	  4. In interactive mode the user can click open matches to set a
	     hypothetical winner (free, no run spent — `resolveScenario` reruns
	     locally on every pick), use "Fill with my picks" to seed from
	     their own bracket entry, or "Reset to live" to clear overrides.
	  5. "See standings" commits a run (`recordSimulatorRun`) and renders
	     the projected standings table underneath, pinning the viewer's
	     own row.

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
	import ResultsBracket from '$lib/components/results/v4/ResultsBracket.svelte';
	import SimulatorBracket from '$lib/components/results/v4/SimulatorBracket.svelte';
	import SimulatorGameShow from '$lib/components/results/v4/SimulatorGameShow.svelte';

	export let fixtures: Fixture[];
	export let bracketPrediction: BracketPrediction | null;
	export let rules: ScoringRules | null;
	/** The signed-in user's active entry id, used to pin their row in the
	 *  projected-standings table. */
	export let myEntryId: string | null = null;

	// ── Status / gating ────────────────────────────────────────────────────
	let status: SimulatorStatus | null = null;
	let statusLoading = true;
	let gameShowOpen = false;
	let simulateOn = false;

	onMount(async () => {
		try {
			status = await getSimulatorStatus();
		} catch {
			status = null;
		} finally {
			statusLoading = false;
		}
	});

	$: featureVisible = !!status && (status.feature_enabled || status.is_admin);
	$: isUnlocked = !!status && (status.is_admin || status.unlocked);

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
		if (simulateOn) {
			simulateOn = false;
			return;
		}
		if (!isUnlocked) {
			gameShowOpen = true;
			return;
		}
		activateSimulator();
	}

	function activateSimulator() {
		simulateOn = true;
		track('simulator_toggled_on');
		void ensurePicksLoaded();
	}

	function handleUnlocked() {
		gameShowOpen = false;
		if (status) status = { ...status, unlocked: true };
		activateSimulator();
	}

	function handleGameShowClose() {
		gameShowOpen = false;
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
	let commitErrorKind: 'locked' | 'capped' | 'other' | null = null;

	async function handleSeeStandings() {
		if (!rules) return;
		commitLoading = true;
		commitError = null;
		commitErrorKind = null;
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
				commitErrorKind = 'locked';
				commitError = 'Answer the trivia challenge to unlock the bracket simulator.';
			} else if (e instanceof ApiResponseError && e.status === 429) {
				commitErrorKind = 'capped';
				commitError = "You've used all your runs today — resets after midnight UTC.";
			} else {
				commitErrorKind = 'other';
				commitError = e instanceof Error ? e.message : 'Could not run that scenario.';
			}
		} finally {
			commitLoading = false;
		}
	}

	$: myRow = standings?.find((row) => row.entry_id === myEntryId) ?? null;
	$: otherRows = standings?.filter((row) => row.entry_id !== myEntryId) ?? [];

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

	$: runsLabel = !status
		? ''
		: status.is_admin || status.runs_remaining === null
			? 'Unlimited'
			: `${status.runs_remaining} / ${status.cap} runs left today`;
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
			{#if simulateOn}
				<span class="rounded-badge bg-primary/15 px-2.5 py-1 text-[11px] font-mono uppercase tracking-[0.12em] text-primary">
					{runsLabel}
				</span>
			{/if}
			{#if status?.is_admin}
				<!-- Admins are auto-unlocked and skip the gate, so they never
				     see the unlock quiz in normal use. This lets them open it
				     on demand to QA the game show. -->
				<button
					type="button"
					class="btn btn-ghost btn-sm"
					on:click={() => (gameShowOpen = true)}
					title="Preview the unlock quiz (admin only)"
				>
					Preview quiz
				</button>
			{/if}
			<button
				type="button"
				class="btn btn-sm {simulateOn ? 'btn-primary' : 'btn-outline'}"
				on:click={handleToggleSimulate}
			>
				🔮 {simulateOn ? 'Simulating' : 'Simulate'}
			</button>
		</div>
	</div>

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
					class="mt-4 rounded-xl border px-4 py-3 text-sm
						{commitErrorKind === 'capped'
						? 'border-warning/40 bg-warning/10 text-warning-text'
						: 'border-error/40 bg-error/10 text-error'}"
					role="status"
				>
					{commitError}
				</div>
			{/if}

			{#if standings}
				<div class="mt-6 border-t border-base-content/10 pt-5">
					<h3 class="font-display text-base tracking-wide mb-1">
						PROJECTED <span class="text-primary">STANDINGS</span>
					</h3>
					{#if !scenario.champion}
						<p class="text-xs text-base-content/55 mb-3">
							Pick a champion in the Final to include bonus questions in a future update — for now this
							preview covers knockout advancement points only.
						</p>
					{:else}
						<p class="text-xs text-base-content/55 mb-3">
							Knockout advancement points only — group-stage points and bonus questions are unchanged.
						</p>
					{/if}

					{#if myRow}
						<div
							class="mb-3 rounded-xl border-2 border-primary bg-primary/10 px-4 py-3 flex items-center gap-3"
						>
							<span class="font-mono text-lg font-bold text-primary w-8 text-center">
								#{myRow.newPos}
							</span>
							<div class="flex-1 min-w-0">
								<div class="font-semibold truncate">{myRow.entry_name}</div>
								<div class="text-xs text-base-content/55">was #{myRow.oldPos} · {myRow.oldTotal} pts</div>
							</div>
							<div class="text-right">
								<div class="font-mono font-bold">{myRow.newTotal} pts</div>
								<div class="text-xs font-mono {movementClass(myRow.deltaPos)}">
									{movementSymbol(myRow.deltaPos)} {Math.abs(myRow.deltaPos)}
								</div>
							</div>
						</div>
					{/if}

					<div class="overflow-x-auto">
						<table class="table table-sm">
							<thead>
								<tr class="text-[11px] uppercase tracking-[0.1em] text-base-content/50">
									<th>Rank</th>
									<th>Entry</th>
									<th class="text-right">Points</th>
									<th class="text-right">Move</th>
								</tr>
							</thead>
							<tbody>
								{#each otherRows as row (row.entry_id)}
									<tr>
										<td class="font-mono">#{row.newPos}</td>
										<td class="truncate max-w-[200px]">{row.entry_name}</td>
										<td class="text-right font-mono">
											{row.newTotal}
											<span class="text-base-content/40 text-xs">(was {row.oldTotal})</span>
										</td>
										<td class="text-right font-mono {movementClass(row.deltaPos)}">
											{movementSymbol(row.deltaPos)} {Math.abs(row.deltaPos)}
										</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				</div>
			{/if}
		</div>
	{/if}
{/if}

<SimulatorGameShow bind:open={gameShowOpen} on:unlocked={handleUnlocked} on:close={handleGameShowClose} />

<style>
	@media (prefers-reduced-motion: reduce) {
		:global(.sim-chip) {
			transition: none !important;
		}
	}
</style>
