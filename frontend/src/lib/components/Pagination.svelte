<!--
	Pagination — footer for paginated lists.

	Renders:
	  "Showing 26–50 of 312"            [ Prev ] [ Next ]

	The parent owns `offset` and `limit`. This component just dispatches
	`prev` / `next` events; the parent decides what to do (usually:
	`offset = Math.max(0, offset - limit)` or `offset = offset + limit`).

	Hidden entirely when `total <= limit` (single page).
-->
<script lang="ts">
	import { createEventDispatcher } from 'svelte';

	export let total: number;
	export let limit: number;
	export let offset: number;

	const dispatch = createEventDispatcher<{ prev: void; next: void }>();

	$: from = total === 0 ? 0 : offset + 1;
	$: to = Math.min(total, offset + limit);
	$: hasPrev = offset > 0;
	$: hasNext = offset + limit < total;
	$: visible = total > limit;
</script>

{#if visible}
	<div class="flex items-center justify-between gap-3 mt-4 text-sm text-base-content/60">
		<span>
			Showing <span class="font-medium text-base-content">{from}–{to}</span> of
			<span class="font-medium text-base-content">{total}</span>
		</span>
		<div class="flex items-center gap-2">
			<button
				type="button"
				class="btn btn-outline btn-sm"
				disabled={!hasPrev}
				on:click={() => dispatch('prev')}
			>
				Prev
			</button>
			<button
				type="button"
				class="btn btn-outline btn-sm"
				disabled={!hasNext}
				on:click={() => dispatch('next')}
			>
				Next
			</button>
		</div>
	</div>
{/if}
