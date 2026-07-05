<!--
	Toaster — renders the transient toast stack (see stores/toast.ts).
	Top-anchored (top-center on mobile, top-right on desktop) so it can never
	be clipped by the mobile bottom nav — floating elements near sticky bars
	clip on mobile (see CLAUDE.md layout lesson).
-->
<script lang="ts">
	import { toasts, dismissToast, type Toast } from '$stores/toast';

	function handleCta(t: Toast) {
		t.onCta?.();
		dismissToast(t.id);
	}
</script>

{#if $toasts.length}
	<div
		class="fixed top-2 inset-x-0 z-[70] flex flex-col items-center gap-2 px-3 pointer-events-none sm:top-4 sm:items-end sm:pr-4"
		aria-live="polite"
	>
		{#each $toasts as t (t.id)}
			<div
				class="toast-in pointer-events-auto w-full max-w-sm bg-base-200 border border-base-300/60 border-l-[3px] border-l-primary rounded-xl shadow-card p-3.5 flex gap-3 items-start"
				role="status"
			>
				<span
					class="flex-none w-7 h-7 rounded-lg bg-primary/15 text-primary grid place-items-center text-sm"
					aria-hidden="true">✦</span
				>
				<div class="min-w-0 flex-1">
					<p class="text-sm font-semibold leading-tight">{t.title}</p>
					{#if t.message}
						<p class="text-xs text-base-content/65 mt-0.5 leading-snug">{t.message}</p>
					{/if}
					{#if t.href}
						<a
							href={t.href}
							on:click={() => handleCta(t)}
							class="inline-block mt-2 text-xs font-semibold text-primary hover:underline"
						>
							{t.cta ?? 'Open →'}
						</a>
					{/if}
				</div>
				<button
					class="flex-none btn btn-ghost btn-xs btn-circle text-base-content/50"
					on:click={() => dismissToast(t.id)}
					aria-label="Dismiss"
				>
					✕
				</button>
			</div>
		{/each}
	</div>
{/if}

<style>
	.toast-in {
		animation: toast-in 0.25s ease-out;
	}
	@keyframes toast-in {
		from {
			opacity: 0;
			transform: translateY(-8px);
		}
		to {
			opacity: 1;
			transform: none;
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.toast-in {
			animation: none;
		}
	}
</style>
