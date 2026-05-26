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

<div class="min-h-screen flex items-center justify-center mobile-padding py-12 auth-bg noise">
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

		<!-- Onboarding card -->
		<div class="stadium-card no-glow p-7">
			<p class="text-xs font-mono uppercase tracking-[0.18em] text-primary mb-2">Welcome</p>
			<h1 class="font-display text-3xl tracking-wide mb-2">What should we call you?</h1>
			<p class="text-sm text-base-content/60 mb-6">
				This is the name your friends will see on the leaderboard. You can change it later in your profile.
			</p>

			{#if localError || $authError}
				<div class="alert alert-error mb-4 py-2">
					<span class="text-sm">{localError || $authError}</span>
				</div>
			{/if}

			<form class="space-y-4" on:submit|preventDefault={handleSubmit}>
				<div class="form-control">
					<label class="label py-1" for="name">
						<span class="label-text text-xs uppercase tracking-wider text-base-content/60"
							>Display name</span
						>
					</label>
					<input
						id="name"
						type="text"
						class="input input-bordered w-full"
						placeholder="Your name"
						bind:value={name}
						disabled={saving}
						autocomplete="name"
						maxlength={100}
						autofocus
					/>
				</div>
				<button type="submit" class="btn btn-primary w-full" disabled={saving}>
					{#if saving}
						<span class="loading loading-spinner loading-sm"></span>
						Saving…
					{:else}
						Let's go
					{/if}
				</button>
			</form>
		</div>
	</div>
</div>
