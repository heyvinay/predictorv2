<script lang="ts">
	// Public privacy statement. No auth gate — prospective joiners should be
	// able to read this before handing over an email. Static content only;
	// kept in sync by hand because there is no markdown renderer in the
	// bundle (one page does not justify the dependency).
	import { onMount } from 'svelte';
	import { pageTitle } from '$stores/pageTitle';
	import { supportOpen } from '$stores/supportPanel';

	const LAST_UPDATED = '29 May 2026';
	// Operator-contact email removed 2026-06-01. Both prior touchpoints
	// (sections 05 and 09) now route users through the in-app support
	// flow (supportOpen.set(true) → SupportPanel modal) instead of a
	// mailto link.

	onMount(() => {
		pageTitle.set('Privacy');
	});
</script>

<svelte:head>
	<title>Privacy - Predictor v2</title>
</svelte:head>

<div class="container mx-auto mobile-padding py-6 space-y-6 max-w-4xl">
	<!-- Hero -->
	<div class="stadium-card p-6">
		<h1 class="text-4xl font-display tracking-wide mb-2">
			<span class="text-gradient">Privacy</span> Statement
		</h1>
		<p class="text-sm text-base-content/60">
			Last updated: {LAST_UPDATED}
		</p>
		<p class="text-sm text-base-content/80 mt-4">
			This site (wc26.heyvinay.com) is a personal hobby project for running a
			prediction game with friends during the 2026 FIFA World Cup. It is not
			affiliated with any commercial entity and will be permanently taken
			offline after the tournament concludes.
		</p>
	</div>

	<!-- 01 — What we collect -->
	<section class="stadium-card no-glow p-5">
		<h2 class="text-lg font-display tracking-wide mb-3">01 · What We Collect</h2>
		<ul class="space-y-2 text-sm text-base-content/80 list-disc list-inside">
			<li><b class="text-base-content">Email address</b> — when you register.</li>
			<li><b class="text-base-content">Your predictions and scores</b> — the entries you make in the game.</li>
			<li>
				<b class="text-base-content">Basic server logs</b> — IP address,
				requested URL, timestamp, and user agent, kept for debugging and
				abuse prevention. No analytics or tracking tools are used.
			</li>
		</ul>
	</section>

	<!-- 02 — How we use it -->
	<section class="stadium-card no-glow p-5">
		<h2 class="text-lg font-display tracking-wide mb-3">02 · How We Use It</h2>
		<ul class="space-y-2 text-sm text-base-content/80 list-disc list-inside">
			<li>Your email identifies your account and is used to send you one-time magic-link sign-in emails.</li>
			<li>Your predictions are used to run the game — scoring, leaderboards, and the bracket.</li>
			<li>
				Your email is <b class="text-base-content">never</b> sold, shared
				for marketing, or used for any purpose outside this game.
			</li>
		</ul>
	</section>

	<!-- 03 — Third parties -->
	<section class="stadium-card no-glow p-5">
		<h2 class="text-lg font-display tracking-wide mb-3">03 · Who Else Sees Your Data</h2>
		<p class="text-sm text-base-content/80 mb-3">
			A few third parties necessarily touch your data so the site can
			function:
		</p>
		<ul class="space-y-2 text-sm text-base-content/80 list-disc list-inside">
			<li><b class="text-base-content">Resend</b> — delivers magic-link sign-in emails.</li>
			<li>
				<b class="text-base-content">Cloudflare</b> — routes traffic to the
				site and provides DDoS protection (sees IP address and request
				metadata).
			</li>
			<li><b class="text-base-content">Hetzner</b> — hosts the server where the database lives.</li>
		</ul>
		<p class="text-sm text-base-content/80 mt-3">
			Match data is fetched from Football-Data.org by the server only; that
			service receives no information about you.
		</p>
	</section>

	<!-- 04 — Cookies & local storage -->
	<section class="stadium-card no-glow p-5">
		<h2 class="text-lg font-display tracking-wide mb-3">04 · Cookies & Local Storage</h2>
		<ul class="space-y-2 text-sm text-base-content/80 list-disc list-inside">
			<li>A session cookie keeps you signed in after you use a magic link.</li>
			<li><code class="font-mono text-xs px-1.5 py-0.5 rounded bg-base-300/40">localStorage</code> stores your theme preference (light/dark).</li>
		</ul>
		<p class="text-sm text-base-content/80 mt-3">
			No advertising or tracking cookies are used.
		</p>
	</section>

	<!-- 05 — Your rights -->
	<section class="stadium-card no-glow p-5">
		<h2 class="text-lg font-display tracking-wide mb-3">05 · Your Rights</h2>
		<p class="text-sm text-base-content/80">
			You can have your data corrected, or have your account and email
			deleted at any time —
			<button
				type="button"
				class="link link-primary"
				on:click={() => supportOpen.set(true)}
			>send a support request</button>.
		</p>
	</section>

	<!-- 06 — Data retention -->
	<section class="stadium-card no-glow p-5">
		<h2 class="text-lg font-display tracking-wide mb-3">06 · Data Retention</h2>
		<p class="text-sm text-base-content/80">
			When the site is taken offline after the 2026 World Cup, all data —
			including email addresses, predictions, scores, and server logs —
			will be permanently deleted, along with any backups.
		</p>
	</section>

	<!-- 07 — Children -->
	<section class="stadium-card no-glow p-5">
		<h2 class="text-lg font-display tracking-wide mb-3">07 · Children</h2>
		<p class="text-sm text-base-content/80">
			This site is intended for adults; we don't knowingly collect data
			from anyone under 16.
		</p>
	</section>

	<!-- 08 — Changes -->
	<section class="stadium-card no-glow p-5">
		<h2 class="text-lg font-display tracking-wide mb-3">08 · Changes</h2>
		<p class="text-sm text-base-content/80">
			If anything material changes, this page and the date above will be
			updated.
		</p>
	</section>

	<!-- 09 — Contact -->
	<section class="stadium-card no-glow p-5">
		<h2 class="text-lg font-display tracking-wide mb-3">09 · Contact</h2>
		<p class="text-sm text-base-content/80">
			Questions or removal requests:
			<button
				type="button"
				class="link link-primary"
				on:click={() => supportOpen.set(true)}
			>send a support request</button>.
		</p>
	</section>
</div>
