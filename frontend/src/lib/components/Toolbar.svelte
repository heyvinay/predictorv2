<!--
	Toolbar — generic horizontal action row above a list/table.

	Layout (left → right):
	  [ search input (flex-1) ] [ filter slot ] [ trailing actions slot ]

	Usage:
	  <Toolbar bind:search>
	    <svelte:fragment slot="filters">
	      <select ...></select>
	      <select ...></select>
	    </svelte:fragment>
	    <svelte:fragment slot="actions">
	      <button class="btn btn-outline btn-sm">Export</button>
	    </svelte:fragment>
	  </Toolbar>

	The search slot is always present; pass `searchPlaceholder=""` to hide
	it, or omit `bind:search` if not needed.
-->
<script lang="ts">
	export let search: string = '';
	export let searchPlaceholder: string = 'Search…';
	/** Optional: passed up on `Enter` or `change` if the parent wants explicit
	 * commit semantics (e.g. server-side search). Otherwise the parent can
	 * react to the bound `search` value directly. */
	export let onSearchCommit: ((value: string) => void) | undefined = undefined;

	function handleKey(e: KeyboardEvent) {
		if (e.key === 'Enter' && onSearchCommit) onSearchCommit(search);
	}
	function handleChange() {
		if (onSearchCommit) onSearchCommit(search);
	}
</script>

<div class="flex flex-wrap items-center gap-2 mb-4">
	{#if searchPlaceholder}
		<input
			type="search"
			class="input input-bordered input-sm flex-1 min-w-[12rem]"
			placeholder={searchPlaceholder}
			bind:value={search}
			on:keydown={handleKey}
			on:change={handleChange}
		/>
	{/if}
	<slot name="filters" />
	<slot name="actions" />
</div>
