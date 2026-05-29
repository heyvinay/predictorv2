<script lang="ts">
	import { onMount } from 'svelte';
	import { isAuthenticated } from '$stores/auth';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import SignInCard from '$components/SignInCard.svelte';

	// returnTo (R7): if the user arrived from a protected route (e.g. clicked
	// a deep link in the submission email while signed out), the wizard
	// appended ?returnTo=/entries/{id}. Stash it in sessionStorage so it
	// survives the email round-trip to the magic-link verify endpoint, then
	// /auth/callback restores it.
	const RETURN_TO_KEY = 'predictor_returnTo';

	$: if ($isAuthenticated) {
		goto('/');
	}

	onMount(() => {
		// Stash returnTo if present in the URL — only safe relative paths
		// (must start with '/'); anything else is dropped on the floor.
		const rt = $page.url.searchParams.get('returnTo');
		if (rt && rt.startsWith('/') && !rt.startsWith('//')) {
			try {
				sessionStorage.setItem(RETURN_TO_KEY, rt);
			} catch {
				/* sessionStorage unavailable — fall through to dashboard redirect */
			}
		}
	});

	function logoFallbackHero(e: Event) {
		const el = e.currentTarget as HTMLImageElement;
		el.outerHTML = '<span class="font-display text-xl leading-none">P</span>';
	}
	function logoFallbackMobile(e: Event) {
		const el = e.currentTarget as HTMLImageElement;
		el.outerHTML = '<span class="font-display text-2xl leading-none">P</span>';
	}
</script>

<svelte:head>
	<title>Sign in — Atlas World Cup 2026 Pools</title>
</svelte:head>

<div class="min-h-screen lg:grid lg:grid-cols-2">
	<!-- ── Desktop editorial hero (lg+) ─────────────────────────────── -->
	<aside
		class="hidden lg:flex flex-col justify-between p-12 xl:p-16 relative overflow-hidden noise pitch-pattern bg-gradient-to-br from-secondary to-base-100"
	>
		<!-- soft gold glow accent -->
		<div class="absolute inset-0 bg-stadium-glow opacity-60 pointer-events-none"></div>

		<!-- Brand lockup (top) -->
		<div class="relative flex items-center gap-3">
			<img
				src="/logo.png"
				alt="Predictor"
				class="w-12 h-12 rounded-full object-cover"
				on:error={logoFallbackHero}
			/>
			<span class="font-display text-2xl tracking-wide">Atlas World Cup 2026 Pools</span>
		</div>

		<!-- Headline + explainer (centre) -->
		<div class="relative max-w-md">
			<p class="text-xs font-mono uppercase tracking-[0.18em] text-accent mb-4">World Cup 2026</p>
			<h1 class="font-display text-5xl xl:text-6xl leading-[0.95] tracking-wide mb-5">
				Call it before kickoff.
			</h1>
			<p class="text-base text-base-content/70 leading-relaxed">
				Predict every group game and the knockout bracket. Points for the right result, a bonus for
				the exact score — and your picks stay hidden until each match locks. May the sharpest
				forecaster top the table.
			</p>
		</div>

		<!-- Footer line (bottom) -->
		<p class="relative text-xs font-mono uppercase tracking-[0.18em] text-base-content/40">
			Atlas × JMFA · Vol. I
		</p>
	</aside>

	<!-- ── Auth form pane ───────────────────────────────────────────── -->
	<main class="flex items-center justify-center mobile-padding py-12 auth-bg noise min-h-screen lg:min-h-0">
		<div class="w-full max-w-md">
			<!-- Brand header — mobile/tablet only; the hero owns branding on lg+. -->
			<div class="flex items-center gap-3 justify-center mb-8 lg:hidden">
				<img
					src="/logo.png"
					alt="Predictor"
					class="w-14 h-14 rounded-full object-cover"
					on:error={logoFallbackMobile}
				/>
				<div class="flex flex-col leading-tight">
					<span class="font-display text-xl tracking-wide">Atlas World Cup 2026 Pools</span>
					<span class="text-[10px] font-mono uppercase tracking-[0.18em] text-base-content/50"
						>Vol. I — WC 2026</span
					>
				</div>
			</div>

			<SignInCard placement="login_page" />

			<!-- Footer hint -->
			<p class="text-center mt-6 text-xs text-base-content/40 font-mono uppercase tracking-widest">
				No account? Just submit your email — we'll create one.
			</p>
		</div>
	</main>
</div>
