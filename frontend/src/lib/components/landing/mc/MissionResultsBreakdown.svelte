<!--
  MissionResultsBreakdown — compact "How your points were scored" list
  per mockup section 4.6 left column.

  Per finished fixture, renders a row with:
    - Score: home flag + h–a + away flag
    - "{HOME} v {AWAY} · you {pick}" + chip row (Outcome / Exact / Rarity)
    - Total points earned (gold for exact, amber for outcome, muted for miss)

  All chips derive from matchBreakdown.computeBreakdown — same engine the
  card carousel uses, so totals reconcile.
-->
<script lang="ts">
	import type { Fixture, MatchPrediction } from '$types';
	import type { FixtureAgreement } from '$api/predictions';
	import type { ScoringConfig } from '$api/competition';
	import { computeBreakdown } from '$lib/utils/matchBreakdown';
	import { teamCode, flagIsoCode } from '$lib/utils/teamCodes';

	export let finishedFixtures: Fixture[];
	export let predictionByFixture: Map<string, MatchPrediction>;
	export let agreementByFixture: Map<string, FixtureAgreement>;
	export let scoringConfig: ScoringConfig;

	$: rows = finishedFixtures.map((f) => {
		const pred = predictionByFixture.get(f.id);
		const agree = agreementByFixture.get(f.id);
		const bd = computeBreakdown(f, pred, agree, scoringConfig);
		const homeIso = flagIsoCode(teamCode(f.home_team));
		const awayIso = flagIsoCode(teamCode(f.away_team));
		const homeCode = teamCode(f.home_team);
		const awayCode = teamCode(f.away_team);
		return { f, pred, bd, homeIso, awayIso, homeCode, awayCode };
	});

	function toneColor(tier: string): string {
		if (tier === 'tier-exact') return '#34d399';
		if (tier === 'tier-outcome') return 'var(--warning-text, #fbbf24)';
		return 'rgba(226,232,240,0.55)';
	}
</script>

<section class="stadium-card no-glow p-6">
	<div class="flex items-center justify-between mb-3">
		<h2 class="font-display font-extrabold text-lg">How your points were scored</h2>
		<a href="/results" class="text-xs font-semibold text-primary hover:underline">
			Results →
		</a>
	</div>

	{#if rows.length === 0}
		<p class="text-sm text-base-content/55 py-4">
			No finished matches yet. Once kickoffs start, your scoring breakdown lands here per match.
		</p>
	{:else}
		<div>
			{#each rows as { f, pred, bd, homeIso, awayIso, homeCode, awayCode }, i (f.id)}
				<a
					href="/results/{f.id}"
					class="grid items-center gap-3.5 py-2.5 cursor-pointer hover:bg-base-300/20 px-1.5 -mx-1.5 rounded transition-colors"
					style="grid-template-columns: auto 1fr auto;"
					style:border-top={i > 0 ? '1px solid rgba(42,53,82,0.5)' : '0'}
				>
					<!-- Score block -->
					<div class="flex items-center gap-2 min-w-0">
						{#if homeIso}
							<span class="fi fi-{homeIso} w-5 h-3.5 rounded-sm flex-none"></span>
						{:else}
							<span class="w-5 h-3.5 rounded-sm bg-base-300 flex-none"></span>
						{/if}
						<span class="font-display font-extrabold text-sm">
							{f.score?.home_score ?? '–'}–{f.score?.away_score ?? '–'}
						</span>
						{#if awayIso}
							<span class="fi fi-{awayIso} w-5 h-3.5 rounded-sm flex-none"></span>
						{:else}
							<span class="w-5 h-3.5 rounded-sm bg-base-300 flex-none"></span>
						{/if}
					</div>

					<!-- Pick + chips -->
					<div class="min-w-0">
						<span class="text-xs text-base-content/72">
							{homeCode} v {awayCode}
							{#if pred}
								· <strong class="text-base-content">you {pred.home_score}-{pred.away_score}</strong>
							{:else}
								· <span class="text-base-content/55">no pick</span>
							{/if}
						</span>
						<div class="flex flex-wrap gap-1.5 mt-1">
							{#if bd.outcomePill.state === 'hit-outcome'}
								<span class="text-[9.5px] font-bold uppercase tracking-[0.04em] px-1.5 py-0.5 rounded bg-warning/20 text-warning-text">
									Outcome +{bd.outcomePill.pts}
								</span>
							{:else if bd.outcomePill.state === 'miss'}
								<span class="text-[9.5px] font-bold uppercase tracking-[0.04em] px-1.5 py-0.5 rounded bg-base-300/40 text-base-content/55">
									Outcome 0
								</span>
							{/if}
							{#if bd.scorePill.state === 'hit-exact'}
								<span class="text-[9.5px] font-bold uppercase tracking-[0.04em] px-1.5 py-0.5 rounded bg-success/20 text-success">
									Exact +{bd.scorePill.pts}
								</span>
							{/if}
							{#if bd.rarityPill.state === 'hit-rarity' || bd.rarityPill.state === 'hit-rarity solo'}
								<span class="text-[9.5px] font-bold uppercase tracking-[0.04em] px-1.5 py-0.5 rounded bg-primary/20 text-primary">
									{bd.rarityPill.lab} +{bd.rarityPill.pts}
								</span>
							{/if}
						</div>
					</div>

					<!-- Total -->
					<span class="font-display font-extrabold text-base justify-self-end" style:color={toneColor(bd.tier)}>
						{bd.totalDisplay}
					</span>
				</a>
			{/each}
		</div>
	{/if}
</section>
