<script lang="ts">
	// Score Sync tab — manual escape hatch for the Football-Data.org sync
	// (the background scheduler runs every 60s during match windows), plus
	// a full read-only fixtures table so the admin can sanity-check that
	// scores landed on the right rows. Moved out of /admin/+page.svelte
	// in v2.160.0; the legacy Score-sync card on the Overview is removed.
	//
	// No backend change — uses the existing public GET /fixtures/ endpoint
	// for the table. Sync button hits the existing /admin/scores/sync.
	import { onDestroy, onMount } from 'svelte';
	import { syncScores, type SyncScoresResponse } from '$lib/api/admin';
	import { getAllFixtures } from '$lib/api/fixtures';
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
		<h2 class="text-lg font-display tracking-wide mb-3">
			Fixtures
			<span class="text-xs text-base-content/40">
				{#if !fixturesLoading}· {fixtures.length} total{/if}
			</span>
		</h2>
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
						</tr>
					</thead>
					<tbody>
						{#each fixtures as fx (fx.id)}
							<tr class="border-t border-base-300/40">
								<td class="font-mono text-xs uppercase">{fx.stage}</td>
								<td class="font-mono text-xs">{fx.group ?? '—'}</td>
								<td class="text-xs whitespace-nowrap">{formatKickoff(fx.kickoff)}</td>
								<td class="text-sm">{fx.home_team}</td>
								<td class="text-sm text-center font-mono whitespace-nowrap">{scoreCell(fx)}</td>
								<td class="text-sm">{fx.away_team}</td>
								<td>
									<span class="badge badge-xs {statusBadgeClass(fx.status)}">
										{fx.status}
									</span>
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{/if}
	</section>
</div>
