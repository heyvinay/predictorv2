<!--
	WelcomeBackCard — the authenticated mirror of SignInCard.

	Same card footprint (stadium-card no-glow p-7), shown in the landing
	hero's right column when `$isAuthenticated` is true. The hero swaps
	`<SignInCard>` ↔ `<WelcomeBackCard>`; everything else on the page is
	identical between auth states.

	Reads `$user` and `$editableEntries` from the auth/entries stores
	directly (already hydrated by +layout.svelte for authenticated users).
	Takes `phase1Deadline` as a prop so the host page controls the
	countdown source (server `load` populates it).

	Props:
	  phase1Deadline?: string | null  — ISO datetime when Phase 1 locks
	                                    (typically `competition.phase1_deadline`).
	  dashboardHref?: string          — destination for the "Open dashboard"
	                                    ghost button. Defaults to /profile
	                                    until a real /home dashboard exists.
	  placement?: string              — analytics tag for cta_clicked.
-->
<script lang="ts">
	import { user } from '$stores/auth';
	import { editableEntries } from '$stores/entries';
	import { track } from '$lib/analytics';

	export let phase1Deadline: string | null = null;
	export let dashboardHref: string = '/profile';
	export let placement: string = 'hero';

	/** First word of the user's display name, uppercased for the hero
	 *  Bebas Neue treatment. Falls back to "Player" if name is missing
	 *  (e.g. user account created via Google before name field existed). */
	$: firstName = (($user?.name ?? '').trim().split(/\s+/)[0] || 'Player').toUpperCase();

	/** Number of editable entries the user has in play. The store may
	 *  not be hydrated on first paint after auth — render 0 until it
	 *  fills, the user sees a brief "0 entries" rather than a flicker. */
	$: entryCount = $editableEntries?.length ?? 0;

	/** Days until Phase 1 locks. `null` when we don't have a deadline
	 *  (server load failed or the competition's deadline isn't set yet).
	 *  Rounded down so "8.7 days" reads as "8". */
	$: daysToLock = computeDaysToLock(phase1Deadline);

	function computeDaysToLock(iso: string | null | undefined): number | null {
		if (!iso) return null;
		const deadline = new Date(iso).getTime();
		if (Number.isNaN(deadline)) return null;
		const diffMs = deadline - Date.now();
		if (diffMs <= 0) return 0;
		return Math.floor(diffMs / (1000 * 60 * 60 * 24));
	}

	/** Plural-aware, fall-back-safe status line. The plan's example was
	 *  "Phase 1 locks in 9 days. You have 2 entries in play, 1 slot left."
	 *  We keep the first half (lock countdown) live; the entries half is
	 *  shown only when we actually have entries to talk about. */
	$: statusLine = buildStatusLine(daysToLock, entryCount);

	function buildStatusLine(days: number | null, entries: number): string {
		const lockPart = (() => {
			if (days === null) return 'Phase 1 locks in soon.';
			if (days === 0) return 'Phase 1 locks today.';
			if (days === 1) return 'Phase 1 locks tomorrow.';
			return `Phase 1 locks in ${days} days.`;
		})();
		const entriesPart = (() => {
			if (entries === 0) return 'Your entries are waiting.';
			if (entries === 1) return 'You have 1 entry in play.';
			return `You have ${entries} entries in play.`;
		})();
		return `${lockPart} ${entriesPart}`;
	}

	function onPredictionsClick() {
		track('cta_clicked', {
			placement,
			cta_label: 'enter_predictions',
			auth_state: 'authenticated'
		});
	}

	function onDashboardClick() {
		track('cta_clicked', {
			placement,
			cta_label: 'open_dashboard',
			auth_state: 'authenticated'
		});
	}
</script>

<div class="stadium-card no-glow p-7">
	<p class="text-xs font-mono uppercase tracking-[0.18em] text-base-content/60 mb-2">
		Welcome back
	</p>
	<h2 class="font-hero text-4xl text-primary tracking-[0.02em] mb-3">
		{firstName}
	</h2>
	<p class="text-sm text-base-content/70 leading-relaxed mb-6">
		{statusLine}
	</p>

	<a
		href="/entries"
		class="btn btn-primary w-full"
		on:click={onPredictionsClick}
	>
		Enter your predictions →
	</a>
	<a
		href={dashboardHref}
		class="btn btn-ghost btn-sm w-full mt-2 text-base-content/70"
		on:click={onDashboardClick}
	>
		Open dashboard
	</a>
</div>
