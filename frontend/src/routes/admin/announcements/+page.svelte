<script lang="ts">
	// Admin announcements (v2.165.0) — authoring surface for the V4
	// Dashboard hero. Create / edit / publish-toggle / delete; the
	// dashboard shows published cards newest-first (capped at 10).
	// Auth guards live in admin/+layout.svelte — none duplicated here.
	import { onMount } from 'svelte';
	import { pageTitle } from '$lib/stores/pageTitle';
	import {
		createAnnouncement,
		deleteAnnouncement,
		getAllAnnouncements,
		getAnnouncements,
		setAnnouncementHeroEnabled,
		updateAnnouncement
	} from '$api/announcements';
	import type { Announcement, AnnouncementTone, AnnouncementWrite } from '$lib/types/dashboard';

	let announcements: Announcement[] = [];
	let loading = true;
	let error: string | null = null;
	let heroEnabled = true;
	let heroToggling = false;

	// ── Form state (create or edit — editingId null = create) ──
	const TONES: { value: AnnouncementTone; label: string; hint: string }[] = [
		{ value: 'gold', label: 'Gold', hint: 'headline / matchday' },
		{ value: 'green', label: 'Green', hint: 'good news / payouts' },
		{ value: 'mute', label: 'Muted', hint: 'housekeeping / rules' }
	];
	let editingId: string | null = null;
	let formTag = 'Matchday';
	let formTone: AnnouncementTone = 'gold';
	let formTitle = '';
	let formBody = '';
	let formPublished = true;
	let saving = false;
	let formError: string | null = null;

	$: formValid =
		formTag.trim().length > 0 && formTitle.trim().length > 0 && formBody.trim().length > 0;

	onMount(() => {
		pageTitle.set('Announcements');
		void load();
	});

	async function load() {
		loading = true;
		error = null;
		try {
			const [all, resp] = await Promise.all([getAllAnnouncements(), getAnnouncements()]);
			announcements = all;
			heroEnabled = resp.hero_enabled;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load announcements';
		} finally {
			loading = false;
		}
	}

	async function handleHeroToggle() {
		heroToggling = true;
		try {
			await setAnnouncementHeroEnabled(heroEnabled);
		} catch (e) {
			heroEnabled = !heroEnabled;
			error = e instanceof Error ? e.message : 'Failed to update hero visibility';
		} finally {
			heroToggling = false;
		}
	}

	function startCreate() {
		editingId = null;
		formTag = 'Matchday';
		formTone = 'gold';
		formTitle = '';
		formBody = '';
		formPublished = true;
		formError = null;
	}

	function startEdit(a: Announcement) {
		editingId = a.id;
		formTag = a.tag;
		formTone = (['gold', 'green', 'mute'].includes(a.tone) ? a.tone : 'gold') as AnnouncementTone;
		formTitle = a.title;
		formBody = a.body;
		formPublished = a.published;
		formError = null;
	}

	async function save() {
		if (!formValid || saving) return;
		saving = true;
		formError = null;
		const payload: AnnouncementWrite = {
			tag: formTag.trim(),
			tone: formTone,
			title: formTitle.trim(),
			body: formBody.trim(),
			published: formPublished
		};
		try {
			if (editingId) {
				await updateAnnouncement(editingId, payload);
			} else {
				await createAnnouncement(payload);
			}
			startCreate();
			await load();
		} catch (e) {
			formError = e instanceof Error ? e.message : 'Save failed';
		} finally {
			saving = false;
		}
	}

	async function togglePublished(a: Announcement) {
		try {
			await updateAnnouncement(a.id, { published: !a.published });
			await load();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Update failed';
		}
	}

	async function remove(a: Announcement) {
		if (!confirm(`Delete "${a.title}"? This cannot be undone.`)) return;
		try {
			await deleteAnnouncement(a.id);
			if (editingId === a.id) startCreate();
			await load();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Delete failed';
		}
	}

	const TONE_BADGE: Record<string, string> = {
		gold: 'bg-primary/15 text-primary',
		green: 'bg-success/20 text-success',
		mute: 'bg-base-300/50 text-base-content/70'
	};

	function postedLabel(iso: string): string {
		return new Date(iso).toLocaleDateString('en-GB', {
			day: 'numeric',
			month: 'short',
			hour: '2-digit',
			minute: '2-digit'
		});
	}
</script>

<svelte:head>
	<title>Announcements · Admin · Predictor v2</title>
</svelte:head>

<div class="container mx-auto mobile-padding py-6 space-y-6">
	<!-- Hero visibility toggle -->
	<section class="rounded-xl border border-base-300/60 bg-base-200 shadow-card p-5">
		<div class="flex items-center justify-between gap-4">
			<div>
				<div class="font-semibold">Show announcement hero on dashboard</div>
				<div class="mt-0.5 text-xs text-base-content/55">
					When off, the hero section is completely hidden for all signed-in users —
					including the welcome card.
				</div>
			</div>
			<label class="label cursor-pointer gap-3 py-0">
				{#if heroToggling}
					<span class="loading loading-spinner loading-xs text-primary"></span>
				{/if}
				<input
					type="checkbox"
					class="toggle toggle-primary"
					bind:checked={heroEnabled}
					disabled={heroToggling}
					on:change={handleHeroToggle}
				/>
			</label>
		</div>
	</section>

	<!-- Composer -->
	<section class="rounded-xl border border-base-300/60 bg-base-200 shadow-card p-5">
		<h2 class="text-lg font-display tracking-wide mb-1">
			{editingId ? 'Edit announcement' : 'New announcement'}
		</h2>
		<p class="text-xs text-base-content/55 mb-4">
			Published announcements rotate in the dashboard hero for every signed-in player —
			newest first.
		</p>

		<div class="grid gap-3 sm:grid-cols-[1fr_auto]">
			<div class="form-control">
				<label class="label py-1" for="ann-tag">
					<span class="label-text text-xs">Tag (pill label)</span>
				</label>
				<input
					id="ann-tag"
					type="text"
					maxlength="32"
					class="input input-bordered input-sm"
					placeholder="Matchday / Prizes / Rules…"
					bind:value={formTag}
				/>
			</div>
			<div class="form-control">
				<span class="label py-1"><span class="label-text text-xs">Tone</span></span>
				<div class="join">
					{#each TONES as t (t.value)}
						<button
							type="button"
							class="btn btn-sm join-item {formTone === t.value ? 'btn-active' : 'btn-ghost'}"
							title={t.hint}
							on:click={() => (formTone = t.value)}>{t.label}</button
						>
					{/each}
				</div>
			</div>
		</div>

		<div class="form-control mt-2">
			<label class="label py-1" for="ann-title">
				<span class="label-text text-xs">Title</span>
			</label>
			<input
				id="ann-title"
				type="text"
				maxlength="120"
				class="input input-bordered input-sm"
				placeholder="One semi-final spot left tonight"
				bind:value={formTitle}
			/>
		</div>

		<div class="form-control mt-2">
			<label class="label py-1" for="ann-body">
				<span class="label-text text-xs">Body</span>
			</label>
			<textarea
				id="ann-body"
				rows="3"
				maxlength="2000"
				class="textarea textarea-bordered text-sm leading-relaxed"
				placeholder="A sentence or three. Plain text."
				bind:value={formBody}
			></textarea>
		</div>

		<div class="mt-3 flex flex-wrap items-center gap-3">
			<label class="label cursor-pointer gap-2 py-0">
				<input type="checkbox" class="toggle toggle-sm toggle-primary" bind:checked={formPublished} />
				<span class="label-text text-xs">Published</span>
			</label>
			<div class="ml-auto flex gap-2">
				{#if editingId}
					<button type="button" class="btn btn-ghost btn-sm" on:click={startCreate}>
						Cancel edit
					</button>
				{/if}
				<button
					type="button"
					class="btn btn-primary btn-sm"
					disabled={!formValid || saving}
					on:click={save}
				>
					{saving ? 'Saving…' : editingId ? 'Save changes' : 'Post announcement'}
				</button>
			</div>
		</div>
		{#if formError}
			<p class="mt-2 text-xs text-error">{formError}</p>
		{/if}
	</section>

	<!-- List -->
	<section class="rounded-xl border border-base-300/60 bg-base-200 shadow-card p-5">
		<h2 class="text-lg font-display tracking-wide mb-3">
			All announcements
			<span class="text-xs text-base-content/40">· {announcements.length}</span>
		</h2>

		{#if loading}
			<div class="flex justify-center py-8">
				<span class="loading loading-spinner text-primary"></span>
			</div>
		{:else if error}
			<p class="text-sm text-error">{error}</p>
		{:else if announcements.length === 0}
			<p class="text-sm text-base-content/55">
				Nothing yet — the dashboard hero shows a generic welcome card until the first
				announcement is published.
			</p>
		{:else}
			<ul class="divide-y divide-base-300/40">
				{#each announcements as a (a.id)}
					<li class="flex flex-col gap-2 py-3 sm:flex-row sm:items-start sm:justify-between">
						<div class="min-w-0">
							<div class="flex flex-wrap items-center gap-2">
								<span
									class="rounded-badge px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-[0.14em] {TONE_BADGE[
										a.tone
									] ?? TONE_BADGE.gold}">{a.tag}</span
								>
								<span class="font-semibold text-sm {a.published ? '' : 'text-base-content/50'}"
									>{a.title}</span
								>
								{#if !a.published}
									<span class="badge badge-ghost badge-xs">unpublished</span>
								{/if}
							</div>
							<p class="mt-1 line-clamp-2 text-xs text-base-content/60">{a.body}</p>
							<p class="mt-1 text-[11px] text-base-content/40">
								{a.author_name} · {postedLabel(a.created_at)}
							</p>
						</div>
						<div class="flex flex-none gap-1.5">
							<button type="button" class="btn btn-ghost btn-xs" on:click={() => startEdit(a)}>
								Edit
							</button>
							<button
								type="button"
								class="btn btn-ghost btn-xs"
								on:click={() => togglePublished(a)}
							>
								{a.published ? 'Unpublish' : 'Publish'}
							</button>
							<button
								type="button"
								class="btn btn-ghost btn-xs text-error"
								on:click={() => remove(a)}
							>
								Delete
							</button>
						</div>
					</li>
				{/each}
			</ul>
		{/if}
	</section>
</div>
