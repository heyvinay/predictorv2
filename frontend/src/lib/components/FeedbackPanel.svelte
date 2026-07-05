<!--
	FeedbackPanel — "Rate & feedback" slide-in side panel. A near-clone of
	SupportPanel: same chrome + focus handling + TallyEmbed, pointed at the
	feedback form and opened via the `feedbackOpen` store. Fires `feedback_opened`.
-->
<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { feedbackOpen } from '$stores/feedbackPanel';
	import { user } from '$stores/auth';
	import { track } from '$lib/analytics';
	import TallyEmbed from '$components/help/TallyEmbed.svelte';

	// TODO: swap for a dedicated Tally "Rate & feedback" form (a rating field
	// + free-text) once created, and configure its notification recipient in
	// the Tally dashboard. Until then we reuse the support form so the panel is
	// functional day one; responses land in the existing support inbox.
	const FEEDBACK_TALLY_FORM_ID = 'D4Mbo5';

	let closeButtonEl: HTMLButtonElement | undefined;
	let lastFocused: HTMLElement | null = null;
	let wasOpen = false;

	function close() {
		feedbackOpen.set(false);
	}

	$: if ($feedbackOpen && !wasOpen) {
		wasOpen = true;
		track('feedback_opened');
		lastFocused = (typeof document !== 'undefined' ? document.activeElement : null) as HTMLElement | null;
		void tick().then(() => closeButtonEl?.focus());
	} else if (!$feedbackOpen && wasOpen) {
		wasOpen = false;
		const el = lastFocused;
		lastFocused = null;
		void tick().then(() => el?.focus?.());
	}

	onMount(() => {
		function onKey(e: KeyboardEvent) {
			if (e.key === 'Escape') close();
		}
		window.addEventListener('keydown', onKey);
		return () => window.removeEventListener('keydown', onKey);
	});
</script>

{#if $feedbackOpen}
	<!-- Backdrop -->
	<div
		class="fixed inset-0 z-[60] bg-black/40 backdrop-blur-sm"
		on:click={close}
		on:keydown={(e) => e.key === 'Enter' && close()}
		role="button"
		tabindex="-1"
		aria-label="Close feedback panel"
	></div>

	<!-- Slide-in side panel (right) -->
	<aside
		class="fixed top-0 right-0 z-[61] h-screen w-full max-w-md bg-base-100 border-l border-base-300/50 shadow-2xl flex flex-col"
		aria-label="Rate and feedback"
		aria-modal="true"
		role="dialog"
	>
		<header class="flex items-center justify-between px-5 h-14 border-b border-base-300/50">
			<h2 class="font-display text-lg tracking-wide">Rate &amp; feedback</h2>
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

		<div class="flex-1 flex flex-col min-h-0 p-5">
			<p class="text-sm text-base-content/60 mb-4">
				Tell us what you love, what's broken, or what you'd like to see next. We read every note.
			</p>
			<TallyEmbed
				formId={FEEDBACK_TALLY_FORM_ID}
				title="Feedback form"
				class="flex-1 min-h-0"
				hiddenFields={{ email: $user?.email }}
			/>
		</div>
	</aside>
{/if}
