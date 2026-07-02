<script lang="ts">
	export let overlayOn: boolean;
	export let onToggle: () => void;
</script>

<div
	class="mb-4 flex flex-wrap items-center gap-3 rounded-xl border border-primary/30 bg-primary/10 px-4 py-2.5 text-sm"
	role="status"
>
	<span class="inline-flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-md bg-primary/20 text-xs font-bold text-primary">
		✓
	</span>
	<p class="flex-1 text-base-content/90">
		Showing <strong class="text-primary">your picks vs live standings</strong>. Row rails show
		qualification zone; the <strong>Pick</strong> column shows how each row matches your
		predictions.
	</p>
	<label class="flex cursor-pointer items-center gap-2 text-xs font-semibold uppercase tracking-wide text-base-content/60">
		Overlay
		<input
			type="checkbox"
			class="toggle toggle-primary toggle-sm"
			checked={overlayOn}
			on:change={onToggle}
		/>
	</label>
</div>
