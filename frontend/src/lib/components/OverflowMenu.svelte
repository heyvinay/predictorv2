<!--
	OverflowMenu — vertical-dots dropdown for per-row actions.

	A thin DaisyUI `dropdown dropdown-end` wrapper. The trigger is a
	16×16 vertical-ellipsis icon button; the panel is a regular
	`menu menu-sm` populated by the consumer via the default slot.

	Usage:
	  <OverflowMenu label="Actions for {entry.display_name}">
	    <li><button on:click={...}>Edit</button></li>
	    <li><button on:click={...}>Withdraw</button></li>
	  </OverflowMenu>
-->
<script lang="ts">
	export let label: string = 'Open menu';
</script>

<div class="dropdown dropdown-end">
	<div
		tabindex="0"
		role="button"
		class="btn btn-ghost btn-sm btn-square"
		aria-label={label}
	>
		<svg
			class="w-4 h-4"
			fill="none"
			viewBox="0 0 24 24"
			stroke="currentColor"
			stroke-width="2"
			aria-hidden="true"
		>
			<circle cx="12" cy="5" r="1.5" fill="currentColor" stroke="none" />
			<circle cx="12" cy="12" r="1.5" fill="currentColor" stroke="none" />
			<circle cx="12" cy="19" r="1.5" fill="currentColor" stroke="none" />
		</svg>
	</div>
	<ul
		tabindex="0"
		class="menu menu-sm dropdown-content z-30 mt-2 p-2 shadow-lg bg-base-200 border border-base-300/50 rounded-xl w-52"
	>
		<slot />
	</ul>
</div>
