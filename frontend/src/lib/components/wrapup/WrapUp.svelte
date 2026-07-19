<script lang="ts">
	/** Post-tournament wrap-up page (Plan C). Bento-grid shell: fetches the
	 *  final podium + pool retrospective + leaderboard + scoring rules in
	 *  parallel, then composes the hero (podium, honours, Final, Atlas)
	 *  plus a grid of supporting tiles. Most tiles are stubs pending
	 *  C3-C6 — see the stub files in this directory for their eventual
	 *  prop contracts. */
	import { onMount } from 'svelte';
	import { isAuthenticated, user } from '$stores/auth';
	import { fetchAllFixtures } from '$stores/fixtures';
	import {
		getFinalPodium,
		getPoolRetrospective,
		getLeaderboardV4,
		getScoringRules
	} from '$api/leaderboard';
	import { track } from '$lib/analytics';
	import type { FinalPodium, PoolRetrospective } from '$lib/types/wrapup';
	import type { LbEntryV4 } from '$lib/types/leaderboard';
	import type { ScoringRules } from '$lib/types/results';
	import PodiumHero from './PodiumHero.svelte';
	import FinalMatchCard from './FinalMatchCard.svelte';
	import AtlasCard from './AtlasCard.svelte';
	import CompareCtaCard from './CompareCtaCard.svelte';
	import TitleMatrix from './TitleMatrix.svelte';
	import FinalLeaderboardTile from './FinalLeaderboardTile.svelte';
	import YourTournament from './YourTournament.svelte';
	import GuestSignInStrip from './GuestSignInStrip.svelte';
	import FeedbackTile from './FeedbackTile.svelte';
	import PoolVsTournament from './PoolVsTournament.svelte';
	import ChampionPicksTile from './ChampionPicksTile.svelte';
	import BonusAnswersTile from './BonusAnswersTile.svelte';
	import PointsDnaTile from './PointsDnaTile.svelte';
	import CharityStrip from './CharityStrip.svelte';

	let podium: FinalPodium | null = null;
	let retro: PoolRetrospective | null = null;
	let rows: LbEntryV4[] = [];
	let rules: ScoringRules | null = null;
	let loading = true;

	async function load() {
		const [p, r, lb, sr] = await Promise.all([
			getFinalPodium().catch(() => null),
			getPoolRetrospective().catch(() => null),
			getLeaderboardV4().catch(() => null),
			getScoringRules().catch(() => null),
			fetchAllFixtures()
		]);
		podium = p;
		retro = r;
		rows = lb?.entries ?? [];
		rules = sr;
		loading = false;
	}

	onMount(() => {
		void load();
		track('wrapup_viewed', { auth_state: $isAuthenticated ? 'authenticated' : 'guest' });
	});

	$: personal = retro?.personal?.[0] ?? null;
</script>

<svelte:head>
	<title>World Cup 2026 — the final story · The Predictor</title>
	<meta name="robots" content="noindex" />
</svelte:head>

<div class="container mx-auto max-w-[1240px] mobile-padding pb-10 pt-3">
	{#if loading}
		<div class="stadium-card no-glow p-10 text-center text-base-content/50">
			Loading the final story…
		</div>
	{:else if !podium}
		<div class="stadium-card no-glow p-10 text-center text-base-content/50">
			The wrap-up appears once the tournament concludes.
		</div>
	{:else}
		<div class="grid grid-cols-6 gap-3 [grid-auto-flow:dense] items-stretch">
			<!-- Row 1: hero (4-wide, 2 rows) + Final + [compare CTA | Atlas for guests] -->
			<section class="col-span-6 min-w-0 min-[1100px]:col-span-4 min-[1100px]:row-span-2">
				<PodiumHero {podium} />
			</section>
			<section class="col-span-6 min-w-0 min-[760px]:col-span-3 min-[1100px]:col-span-2">
				<FinalMatchCard finalMatch={podium.final_match} />
			</section>
			{#if $isAuthenticated}
				<section class="col-span-6 min-w-0 min-[760px]:col-span-3 min-[1100px]:col-span-2">
					<CompareCtaCard
						championEntryId={podium.entries[0]?.entry_id ?? null}
						myEntryId={personal?.entry_id ?? null}
					/>
				</section>
			{:else}
				<section class="col-span-6 min-w-0 min-[760px]:col-span-3 min-[1100px]:col-span-2">
					<AtlasCard />
				</section>
			{/if}

			<!-- Row 2: title matrix + final leaderboard -->
			<section class="col-span-6 min-w-0 min-[760px]:col-span-3">
				<TitleMatrix {podium} {rows} {rules} />
			</section>
			<section class="col-span-6 min-w-0 min-[760px]:col-span-3">
				<FinalLeaderboardTile
					{rows}
					championTeam={retro?.final_winner_team ?? null}
					myUserId={$user?.id ?? null}
				/>
			</section>

			<!-- Row 3: personal / sign-in + feedback -->
			{#if $isAuthenticated && personal}
				<section class="col-span-6 min-w-0 min-[1100px]:col-span-4">
					<YourTournament {personal} allPersonal={retro?.personal ?? [personal]} poolSize={rows.length} />
				</section>
				<section class="col-span-6 min-w-0 min-[760px]:col-span-3 min-[1100px]:col-span-2">
					<FeedbackTile />
				</section>
			{:else if !$isAuthenticated}
				<section class="col-span-6 min-w-0">
					<GuestSignInStrip />
				</section>
			{/if}

			<!-- Row 4: pool retrospective (tall) + two small tiles -->
			{#if retro}
				<section class="col-span-6 min-w-0 min-[1100px]:col-span-4 min-[1100px]:row-span-2">
					<PoolVsTournament {retro} poolSize={rows.length} />
				</section>
				<section class="col-span-6 min-w-0 min-[760px]:col-span-3 min-[1100px]:col-span-2">
					<ChampionPicksTile picks={retro.champion_distribution} poolSize={rows.length} />
				</section>
				<section class="col-span-6 min-w-0 min-[760px]:col-span-3 min-[1100px]:col-span-2">
					<BonusAnswersTile bonus={retro.bonus} />
				</section>
			{/if}

			<!-- Row 5: Points DNA full width -->
			<section class="col-span-6 min-w-0">
				<PointsDnaTile {rows} myUserId={$user?.id ?? null} />
			</section>

			<!-- Row 6: Atlas (members; guests saw it up top) + charity -->
			{#if $isAuthenticated}
				<section class="col-span-6 min-w-0 min-[760px]:col-span-2">
					<AtlasCard />
				</section>
			{/if}
			<section class="col-span-6 min-w-0 min-[760px]:col-span-4">
				<CharityStrip isMember={$isAuthenticated} />
			</section>
		</div>
	{/if}
</div>
