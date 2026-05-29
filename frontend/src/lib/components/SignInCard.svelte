<!--
	SignInCard — magic-link + Google OAuth sign-in card.

	Used standalone on /login (wrapped in the editorial hero layout) and
	embedded inline in the landing-page hero so unauthenticated visitors
	can sign up without a detour to /login.

	Self-contained:
	  - All state (email, sent flag, cooldown timer, captcha token, widget
	    id) lives inside. The host page only positions the card.
	  - Reads `$stores/auth` directly for `requestMagicLink`, `$loading`,
	    `$authError`.
	  - Embeds `<GoogleLoginButton>` for OAuth.
	  - Honours Turnstile when `VITE_TURNSTILE_SITE_KEY` is set; renders
	    the widget and gates the Send button on a live token.
	  - Fires `signin_email_focused` / `signin_email_submitted` /
	    `signin_google_clicked` / `signin_abandoned` analytics events.
	    The abandoned event fires on email-blur-without-submit OR on
	    `beforeunload` — captures users who almost signed up.

	Props:
	  id?: string         — DOM id for anchor links (landing uses "signin").
	  placement?: string  — analytics tag (e.g. "hero" / "final_band" /
	                        "login_page"). Defaults to "standalone".
-->
<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { requestMagicLink, loading, error as authError } from '$stores/auth';
	import GoogleLoginButton from '$components/GoogleLoginButton.svelte';
	import { track } from '$lib/analytics';

	export let id: string | undefined = undefined;
	export let placement: string = 'standalone';

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

	// signin_abandoned tracking — fires when the user has touched the
	// email field but doesn't end up submitting (blur or page unload).
	let emailFocused = false;
	let emailSubmitted = false;
	let abandonedFired = false;

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

	function maybeFireAbandoned(charCount: number) {
		// Only fire once, only if the user touched the field, only if they
		// didn't actually submit.
		if (abandonedFired || !emailFocused || emailSubmitted) return;
		// Skip "abandon" for empty fields — they didn't really engage.
		if (charCount === 0) return;
		abandonedFired = true;
		track('signin_abandoned', { placement, chars_entered: charCount });
	}

	function onEmailFocus() {
		if (emailFocused) return;
		emailFocused = true;
		track('signin_email_focused', { placement });
	}

	function onEmailBlur(e: FocusEvent) {
		const value = (e.currentTarget as HTMLInputElement)?.value ?? '';
		maybeFireAbandoned(value.length);
	}

	function onBeforeUnload() {
		maybeFireAbandoned(email.length);
	}

	onMount(() => {
		window.addEventListener('beforeunload', onBeforeUnload);

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
		if (cooldownTimer) clearInterval(cooldownTimer);
		if (typeof window !== 'undefined') {
			window.removeEventListener('beforeunload', onBeforeUnload);
		}
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
		emailSubmitted = true;
		track('signin_email_submitted', { placement });
		const success = await requestMagicLink(email, captchaToken);
		if (success) {
			sent = true;
			startCooldown();
			resetWidget(); // single-use; mint a fresh token for any resend
		} else {
			// Submission failed at the API — let user retry, treat as
			// not-yet-submitted for abandon-tracking purposes.
			emailSubmitted = false;
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
		// Mid-flow reset = effectively a fresh card; clear abandon flags
		// too so a later real abandon still records.
		emailSubmitted = false;
		abandonedFired = false;
		if (cooldownTimer) {
			clearInterval(cooldownTimer);
			cooldownTimer = null;
		}
	}

	function onGoogleClick() {
		track('signin_google_clicked', { placement });
	}
</script>

<div {id} class="stadium-card no-glow p-7">
	{#if !sent}
		<h2 class="font-display text-2xl tracking-wide mb-1">Sign in</h2>
		<p class="text-sm text-base-content/60 mb-6">
			We'll email you a one-time link — no password required.
		</p>
	{:else}
		<div class="flex flex-col items-center text-center mb-6">
			<div class="w-12 h-12 rounded-full bg-success/15 grid place-items-center mb-4">
				<svg
					class="w-6 h-6 text-success"
					fill="none"
					viewBox="0 0 24 24"
					stroke="currentColor"
					stroke-width="2"
				>
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
					/>
				</svg>
			</div>
			<h2 class="font-display text-2xl tracking-wide mb-2">Check your email</h2>
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
			<label class="label py-1" for="signin-card-email">
				<span class="label-text text-xs uppercase tracking-wider text-base-content/60">Email</span>
			</label>
			<input
				id="signin-card-email"
				type="email"
				class="input input-bordered w-full"
				placeholder="your@email.com"
				bind:value={email}
				disabled={$loading || sent}
				autocomplete="email"
				on:focus={onEmailFocus}
				on:blur={onEmailBlur}
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
		<div on:click={onGoogleClick} on:keydown role="presentation">
			<GoogleLoginButton disabled={$loading} />
		</div>
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
