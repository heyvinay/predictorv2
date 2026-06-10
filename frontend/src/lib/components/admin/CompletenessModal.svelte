<script lang="ts">
	/** Entry completeness check modal (E.1, v2.163.0).
	 *
	 *  Report-only: lists eligible entries with missing picks so the admin
	 *  can chase them up out of band. The CSV download mirrors the table
	 *  (incompletes only). No disable / enforcement actions by design.
	 */
	import {
		downloadCompletenessCsv,
		fetchCompletenessCheck
	} from '$lib/api/admin';
	import type { EntryCompletenessResult } from '$lib/types/admin';

	export let open = false;
	export let onClose: () => void;

	let loading = false;
	let downloading = false;
	let error: string | null = null;
	let allResults: EntryCompletenessResult[] = [];
	let loadedOnce = false;

	$: incompletes = allResults.filter((r) => !r.is_complete);
	$: allComplete =
		!loading && error === null && loadedOnce && incompletes.length === 0;

	async function load() {
		loading = true;
		error = null;
		try {
			allResults = await fetchCompletenessCheck(false);
			loadedOnce = true;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to run completeness check';
			allResults = [];
		} finally {
			loading = false;
		}
	}

	// Re-run on every open so the admin always sees fresh state.
	$: if (open) load();

	async function handleDownload() {
		downloading = true;
		try {
			await downloadCompletenessCsv();
		} catch (e) {
			error = e instanceof Error ? e.message : 'CSV download failed';
		} finally {
			downloading = false;
		}
	}

	function handleKeydown(e: KeyboardEvent) {
		if (open && e.key === 'Escape') onClose();
	}
</script>

<svelte:window on:keydown={handleKeydown} />

{#if open}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-base-300/70 backdrop-blur-sm p-4"
		role="dialog"
		aria-modal="true"
		aria-labelledby="completeness-title"
	>
		<!-- Click-outside backdrop -->
		<button
			class="absolute inset-0 w-full h-full cursor-default"
			aria-label="Close"
			on:click={onClose}
			tabindex="-1"
		></button>

		<div
			class="relative bg-base-200 rounded-box shadow-card w-full max-w-3xl max-h-[85vh] flex flex-col border border-base-300/40"
		>
			<header
				class="flex items-center justify-between gap-3 p-4 border-b border-base-300/40"
			>
				<div>
					<h2 id="completeness-title" class="font-display text-xl tracking-wide">
						Entry completeness check
					</h2>
					<p class="text-xs text-base-content/55 mt-0.5">
						Every eligible entry must have all match, bracket, and bonus picks.
					</p>
				</div>
				<div class="flex items-center gap-2">
					<button
						class="btn btn-outline btn-sm gap-2"
						on:click={handleDownload}
						disabled={loading || downloading || incompletes.length === 0}
					>
						{downloading ? 'Downloading…' : 'Download CSV'}
					</button>
					<button class="btn btn-ghost btn-sm" on:click={onClose} aria-label="Close">
						✕
					</button>
				</div>
			</header>

			<div class="flex-1 overflow-y-auto p-4">
				{#if loading}
					<div class="flex justify-center py-12">
						<span class="loading loading-spinner loading-lg text-primary"></span>
					</div>
				{:else if error}
					<div class="text-error text-center py-8" role="alert">{error}</div>
				{:else if allComplete}
					<div class="bg-success/20 border border-success/40 rounded-btn p-4 text-center">
						<p class="text-success font-semibold">All eligible entries are complete ✓</p>
						<p class="text-base-content/55 text-sm mt-1">
							{allResults.length}
							{allResults.length === 1 ? 'eligible entry' : 'eligible entries'} checked — no gaps.
						</p>
					</div>
				{:else if incompletes.length > 0}
					<p class="text-sm text-base-content/70 mb-3">
						{incompletes.length} of {allResults.length} eligible entries have missing
						picks. Download the CSV to chase up.
					</p>
					<table class="table table-sm">
						<thead>
							<tr class="text-base-content/55">
								<th>Entry</th>
								<th>User</th>
								<th class="text-right">Matches</th>
								<th class="text-right">Bracket</th>
								<th class="text-right">Bonus</th>
							</tr>
						</thead>
						<tbody>
							{#each incompletes as r (r.entry_id)}
								<tr>
									<td class="font-medium">{r.entry_name}</td>
									<td>
										<div class="text-sm">{r.user_name}</div>
										<div class="text-xs text-base-content/55">{r.user_email}</div>
									</td>
									<td class="text-right {r.missing_match_picks > 0 ? 'text-error font-semibold' : 'text-base-content/30'}">
										{r.missing_match_picks}
									</td>
									<td class="text-right {r.missing_bracket_picks > 0 ? 'text-error font-semibold' : 'text-base-content/30'}">
										{r.missing_bracket_picks}
									</td>
									<td class="text-right {r.missing_bonus_picks > 0 ? 'text-error font-semibold' : 'text-base-content/30'}">
										{r.missing_bonus_picks}
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				{:else}
					<div class="text-center py-8 text-base-content/55">
						No eligible entries to check.
					</div>
				{/if}
			</div>
		</div>
	</div>
{/if}
