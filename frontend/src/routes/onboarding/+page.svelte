<script lang="ts">
	import { goto } from '$app/navigation';
	import { user, loading, error as authError } from '$stores/auth';
	import { updateProfile } from '$api/auth';

	let name = '';
	let localError = '';
	let saving = false;

	// Already has a name — skip straight to dashboard
	$: if ($user && $user.name) {
		goto('/', { replaceState: true });
	}

	// Not logged in — send to login
	$: if ($user === null && !$loading) {
		goto('/login', { replaceState: true });
	}

	async function handleSubmit() {
		localError = '';
		const trimmed = name.trim();
		if (!trimmed) {
			localError = 'Please enter a display name';
			return;
		}
		if (trimmed.length > 100) {
			localError = 'Name must be 100 characters or fewer';
			return;
		}

		saving = true;
		try {
			const updated = await updateProfile({ name: trimmed });
			user.set(updated);
			goto('/');
		} catch (e) {
			localError = e instanceof Error ? e.message : 'Could not save name';
		} finally {
			saving = false;
		}
	}
</script>

<svelte:head>
	<title>Welcome — Predictor</title>
</svelte:head>

<div class="pn">
	<div class="pn-auth-page">
		<div class="pn-auth-card">
			<div class="pn-auth-crest">
				<div class="crest">P</div>
				<div class="nm">The Predictor<span class="sub">Vol. I — WC 2026</span></div>
			</div>

			<h1 class="pn-auth-h">What should we <em>call you?</em></h1>

			<p class="pn-auth-info">
				This is the name your friends will see on the leaderboard.
			</p>

			{#if localError || $authError}
				<div class="pn-form-error">{localError || $authError}</div>
			{/if}

			<form class="pn-form" on:submit|preventDefault={handleSubmit}>
				<div class="pn-field">
					<label for="name">Display name</label>
					<input
						id="name"
						type="text"
						placeholder="Your name"
						bind:value={name}
						disabled={saving}
						autocomplete="name"
						maxlength="100"
					/>
				</div>
				<button
					type="submit"
					class="pn-btn"
					style="justify-content: center; margin-top: 6px;"
					disabled={saving}
				>
					{saving ? 'Saving…' : "Let's go"}
				</button>
			</form>
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
		margin: 0 0 16px;
	}
</style>
