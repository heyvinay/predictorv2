<script lang="ts">
	import { goto } from '$app/navigation';
	import { requestMagicLink, isAuthenticated, loading, error as authError } from '$stores/auth';
	import GoogleLoginButton from '$components/GoogleLoginButton.svelte';

	let email = '';
	let sent = false;
	let localError = '';
	let cooldown = 0;
	let cooldownTimer: ReturnType<typeof setInterval> | null = null;

	$: if ($isAuthenticated) {
		goto('/');
	}

	async function handleSubmit() {
		localError = '';
		if (!email) {
			localError = 'Please enter your email address';
			return;
		}
		const success = await requestMagicLink(email);
		if (success) {
			sent = true;
			startCooldown();
		}
	}

	async function handleResend() {
		if (cooldown > 0) return;
		const success = await requestMagicLink(email);
		if (success) startCooldown();
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
</script>

<svelte:head>
	<title>Sign in — Predictor</title>
</svelte:head>

<div class="min-h-screen flex items-center justify-center mobile-padding py-12 bg-base-100">
	<div class="w-full max-w-md">
		<!-- Brand header -->
		<div class="flex items-center gap-3 justify-center mb-8">
			<div
				class="w-14 h-14 rounded-full bg-gradient-to-br from-primary to-accent grid place-items-center ring-2 ring-primary/20 shadow-glow-gold"
			>
				<span
					class="text-2xl font-bold text-primary-content leading-none translate-y-0.5"
					>P</span
				>
			</div>
			<div class="flex flex-col leading-tight">
				<span class="font-display text-xl tracking-wide">The Predictor</span>
				<span
					class="text-[10px] font-mono uppercase tracking-[0.18em] text-base-content/50"
					>Vol. I — WC 2026</span
				>
			</div>
		</div>

		<!-- Auth card -->
		<div class="stadium-card no-glow p-7">
			{#if !sent}
				<!-- ── State 1: email form ──────────────────────────────────── -->
				<h1 class="font-display text-2xl tracking-wide mb-1">Sign in</h1>
				<p class="text-sm text-base-content/60 mb-6">
					We'll email you a one-time link — no password required.
				</p>

				{#if localError || $authError}
					<div class="alert alert-error mb-4 py-2">
						<span class="text-sm">{localError || $authError}</span>
					</div>
				{/if}

				<form class="space-y-4" on:submit|preventDefault={handleSubmit}>
					<div class="form-control">
						<label class="label py-1" for="email">
							<span class="label-text text-xs uppercase tracking-wider text-base-content/60"
								>Email</span
							>
						</label>
						<input
							id="email"
							type="email"
							class="input input-bordered w-full"
							placeholder="your@email.com"
							bind:value={email}
							disabled={$loading}
							autocomplete="email"
							autofocus
						/>
					</div>
					<button type="submit" class="btn btn-primary w-full" disabled={$loading}>
						{#if $loading}
							<span class="loading loading-spinner loading-sm"></span>
							Sending…
						{:else}
							Send me a link
						{/if}
					</button>
				</form>

				<div class="divider text-xs text-base-content/40 my-6">or continue with</div>

				<GoogleLoginButton disabled={$loading} />
			{:else}
				<!-- ── State 2: check-your-email confirmation ───────────────── -->
				<div class="flex flex-col items-center text-center">
					<div
						class="w-12 h-12 rounded-full bg-success/15 grid place-items-center mb-4"
					>
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
					<h1 class="font-display text-2xl tracking-wide mb-2">Check your email</h1>
					<p class="text-sm text-base-content/70 leading-relaxed">
						We sent a sign-in link to<br />
						<strong class="text-base-content">{email}</strong>
					</p>
					<p class="text-xs text-base-content/50 mt-2">
						The link expires in 15 minutes and can only be used once.
					</p>
				</div>

				<button
					type="button"
					class="btn btn-outline w-full mt-6"
					disabled={cooldown > 0 || $loading}
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
		<p
			class="text-center mt-6 text-xs text-base-content/40 font-mono uppercase tracking-widest"
		>
			No account? Just submit your email — we'll create one.
		</p>
	</div>
</div>
