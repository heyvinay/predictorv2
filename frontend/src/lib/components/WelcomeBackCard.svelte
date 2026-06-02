<!--
	WelcomeBackCard — auth-aware hero card on the landing page.

	Shows: welcome eyebrow + summary of the user's entries + a
	contextual deadline message + two CTAs (View entries / Add new
	entry). Message and CTA labels vary on (entry_state, deadline_band)
	per the 3x4 matrix in the plan; visual chrome stays constant — same
	gold primary, same outlined secondary, same card footprint at every
	urgency level. No red, no border alarm, no glow change. Urgency
	lives in the words.

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

	type EntryState = 'zero' | 'has_drafts' | 'all_submitted';
	type Band = 'chill' | 'soon' | 'urgent' | 'locked';

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

	function classifyBand(days: number | null, passed: boolean): Band {
		if (passed) return 'locked';
		if (days === null) return 'chill';
		if (days <= 1) return 'urgent';
		if (days <= 7) return 'soon';
		return 'chill';
	}

	function classifyState(draft: number, submitted: number): EntryState {
		if (draft + submitted === 0) return 'zero';
		if (draft === 0) return 'all_submitted';
		return 'has_drafts';
	}

	function deadlinePhrase(days: number | null, passed: boolean): string {
		if (passed) return 'Submissions are closed';
		if (days === null) return 'Deadline coming up';
		if (days === 0) return 'Deadline today';
		if (days === 1) return 'Deadline tomorrow';
		return `Deadline in ${days} days`;
	}

	function pluralDrafts(n: number): string {
		return n === 1 ? 'draft' : 'drafts';
	}

	const VIEW: CtaLink = {
		label: 'View your entries →',
		href: '/entries',
		analyticsLabel: 'view_entries'
	};
	const ADD_NEW: CtaLink = {
		label: 'Add new entry',
		href: '/entries?new=1',
		analyticsLabel: 'add_new_entry'
	};
	const ADD_FIRST: CtaLink = {
		label: 'Add your first entry',
		href: '/entries?new=1',
		analyticsLabel: 'add_first_entry'
	};
	const SUBMIT_DRAFTS: CtaLink = {
		label: 'Submit your drafts →',
		href: '/entries',
		analyticsLabel: 'submit_drafts'
	};

	function buildContent(
		state: EntryState,
		band: Band,
		draftCount: number,
		days: number | null
	): CardContent {
		if (state === 'zero') {
			const message =
				band === 'locked'
					? 'Submissions are closed.'
					: band === 'urgent'
						? 'Last day — create your entry and submit it before kickoff.'
						: band === 'soon'
							? `${days} ${days === 1 ? 'day' : 'days'} left to make your picks.`
							: 'Create your first entry, fill it in, and submit before the deadline.';
			return {
				message,
				primary: band === 'locked' ? VIEW : ADD_FIRST,
				secondary: null
			};
		}

		if (state === 'all_submitted') {
			const dp = deadlinePhrase(days, band === 'locked');
			const message =
				band === 'locked'
					? 'Submissions are closed.'
					: band === 'urgent'
						? `All entries locked in. ${dp}.`
						: band === 'soon'
							? `All entries submitted. ${dp}.`
							: `You're all set. ${dp}.`;
			return {
				message,
				primary: VIEW,
				secondary: band === 'locked' ? null : ADD_NEW
			};
		}

		// has_drafts
		const n = draftCount;
		const d = pluralDrafts(n);

		if (band === 'locked') {
			return {
				message: `Submissions are closed. ${n} ${d} did not count.`,
				primary: VIEW,
				secondary: null
			};
		}
		if (band === 'urgent') {
			const lead = days === 0 ? 'Today' : days === 1 ? 'Tomorrow' : 'Last day';
			return {
				message: `${lead} — ${n} ${d} must be submitted to count.`,
				primary: SUBMIT_DRAFTS,
				secondary: null
			};
		}
		if (band === 'soon') {
			return {
				message: `Deadline in ${days} days — ${n} ${d} still need submitting.`,
				primary: VIEW,
				secondary: ADD_NEW
			};
		}
		return {
			message: `You have ${n} ${d}. Submit before the deadline to count.`,
			primary: VIEW,
			secondary: ADD_NEW
		};
	}

	function summaryLine(draft: number, submitted: number): string {
		const total = draft + submitted;
		const parts: string[] = [`${total} ${total === 1 ? 'entry' : 'entries'}`];
		if (submitted > 0) parts.push(`${submitted} submitted`);
		if (draft > 0) parts.push(`${draft} ${pluralDrafts(draft)}`);
		return parts.join(' · ');
	}

	$: firstName = ($user?.name ?? '').trim().split(/\s+/)[0] || 'Player';
	$: draftCount = $editableEntries.length;
	$: submittedCount = $submittedEntries.length;
	$: totalCount = draftCount + submittedCount;
	$: daysToLock = computeDaysToLock(phase1Deadline);
	$: passed = isDeadlinePassed(phase1Deadline);
	$: band = classifyBand(daysToLock, passed);
	$: state = classifyState(draftCount, submittedCount);
	$: content = buildContent(state, band, draftCount, daysToLock);
	$: summary = totalCount > 0 ? summaryLine(draftCount, submittedCount) : null;

	function onCtaClick(cta: CtaLink) {
		track('cta_clicked', {
			placement,
			cta_label: cta.analyticsLabel,
			auth_state: 'authenticated',
			total_entries: totalCount,
			band
		});
	}
</script>

<div class="stadium-card no-glow p-7">
	<p class="text-xs font-mono uppercase tracking-[0.18em] text-base-content/60 mb-3">
		Welcome back, {firstName}
	</p>

	{#if summary}
		<p class="font-display font-semibold text-base text-base-content mb-1.5">
			{summary}
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
