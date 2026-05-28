<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { handleOAuthCallback } from '$stores/auth';

	let error = '';

	onMount(async () => {
		const token = $page.url.searchParams.get('token');
		const errorParam = $page.url.searchParams.get('error');

		if (errorParam) {
			error = errorParam;
			return;
		}

		if (token) {
			// Wait for user load so the next route mounts with $user populated
			// (otherwise the dashboard's auth reactive can fire `goto('/login')`
			// during the transient window between token-set and user-load).
			await handleOAuthCallback(token);

			// returnTo round-trip (R7): if the user was deep-linked through
			// /login?returnTo=/entries/X, restore that destination. Strict
			// anti-open-redirect: must start with a single '/'; reject absolute
			// URLs, protocol-relative URLs, and anything malformed.
			let dest = '/';
			try {
				const rt = sessionStorage.getItem('predictor_returnTo');
				if (rt && rt.startsWith('/') && !rt.startsWith('//')) {
					dest = rt;
				}
				sessionStorage.removeItem('predictor_returnTo');
			} catch {
				/* sessionStorage unavailable — fall through to dashboard */
			}
			goto(dest);
		} else {
			error = 'No authentication token received';
		}
	});
</script>

<svelte:head>
	<title>Authenticating... - Predictor v2</title>
</svelte:head>

<div class="auth-bg flex items-center justify-center px-4 py-12">
	{#if error}
		<div class="stadium-card p-6 sm:p-8 text-center max-w-md w-full">
			<h2 class="text-xl font-display tracking-wide text-error mb-2">Authentication Failed</h2>
			<p class="text-base-content/70 text-sm">{error}</p>
			<div class="mt-6">
				<a href="/login" class="btn btn-primary">Back to Login</a>
			</div>
		</div>
	{:else}
		<div class="text-center">
			<span class="loading loading-spinner loading-lg text-primary"></span>
			<p class="mt-4 text-base-content/70">Completing authentication...</p>
		</div>
	{/if}
</div>
