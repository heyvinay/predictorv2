<!--
	Breadcrumb — generic Module → Section → Record navigator.

	Used in the topbar to navigate back up the hierarchy when the user is
	viewing a record's maintenance page. Each crumb except the last is a
	link (muted text); the last is the current location (semibold).

	Designed reusable: any future `Module → Section → Record` flow can
	pass its own crumb stack.
-->
<script lang="ts">
	export let crumbs: { label: string; href?: string }[] = [];
</script>

<nav class="flex items-center gap-2 text-sm min-w-0" aria-label="Breadcrumb">
	{#each crumbs as crumb, i (i)}
		{#if crumb.href && i < crumbs.length - 1}
			<a
				href={crumb.href}
				class="text-base-content/60 hover:text-base-content truncate transition-colors"
			>
				{crumb.label}
			</a>
		{:else}
			<span class="font-semibold truncate" aria-current={i === crumbs.length - 1 ? 'page' : undefined}>
				{crumb.label}
			</span>
		{/if}
		{#if i < crumbs.length - 1}
			<span class="text-base-content/30 flex-shrink-0" aria-hidden="true">›</span>
		{/if}
	{/each}
</nav>
