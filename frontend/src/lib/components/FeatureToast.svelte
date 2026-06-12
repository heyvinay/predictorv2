<!--
	FeatureToast — bottom-right feature announcement card (v2.173.0).

	Reusable "something new shipped" spotlight, following the
	SiteNoticeBanner editorial model: to announce a future feature,
	edit the EDITORIAL block below (new FEATURE_ID + copy + CTA) and
	everyone sees it once; dismissals are keyed per FEATURE_ID. Retire
	entirely by flipping FEATURE_TOAST_ENABLED.

	Floating card, not in-flow chrome: bottom-[4.5rem] on mobile clears
	the fixed h-14 bottom nav; z-40 keeps it under modals and navs
	(z-50) so the welcome tour or SmartFill can cover it. The toast
	also self-suppresses on any page load where the WelcomeTourModal
	is still pending — tour wins, toast shows on the next visit.
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import { fly } from 'svelte/transition';
	import { page } from '$app/stores';
	import { isAuthenticated } from '$stores/auth';
	import Sparkles from 'lucide-svelte/icons/sparkles';
	import { TOUR_ENABLED, TOUR_SEEN_KEY } from '$lib/components/WelcomeTourModal.svelte';

	// ── EDITORIAL: edit these per release ───────────────────────────
	const FEATURE_TOAST_ENABLED = true;
	const FEATURE_ID = '2026-06-12-all-entries-csv';
	const TITLE = 'New: the full pool, one spreadsheet';
	const BODY =
		'Now that the deadline has passed, every entry is open. Download the ' +
		'all-entries CSV from the Leaderboard to browse the whole pool’s ' +
		'picks side by side.';
	const CTA_LABEL = 'Open Leaderboard';
	const CTA_HREF = '/leaderboard';
	// ────────────────────────────────────────────────────────────────

	const KEY = `predictor:feature:${FEATURE_ID}:dismissed`;

	// Hidden until onMount so a dismissed device never sees a flash.
	let dismissed = true;
	let tourPending = false;

	onMount(() => {
		try {
			dismissed = localStorage.getItem(KEY) === '1';
			tourPending = TOUR_ENABLED && localStorage.getItem(TOUR_SEEN_KEY) !== '1';
		} catch {
			dismissed = true; // storage unavailable → never show
		}
	});

	// Following the CTA counts as acknowledged, so it dismisses too.
	function dismiss() {
		dismissed = true;
		try {
			localStorage.setItem(KEY, '1');
		} catch {
			/* storage unavailable — toast still hides for this session */
		}
	}

	$: show =
		FEATURE_TOAST_ENABLED &&
		$isAuthenticated &&
		!dismissed &&
		!tourPending &&
		!$page.url.pathname.startsWith('/admin') &&
		$page.url.pathname !== '/onboarding';
</script>

{#if show}
	<div
		class="fixed bottom-[4.5rem] right-3 min-[700px]:bottom-6 min-[700px]:right-6 z-40
			w-[calc(100%-1.5rem)] max-w-sm min-[700px]:w-96
			bg-base-200 rounded-2xl shadow-2xl border border-base-content/10 p-4"
		role="status"
		transition:fly={{ x: 24, duration: 200 }}
	>
		<div class="flex items-start gap-3">
			<Sparkles size={20} strokeWidth={1.75} class="shrink-0 mt-0.5 text-primary" aria-hidden="true" />
			<div class="flex-1 min-w-0">
				<p class="text-sm font-display font-bold">{TITLE}</p>
				<p class="mt-1 text-[12.5px] leading-snug text-base-content/70">{BODY}</p>
				<a href={CTA_HREF} class="btn btn-primary btn-xs mt-3" on:click={dismiss}>
					{CTA_LABEL}
				</a>
			</div>
			<button
				class="btn btn-ghost btn-xs shrink-0 px-1.5 text-base-content/60 hover:text-base-content"
				aria-label="Dismiss announcement"
				title="Dismiss"
				on:click={dismiss}
			>
				✕
			</button>
		</div>
	</div>
{/if}
