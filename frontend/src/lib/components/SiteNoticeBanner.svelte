<script lang="ts">
	/** Site-wide housekeeping notice (v2.171.0).
	 *
	 *  Full-width amber strip mounted in the root layout, in normal
	 *  document flow (NOT floating — floating elements near sticky bars
	 *  clip on mobile), shown on every signed-in page except /admin.
	 *  Dismissible per device; the dismissal is keyed by NOTICE_ID, so
	 *  publishing a future notice = change the ID + copy and everyone
	 *  sees it again. Retire entirely by flipping SITE_NOTICE_ENABLED
	 *  (same kill-switch pattern as the V4 page flags). */
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { isAuthenticated } from '$stores/auth';
	import { supportOpen } from '$stores/supportPanel';
	import { tournamentConcluded } from '$stores/phase';

	const SITE_NOTICE_ENABLED = true;
	// Bumped 2026-07-19: tournament wrap-up — everyone who'd dismissed the
	// rarity-bonus notice sees this one fresh, gated on conclusion instead.
	const NOTICE_ID = '2026-07-19-wrapup';
	const KEY = `predictor:notice:${NOTICE_ID}:dismissed`;

	// Hidden until onMount so a dismissed device never sees a flash;
	// non-dismissed devices get a harmless one-tick pop-in.
	let dismissed = true;
	onMount(() => {
		dismissed = localStorage.getItem(KEY) === '1';
	});

	function dismiss() {
		dismissed = true;
		localStorage.setItem(KEY, '1');
	}

	$: show =
		SITE_NOTICE_ENABLED &&
		$tournamentConcluded &&
		$isAuthenticated &&
		!dismissed &&
		!$page.url.pathname.startsWith('/admin') &&
		$page.url.pathname !== '/';
</script>

{#if show}
	<div
		class="flex items-start justify-center gap-2 border-b border-success/40 bg-success/15 px-3 py-2 sm:items-center"
		role="status"
	>
		<p class="max-w-4xl text-center text-[12.5px] leading-snug text-base-content/85">
			<span class="font-bold text-success">🏆 That's a wrap on WC26 — congratulations to our champion.</span>
			<a
				href="/"
				class="font-semibold text-success underline decoration-success/50 underline-offset-2"
				>See the final story &amp; tell us what you thought →</a
			>
			Spot anything that looks off? Drop us a note via
			<button
				class="font-semibold text-success underline decoration-success/50 underline-offset-2"
				on:click={() => supportOpen.set(true)}
			>
				Help &amp; Support</button
			>.
		</p>
		<button
			class="btn btn-ghost btn-xs shrink-0 px-1.5 text-base-content/60 hover:text-base-content"
			aria-label="Dismiss notice"
			title="Dismiss"
			on:click={dismiss}
		>
			✕
		</button>
	</div>
{/if}
