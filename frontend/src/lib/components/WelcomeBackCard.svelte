<!--
	WelcomeBackCard — auth-aware hero card on the landing page.

	v2.160.x (this revision) — cohort-aware copy + accent colors.

	Five cohorts, same card chassis:

	  1. zero            — no entries yet. Create-first messaging.
	  2. draft_only_solo — exactly one entry, in draft. Finish-it framing.
	  3. submitted_only_solo — exactly one entry, submitted. CONVERSION
	     target — primary CTA pushes toward a second entry.
	  4. multi_with_drafts — 2+ entries with at least one draft. "Continue
	     and finish" framing — the user already knows the wizard, just
	     needs to close out drafts.
	  5. multi_all_submitted — 2+ entries, all submitted. Quiet success;
	     soft nudge to add one more.

	If the deadline has passed, all cohorts collapse to the locked view.

	Visual chrome stays constant — same gold primary, same outlined
	secondary, same card footprint. Urgency lives in:
	  • the words (per cohort)
	  • a single accent on the stats line: amber chip for drafts,
	    green check for submitted-only.

	Phase 2 doesn't exist for this tournament. Draft/submitted counts
	come from $editableEntries / $submittedEntries, which are narrowed
	to the entry's phase_1 status in stores/entries.ts. New code in this
	component never mentions phases.

	Props:
	  phase1Deadline?: string | null  — ISO datetime of the deadline.
	  placement?: string              — analytics tag for cta_clicked.
-->
<script lang="ts">
	import { user } from '$stores/auth';
	import { editableEntries, submittedEntries } from '$stores/entries';
	import { track } from '$lib/analytics';

	export let phase1Deadline: string | null = null;
	export let placement: string = 'hero';

	type Cohort =
		| 'zero'
		| 'draft_only_solo'
		| 'submitted_only_solo'
		| 'multi_with_drafts'
		| 'multi_all_submitted'
		| 'locked';

	interface CtaLink {
		label: string;
		href: string;
		analyticsLabel: string;
	}

	interface CardContent {
		message: string;
		primary: CtaLink;
		secondary: CtaLink | null;
	}

	function computeDaysToLock(iso: string | null | undefined): number | null {
		if (!iso) return null;
		const t = new Date(iso).getTime();
		if (Number.isNaN(t)) return null;
		const diffMs = t - Date.now();
		if (diffMs <= 0) return 0;
		return Math.floor(diffMs / (1000 * 60 * 60 * 24));
	}

	function isDeadlinePassed(iso: string | null | undefined): boolean {
		if (!iso) return false;
		const t = new Date(iso).getTime();
		if (Number.isNaN(t)) return false;
		return t <= Date.now();
	}

	function deadlinePhrase(days: number | null): string {
		if (days === null) return '';
		if (days === 0) return 'Deadline today.';
		if (days === 1) return 'Deadline tomorrow.';
		return `Deadline in ${days} days.`;
	}

	function classifyCohort(
		draft: number,
		submitted: number,
		passed: boolean
	): Cohort {
		if (passed) return 'locked';
		const total = draft + submitted;
		if (total === 0) return 'zero';
		if (total === 1 && draft === 1) return 'draft_only_solo';
		if (total === 1 && submitted === 1) return 'submitted_only_solo';
		if (draft > 0) return 'multi_with_drafts';
		return 'multi_all_submitted';
	}

	// ─── CTA link constants ──────────────────────────────────────────────
	const VIEW_ENTRIES: CtaLink = {
		label: 'View your entries →',
		href: '/entries',
		analyticsLabel: 'view_entries'
	};
	const VIEW_ENTRY: CtaLink = {
		label: 'View your entry →',
		href: '/entries',
		analyticsLabel: 'view_entry'
	};
	const ADD_ANOTHER: CtaLink = {
		label: 'Add another entry',
		href: '/entries?new=1',
		analyticsLabel: 'add_another_entry'
	};
	const CREATE_FIRST: CtaLink = {
		label: 'Create your entry →',
		href: '/entries?new=1',
		analyticsLabel: 'create_first_entry'
	};
	const FINISH_ENTRY: CtaLink = {
		label: 'Finish your entry →',
		href: '/entries',
		analyticsLabel: 'finish_entry'
	};
	const CONTINUE_FINISH: CtaLink = {
		label: 'Continue and finish →',
		href: '/entries',
		analyticsLabel: 'continue_and_finish'
	};

	function buildContent(
		cohort: Cohort,
		days: number | null,
		draftCount: number
	): CardContent {
		const dp = deadlinePhrase(days);
		const draftWord = draftCount === 1 ? 'draft' : 'drafts';

		switch (cohort) {
			case 'locked':
				return {
					message: 'Submissions are closed.',
					primary: VIEW_ENTRIES,
					secondary: null
				};

			case 'zero':
				return {
					message:
						`You haven't entered yet. Pick a team, score the games, and join the pool. ${dp}`.trim(),
					primary: CREATE_FIRST,
					secondary: null
				};

			case 'draft_only_solo':
				return {
					message: `Finish your picks, then back yourself with a second entry. ${dp}`.trim(),
					primary: FINISH_ENTRY,
					secondary: ADD_ANOTHER
				};

			case 'submitted_only_solo':
				// CONVERSION-FOCUS cohort. Primary leads with the upsell;
				// secondary lets them peek at their existing entry.
				return {
					message: `You're in. Boost your odds — add a second entry before the deadline. ${dp}`.trim(),
					primary: ADD_ANOTHER,
					secondary: VIEW_ENTRY
				};

			case 'multi_with_drafts':
				return {
					message: `${draftCount} ${draftWord} still need submitting. ${dp}`.trim(),
					primary: CONTINUE_FINISH,
					secondary: ADD_ANOTHER
				};

			case 'multi_all_submitted':
				return {
					message: `You're all in. Add one more? ${dp}`.trim(),
					primary: ADD_ANOTHER,
					secondary: VIEW_ENTRIES
				};
		}
	}

	/** Stats line — "1 entry · in draft" / "3 entries · 2 submitted · 1 draft".
	 *
	 * Cohort 1 returns null (no stats line; subtitle already says
	 * "You haven't entered yet"). Cohorts 3 + 5 (all-submitted variants)
	 * pick up a green ✓ token; cohorts 2 + 4 stay neutral text with the
	 * draft count carrying the visual weight via accent color on the
	 * surrounding chip. */
	function buildStatsLine(cohort: Cohort, draft: number, submitted: number): {
		text: string;
		accent: 'success' | 'warning' | 'neutral';
	} | null {
		if (cohort === 'zero') return null;

		const total = draft + submitted;
		if (cohort === 'draft_only_solo') {
			return { text: '1 entry · in draft', accent: 'warning' };
		}
		if (cohort === 'submitted_only_solo') {
			return { text: '1 entry · submitted ✓', accent: 'success' };
		}
		if (cohort === 'multi_with_drafts') {
			const draftWord = draft === 1 ? 'draft' : 'drafts';
			return {
				text: `${total} entries · ${submitted} submitted · ${draft} ${draftWord}`,
				accent: 'warning'
			};
		}
		if (cohort === 'multi_all_submitted') {
			return { text: `${total} entries · all submitted ✓`, accent: 'success' };
		}
		// locked
		const parts: string[] = [`${total} ${total === 1 ? 'entry' : 'entries'}`];
		if (submitted > 0) parts.push(`${submitted} submitted`);
		if (draft > 0) parts.push(`${draft} ${draft === 1 ? 'draft' : 'drafts'}`);
		return { text: parts.join(' · '), accent: 'neutral' };
	}

	$: firstName = ($user?.name ?? '').trim().split(/\s+/)[0] || 'Player';
	$: draftCount = $editableEntries.length;
	$: submittedCount = $submittedEntries.length;
	$: totalCount = draftCount + submittedCount;
	$: daysToLock = computeDaysToLock(phase1Deadline);
	$: passed = isDeadlinePassed(phase1Deadline);
	$: cohort = classifyCohort(draftCount, submittedCount, passed);
	$: content = buildContent(cohort, daysToLock, draftCount);
	$: statsLine = buildStatsLine(cohort, draftCount, submittedCount);

	function statsLineClass(accent: 'success' | 'warning' | 'neutral'): string {
		// text-warning-text — the theme-aware amber foreground per
		// feedback_text_warning_token_trap.md (NOT text-warning, which is
		// a surface token).
		if (accent === 'success') return 'text-success';
		if (accent === 'warning') return 'text-warning-text';
		return 'text-base-content';
	}

	function onCtaClick(cta: CtaLink) {
		track('cta_clicked', {
			placement,
			cta_label: cta.analyticsLabel,
			auth_state: 'authenticated',
			total_entries: totalCount,
			cohort
		});
	}
</script>

<div class="stadium-card no-glow p-7">
	<p class="text-xs font-mono uppercase tracking-[0.18em] text-base-content/60 mb-3">
		Welcome back, {firstName}
	</p>

	{#if statsLine}
		<p class="font-display font-semibold text-base mb-1.5 {statsLineClass(statsLine.accent)}">
			{statsLine.text}
		</p>
	{/if}

	<p class="text-sm text-base-content/70 leading-relaxed mb-6">
		{content.message}
	</p>

	<a
		href={content.primary.href}
		class="btn btn-primary w-full"
		on:click={() => onCtaClick(content.primary)}
	>
		{content.primary.label}
	</a>

	{#if content.secondary}
		{@const sec = content.secondary}
		<a
			href={sec.href}
			class="btn btn-outline w-full mt-3"
			on:click={() => onCtaClick(sec)}
		>
			{sec.label}
		</a>
	{/if}
</div>
