<script lang="ts">
	// Score Sync tab — manual escape hatch for the Football-Data.org sync
	// (the background scheduler runs every 60s during match windows), plus
	// the fixtures table with INLINE EDITING (v2.162.0): the admin can
	// enter match scores by hand (any fixture) and seed team names into
	// knockout fixtures. Two jobs:
	//   1. dev-test vehicle — simulate a tournament and watch points flow;
	//   2. production escape hatch when the API fails, lags, or serves a
	//      wrong score mid-tournament.
	//
	// Manual saves set `verified: true` by default, which LOCKS the score
	// against the API sync (score_sync skips verified rows) — a manual
	// correction survives the 60-second scheduler. Un-tick "verified" in
	// the editor to hand control back to the API.
	import { onDestroy, onMount } from 'svelte';
	import { syncScores, type SyncScoresResponse } from '$lib/api/admin';
	import { getAllFixtures, updateFixture } from '$lib/api/fixtures';
	import { updateScore } from '$lib/api/scores';
	import { pageTitle } from '$lib/stores/pageTitle';
	import type { Fixture } from '$types';

	let fixtures: Fixture[] = [];
	let fixturesLoading = false;
	let fixturesError: string | null = null;

	let syncing = false;
	let syncResult: SyncScoresResponse | null = null;
	let syncError: string | null = null;
	let syncedAt: Date | null = null;

	async function loadFixtures() {
		fixturesLoading = true;
		fixturesError = null;
		try {
			const rows = await getAllFixtures();
			// Order: kickoff ascending. Mirrors the order admins read in the
			// Football-Data.org dashboard so cross-checking is one-to-one.
			fixtures = [...rows].sort((a, b) => a.kickoff.localeCompare(b.kickoff));
		} catch (e) {
			fixturesError = e instanceof Error ? e.message : 'Failed to load fixtures';
		} finally {
			fixturesLoading = false;
		}
	}

	async function handleSyncScores() {
		syncing = true;
		syncError = null;
		try {
			syncResult = await syncScores();
			syncedAt = new Date();
			// Refresh the table so the new scores appear immediately.
			await loadFixtures();
		} catch (e) {
			syncError = e instanceof Error ? e.message : 'Score sync failed';
		} finally {
			syncing = false;
		}
	}

	function formatKickoff(iso: string): string {
		const d = new Date(iso);
		return d.toLocaleString(undefined, {
			day: 'numeric',
			month: 'short',
			hour: '2-digit',
			minute: '2-digit'
		});
	}

	function scoreCell(fx: Fixture): string {
		if (!fx.score) return '—';
		return `${fx.score.home_score} – ${fx.score.away_score}`;
	}

	function statusBadgeClass(status: string): string {
		switch (status) {
			case 'finished':
				return 'badge-success';
			case 'live':
			case 'in_play':
				return 'badge-error';
			case 'halftime':
				return 'badge-warning';
			case 'postponed':
			case 'cancelled':
				return 'badge-ghost';
			default:
				return 'badge-ghost';
		}
	}

	// ---- Inline editor (v2.162.0) -----------------------------------------
	let editingId: string | null = null;
	let eHome: number | null = null;
	let eAway: number | null = null;
	let eEt = false; // "went to extra time / penalties" toggle
	let eHomeEt: number | null = null;
	let eAwayEt: number | null = null;
	let eHomePens: number | null = null;
	let eAwayPens: number | null = null;
	let eHomeTeam = '';
	let eAwayTeam = '';
	let eVerified = true;
	let saving = false;
	let editError: string | null = null;
	let confirmOpen = false;

	$: editingFixture = fixtures.find((f) => f.id === editingId) ?? null;
	$: editingKnockout = editingFixture ? editingFixture.stage !== 'group' : false;
	$: scoreEntered = eHome !== null && eAway !== null;
	$: teamsChanged =
		editingKnockout &&
		editingFixture !== null &&
		eHomeTeam.trim().length > 0 &&
		eAwayTeam.trim().length > 0 &&
		(eHomeTeam.trim() !== editingFixture.home_team ||
			eAwayTeam.trim() !== editingFixture.away_team);

	function startEdit(fx: Fixture) {
		editingId = fx.id;
		editError = null;
		eHome = fx.score?.home_score ?? null;
		eAway = fx.score?.away_score ?? null;
		eHomeEt = fx.score?.home_score_et ?? null;
		eAwayEt = fx.score?.away_score_et ?? null;
		eHomePens = fx.score?.home_penalties ?? null;
		eAwayPens = fx.score?.away_penalties ?? null;
		eEt = eHomeEt !== null || eHomePens !== null;
		eHomeTeam = fx.home_team;
		eAwayTeam = fx.away_team;
		// Manual entries default to verified (locked against the API sync);
		// existing scores keep their current flag.
		eVerified = fx.score?.verified ?? true;
	}

	function cancelEdit() {
		editingId = null;
		confirmOpen = false;
		editError = null;
	}

	function requestSave() {
		editError = null;
		if (!editingFixture) return;

		if (!scoreEntered && !teamsChanged) {
			editError = 'Nothing to save — enter a score or change the teams.';
			return;
		}

		if (scoreEntered && editingKnockout) {
			// A level knockout result can't advance anyone: Score.outcome
			// resolves penalties → ET → regular time, and the advancement
			// logic needs a 1/2 winner. Force the admin to break the tie.
			const finalHome = eEt && eHomeEt !== null ? eHomeEt : eHome;
			const finalAway = eEt && eAwayEt !== null ? eAwayEt : eAway;
			const pensDecide =
				eEt && eHomePens !== null && eAwayPens !== null && eHomePens !== eAwayPens;
			if (finalHome === finalAway && !pensDecide) {
				editError =
					'Level knockout score — add extra-time scores or penalties so a winner can be resolved.';
				return;
			}
		}

		confirmOpen = true;
	}

	async function confirmSave() {
		if (!editingFixture) return;
		saving = true;
		editError = null;
		try {
			if (teamsChanged) {
				await updateFixture(editingFixture.id, {
					home_team: eHomeTeam.trim(),
					away_team: eAwayTeam.trim()
				});
			}
			if (scoreEntered && eHome !== null && eAway !== null) {
				await updateScore(editingFixture.id, {
					home_score: eHome,
					away_score: eAway,
					home_score_et: eEt ? eHomeEt : null,
					away_score_et: eEt ? eAwayEt : null,
					home_penalties: eEt ? eHomePens : null,
					away_penalties: eEt ? eAwayPens : null,
					verified: eVerified
				});
			}
			await loadFixtures();
			editingId = null;
			confirmOpen = false;
		} catch (e) {
			confirmOpen = false;
			editError = e instanceof Error ? e.message : 'Save failed';
		} finally {
			saving = false;
		}
	}

	onMount(async () => {
		pageTitle.set('Score Sync · Football-Data.org');
		await loadFixtures();
	});

	onDestroy(() => {
		pageTitle.set('');
	});
</script>

<svelte:head>
	<title>Score Sync · Admin · Predictor v2</title>
</svelte:head>

<div class="container mx-auto mobile-padding py-6 space-y-6">
	<!-- Sync card -->
	<section class="rounded-xl border bg-base-200 shadow-card p-5">
		<h2 class="text-lg font-display tracking-wide mb-3">
			Score Sync
			<span class="text-xs text-base-content/40">· Football-Data.org</span>
		</h2>
		{#if syncError}<div class="alert alert-error text-sm mb-3">{syncError}</div>{/if}
		{#if syncResult}
			<div class="mb-3 text-sm">
				<div>Last sync: <b>{syncedAt?.toLocaleTimeString() ?? ''}</b></div>
				<div class="flex gap-2 mt-1 flex-wrap">
					<span class="badge badge-success">{syncResult.synced} created</span>
					<span class="badge badge-ghost">{syncResult.updated} updated</span>
					{#if syncResult.skipped_verified > 0}
						<span class="badge badge-ghost" title="Admin-verified scores are locked against the API sync">
							🔒 {syncResult.skipped_verified} skipped (verified)
						</span>
					{/if}
					{#if syncResult.errors.length > 0}
						<span class="badge badge-error">{syncResult.errors.length} errors</span>
					{/if}
				</div>
				{#if syncResult.errors.length > 0}
					<div class="mt-2 text-xs text-error">
						{#each syncResult.errors as err}
							<div>• {err}</div>
						{/each}
					</div>
				{/if}
			</div>
		{/if}
		<p class="text-xs text-base-content/50 mb-3">
			The background scheduler runs every 60s during match windows; this is the manual
			escape hatch. After syncing, scroll down to verify the new scores landed on the
			right fixtures.
		</p>
		<button
			class="btn btn-primary btn-sm"
			type="button"
			on:click={handleSyncScores}
			disabled={syncing}
		>
			{syncing ? 'Syncing…' : 'Sync scores now'}
		</button>
	</section>

	<!-- Full fixtures table -->
	<section class="rounded-xl border bg-base-200 shadow-card p-5">
		<h2 class="text-lg font-display tracking-wide mb-1">
			Fixtures
			<span class="text-xs text-base-content/40">
				{#if !fixturesLoading}· {fixtures.length} total{/if}
			</span>
		</h2>
		<p class="text-xs text-base-content/50 mb-3">
			Edit a row to enter a result by hand (it marks the match finished and updates the
			leaderboard) or to seed team names into a knockout fixture. Manual scores are
			🔒 verified by default — the API sync won't overwrite them.
		</p>
		{#if fixturesError}<div class="alert alert-error text-sm mb-3">{fixturesError}</div>{/if}
		{#if fixturesLoading}
			<p class="text-sm text-base-content/50">Loading fixtures…</p>
		{:else if fixtures.length === 0}
			<p class="text-sm text-base-content/50">No fixtures.</p>
		{:else}
			<div class="overflow-x-auto">
				<table class="table table-sm w-full">
					<thead>
						<tr class="text-left text-xs uppercase tracking-wide text-base-content/55">
							<th>Stage</th>
							<th>Group</th>
							<th>Kickoff</th>
							<th>Home</th>
							<th class="text-center">Score</th>
							<th>Away</th>
							<th>Status</th>
							<th></th>
						</tr>
					</thead>
					<tbody>
						{#each fixtures as fx (fx.id)}
							<tr class="border-t border-base-300/40">
								<td class="font-mono text-xs uppercase">{fx.stage}</td>
								<td class="font-mono text-xs">{fx.group ?? '—'}</td>
								<td class="text-xs whitespace-nowrap">{formatKickoff(fx.kickoff)}</td>
								<td class="text-sm">{fx.home_team}</td>
								<td class="text-sm text-center font-mono whitespace-nowrap">
									{scoreCell(fx)}
									{#if fx.score?.verified}
										<span title="Admin-verified — the API sync won't overwrite this score">🔒</span>
									{/if}
								</td>
								<td class="text-sm">{fx.away_team}</td>
								<td>
									<span class="badge badge-xs {statusBadgeClass(fx.status)}">
										{fx.status}
									</span>
								</td>
								<td class="text-right">
									{#if editingId === fx.id}
										<button class="btn btn-ghost btn-xs" type="button" on:click={cancelEdit}>
											Cancel
										</button>
									{:else}
										<button
											class="btn btn-ghost btn-xs"
											type="button"
											on:click={() => startEdit(fx)}
											disabled={editingId !== null}
										>
											Edit
										</button>
									{/if}
								</td>
							</tr>
							{#if editingId === fx.id}
								<tr class="border-t border-base-300/40 bg-base-300/30">
									<td colspan="8" class="p-4">
										<div class="space-y-3">
											{#if editError}
												<div class="alert alert-error text-sm py-2">{editError}</div>
											{/if}

											{#if fx.stage !== 'group'}
												<!-- Knockout team seeding -->
												<div class="flex flex-wrap items-end gap-3">
													<div>
														<label class="label py-0" for="home-team-{fx.id}">
															<span class="label-text text-xs">Home team</span>
														</label>
														<input
															id="home-team-{fx.id}"
															class="input input-bordered input-sm w-44"
															type="text"
															bind:value={eHomeTeam}
														/>
													</div>
													<div>
														<label class="label py-0" for="away-team-{fx.id}">
															<span class="label-text text-xs">Away team</span>
														</label>
														<input
															id="away-team-{fx.id}"
															class="input input-bordered input-sm w-44"
															type="text"
															bind:value={eAwayTeam}
														/>
													</div>
													<p class="text-xs text-base-content/50 pb-1">
														Seeding teams into a knockout round pays "reached stage"
														points immediately.
													</p>
												</div>
											{/if}

											<!-- Score entry -->
											<div class="flex flex-wrap items-end gap-3">
												<div>
													<label class="label py-0" for="home-score-{fx.id}">
														<span class="label-text text-xs">{eHomeTeam || fx.home_team} goals</span>
													</label>
													<input
														id="home-score-{fx.id}"
														class="input input-bordered input-sm w-20 text-center font-mono"
														type="number"
														min="0"
														max="15"
														bind:value={eHome}
													/>
												</div>
												<span class="pb-2 font-mono text-base-content/55">–</span>
												<div>
													<label class="label py-0" for="away-score-{fx.id}">
														<span class="label-text text-xs">{eAwayTeam || fx.away_team} goals</span>
													</label>
													<input
														id="away-score-{fx.id}"
														class="input input-bordered input-sm w-20 text-center font-mono"
														type="number"
														min="0"
														max="15"
														bind:value={eAway}
													/>
												</div>

												{#if fx.stage !== 'group'}
													<label class="label cursor-pointer gap-2 pb-1">
														<input type="checkbox" class="checkbox checkbox-sm" bind:checked={eEt} />
														<span class="label-text text-xs">Went to extra time / penalties</span>
													</label>
												{/if}
											</div>

											{#if fx.stage !== 'group' && eEt}
												<div class="flex flex-wrap items-end gap-3">
													<div>
														<label class="label py-0" for="home-et-{fx.id}">
															<span class="label-text text-xs">After ET (home)</span>
														</label>
														<input
															id="home-et-{fx.id}"
															class="input input-bordered input-sm w-20 text-center font-mono"
															type="number"
															min="0"
															max="15"
															bind:value={eHomeEt}
														/>
													</div>
													<div>
														<label class="label py-0" for="away-et-{fx.id}">
															<span class="label-text text-xs">After ET (away)</span>
														</label>
														<input
															id="away-et-{fx.id}"
															class="input input-bordered input-sm w-20 text-center font-mono"
															type="number"
															min="0"
															max="15"
															bind:value={eAwayEt}
														/>
													</div>
													<div>
														<label class="label py-0" for="home-pens-{fx.id}">
															<span class="label-text text-xs">Pens (home)</span>
														</label>
														<input
															id="home-pens-{fx.id}"
															class="input input-bordered input-sm w-20 text-center font-mono"
															type="number"
															min="0"
															max="30"
															bind:value={eHomePens}
														/>
													</div>
													<div>
														<label class="label py-0" for="away-pens-{fx.id}">
															<span class="label-text text-xs">Pens (away)</span>
														</label>
														<input
															id="away-pens-{fx.id}"
															class="input input-bordered input-sm w-20 text-center font-mono"
															type="number"
															min="0"
															max="30"
															bind:value={eAwayPens}
														/>
													</div>
												</div>
											{/if}

											<div class="flex flex-wrap items-center gap-4">
												<label class="label cursor-pointer gap-2">
													<input
														type="checkbox"
														class="checkbox checkbox-sm"
														bind:checked={eVerified}
													/>
													<span class="label-text text-xs">
														🔒 Verified — API sync won't overwrite this score
													</span>
												</label>
												<div class="ml-auto flex gap-2">
													<button class="btn btn-ghost btn-sm" type="button" on:click={cancelEdit}>
														Cancel
													</button>
													<button
														class="btn btn-primary btn-sm"
														type="button"
														on:click={requestSave}
														disabled={saving}
													>
														{saving ? 'Saving…' : 'Save'}
													</button>
												</div>
											</div>
										</div>
									</td>
								</tr>
							{/if}
						{/each}
					</tbody>
				</table>
			</div>
		{/if}
	</section>
</div>

<!-- Confirm dialog -->
{#if confirmOpen && editingFixture}
	<div class="modal modal-open" role="dialog">
		<div class="modal-box">
			<h3 class="font-display text-lg mb-2">Confirm manual update</h3>
			<div class="space-y-2 text-sm">
				{#if teamsChanged}
					<p>
						Seed <b>{eHomeTeam.trim()}</b> vs <b>{eAwayTeam.trim()}</b> into this
						<span class="font-mono uppercase text-xs">{editingFixture.stage}</span> fixture.
						Advancement points for these teams pay out immediately.
					</p>
				{/if}
				{#if scoreEntered}
					<p>
						Save <b class="font-mono">{eHome} – {eAway}</b>
						{#if eEt && eHomePens !== null && eAwayPens !== null}
							<span class="text-base-content/55">(pens {eHomePens}–{eAwayPens})</span>
						{/if}
						for <b>{eHomeTeam.trim() || editingFixture.home_team}</b> vs
						<b>{eAwayTeam.trim() || editingFixture.away_team}</b>?
					</p>
					<p class="text-base-content/70">
						This marks the match <b>FINISHED</b> and updates the leaderboard for everyone.
					</p>
					<p class="text-xs text-base-content/55">
						{#if eVerified}
							🔒 Verified: the API sync will not overwrite this score.
						{:else}
							Not verified: the API sync may overwrite this score on its next run.
						{/if}
					</p>
				{/if}
			</div>
			<div class="modal-action">
				<button class="btn btn-ghost btn-sm" type="button" on:click={() => (confirmOpen = false)}>
					Back
				</button>
				<button class="btn btn-primary btn-sm" type="button" on:click={confirmSave} disabled={saving}>
					{saving ? 'Saving…' : 'Confirm'}
				</button>
			</div>
		</div>
	</div>
{/if}
