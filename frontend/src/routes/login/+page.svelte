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

<div class="pn">
	<div class="pn-auth-page">
		<div class="pn-auth-card">
			<div class="pn-auth-crest">
				<div class="crest">P</div>
				<div class="nm">The Predictor<span class="sub">Vol. I — WC 2026</span></div>
			</div>

			{#if !sent}
				<!-- State 1: Email form -->
				<h1 class="pn-auth-h">Sign <em>in</em></h1>

				{#if localError || $authError}
					<div class="pn-form-error">{localError || $authError}</div>
				{/if}

				<form class="pn-form" on:submit|preventDefault={handleSubmit}>
					<div class="pn-field">
						<label for="email">Email</label>
						<input
							id="email"
							type="email"
							placeholder="your@email.com"
							bind:value={email}
							disabled={$loading}
						/>
					</div>
					<button
						type="submit"
						class="pn-btn"
						style="justify-content: center; margin-top: 6px;"
						disabled={$loading}
					>
						{$loading ? 'Sending…' : 'Send me a link'}
					</button>
				</form>

				<div class="pn-auth-divider">or continue with</div>
				<GoogleLoginButton disabled={$loading} />
			{:else}
				<!-- State 2: Check email -->
				<h1 class="pn-auth-h">Check your <em>email</em></h1>

				<p class="pn-auth-info">
					We sent a sign-in link to <strong>{email}</strong>.<br />
					Click it to sign in — the link expires in 15 minutes.
				</p>

				<button
					class="pn-btn"
					style="justify-content: center; width: 100%; margin-top: 16px;"
					disabled={cooldown > 0 || $loading}
					on:click={handleResend}
				>
					{cooldown > 0 ? `Resend in ${cooldown}s` : $loading ? 'Sending…' : "Didn't get it? Resend"}
				</button>

				<p class="pn-auth-footer" style="margin-top: 16px;">
					<button class="pn-link-btn" on:click={reset}>Use a different email</button>
				</p>
			{/if}
		</div>
	</div>
</div>

<style>
	.pn-auth-info {
		font-family: var(--body);
		font-size: 14px;
		color: var(--ink-2);
		line-height: 1.6;
		text-align: center;
		margin: 0 0 8px;
	}

	.pn-link-btn {
		background: none;
		border: none;
		padding: 0;
		font-family: var(--mono);
		font-size: 11px;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: var(--ink-3);
		cursor: pointer;
		text-decoration: underline;
	}

	.pn-link-btn:hover {
		color: var(--ink);
	}
</style>
