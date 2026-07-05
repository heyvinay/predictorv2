<!--
	WhatsNew — user-facing "What's new" panel. Renders the curated
	`featureHighlights.json` as a short, scannable feature story (NOT the raw
	per-semver changelog). Centered modal on desktop, bottom sheet on mobile.
	Shows the current app version in the header. Opened from the nav sparkle
	button (see +layout.svelte); admins get a link onward to full release notes.
-->
<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { whatsNewOpen, closeWhatsNew } from '$stores/whatsNew';
	import { user } from '$stores/auth';
	import { featureHighlights, currentVersion, type FeatureHighlight } from '$lib/utils/releases';
	import { featureVerdicts, rateFeature } from '$stores/featureFeedback';
	import { track } from '$lib/analytics';

	const version = currentVersion();
	const highlights = featureHighlights;

	let closeButtonEl: HTMLButtonElement | undefined;
	let lastFocused: HTMLElement | null = null;
	let wasOpen = false;

	function close() {
		closeWhatsNew();
	}

	function onFeatureClick(h: FeatureHighlight) {
		track('whats_new_feature_clicked', { feature_id: h.id });
		close();
	}

	// Fire the open event once + manage focus on open/close. Mirrors the
	// SupportPanel focus dance; a full trap would fight nothing here (no
	// iframe) but keyboard users still want to land on the close button.
	$: if ($whatsNewOpen && !wasOpen) {
		wasOpen = true;
		track('whats_new_opened');
		lastFocused = (typeof document !== 'undefined' ? document.activeElement : null) as HTMLElement | null;
		void tick().then(() => closeButtonEl?.focus());
	} else if (!$whatsNewOpen && wasOpen) {
		wasOpen = false;
		const el = lastFocused;
		lastFocused = null;
		void tick().then(() => el?.focus?.());
	}

	onMount(() => {
		function onKey(e: KeyboardEvent) {
			if (e.key === 'Escape' && $whatsNewOpen) close();
		}
		window.addEventListener('keydown', onKey);
		return () => window.removeEventListener('keydown', onKey);
	});
</script>

{#if $whatsNewOpen}
	<!-- Backdrop -->
	<div
		class="fixed inset-0 z-[60] bg-black/50 backdrop-blur-sm"
		on:click={close}
		on:keydown={(e) => e.key === 'Enter' && close()}
		role="button"
		tabindex="-1"
		aria-label="Close what's new"
	></div>

	<!-- Panel: bottom sheet on mobile, centered modal on sm+ -->
	<div
		class="fixed inset-x-0 bottom-0 sm:inset-0 z-[61] flex sm:items-center sm:justify-center pointer-events-none"
	>
		<div
			class="pointer-events-auto w-full sm:max-w-lg bg-base-100 border border-base-300/50 shadow-2xl rounded-t-2xl sm:rounded-2xl flex flex-col max-h-[85vh] sm:max-h-[80vh]"
			role="dialog"
			aria-modal="true"
			aria-label="What's new"
		>
			<header
				class="flex items-center justify-between gap-3 px-5 h-14 border-b border-base-300/50 flex-shrink-0"
			>
				<div class="flex items-center gap-2 min-w-0">
					<h2 class="font-display text-lg tracking-wide">What's new</h2>
					<span class="badge badge-sm badge-ghost font-mono">v{version}</span>
				</div>
				<button
					bind:this={closeButtonEl}
					class="btn btn-ghost btn-sm btn-circle"
					on:click={close}
					aria-label="Close"
				>
					<svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
					</svg>
				</button>
			</header>

			<div class="flex-1 overflow-y-auto px-4 py-4 flex flex-col gap-3">
				{#each highlights as h (h.id)}
					<div class="rounded-xl border border-base-300/50 bg-base-200 p-4">
						<div class="flex items-center gap-2 mb-1.5">
							<span class="badge badge-sm badge-success">New</span>
							<h3 class="font-semibold text-[15px] leading-tight">{h.title}</h3>
							<span class="ml-auto text-[11px] font-mono text-base-content/40 whitespace-nowrap"
								>Since v{h.since}</span
							>
						</div>
						<p class="text-sm text-base-content/70 leading-relaxed">{h.blurb}</p>
						{#if h.href}
							<a
								href={h.href}
								on:click={() => onFeatureClick(h)}
								class="inline-block mt-3 text-sm font-semibold text-primary hover:underline"
							>
								{h.cta ?? 'Open →'}
							</a>
						{/if}
						<!-- Subtle, one-shot "Was this useful?" — only seen inside the
						     panel the user chose to open; collapses to a thank-you once
						     answered and never re-asks. -->
						<div class="mt-3 flex items-center gap-2 text-[11px] text-base-content/40">
							{#if $featureVerdicts[h.id]}
								<span>Thanks for the feedback 🙏</span>
							{:else}
								<span>Was this useful?</span>
								<button
									class="leading-none hover:text-base-content transition-colors"
									on:click={() => rateFeature(h.id, 'up')}
									aria-label="Yes, useful"
								>
									👍
								</button>
								<button
									class="leading-none hover:text-base-content transition-colors"
									on:click={() => rateFeature(h.id, 'down')}
									aria-label="Not useful"
								>
									👎
								</button>
							{/if}
						</div>
					</div>
				{/each}
			</div>

			{#if $user?.is_admin}
				<footer class="flex-shrink-0 px-5 py-3 border-t border-base-300/50 text-center">
					<a
						href="/admin/releases"
						on:click={close}
						class="text-xs text-base-content/50 hover:text-base-content"
					>
						Full release notes →
					</a>
				</footer>
			{/if}
		</div>
	</div>
{/if}
