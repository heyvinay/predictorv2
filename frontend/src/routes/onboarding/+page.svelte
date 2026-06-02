<script lang="ts">
	import { get } from 'svelte/store';
	import { goto } from '$app/navigation';
	import { user, loading, error as authError } from '$stores/auth';
	import { updateProfile } from '$api/auth';
	import { needsOnboarding } from '$lib/utils/onboarding';
	import { loadEntries, entries } from '$stores/entries';
	import { createEntry } from '$api/entries';
	import type { Employer, UserUpdate } from '$types';

	const EMPLOYER_OPTIONS: { v: Employer; l: string }[] = [
		{ v: 'atlas', l: 'Atlas' },
		{ v: 'jmfa', l: 'JMFA' },
		{ v: 'neither', l: 'Neither' }
	];

	let name = '';
	let employer: Employer | '' = '';
	let companyContact = '';
	let localError = '';
	let saving = false;
	let prefilled = false;
	// While handleSubmit is mid-flight, the user.set(updated) call below
	// would otherwise trip the "needsOnboarding → goto('/')" reactive
	// below and race our ensure-entry + goto-wizard flow. The flag
	// suppresses that redirect path; handleSubmit owns navigation while
	// it's running.
	let handlingSubmit = false;

	// Prefill name for users who already have one (e.g. Google sign-ups
	// routed here to complete the new mandatory fields).
	$: if ($user && !prefilled) {
		name = $user.name ?? '';
		employer = $user.employer ?? '';
		companyContact = $user.company_contact ?? '';
		prefilled = true;
	}

	// Onboarding complete — go to the dashboard. Suppressed while
	// handleSubmit is owning the navigation (it routes to a wizard
	// instead of /, see Tweak 2b in stay-in-plan-mode-dynamic-adleman.md).
	$: if ($user && !needsOnboarding($user) && !handlingSubmit) {
		goto('/', { replaceState: true });
	}

	// Not logged in — send to login
	$: if ($user === null && !$loading) {
		goto('/login', { replaceState: true });
	}

	// Reactive form validity — drives the disabled state of "Let's go".
	// This replaces the old "click → red error" pattern, which had a stale-
	// state bug (errors lingered after the user corrected the selection).
	// The backend's model_validator stays as the safety net.
	$: trimmedName = name.trim();
	$: trimmedContact = companyContact.trim();
	$: canSubmit =
		!!trimmedName &&
		trimmedName.length <= 100 &&
		!!employer &&
		(employer !== 'neither' || !!trimmedContact);

	async function handleSubmit() {
		if (!canSubmit) return;
		localError = '';

		const payload: UserUpdate = { name: trimmedName, employer: employer as Employer };
		if (employer === 'neither') payload.company_contact = trimmedContact;

		saving = true;
		handlingSubmit = true;
		try {
			const updated = await updateProfile(payload);
			user.set(updated);

			// Ensure the user has at least one entry, then jump straight to
			// picks. loadEntries auto-creates when settings.auto_create_first_entry
			// is true (stores/entries.ts:142). When the flag is false, fall
			// through to a manual createEntry so the user still lands on a
			// usable wizard rather than the `/` zero-state card.
			await loadEntries(updated.id);
			let firstId = get(entries)[0]?.id;
			if (!firstId) {
				const created = await createEntry({});
				await loadEntries(updated.id);
				firstId = created.id;
			}
			await goto(`/entries/${firstId}`);
		} catch (e) {
			localError = e instanceof Error ? e.message : 'Could not save your details';
			handlingSubmit = false;
		} finally {
			saving = false;
		}
	}

	function logoFallback(e: Event) {
		const el = e.currentTarget as HTMLImageElement;
		el.outerHTML = '<span class="font-display text-2xl leading-none">P</span>';
	}
</script>

<svelte:head>
	<title>Welcome — Atlas World Cup 2026 Pools</title>
</svelte:head>

<div class="min-h-screen flex items-center justify-center mobile-padding py-12 auth-bg noise">
	<div class="w-full max-w-md">
		<!-- Brand header -->
		<div class="flex items-center gap-3 justify-center mb-8">
			<img
				src="/logo.png"
				alt="Predictor"
				class="w-14 h-14 rounded-full object-cover"
				on:error={logoFallback}
			/>
			<div class="flex flex-col leading-tight">
				<span class="font-display text-xl tracking-wide">Atlas World Cup 2026 Pools</span>
				<span class="text-[10px] font-mono uppercase tracking-[0.18em] text-base-content/50">Vol. I — WC 2026</span>
			</div>
		</div>

		<!-- Onboarding card -->
		<div class="stadium-card no-glow p-7">
			<p class="text-xs font-mono uppercase tracking-[0.18em] text-primary mb-2">Welcome</p>
			<h1 class="font-display text-3xl tracking-wide mb-2">Tell us about you</h1>
			<p class="text-sm text-base-content/60 mb-6">
				A few details so we can set up your pool. You can change these later in your profile.
			</p>

			{#if localError || $authError}
				<div class="alert alert-error mb-4 py-2">
					<span class="text-sm">{localError || $authError}</span>
				</div>
			{/if}

			<form class="space-y-5" on:submit|preventDefault={handleSubmit}>
				<!-- Full name -->
				<div class="form-control">
					<label class="label py-1" for="name">
						<span class="label-text text-xs uppercase tracking-wider text-base-content/60">Full name</span>
					</label>
					<input
						id="name"
						type="text"
						class="input input-bordered w-full"
						placeholder="Your full name"
						bind:value={name}
						disabled={saving}
						autocomplete="name"
						maxlength={100}
					/>
				</div>

				<!-- Employer -->
				<div class="form-control">
					<span class="label-text text-xs uppercase tracking-wider text-base-content/60 mb-2 block">Where do you work?</span>
					<div class="grid grid-cols-3 gap-2">
						{#each EMPLOYER_OPTIONS as opt}
							<button
								type="button"
								disabled={saving}
								class="btn btn-sm normal-case {employer === opt.v ? 'btn-primary' : 'btn-outline'}"
								aria-pressed={employer === opt.v}
								on:click={() => (employer = opt.v)}
							>
								{opt.l}
							</button>
						{/each}
					</div>
				</div>

				<!-- Conditional company contact -->
				{#if employer === 'neither'}
					<div class="form-control">
						<label class="label py-1" for="contact">
							<span class="label-text text-xs uppercase tracking-wider text-base-content/60">Who is your contact at Atlas or JMFA</span>
						</label>
						<input
							id="contact"
							type="text"
							class="input input-bordered w-full"
							placeholder="Name of your contact"
							bind:value={companyContact}
							disabled={saving}
							maxlength={100}
						/>
					</div>
				{/if}

				<button type="submit" class="btn btn-primary w-full" disabled={saving || !canSubmit}>
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
