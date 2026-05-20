<script lang="ts">
	import { goto } from '$app/navigation';
	import { register, isAuthenticated, loading, error as authError } from '$stores/auth';
	import ErrorAlert from '$components/ErrorAlert.svelte';
	import GoogleLoginButton from '$components/GoogleLoginButton.svelte';

	let name = '';
	let email = '';
	let password = '';
	let confirmPassword = '';
	let localError = '';

	$: if ($isAuthenticated) {
		goto('/');
	}

	async function handleSubmit() {
		localError = '';

		if (!name || !email || !password || !confirmPassword) {
			localError = 'Please fill in all fields';
			return;
		}

		if (password.length < 8) {
			localError = 'Password must be at least 8 characters';
			return;
		}

		if (password !== confirmPassword) {
			localError = 'Passwords do not match';
			return;
		}

		const success = await register({ name, email, password });
		if (success) {
			goto('/');
		}
	}
</script>

<svelte:head>
	<title>Register - Predictor v2</title>
</svelte:head>

<div class="auth-bg flex items-center justify-center px-4 py-12">
	<div class="w-full max-w-md animate-slide-up">
		<!-- Logo/Brand -->
		<div class="text-center mb-8">
			<h1 class="text-5xl font-display tracking-wider text-gradient mb-2">PREDICTOR</h1>
			<p class="text-base-content/50 text-sm">World Cup 2026 Predictions</p>
		</div>

		<!-- Register Card -->
		<div class="stadium-card p-6 sm:p-8">
			<h2 class="text-2xl font-display tracking-wide text-center mb-6">Create Account</h2>

			<ErrorAlert message={localError || $authError} />

			<form on:submit|preventDefault={handleSubmit} class="space-y-4">
				<div>
					<label class="block text-sm font-medium text-base-content/70 mb-2" for="name">
						Display Name
					</label>
					<input
						id="name"
						type="text"
						placeholder="Your name"
						class="auth-input"
						bind:value={name}
						disabled={$loading}
					/>
				</div>

				<div>
					<label class="block text-sm font-medium text-base-content/70 mb-2" for="email">
						Email
					</label>
					<input
						id="email"
						type="email"
						placeholder="your@email.com"
						class="auth-input"
						bind:value={email}
						disabled={$loading}
					/>
				</div>

				<div>
					<label class="block text-sm font-medium text-base-content/70 mb-2" for="password">
						Password
					</label>
					<input
						id="password"
						type="password"
						placeholder="••••••••"
						class="auth-input"
						bind:value={password}
						disabled={$loading}
					/>
					<p class="mt-1.5 text-xs text-base-content/40">Minimum 8 characters</p>
				</div>

				<div>
					<label class="block text-sm font-medium text-base-content/70 mb-2" for="confirmPassword">
						Confirm Password
					</label>
					<input
						id="confirmPassword"
						type="password"
						placeholder="••••••••"
						class="auth-input"
						bind:value={confirmPassword}
						disabled={$loading}
					/>
				</div>

				<button
					type="submit"
					class="w-full btn btn-primary btn-lg font-semibold gap-2 mt-2"
					disabled={$loading}
				>
					{#if $loading}
						<span class="loading loading-spinner loading-sm"></span>
					{/if}
					Create Account
				</button>
			</form>

			<div class="relative my-6">
				<div class="absolute inset-0 flex items-center">
					<div class="w-full border-t border-base-300"></div>
				</div>
				<div class="relative flex justify-center">
					<span class="px-4 text-sm text-base-content/40 bg-base-200">or continue with</span>
				</div>
			</div>

			<GoogleLoginButton disabled={$loading} />

			<p class="text-center text-sm text-base-content/50 mt-6">
				Already have an account?
				<a href="/login" class="text-primary hover:text-primary/80 transition-colors font-medium">
					Sign in
				</a>
			</p>
		</div>
	</div>
</div>
