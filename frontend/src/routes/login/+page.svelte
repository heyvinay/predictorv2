<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { requestMagicLink, isAuthenticated, loading, error as authError } from '$stores/auth';
	import GoogleLoginButton from '$components/GoogleLoginButton.svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';

	// returnTo (R7): if the user arrived from a protected route (e.g. clicked
	// a deep link in the submission email while signed out), the wizard
	// appended ?returnTo=/entries/{id}. Stash it in sessionStorage so it
	// survives the email round-trip to the magic-link verify endpoint, then
	// /auth/callback restores it.
	const RETURN_TO_KEY = 'predictor_returnTo';

	interface TurnstileApi {
		render: (el: HTMLElement, opts: Record<string, unknown>) => string;
		reset: (id?: string) => void;
		remove: (id?: string) => void;
	}
	const win = (typeof window !== 'undefined' ? window : undefined) as
		| (Window & { turnstile?: TurnstileApi })
		| undefined;

	const siteKey: string | undefined = import.meta.env.VITE_TURNSTILE_SITE_KEY;
	const captchaEnabled = !!siteKey;

	let email = '';
	let sent = false;
	let localError = '';
	let cooldown = 0;
	let cooldownTimer: ReturnType<typeof setInterval> | null = null;

	// Turnstile state.
	let captchaToken: string | null = null;
	let turnstileEl: HTMLElement | null = null;
	let widgetId: string | null = null;

	$: if ($isAuthenticated) {
		goto('/');
	}

	// "Send" is gated on a live Turnstile token (when CAPTCHA is enabled).
	$: sendDisabled = $loading || (captchaEnabled && !captchaToken);

	const TURNSTILE_SRC = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';

	function renderWidget() {
		if (!captchaEnabled || !turnstileEl || !win?.turnstile || widgetId) return;
		widgetId = win.turnstile.render(turnstileEl, {
			sitekey: siteKey,
			callback: (token: string) => {
				captchaToken = token;
			},
			'expired-callback': () => {
				captchaToken = null;
			},
			'error-callback': () => {
				captchaToken = null;
			}
		});
	}

	function resetWidget() {
		captchaToken = null;
		if (widgetId && win?.turnstile) win.turnstile.reset(widgetId);
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

		if (!captchaEnabled) return;
		if (win?.turnstile) {
			renderWidget();
			return;
		}
		// Inject the script once; render on load.
		let script = document.querySelector<HTMLScriptElement>(`script[src^="${TURNSTILE_SRC}"]`);
		if (!script) {
			script = document.createElement('script');
			script.src = TURNSTILE_SRC;
			script.async = true;
			script.defer = true;
			document.head.appendChild(script);
		}
		script.addEventListener('load', renderWidget);
	});

	onDestroy(() => {
		if (widgetId && win?.turnstile) win.turnstile.remove(widgetId);
	});

	async function handleSubmit() {
		localError = '';
		if (!email) {
			localError = 'Please enter your email address';
			return;
		}
		if (captchaEnabled && !captchaToken) {
			localError = 'Please complete the human check';
			return;
		}
		const success = await requestMagicLink(email, captchaToken);
		if (success) {
			sent = true;
			startCooldown();
			resetWidget(); // single-use; mint a fresh token for any resend
		}
	}

	async function handleResend() {
		if (cooldown > 0) return;
		if (captchaEnabled && !captchaToken) {
			localError = 'Please complete the human check again';
			return;
		}
		const success = await requestMagicLink(email, captchaToken);
		if (success) {
			startCooldown();
			resetWidget();
		}
	}

	function startCooldown() {
		cooldown = 60;
		if (cooldownTimer) clearInterval(cooldownTimer);
		cooldownTimer = setInterval(() => {
			cooldown--;
			if (cooldown <= 0 && cooldownTimer) {
				clearInterval(cooldownTimer);
				cooldownTimer = null;
			}
		}, 1000);
	}

	function reset() {
		sent = false;
		localError = '';
		cooldown = 0;
		if (cooldownTimer) {
			clearInterval(cooldownTimer);
			cooldownTimer = null;
		}
	}

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
					<span class="text-[10px] font-mono uppercase tracking-[0.18em] text-base-content/50">Vol. I — WC 2026</span>
				</div>
			</div>

			<!-- Auth card. The <form> (with the email input + Turnstile widget)
			     stays mounted across both states so the widget persists and
			     resend can mint a fresh single-use token; only the surrounding
			     chrome toggles on `sent`. -->
			<div class="stadium-card no-glow p-7">
				{#if !sent}
					<h1 class="font-display text-2xl tracking-wide mb-1">Sign in</h1>
					<p class="text-sm text-base-content/60 mb-6">
						We'll email you a one-time link — no password required.
					</p>
				{:else}
					<div class="flex flex-col items-center text-center mb-6">
						<div class="w-12 h-12 rounded-full bg-success/15 grid place-items-center mb-4">
							<svg class="w-6 h-6 text-success" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
								<path stroke-linecap="round" stroke-linejoin="round" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
							</svg>
						</div>
						<h1 class="font-display text-2xl tracking-wide mb-2">Check your email</h1>
						<p class="text-sm text-base-content/70 leading-relaxed">
							We sent a sign-in link to<br />
							<strong class="text-base-content">{email}</strong>
						</p>
						<p class="text-xs text-base-content/50 mt-2">
							The link expires in 15 minutes and can only be used once.
						</p>
					</div>
				{/if}

				{#if localError || $authError}
					<div class="alert alert-error mb-4 py-2">
						<span class="text-sm">{localError || $authError}</span>
					</div>
				{/if}

				<form class="space-y-4" on:submit|preventDefault={handleSubmit}>
					<div class="form-control" class:hidden={sent}>
						<label class="label py-1" for="email">
							<span class="label-text text-xs uppercase tracking-wider text-base-content/60">Email</span>
						</label>
						<input
							id="email"
							type="email"
							class="input input-bordered w-full"
							placeholder="your@email.com"
							bind:value={email}
							disabled={$loading || sent}
							autocomplete="email"
						/>
					</div>

					<!-- Persistent across states; visually hidden once sent so the
					     managed widget can still refresh the token for resend. -->
					{#if captchaEnabled}
						<div bind:this={turnstileEl} class="flex justify-center" class:sr-only={sent}></div>
					{/if}

					{#if !sent}
						<button type="submit" class="btn btn-primary w-full" disabled={sendDisabled}>
							{#if $loading}
								<span class="loading loading-spinner loading-sm"></span>
								Sending…
							{:else}
								Send me a link
							{/if}
						</button>
					{:else}
						<button
							type="button"
							class="btn btn-outline w-full"
							disabled={cooldown > 0 || sendDisabled}
							on:click={handleResend}
						>
							{#if cooldown > 0}
								Resend in {cooldown}s
							{:else if $loading}
								<span class="loading loading-spinner loading-sm"></span>
								Sending…
							{:else}
								Didn't get it? Resend
							{/if}
						</button>
					{/if}
				</form>

				{#if !sent}
					<div class="divider text-xs text-base-content/40 my-6">or continue with</div>
					<GoogleLoginButton disabled={$loading} />
				{:else}
					<div class="text-center mt-4">
						<button
							type="button"
							class="text-xs font-mono uppercase tracking-widest text-base-content/50 hover:text-base-content underline"
							on:click={reset}
						>
							Use a different email
						</button>
					</div>
				{/if}
			</div>

			<!-- Footer hint -->
			<p class="text-center mt-6 text-xs text-base-content/40 font-mono uppercase tracking-widest">
				No account? Just submit your email — we'll create one.
			</p>
		</div>
	</main>
</div>
