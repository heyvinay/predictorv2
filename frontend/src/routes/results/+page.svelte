<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { isAuthenticated } from '$stores/auth';
	import { fetchAllFixtures, finishedFixtures } from '$stores/fixtures';
	import { fetchMatchPredictions, predictionsByFixture } from '$stores/predictions';
	import { getPredictionResult, type PredictionResult } from '$lib/utils/predictionResult';
	import { getCommunityPredictions } from '$api/predictions';
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';
	import { displayTeamName } from '$lib/utils/teamName';
	import ScatterPlot from '$lib/components/ScatterPlot.svelte';
	import type { Fixture, CommunityPredictionsResponse } from '$types';

	$: if (!$isAuthenticated) {
		goto('/login');
	}

	let loading = true;

	onMount(async () => {
		if ($isAuthenticated) {
			await Promise.all([fetchAllFixtures(), fetchMatchPredictions()]);
			loading = false;
		}
	});

	// Filters
	let groupFilter = 'all';
	let resultFilter: 'all' | PredictionResult = 'all';

	// Derive sorted finished fixtures (newest first)
	$: sorted = [...$finishedFixtures].sort(
		(a, b) => new Date(b.kickoff).getTime() - new Date(a.kickoff).getTime()
	);

	// Collect available groups for filter
	$: availableGroups = (() => {
		const groups = new Set<string>();
		for (const f of $finishedFixtures) {
			if (f.group) groups.add(f.group);
			else groups.add('knockout');
		}
		return Array.from(groups).sort();
	})();

	// Apply filters
	$: filtered = sorted.filter((f) => {
		if (groupFilter !== 'all') {
			if (groupFilter === 'knockout') {
				if (f.group) return false;
			} else {
				if (f.group !== groupFilter) return false;
			}
		}
		if (resultFilter !== 'all') {
			const pred = $predictionsByFixture.get(f.id);
			const result = getPredictionResult(f, pred);
			if (result !== resultFilter) return false;
		}
		return true;
	});

	// Stats
	$: stats = (() => {
		let exact = 0;
		let outcome = 0;
		let wrong = 0;
		let pending = 0;
		for (const f of $finishedFixtures) {
			const pred = $predictionsByFixture.get(f.id);
			const result = getPredictionResult(f, pred);
			if (result === 'exact') exact++;
			else if (result === 'outcome') outcome++;
			else if (result === 'wrong') wrong++;
			else pending++;
		}
		return { exact, outcome, wrong, pending, total: $finishedFixtures.length };
	})();

	// Group filtered matches by date
	interface DayGroup {
		date: string;
		matches: Fixture[];
		exact: number;
		outcome: number;
		wrong: number;
		pending: number;
	}
	$: groupedByDate = (() => {
		const groups: DayGroup[] = [];
		let currentDate = '';
		let current: DayGroup | null = null;

		for (const f of filtered) {
			const date = new Date(f.kickoff).toLocaleDateString('en-GB', {
				weekday: 'short',
				day: 'numeric',
				month: 'short'
			});
			if (date !== currentDate) {
				if (current) groups.push(current);
				currentDate = date;
				current = { date, matches: [], exact: 0, outcome: 0, wrong: 0, pending: 0 };
			}
			if (current) {
				current.matches.push(f);
				const pred = $predictionsByFixture.get(f.id);
				const result = getPredictionResult(f, pred);
				if (result === 'exact') current.exact++;
				else if (result === 'outcome') current.outcome++;
				else if (result === 'wrong') current.wrong++;
				else current.pending++;
			}
		}
		if (current) groups.push(current);
		return groups;
	})();

	// Day-level accordion state
	let expandedDays = new Set<string>();
	let dayData = new Map<string, Map<string, CommunityPredictionsResponse>>();
	let dayLoading = new Set<string>();
	let dayErrors = new Map<string, string>();

	async function toggleDay(date: string, matches: Fixture[]) {
		if (expandedDays.has(date)) {
			expandedDays.delete(date);
			expandedDays = expandedDays;
			return;
		}

		expandedDays.add(date);
		expandedDays = expandedDays;

		// Already loaded
		if (dayData.has(date)) return;

		dayLoading.add(date);
		dayLoading = dayLoading;
		dayErrors.delete(date);

		try {
			const results = await Promise.all(
				matches.map(async (f) => {
					const data = await getCommunityPredictions(f.id);
					return { fixtureId: f.id, data };
				})
			);
			const fixtureMap = new Map<string, CommunityPredictionsResponse>();
			for (const r of results) {
				fixtureMap.set(r.fixtureId, r.data);
			}
			dayData.set(date, fixtureMap);
			dayData = dayData;
		} catch (e) {
			dayErrors.set(date, e instanceof Error ? e.message : 'Failed to load predictions');
			dayErrors = dayErrors;
		} finally {
			dayLoading.delete(date);
			dayLoading = dayLoading;
		}
	}

	// Result border color helper
	function resultBorderClass(result: PredictionResult): string {
		if (result === 'exact') return 'border-success/60';
		if (result === 'outcome') return 'border-warning/60';
		if (result === 'wrong') return 'border-error/60';
		return 'border-base-content/15';
	}
</script>

<svelte:head>
	<title>Results - Predictor v2</title>
</svelte:head>

{#if $isAuthenticated}
	<div class="container mx-auto mobile-padding py-6">
		<!-- Header -->
		<div class="mb-4">
			<h1 class="text-3xl sm:text-4xl font-display tracking-wide">Results</h1>
			<p class="text-sm text-base-content/50 mt-1">
				{stats.total} finished matches — tap a matchday to see community predictions
			</p>
		</div>

		{#if loading}
			<div class="flex justify-center py-16">
				<span class="loading loading-spinner loading-lg text-primary"></span>
			</div>
		{:else if $finishedFixtures.length === 0}
			<div class="stadium-card no-glow p-8 text-center">
				<svg class="w-16 h-16 mx-auto mb-4 text-base-content/20" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
					<path stroke-linecap="round" stroke-linejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" />
				</svg>
				<p class="text-base-content/50">No finished matches yet.</p>
				<p class="text-base-content/30 text-sm mt-1">Results will appear here as matches are completed.</p>
			</div>
		{:else}
			<!-- Stats summary -->
			<div class="grid grid-cols-4 gap-2 sm:gap-3 mb-4">
				<div class="stat-card !p-3">
					<div class="stat-title text-[10px]">Exact</div>
					<div class="stat-value !text-2xl text-success">{stats.exact}</div>
				</div>
				<div class="stat-card !p-3">
					<div class="stat-title text-[10px]">Correct</div>
					<div class="stat-value !text-2xl text-warning">{stats.outcome}</div>
				</div>
				<div class="stat-card !p-3">
					<div class="stat-title text-[10px]">Wrong</div>
					<div class="stat-value !text-2xl text-error">{stats.wrong}</div>
				</div>
				<div class="stat-card !p-3">
					<div class="stat-title text-[10px]">No Pred</div>
					<div class="stat-value !text-2xl text-base-content/40">{stats.pending}</div>
				</div>
			</div>

			<!-- Filters -->
			<div class="flex flex-wrap gap-2 mb-4">
				<select
					class="select select-sm bg-base-200 border-base-300/50 text-sm"
					bind:value={groupFilter}
				>
					<option value="all">All Stages</option>
					{#each availableGroups as g}
						<option value={g}>{g === 'knockout' ? 'Knockout' : `Group ${g}`}</option>
					{/each}
				</select>

				<div class="flex gap-1 p-0.5 bg-base-300/30 rounded-lg">
					<button
						class="px-3 py-1 rounded-md text-xs font-medium transition-all {resultFilter === 'all'
							? 'bg-primary text-primary-content'
							: 'hover:bg-base-300/50 text-base-content/70'}"
						on:click={() => (resultFilter = 'all')}
					>All</button>
					<button
						class="px-3 py-1 rounded-md text-xs font-medium transition-all {resultFilter === 'exact'
							? 'bg-success text-success-content'
							: 'hover:bg-base-300/50 text-base-content/70'}"
						on:click={() => (resultFilter = 'exact')}
					>Exact</button>
					<button
						class="px-3 py-1 rounded-md text-xs font-medium transition-all {resultFilter === 'outcome'
							? 'bg-warning text-warning-content'
							: 'hover:bg-base-300/50 text-base-content/70'}"
						on:click={() => (resultFilter = 'outcome')}
					>Correct</button>
					<button
						class="px-3 py-1 rounded-md text-xs font-medium transition-all {resultFilter === 'wrong'
							? 'bg-error text-error-content'
							: 'hover:bg-base-300/50 text-base-content/70'}"
						on:click={() => (resultFilter = 'wrong')}
					>Wrong</button>
				</div>
			</div>

			<!-- Day cards -->
			{#if filtered.length === 0}
				<div class="text-center py-8 text-base-content/40 text-sm">
					No matches match your filters.
				</div>
			{:else}
				<div class="space-y-3">
					{#each groupedByDate as day (day.date)}
						{@const isExpanded = expandedDays.has(day.date)}
						{@const isLoading = dayLoading.has(day.date)}
						{@const communityMap = dayData.get(day.date)}
						{@const errorMsg = dayErrors.get(day.date)}

						<div class="stadium-card no-glow overflow-hidden">
							<!-- Clickable day header -->
							<button
								class="w-full p-4 text-left hover:bg-base-300/10 transition-colors"
								on:click={() => toggleDay(day.date, day.matches)}
							>
								<!-- Date row -->
								<div class="flex items-center justify-between mb-3">
									<div class="flex items-center gap-2">
										<span class="text-sm font-display tracking-wide text-base-content/70">{day.date}</span>
										<span class="text-[10px] text-base-content/30">{day.matches.length} {day.matches.length === 1 ? 'match' : 'matches'}</span>
									</div>
									<svg
										class="w-4 h-4 text-base-content/30 transition-transform {isExpanded ? 'rotate-180' : ''}"
										fill="none" viewBox="0 0 24 24" stroke="currentColor"
									>
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
									</svg>
								</div>

								<!-- Mini match scores -->
								<div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
									{#each day.matches as fixture}
										{@const pred = $predictionsByFixture.get(fixture.id)}
										{@const result = getPredictionResult(fixture, pred)}
										<div class="rounded-lg border {resultBorderClass(result)} px-2.5 py-1.5 bg-base-300/20">
											<!-- Actual score row -->
											<div class="flex items-center justify-center gap-1.5">
												{#if hasFlag(fixture.home_team)}
													<img src={getFlagUrl(fixture.home_team, 'sm')} alt="" class="w-4 h-auto rounded-sm shrink-0" />
												{/if}
												<span class="truncate text-xs text-base-content/80">{displayTeamName(fixture.home_team)}</span>
												{#if fixture.score}
													<span class="font-display text-sm tracking-wide shrink-0 mx-0.5">
														{fixture.score.home_score} - {fixture.score.away_score}
													</span>
												{/if}
												<span class="truncate text-xs text-base-content/80">{displayTeamName(fixture.away_team)}</span>
												{#if hasFlag(fixture.away_team)}
													<img src={getFlagUrl(fixture.away_team, 'sm')} alt="" class="w-4 h-auto rounded-sm shrink-0" />
												{/if}
											</div>
											<!-- Your prediction underneath -->
											<div class="text-center text-[10px] text-base-content/40 mt-0.5">
												{#if pred}
													You: {pred.home_score} - {pred.away_score}
												{:else}
													No prediction
												{/if}
											</div>
										</div>
									{/each}
								</div>

								<!-- Daily stats -->
								<div class="flex items-center gap-3 mt-3 text-[10px] text-base-content/40">
									{#if day.exact > 0}
										<span class="flex items-center gap-1">
											<span class="w-1.5 h-1.5 rounded-full bg-success"></span>
											{day.exact} exact
										</span>
									{/if}
									{#if day.outcome > 0}
										<span class="flex items-center gap-1">
											<span class="w-1.5 h-1.5 rounded-full bg-warning"></span>
											{day.outcome} correct
										</span>
									{/if}
									{#if day.wrong > 0}
										<span class="flex items-center gap-1">
											<span class="w-1.5 h-1.5 rounded-full bg-error/70"></span>
											{day.wrong} wrong
										</span>
									{/if}
									{#if day.pending > 0}
										<span class="flex items-center gap-1">
											<span class="w-1.5 h-1.5 rounded-full bg-base-content/25"></span>
											{day.pending} no pred
										</span>
									{/if}
								</div>
							</button>

							<!-- Expanded: Scatter plots -->
							{#if isExpanded}
								<div class="border-t border-base-300/30 p-4 bg-base-300/10">
									{#if isLoading}
										<div class="flex justify-center py-8">
											<span class="loading loading-spinner loading-md text-primary"></span>
										</div>
									{:else if errorMsg}
										<div class="text-center py-4 text-error text-sm">{errorMsg}</div>
									{:else if communityMap}
										<div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
											{#each day.matches as fixture (fixture.id)}
												{@const community = communityMap.get(fixture.id)}
												{#if community}
													{@const pred = $predictionsByFixture.get(fixture.id)}
													<div>
														<!-- Match header above plot -->
														<div class="flex items-center justify-center gap-2 mb-2 text-sm">
															{#if hasFlag(fixture.home_team)}
																<img src={getFlagUrl(fixture.home_team, 'sm')} alt="" class="w-4 h-auto rounded-sm" />
															{/if}
															<span class="font-semibold text-xs">{displayTeamName(fixture.home_team)}</span>
															{#if fixture.score}
																<span class="font-display text-base tracking-wide">
																	{fixture.score.home_score} - {fixture.score.away_score}
																</span>
															{/if}
															<span class="font-semibold text-xs">{displayTeamName(fixture.away_team)}</span>
															{#if hasFlag(fixture.away_team)}
																<img src={getFlagUrl(fixture.away_team, 'sm')} alt="" class="w-4 h-auto rounded-sm" />
															{/if}
														</div>
														<div class="text-center text-[10px] text-base-content/40 mb-1">
															{community.predictions.length} predictions
														</div>
													<ScatterPlot
															predictions={community.predictions}
															actual={community.actual}
															homeTeam={fixture.home_team}
															awayTeam={fixture.away_team}
															userPrediction={pred ? { home_score: pred.home_score, away_score: pred.away_score } : null}
														/>
													</div>
												{/if}
											{/each}
										</div>

										<!-- Shared legend -->
										<div class="flex items-center justify-center gap-4 mt-4 text-[10px] text-base-content/40">
											<div class="flex items-center gap-1">
												<span class="w-2.5 h-2.5 bg-success" style="clip-path: polygon(50% 0%, 61% 35%, 98% 35%, 68% 57%, 79% 91%, 50% 70%, 21% 91%, 32% 57%, 2% 35%, 39% 35%);"></span>
												Exact
											</div>
											<div class="flex items-center gap-1">
												<span class="w-2.5 h-2.5 rounded-full bg-warning"></span>
												Correct
											</div>
											<div class="flex items-center gap-1">
												<span class="w-2.5 h-2.5 rounded-full bg-error/70"></span>
												Wrong
											</div>
										</div>
									<div class="text-center mt-1.5 text-[9px] text-base-content/30">
										Numbers show how many players predicted each score
									</div>
									{/if}
								</div>
							{/if}
						</div>
					{/each}
				</div>
			{/if}
		{/if}
	</div>
{/if}
