<script lang="ts">
	/** Final-hours deadline banner (v2.166.0).
	 *
	 *  Full-width, in normal document flow (NOT floating — floating
	 *  elements near sticky bars clip on mobile), mounted in the root
	 *  layout for every signed-in page during the last 24h before the
	 *  deadline. Personalized:
	 *    · unsubmitted draft(s)  → loud red + "Submit now" CTA
	 *    · no entry at all       → loud red + "Start your entry" CTA
	 *    · everything submitted  → calm gold "you're locked in"
	 *  Disappears the moment the deadline passes (the close-out copy
	 *  takes over elsewhere). Hidden on /admin. */
	import { page } from '$app/stores';
	import { isAuthenticated, user } from '$stores/auth';
	import { currentTime, phase1Countdown, phase1Deadline } from '$stores/phase';
	import { editableEntries, entries, loadEntries, submittedEntries } from '$stores/entries';

	// Entries hydrate lazily — same idempotent loader the landing uses.
	let requested = false;
	$: if ($isAuthenticated && $user?.id && !requested) {
		requested = true;
		void loadEntries($user.id);
	}

	const WINDOW_MS = 24 * 60 * 60 * 1000;
	$: msLeft = $phase1Deadline
		? new Date($phase1Deadline).getTime() - $currentTime.getTime()
		: null;
	$: show =
		$isAuthenticated &&
		msLeft != null &&
		msLeft > 0 &&
		msLeft < WINDOW_MS &&
		!$page.url.pathname.startsWith('/admin');

	$: lockTime = $phase1Deadline
		? new Date($phase1Deadline).toLocaleTimeString('en-GB', {
				hour: '2-digit',
				minute: '2-digit'
		  })
		: '';

	$: drafts = $editableEntries;
	$: nSubmitted = $submittedEntries.length;
	$: hasEntries = $entries.length > 0;
	$: draftHref = drafts.length === 1 ? `/entries/${drafts[0].id}` : '/entries';
</script>

{#if show}
	{#if drafts.length > 0}
		<div
			class="flex flex-wrap items-center justify-center gap-x-3 gap-y-1.5 border-b border-error/40 bg-error/15 px-3 py-2 text-center"
			role="alert"
		>
			<span class="text-[12.5px] font-bold text-error">
				⚠ {drafts.length === 1
					? `Your entry “${drafts[0].display_name}” is still a draft`
					: `${drafts.length} of your entries are still drafts`} — drafts don't count.
			</span>
			<span class="font-mono text-[12px] font-semibold tabular-nums text-base-content/80">
				Locks at {lockTime} · {$phase1Countdown} left
			</span>
			<a href={draftHref} class="btn btn-error btn-xs font-bold">Submit now →</a>
		</div>
	{:else if !hasEntries}
		<div
			class="flex flex-wrap items-center justify-center gap-x-3 gap-y-1.5 border-b border-error/40 bg-error/15 px-3 py-2 text-center"
			role="alert"
		>
			<span class="text-[12.5px] font-bold text-error">
				⚠ You haven't entered yet — the pool locks at {lockTime}.
			</span>
			<span class="font-mono text-[12px] font-semibold tabular-nums text-base-content/80">
				{$phase1Countdown} left
			</span>
			<a href="/entries" class="btn btn-error btn-xs font-bold">Start your entry →</a>
		</div>
	{:else}
		<div
			class="flex flex-wrap items-center justify-center gap-x-3 gap-y-1 border-b border-primary/30 bg-primary/10 px-3 py-1.5 text-center"
		>
			<span class="text-[12px] font-bold text-primary">
				✓ You're locked in — {nSubmitted}
				{nSubmitted === 1 ? 'entry' : 'entries'} submitted.
			</span>
			<span class="font-mono text-[11.5px] font-semibold tabular-nums text-base-content/70">
				Pool locks at {lockTime} · {$phase1Countdown} left
			</span>
		</div>
	{/if}
{/if}
