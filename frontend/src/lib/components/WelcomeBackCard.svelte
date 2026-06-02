<!--
	WelcomeBackCard — auth-aware hero card on the landing page.

	Classifies the user's entry state (no_entries / one_draft /
	one_submitted / mixed_drafts / all_submitted) and combines that with
	the deadline urgency tier to drive an eyebrow + Bebas headline +
	sub-line + CTA. The headline slot — previously the user's first name
	in giant Bebas — now carries the state copy; the name moves into the
	smaller eyebrow.

	The high-stakes case the card protects against: a draft entry with
	every pick filled in but never submitted. A draft is invisible to
	scoring, so the user can do all the work and still not be in the
	pool. When that's detected (via per-entry completion summary loaded
	on the landing page), the card flips to the "ONE TAP FROM LOCKED IN"
	framing and surfaces an amber "Ready to submit" chip — gold stays
	reserved for the primary CTA, no red anywhere.

	Reads stores: $user, $editableEntries, $submittedEntries,
	$completionSummaries. The landing route (+page.svelte) hydrates
	them on auth.

	Props:
	  phase1Deadline?: string | null  — ISO datetime of the global deadline.
	  placement?: string              — analytics tag for cta_clicked.
-->
<script lang="ts">
	import { user } from '$stores/auth';
	import {
		editableEntries,
		submittedEntries,
		completionSummaries,
		isEntryComplete
	} from '$stores/entries';
	import { track } from '$lib/analytics';
	import type { Entry, CompletionSummary } from '$lib/types/entry';

	export let phase1Deadline: string | null = null;
	export let placement: string = 'hero';

	type EntryState =
		| 'no_entries'
		| 'one_draft'
		| 'one_submitted'
		| 'mixed_drafts'
		| 'all_submitted';

	type Urgency = 'chill' | 'nudge' | 'soon' | 'urgent' | 'locked';

	interface EntryRow {
		id: string;
		name: string;
		status: 'draft' | 'submitted';
		isReady: boolean;
		href: string;
	}

	interface CardContent {
		eyebrow: string;
		eyebrowClass: string;
		headline: string;
		subline: string;
		chip: { text: string; tone: 'gold' | 'amber' } | null;
		primary: { label: string; href: string };
		secondary: { label: string; href: string } | null;
	}

	function buildRows(
		drafts: Entry[],
		submitted: Entry[],
		summaries: Record<string, CompletionSummary>
	): EntryRow[] {
		const toRow = (e: Entry, status: 'draft' | 'submitted'): EntryRow => ({
			id: e.id,
			name: e.display_name || `Entry #${e.entry_number}`,
			status,
			isReady: status === 'draft' && isEntryComplete(summaries[e.id]),
			href: `/entries/${e.id}`
		});
		return [
			...drafts.map((e) => toRow(e, 'draft')),
			...submitted.map((e) => toRow(e, 'submitted'))
		];
	}

	function classifyState(rows: EntryRow[]): EntryState {
		if (rows.length === 0) return 'no_entries';
		if (rows.length === 1) {
			return rows[0].status === 'draft' ? 'one_draft' : 'one_submitted';
		}
		return rows.some((r) => r.status === 'draft') ? 'mixed_drafts' : 'all_submitted';
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

	function classifyUrgency(days: number | null, passed: boolean): Urgency {
		if (passed) return 'locked';
		if (days === null) return 'chill';
		if (days <= 1) return 'urgent';
		if (days <= 7) return 'soon';
		if (days <= 14) return 'nudge';
		return 'chill';
	}

	function deadlinePhrase(days: number | null, passed: boolean): string {
		if (passed) return 'Deadline passed';
		if (days === null) return 'Deadline coming up';
		if (days === 0) return 'Deadline today';
		if (days === 1) return 'Deadline tomorrow';
		return `Deadline in ${days} days`;
	}

	function pickPrimaryEntry(state: EntryState, rows: EntryRow[]): EntryRow | null {
		if (state === 'no_entries') return null;
		if (state === 'one_draft' || state === 'one_submitted') return rows[0];
		if (state === 'mixed_drafts') {
			return (
				rows.find((r) => r.status === 'draft' && r.isReady) ??
				rows.find((r) => r.status === 'draft') ??
				null
			);
		}
		return null;
	}

	function buildContent(
		state: EntryState,
		rows: EntryRow[],
		firstName: string,
		urgency: Urgency,
		days: number | null,
		passed: boolean
	): CardContent {
		const primaryEntry = pickPrimaryEntry(state, rows);
		const deadline = deadlinePhrase(days, passed);

		if (urgency === 'locked') {
			return {
				eyebrow: 'Submissions locked',
				eyebrowClass: 'text-base-content/55',
				headline: 'PREDICTIONS ARE LOCKED',
				subline:
					'The deadline has passed. Watch the matches and see how your picks fare.',
				chip: null,
				primary: { label: 'Review your picks →', href: '/entries' },
				secondary: null
			};
		}

		const urgencyChip =
			urgency === 'urgent'
				? {
						text: days === 0 ? 'Locks today' : 'Last day',
						tone: 'amber' as const
					}
				: urgency === 'soon'
					? { text: `${days} days left`, tone: 'gold' as const }
					: null;

		switch (state) {
			case 'no_entries':
				return {
					eyebrow: `Welcome, ${firstName}`,
					eyebrowClass: 'text-base-content/60',
					headline: "YOU HAVEN'T MADE AN ENTRY YET",
					subline:
						urgency === 'urgent' || urgency === 'soon'
							? `${deadline}. Get your picks in.`
							: 'Create your entry, fill it in, submit before the deadline.',
					chip: urgencyChip,
					primary: { label: 'Create your entry →', href: '/entries' },
					secondary: null
				};

			case 'one_draft': {
				const entry = primaryEntry!;
				if (entry.isReady) {
					return {
						eyebrow: `${entry.name} · ready`,
						eyebrowClass: 'text-warning-text',
						headline: 'ONE TAP FROM LOCKED IN',
						subline:
							"Every pick is filled — but a draft doesn't count. Submit to lock it in.",
						chip: { text: 'Ready to submit', tone: 'amber' },
						primary: { label: 'Submit my entry →', href: entry.href },
						secondary: { label: 'or review my picks', href: entry.href }
					};
				}
				return {
					eyebrow: `Welcome back, ${firstName}`,
					eyebrowClass: 'text-base-content/60',
					headline: 'PICK UP WHERE YOU LEFT OFF',
					subline:
						urgency === 'urgent'
							? `${deadline}. Finish your picks and submit.`
							: 'Keep filling in your picks — then submit before the deadline.',
					chip: urgencyChip,
					primary: { label: 'Continue your picks →', href: entry.href },
					secondary: null
				};
			}

			case 'one_submitted': {
				const entry = primaryEntry!;
				const isUrgent = urgency === 'urgent' || urgency === 'soon';
				return {
					eyebrow: `${entry.name} · submitted ✓`,
					eyebrowClass: 'text-success',
					headline: "YOU'RE IN THE POOL",
					subline: isUrgent
						? `${deadline}. Squeeze in a second?`
						: 'Your entry is locked in. Want to add a second?',
					chip: urgencyChip,
					primary: { label: 'Start a second entry →', href: '/entries' },
					secondary: { label: 'or review my first', href: entry.href }
				};
			}

			case 'mixed_drafts': {
				const entry = primaryEntry!;
				const readyCount = rows.filter(
					(r) => r.status === 'draft' && r.isReady
				).length;
				if (readyCount > 0) {
					return {
						eyebrow: 'Drafts ready to submit',
						eyebrowClass: 'text-warning-text',
						headline: "DON'T LEAVE THEM AS DRAFTS",
						subline:
							readyCount === 1
								? "1 draft is ready to submit — drafts that stay drafts don't count."
								: `${readyCount} drafts are ready to submit — drafts that stay drafts don't count.`,
						chip: { text: 'Ready to submit', tone: 'amber' },
						primary: { label: `Submit ${entry.name} →`, href: entry.href },
						secondary: { label: 'or see all entries', href: '/entries' }
					};
				}
				return {
					eyebrow: `Welcome back, ${firstName}`,
					eyebrowClass: 'text-base-content/60',
					headline: 'FINISH YOUR DRAFTS',
					subline:
						urgency === 'urgent'
							? `${deadline}. Finish your drafts and submit them.`
							: 'Finish your remaining drafts and submit them before the deadline.',
					chip: urgencyChip,
					primary: { label: `Continue ${entry.name} →`, href: entry.href },
					secondary: { label: 'or see all entries', href: '/entries' }
				};
			}

			case 'all_submitted':
				return {
					eyebrow: 'All entries submitted ✓',
					eyebrowClass: 'text-success',
					headline: 'ALL LOCKED IN',
					subline: `Your entries are in. ${deadline}.`,
					chip: null,
					primary: { label: 'Review your picks →', href: '/entries' },
					secondary: null
				};
		}
	}

	function rowChip(row: EntryRow): { text: string; class: string } {
		if (row.status === 'submitted') {
			return { text: 'SUBMITTED ✓', class: 'bg-success/20 text-success' };
		}
		if (row.isReady) {
			return { text: 'DRAFT · READY', class: 'bg-warning/20 text-warning-text' };
		}
		return { text: 'DRAFT', class: 'bg-base-300 text-base-content/70' };
	}

	$: firstName = ($user?.name ?? '').trim().split(/\s+/)[0] || 'Player';
	$: rows = buildRows($editableEntries, $submittedEntries, $completionSummaries);
	$: entryState = classifyState(rows);
	$: daysToLock = computeDaysToLock(phase1Deadline);
	$: passed = isDeadlinePassed(phase1Deadline);
	$: urgency = classifyUrgency(daysToLock, passed);
	$: content = buildContent(entryState, rows, firstName, urgency, daysToLock, passed);
	$: sublineToneClass =
		urgency === 'locked'
			? 'text-base-content/55'
			: content.chip?.tone === 'amber'
				? 'text-warning-text'
				: urgency === 'soon'
					? 'text-base-content/85'
					: 'text-base-content/70';
	$: showRows = rows.length >= 2;
	$: hasReadyDraft = rows.some((r) => r.status === 'draft' && r.isReady);

	function onPrimaryClick() {
		track('cta_clicked', {
			placement,
			cta_label: `welcome_${entryState}`,
			auth_state: 'authenticated',
			urgency,
			ready_draft: hasReadyDraft
		});
	}

	function onSecondaryClick() {
		track('cta_clicked', {
			placement,
			cta_label: `welcome_${entryState}_secondary`,
			auth_state: 'authenticated',
			urgency
		});
	}
</script>

<div class="stadium-card no-glow p-7">
	<p class="text-xs font-mono uppercase tracking-[0.18em] mb-2 {content.eyebrowClass}">
		{content.eyebrow}
	</p>

	<h2
		class="font-hero text-3xl sm:text-[2.25rem] tracking-[0.02em] leading-[0.95] mb-3 {urgency ===
		'locked'
			? 'text-base-content/60'
			: 'text-base-content'}"
	>
		{content.headline}
	</h2>

	<p class="text-sm leading-relaxed {showRows ? 'mb-4' : 'mb-6'} {sublineToneClass}">
		{content.subline}
		{#if content.chip}
			<span
				class="inline-flex items-center ml-1.5 px-2 py-0.5 rounded-badge text-[10px] font-mono font-bold uppercase tracking-wider whitespace-nowrap {content
					.chip.tone === 'amber'
					? 'bg-warning/20 text-warning-text'
					: 'bg-primary/15 text-primary/85'}"
			>
				{content.chip.text}
			</span>
		{/if}
	</p>

	{#if showRows}
		<div class="space-y-1.5 mb-6">
			{#each rows as row (row.id)}
				{@const chip = rowChip(row)}
				<div
					class="flex items-center justify-between gap-3 px-3 py-2 rounded-btn bg-base-100/40 border border-base-300/55"
				>
					<span class="font-display font-semibold text-sm truncate">{row.name}</span>
					<span
						class="text-[10px] font-mono font-bold uppercase tracking-wider px-2 py-0.5 rounded-badge whitespace-nowrap {chip.class}"
					>
						{chip.text}
					</span>
				</div>
			{/each}
		</div>
	{/if}

	<a href={content.primary.href} class="btn btn-primary w-full" on:click={onPrimaryClick}>
		{content.primary.label}
	</a>

	{#if content.secondary}
		<a
			href={content.secondary.href}
			class="block text-center text-xs font-mono uppercase tracking-widest text-base-content/55 hover:text-primary transition-colors mt-3"
			on:click={onSecondaryClick}
		>
			{content.secondary.label}
		</a>
	{/if}
</div>
