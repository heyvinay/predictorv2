<!--
	WelcomeTourModal — one-time 3-step "what matters now" tour (v2.173.0).

	Shown once per device to signed-in users with a complete profile,
	on every page except /admin and /onboarding. The seen-flag is keyed
	by TOUR_ID, so re-running the tour for everyone = bump the ID
	(same editorial model as SiteNoticeBanner's NOTICE_ID). Retire
	entirely by flipping TOUR_ENABLED.

	Not to be confused with the /onboarding route — that's the
	mandatory profile-completion form (name/employer); this is an
	optional, dismissible walkthrough that waits until the profile
	redirect can no longer fire.

	FeatureToast imports TOUR_ENABLED / TOUR_SEEN_KEY from this
	module context to suppress itself on any load where the tour is
	still pending (tour wins; the toast shows on the next visit).
-->
<script lang="ts" context="module">
	export const TOUR_ENABLED = true;
	export const TOUR_ID = '2026-06-12-live-tour';
	export const TOUR_SEEN_KEY = `predictor:tour:${TOUR_ID}:seen`;
</script>

<script lang="ts">
	import { onMount } from 'svelte';
	import { fade, scale } from 'svelte/transition';
	import { page } from '$app/stores';
	import { isAuthenticated, user } from '$stores/auth';
	import { supportOpen } from '$stores/supportPanel';
	import { needsOnboarding } from '$lib/utils/onboarding';
	import Trophy from 'lucide-svelte/icons/trophy';
	import ListChecks from 'lucide-svelte/icons/list-checks';
	import LifeBuoy from 'lucide-svelte/icons/life-buoy';

	const steps = [
		{
			Icon: Trophy,
			title: 'The tournament is live',
			body: 'Matches are underway and scores roll in automatically. As each game finishes, your points update and the leaderboard reshuffles — check back after every matchday to see where you stand.'
		},
		{
			Icon: ListChecks,
			title: 'Follow every pick',
			body: 'The Results page breaks down your entry round by round — every scoreline, every bracket call. Tap any match to see how the whole pool predicted it and where the points went.'
		},
		{
			Icon: LifeBuoy,
			title: "We've got your back",
			body: 'Scoring details live on the Rules page, and if anything looks off — a missing point, a wrong score — drop us a note via'
		}
	];

	// Hidden until onMount so a device that has seen the tour never
	// gets a flash; fresh devices get a harmless one-tick pop-in.
	let seen = true;
	let step = 0;

	onMount(() => {
		try {
			seen = localStorage.getItem(TOUR_SEEN_KEY) === '1';
		} catch {
			seen = true; // storage unavailable → never show
		}
	});

	// Every exit path (X, Skip, Escape, backdrop, final CTA) lands here.
	function finish() {
		seen = true;
		try {
			localStorage.setItem(TOUR_SEEN_KEY, '1');
		} catch {
			/* storage unavailable — modal still closes for this session */
		}
	}

	function next() {
		step = Math.min(step + 1, steps.length - 1);
	}

	function back() {
		step = Math.max(step - 1, 0);
	}

	function openSupport() {
		finish();
		supportOpen.set(true);
	}

	function handleKey(e: KeyboardEvent) {
		if (!show) return;
		if (e.key === 'Escape') {
			e.preventDefault();
			finish();
		}
	}

	// `!!$user` matters: while the user record is loading,
	// needsOnboarding(null) returns false, and the tour must not
	// flash for someone about to be redirected to /onboarding.
	$: show =
		TOUR_ENABLED &&
		$isAuthenticated &&
		!seen &&
		!!$user &&
		!needsOnboarding($user) &&
		!$page.url.pathname.startsWith('/admin') &&
		$page.url.pathname !== '/onboarding';
	$: isLast = step === steps.length - 1;
</script>

<svelte:window on:keydown={handleKey} />

{#if show}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center p-4"
		role="dialog"
		aria-modal="true"
		aria-labelledby="tour-title"
	>
		<!-- Backdrop -->
		<button
			type="button"
			class="absolute inset-0 bg-black/60 backdrop-blur-sm cursor-default"
			tabindex="-1"
			aria-label="Close tour"
			on:click={finish}
			transition:fade={{ duration: 150 }}
		></button>

		<!-- Dialog -->
		<div
			class="relative bg-base-200 rounded-2xl shadow-2xl border border-base-content/10 max-w-sm w-full p-6"
			transition:scale={{ duration: 180, start: 0.95, opacity: 0 }}
		>
			<button
				class="btn btn-ghost btn-xs absolute right-3 top-3 px-1.5 text-base-content/60 hover:text-base-content"
				aria-label="Skip tour"
				title="Skip"
				on:click={finish}
			>
				✕
			</button>

			<!-- Step content. Keyed in-only fade: exactly one step element
			     exists at any moment, so the card never double-stacks
			     mid-transition; min-h absorbs copy-length differences. -->
			<div class="min-h-[200px] flex items-center">
				{#key step}
					<div in:fade={{ duration: 150 }} class="w-full text-center">
						<svelte:component
							this={steps[step].Icon}
							size={40}
							strokeWidth={1.75}
							class="mx-auto mb-3 text-primary"
							aria-hidden="true"
						/>
						<h2 id="tour-title" class="text-xl font-display font-bold mb-2">
							{steps[step].title}
						</h2>
						<p class="text-sm text-base-content/70 leading-relaxed">
							{steps[step].body}
							{#if isLast}
								<button
									class="font-semibold text-primary underline decoration-primary/50 underline-offset-2"
									on:click={openSupport}
								>
									Help &amp; Support</button
								>
								and we&rsquo;ll sort it.
							{/if}
						</p>
					</div>
				{/key}
			</div>

			<!-- Footer: progress dots + controls -->
			<div class="flex items-center justify-between mt-5 pt-4 border-t border-base-content/10">
				<div class="flex gap-1.5" aria-hidden="true">
					{#each steps as _, i}
						<span
							class="h-1.5 rounded-full transition-all duration-300 {i === step
								? 'w-5 bg-primary'
								: 'w-1.5 bg-base-content/20'}"
						></span>
					{/each}
				</div>

				<div class="flex items-center gap-2">
					{#if isLast}
						<button class="btn btn-ghost btn-sm" on:click={finish}>Done</button>
						<a href="/leaderboard" class="btn btn-primary btn-sm" on:click={finish}>
							View the leaderboard
						</a>
					{:else}
						{#if step > 0}
							<button class="btn btn-ghost btn-sm" on:click={back}>Back</button>
						{:else}
							<button class="btn btn-ghost btn-sm" on:click={finish}>Skip</button>
						{/if}
						<button class="btn btn-primary btn-sm" on:click={next}>Next</button>
					{/if}
				</div>
			</div>
		</div>
	</div>
{/if}
