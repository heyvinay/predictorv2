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

	const SITE_NOTICE_ENABLED = true;
	// Bumped 2026-06-12 (v2.175.0): rarity bonus came back online; everyone
	// who'd dismissed the previous launch-week notice sees this one fresh.
	const NOTICE_ID = '2026-06-12-rarity-on';
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
		$isAuthenticated &&
		!dismissed &&
		!$page.url.pathname.startsWith('/admin');
</script>

{#if show}
	<div
		class="flex items-start justify-center gap-2 border-b border-success/40 bg-success/15 px-3 py-2 sm:items-center"
		role="status"
	>
		<p class="max-w-4xl text-center text-[12.5px] leading-snug text-base-content/85">
			<span class="font-bold text-success">Rarity bonus is now in operation.</span>
			With the entry pool confirmed, the rarity bonus is live and has been applied
			retroactively to every finished match — totals on the leaderboard have updated.
			See the <a
				href="/rules"
				class="font-semibold text-success underline decoration-success/50 underline-offset-2"
				>rules page</a
			>
			for the bands. Spot anything that looks off? Drop us a note via
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
