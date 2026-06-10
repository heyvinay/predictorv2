<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { isAuthenticated, user } from '$stores/auth';
	import { getUserProfile, getUserPredictions } from '$api/users';
	import PredictionTable from '$lib/components/PredictionTable.svelte';
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';
	import type { PublicProfile, UserPredictionsResponse } from '$types';

	$: if (!$isAuthenticated) {
		goto('/login');
	}

	$: userId = $page.params.userId;
	$: isOwnProfile = userId === $user?.id;

	let profile: PublicProfile | null = null;
	let predictions: UserPredictionsResponse | null = null;
	let loading = true;
	let error: string | null = null;

	// Refetch when userId changes
	$: if (userId && $isAuthenticated) {
		loadData(userId);
	}

	async function loadData(id: string) {
		loading = true;
		error = null;
		try {
			const [p, preds] = await Promise.all([
				getUserProfile(id),
				getUserPredictions(id)
			]);
			profile = p;
			predictions = preds;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load profile';
		} finally {
			loading = false;
		}
	}

	function formatDate(dateStr: string): string {
		return new Date(dateStr).toLocaleDateString('en-GB', {
			day: 'numeric',
			month: 'long',
			year: 'numeric'
		});
	}

	// Bracket stage display order. Stored stage values are singular as of
	// v2.161.0; the plural spellings are kept for any stale cached payloads.
	const stageOrder = [
		'round_of_32',
		'round_of_16',
		'quarter_final',
		'quarter_finals',
		'semi_final',
		'semi_finals',
		'final',
		'winner'
	];
	const stageLabels: Record<string, string> = {
		'group': 'Group Stage',
		'round_of_32': 'Round of 32',
		'round_of_16': 'Round of 16',
		'quarter_finals': 'Quarter Finals',
		'quarter_final': 'Quarter Finals',
		'semi_finals': 'Semi Finals',
		'semi_final': 'Semi Finals',
		'final': 'Final',
		'winner': 'Winner'
	};

	// Funnel max-widths (px) — for single-bracket pyramid mode only
	const stageMaxWidth: Record<string, number> = {
		'winner': 220,
		'final': 300,
		'semi_finals': 440,
		'semi_final': 440,
		'quarter_finals': 560,
		'quarter_final': 560,
		'round_of_16': 700,
		'round_of_32': 900,
	};

	// Phase detection and bracket data
	$: hasPhase2 = predictions
		? Object.keys(predictions.bracket_summary.phase2_stages ?? {}).length > 0
		: false;

	$: bracketPhases = (() => {
		if (!predictions) return [];
		const bs = predictions.bracket_summary;
		const p1 = bs.phase1_stages ?? {};
		const p2 = bs.phase2_stages ?? {};
		const hasP1 = Object.keys(p1).length > 0;
		const hasP2 = Object.keys(p2).length > 0;

		if (hasP2) {
			return [
				{ label: 'Phase 1', stages: p1 },
				{ label: 'Phase 2', stages: p2 }
			];
		}
		// Single phase — use phase1 if available, else fallback to merged stages
		return [{ label: '', stages: hasP1 ? p1 : bs.stages }];
	})();

	function sortStageEntries(stages: Record<string, string[]>): [string, string[]][] {
		return Object.entries(stages).sort(([a], [b]) => {
			const ai = stageOrder.indexOf(a);
			const bi = stageOrder.indexOf(b);
			return (bi === -1 ? -1 : bi) - (ai === -1 ? -1 : ai);
		});
	}
</script>

<svelte:head>
	<title>{profile?.name ?? 'Player'} - Predictor v2</title>
</svelte:head>

{#if $isAuthenticated}
	<div class="container mx-auto mobile-padding py-6">
		{#if loading}
			<div class="flex justify-center py-16">
				<span class="loading loading-spinner loading-lg text-primary"></span>
			</div>
		{:else if error}
			<div class="stadium-card no-glow p-8 text-center">
				<svg class="w-12 h-12 mx-auto mb-3 text-error/50" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
					<path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
				</svg>
				<p class="text-error">{error}</p>
				<button class="btn btn-ghost btn-sm mt-4" on:click={() => { if (userId) loadData(userId); }}>Retry</button>
			</div>
		{:else if profile}
			<!-- Header -->
			<div class="mb-8">
				<div class="flex items-center gap-4">
					<div class="w-14 h-14 rounded-full bg-gradient-to-br from-primary to-accent grid place-items-center ring-2 ring-primary/20">
						<span class="text-2xl font-bold text-white leading-none translate-y-0.5">
							{profile.name.charAt(0).toUpperCase()}
						</span>
					</div>
					<div>
						<h1 class="text-3xl sm:text-4xl font-display tracking-wide flex items-center gap-2">
							{profile.name}
							{#if isOwnProfile}<span class="badge badge-primary badge-sm align-middle">YOU</span>{/if}
						</h1>
						<p class="text-sm text-base-content/50">Member since {formatDate(profile.created_at)}</p>
					</div>
				</div>
				{#if isOwnProfile}
					<a href="/profile" class="btn btn-ghost btn-sm mt-3 gap-1">
						<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
							<path stroke-linecap="round" stroke-linejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
							<path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
						</svg>
						Account Settings
					</a>
				{/if}
			</div>

			<!-- Stats grid -->
			<div class="grid grid-cols-2 sm:grid-cols-3 gap-3 sm:gap-4 mb-8">
				<div class="stat-card">
					<p class="stat-title">Leaderboard</p>
					<p class="stat-value {profile.stats.leaderboard_position && profile.stats.leaderboard_position <= 3 ? 'text-primary' : ''}">
						{#if profile.stats.leaderboard_position}
							#{profile.stats.leaderboard_position}
						{:else}
							-
						{/if}
					</p>
					<p class="text-xs text-base-content/40 mt-1">of {profile.stats.total_participants}</p>
				</div>
				<div class="stat-card">
					<p class="stat-title">Total Points</p>
					<p class="stat-value">{profile.stats.total_points}</p>
				</div>
				<div class="stat-card">
					<p class="stat-title">Accuracy</p>
					<p class="stat-value">{profile.stats.accuracy_pct}%</p>
				</div>
				<div class="stat-card">
					<p class="stat-title">Predictions</p>
					<p class="stat-value">{profile.stats.total_predictions}</p>
					<p class="text-xs text-base-content/40 mt-1">
						{profile.stats.total_match_predictions} match, {profile.stats.total_team_predictions} team
					</p>
				</div>
				<div class="stat-card">
					<p class="stat-title">Correct Outcomes</p>
					<p class="stat-value text-success">{profile.stats.correct_outcomes}</p>
				</div>
				<div class="stat-card">
					<p class="stat-title">Exact Scores</p>
					<p class="stat-value text-primary">{profile.stats.exact_scores}</p>
				</div>
				<div class="stat-card">
					<p class="stat-title">Bonus Haul</p>
					<p class="stat-value text-accent">{profile.stats.breakdown.hybrid_bonus_points}</p>
				</div>
			</div>

			<!-- Match Predictions -->
			{#if predictions && predictions.match_predictions.length > 0}
				<div class="stadium-card no-glow p-4 sm:p-6 mb-8">
					<h2 class="text-lg font-display tracking-wide mb-4">Match Predictions</h2>
					<PredictionTable predictions={predictions.match_predictions} />
				</div>
			{/if}

			<!-- Bracket Predictions -->
			{#if predictions && (Object.keys(predictions.bracket_summary.phase1_stages ?? {}).length > 0 || Object.keys(predictions.bracket_summary.stages).length > 0)}
				<div class="stadium-card no-glow p-4 sm:p-6">
					<h2 class="text-lg font-display tracking-wide mb-5">Bracket Predictions</h2>

					<div class={hasPhase2 ? 'grid grid-cols-2 gap-4 sm:gap-6 divide-x divide-base-content/10' : ''}>
						{#each bracketPhases as phase}
							<div class={hasPhase2 ? 'pl-4 sm:pl-6 first:pl-0' : ''}>
								<!-- Phase label (only when both phases exist) -->
								{#if phase.label}
									<div class="mb-4 {hasPhase2 ? 'text-center' : ''}">
										<span class="text-xs font-semibold uppercase tracking-wider px-3 py-1 rounded-full
											{phase.label === 'Phase 1' ? 'bg-primary/10 text-primary/70' : 'bg-accent/10 text-accent/70'}">
											{phase.label}
										</span>
									</div>
								{/if}

								<!-- Stages -->
								<div class="flex flex-col {hasPhase2 ? '' : 'items-center'} gap-3">
									{#each sortStageEntries(phase.stages) as [stage, teams], i}
										{#if teams.length > 0}
											<div class="w-full" style="{hasPhase2 ? '' : `max-width: ${stageMaxWidth[stage] ?? 800}px`}">
												<div class="text-[10px] uppercase tracking-widest font-semibold mb-1.5 {hasPhase2 ? '' : 'text-center'} text-base-content/35">
													{#if stage === 'winner'}
														<svg class="w-3.5 h-3.5 text-yellow-400 inline -mt-0.5 mr-0.5" viewBox="0 0 24 24" fill="currentColor">
															<path d="M5 3h14c0 0 0 .5-.1 1H19l-1.6 5.2A4.5 4.5 0 0113.5 13h-3a4.5 4.5 0 01-3.9-3.8L5 4h.1C5 3.5 5 3 5 3zm4.5 12h5v1.5a.5.5 0 01-.5.5h-4a.5.5 0 01-.5-.5V15zm-1 3h7a1 1 0 011 1v1H7.5v-1a1 1 0 011-1zm-1.5 3h8v1h-8v-1z"/>
														</svg>
													{/if}
													{stageLabels[stage] ?? stage}
													{#if stage !== 'winner'}
														<span class="text-base-content/20 ml-1">({teams.length})</span>
													{/if}
												</div>
												<div class="{hasPhase2 ? 'grid grid-cols-1 sm:grid-cols-2 gap-1.5' : 'grid grid-cols-2 sm:grid-cols-4 gap-1.5 justify-items-center'}">
													{#each teams as team}
														<span class="inline-flex items-center gap-1.5 w-full px-2.5 py-1.5 rounded-lg text-xs font-medium bg-base-300/50 border border-base-content/10 text-base-content/80">
															{#if hasFlag(team)}
																<img src={getFlagUrl(team, 'sm')} alt="" class="w-4 h-auto rounded-sm shrink-0" />
															{/if}
															<span class="truncate">{team}</span>
														</span>
													{/each}
												</div>
											</div>
										{/if}
									{/each}
								</div>
							</div>
						{/each}
					</div>
				</div>
			{/if}
		{/if}
	</div>
{/if}
