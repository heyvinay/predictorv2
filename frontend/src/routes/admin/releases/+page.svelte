<script lang="ts">
	// Release notes — every May 2026+ commit noted, latest first.
	// Sourced from frontend/src/lib/data/changelog.json (bundled at build time).
	// Filterable by type; defaults to showing the 50 most-recent entries
	// with a "Show more" button. Moved out of /admin/+page.svelte in v2.160.0
	// so the Overview is no longer a kitchen-sink.
	import { onMount } from 'svelte';
	import changelogData from '$lib/data/changelog.json';
	import { pageTitle } from '$lib/stores/pageTitle';

	type ReleaseEntry = {
		version: string;
		date: string;
		type: string;
		summary: string;
		commit: string;
	};

	// Changelog ships oldest-first; UI wants newest-first.
	const allReleases: ReleaseEntry[] = (
		[...changelogData.entries] as ReleaseEntry[]
	).reverse();
	const releaseTypes = [
		'all',
		'feature',
		'improvement',
		'fix',
		'internal',
		'merge'
	] as const;
	let releaseFilter: (typeof releaseTypes)[number] = 'all';
	let releaseLimit = 50;
	$: filteredReleases =
		releaseFilter === 'all'
			? allReleases
			: allReleases.filter((r) => r.type === releaseFilter);
	$: visibleReleases = filteredReleases.slice(0, releaseLimit);
	$: latestVersion = allReleases[0]?.version ?? '—';

	const RELEASE_TYPE_BADGE: Record<string, string> = {
		feature: 'badge-success',
		improvement: 'badge-info',
		fix: 'badge-warning',
		internal: 'badge-ghost',
		merge: 'badge-primary'
	};
	const RELEASE_TYPE_LABEL: Record<string, string> = {
		feature: 'New',
		improvement: 'Polish',
		fix: 'Fix',
		internal: 'Internal',
		merge: 'Merge'
	};

	onMount(() => {
		pageTitle.set(`Release Notes · latest ${latestVersion} · ${allReleases.length} entries`);
	});
</script>

<svelte:head>
	<title>Release Notes · Admin · Predictor v2</title>
</svelte:head>

<div class="container mx-auto mobile-padding py-6 space-y-6">
	<section class="rounded-xl border bg-base-200 shadow-card p-5">
		<h2 class="text-lg font-display tracking-wide mb-3">
			Release Notes
			<span class="text-xs text-base-content/40">
				· latest {latestVersion} · {allReleases.length} entries
			</span>
		</h2>

		<div class="flex flex-wrap gap-1.5 mb-4">
			{#each releaseTypes as t}
				<button
					type="button"
					class="btn btn-xs {releaseFilter === t ? 'btn-primary' : 'btn-ghost'}"
					on:click={() => {
						releaseFilter = t;
						releaseLimit = 50;
					}}
				>
					{t === 'all' ? 'All' : RELEASE_TYPE_LABEL[t] ?? t}
					<span class="ml-1 opacity-60">
						{t === 'all'
							? allReleases.length
							: allReleases.filter((r) => r.type === t).length}
					</span>
				</button>
			{/each}
		</div>

		{#if filteredReleases.length === 0}
			<p class="text-sm text-base-content/50">No entries match this filter.</p>
		{:else}
			<ol class="space-y-2">
				{#each visibleReleases as r (`${r.version}-${r.commit}`)}
					<li class="flex items-start gap-3 rounded-lg border border-base-300/40 p-3">
						<div class="flex-shrink-0 w-20 text-right">
							<div class="font-mono text-xs font-semibold tracking-tight">{r.version}</div>
							<div class="text-[10px] text-base-content/50 mt-0.5">{r.date}</div>
						</div>
						<div class="flex-1 min-w-0">
							<div class="flex items-start gap-2 flex-wrap">
								<span class="badge badge-sm {RELEASE_TYPE_BADGE[r.type] ?? 'badge-ghost'}">
									{RELEASE_TYPE_LABEL[r.type] ?? r.type}
								</span>
								<p class="text-sm text-base-content/90 flex-1 min-w-0">{r.summary}</p>
							</div>
							<div class="text-[10px] text-base-content/40 font-mono mt-1">{r.commit}</div>
						</div>
					</li>
				{/each}
			</ol>

			{#if visibleReleases.length < filteredReleases.length}
				<div class="text-center mt-4">
					<button
						type="button"
						class="btn btn-sm btn-outline"
						on:click={() => (releaseLimit += 50)}
					>
						Show more
						<span class="opacity-60">
							({filteredReleases.length - visibleReleases.length} remaining)
						</span>
					</button>
				</div>
			{/if}
		{/if}
	</section>
</div>
