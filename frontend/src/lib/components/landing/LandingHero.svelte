<!--
	LandingHero — the page's opening surface. Split grid: PrizeHero on
	the left (Atlas TRIONDA match-ball callout), an auth-aware card on
	the right (SignInCard for guests, WelcomeBackCard for returning
	members). The "MAKE EVERY WORLD CUP MATCH MATTER" typographic block
	moved to TypographicHero (rendered as its own section below) in
	v2.159 so the prize moment leads the page.

	On `lg+` the layout is two columns 1.5fr / 1fr; below that the card
	stacks under the prize, with the email field still anchorable via
	the `#signin` id on SignInCard.
-->
<script lang="ts">
	import { isAuthenticated } from '$stores/auth';
	import SignInCard from '$components/SignInCard.svelte';
	import WelcomeBackCard from '$components/WelcomeBackCard.svelte';
	import PrizeHero from './PrizeHero.svelte';
	import SocialProofCard from './SocialProofCard.svelte';

	/** ISO datetime when Phase 1 locks. Drives the WelcomeBackCard's
	 *  status line. */
	export let phase1Deadline: string | null = null;
</script>

<div class="relative overflow-hidden bg-base-200 border-b border-base-300/40">
	<div
		class="relative max-w-[1200px] mx-auto mobile-padding py-8 sm:py-12 lg:py-16
			grid grid-cols-1 lg:grid-cols-[1.2fr_1fr] gap-6 lg:gap-12 items-center"
	>
		<!--
			Mobile-first order (sub-lg): CTA → social proof → prize.
			Action above context above decoration. Atlas panel sinks to
			the bottom so users don't have to scroll past it to reach
			the welcome card.

			Desktop order (lg+): prize on the left, social proof above
			welcome on the right. `lg:order-*` overrides restore the
			intended desktop hierarchy.
		-->

		<!-- ── Atlas TRIONDA prize ─────────────────────────────────── -->
		<div class="order-3 lg:order-1">
			<PrizeHero />
		</div>

		<!-- ── Right column — Welcome (CTA) + SocialProof ──────────── -->
		<div
			class="order-1 lg:order-2 w-full max-w-lg justify-self-stretch lg:justify-self-end flex flex-col"
		>
			<!-- SocialProof: second on mobile (below CTA), first on desktop. -->
			<div class="order-2 lg:order-1">
				<SocialProofCard />
			</div>
			<!-- Welcome / SignIn: first on mobile (CTA on top), second on desktop. -->
			<div class="order-1 lg:order-2">
				{#if $isAuthenticated}
					<WelcomeBackCard {phase1Deadline} placement="hero" />
				{:else}
					<SignInCard id="signin" placement="hero" />
				{/if}
			</div>
		</div>
	</div>
</div>
