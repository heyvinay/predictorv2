<!--
	CountdownBand — live countdown to Phase 1 lock with urgency tiers
	that escalate as the deadline approaches. Same component, four
	visually-distinct states driven by time remaining:

	  calm      — > 7 days  → mint green, "Phase 1 locks in"
	  heads-up  — 1-7 days  → amber, "Last week"
	  urgent    — < 24h     → red, "Last day" + inline "Lock in →" pill
	  critical  — < 1h      → red + pulsing, "Minutes left" + larger CTA
	  locked    — past 0    → mint, "Locked — the tournament begins"

	`setInterval(1000)` updates every second. The `countdown_phase`
	analytics event fires once per tier transition so we can measure
	how visitors behave at different urgency levels.

	Falls back to "Locks in soon" when `phase1Deadline` is null (e.g.
	competition not yet configured / API down).
-->
<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { track } from '$lib/analytics';
	import ArrowRight from 'lucide-svelte/icons/arrow-right';

	export let phase1Deadline: string | null = null;
	/** Where this countdown is rendered — passed to the auth CTA for
	 *  consistent analytics tagging. */
	export let ctaHref: string = '/login';
	export let ctaPlacement: string = 'countdown';

	type Phase = 'calm' | 'heads_up' | 'urgent' | 'critical' | 'locked' | 'unknown';

	let now = Date.now();
	let timer: ReturnType<typeof setInterval> | null = null;
	let lastPhase: Phase = 'unknown';

	onMount(() => {
		timer = setInterval(() => {
			now = Date.now();
		}, 1000);
	});

	onDestroy(() => {
		if (timer) clearInterval(timer);
	});

	$: deadlineMs = phase1Deadline ? new Date(phase1Deadline).getTime() : null;
	$: secondsRemaining = deadlineMs === null ? null : Math.max(0, Math.floor((deadlineMs - now) / 1000));
	$: phase = derivePhase(secondsRemaining);
	$: parts = secondsRemaining === null ? null : breakdown(secondsRemaining);
	$: config = PHASE_CONFIG[phase];

	// Fire analytics on phase transition.
	$: if (phase !== lastPhase && phase !== 'unknown') {
		if (lastPhase !== 'unknown') {
			track('countdown_phase', {
				phase,
				seconds_remaining: secondsRemaining ?? 0
			});
		}
		lastPhase = phase;
	}

	function derivePhase(secs: number | null): Phase {
		if (secs === null) return 'unknown';
		if (secs <= 0) return 'locked';
		if (secs < 3600) return 'critical';
		if (secs < 86_400) return 'urgent';
		if (secs < 604_800) return 'heads_up';
		return 'calm';
	}

	function breakdown(secs: number): { dd: string; hh: string; mm: string; ss: string } {
		const dd = Math.floor(secs / 86_400);
		const hh = Math.floor((secs % 86_400) / 3600);
		const mm = Math.floor((secs % 3600) / 60);
		const ss = secs % 60;
		return {
			dd: String(dd).padStart(2, '0'),
			hh: String(hh).padStart(2, '0'),
			mm: String(mm).padStart(2, '0'),
			ss: String(ss).padStart(2, '0')
		};
	}

	type PhaseConfig = {
		colorClass: string;
		pulseClass: string;
		label: string;
		subline: string;
		ctaLabel: string | null;
	};

	const PHASE_CONFIG: Record<Phase, PhaseConfig> = {
		calm: {
			colorClass: 'text-success',
			pulseClass: '',
			label: 'Phase 1 locks in',
			subline:
				"Plenty of time. But picks stay editable until kickoff — lock in early, tweak later.",
			ctaLabel: null
		},
		heads_up: {
			colorClass: 'text-warning',
			pulseClass: 'animate-pulse-soft',
			label: 'Last week',
			subline: "One week until your picks are frozen. Don't be the friend who forgot.",
			ctaLabel: null
		},
		urgent: {
			colorClass: 'text-error',
			pulseClass: 'animate-pulse-soft',
			label: 'Last day',
			subline: 'Lock in your picks now. Smart Fill takes 2 minutes.',
			ctaLabel: 'Lock in'
		},
		critical: {
			colorClass: 'text-error',
			pulseClass: 'animate-pulse-soft',
			label: 'Minutes left',
			subline: 'Last chance. Smart Fill finishes in 90 seconds.',
			ctaLabel: 'Quick fill'
		},
		locked: {
			colorClass: 'text-success',
			pulseClass: '',
			label: 'Locked',
			subline: 'The tournament begins.',
			ctaLabel: null
		},
		unknown: {
			colorClass: 'text-base-content/60',
			pulseClass: '',
			label: 'Phase 1',
			subline: 'Locks in soon.',
			ctaLabel: null
		}
	};

	function onCtaClick() {
		track('cta_clicked', {
			placement: ctaPlacement,
			cta_label: config.ctaLabel ?? 'countdown_cta'
		});
	}
</script>

<div class="bg-base-300/40 border-y border-primary noise">
	<div class="max-w-[1200px] mx-auto mobile-padding py-10 sm:py-12 text-center">
		<p class="text-xs sm:text-sm font-mono uppercase tracking-[0.18em] {config.colorClass} mb-3">
			{config.label}
		</p>

		<div
			class="font-hero tabular-nums {config.colorClass} {config.pulseClass}
				text-[clamp(54px,10.5vw,124px)] leading-none tracking-[0.05em]"
		>
			{#if parts}
				<span class="inline-block min-w-[1.6em]">{parts.dd}</span>
				<span class="opacity-60">:</span>
				<span class="inline-block min-w-[1.6em]">{parts.hh}</span>
				<span class="opacity-60">:</span>
				<span class="inline-block min-w-[1.6em]">{parts.mm}</span>
				<span class="opacity-60">:</span>
				<span class="inline-block min-w-[1.6em]">{parts.ss}</span>
			{:else}
				<span class="inline-block min-w-[1.6em]">—</span>
				<span class="opacity-60">:</span>
				<span class="inline-block min-w-[1.6em]">—</span>
				<span class="opacity-60">:</span>
				<span class="inline-block min-w-[1.6em]">—</span>
				<span class="opacity-60">:</span>
				<span class="inline-block min-w-[1.6em]">—</span>
			{/if}
		</div>

		<p class="text-sm text-base-content/70 mt-4 max-w-2xl mx-auto leading-relaxed">
			{config.subline}
		</p>

		{#if config.ctaLabel}
			<a
				href={ctaHref}
				class="inline-flex items-center gap-1.5 mt-5 px-4 py-2 rounded-btn
					bg-primary text-primary-content font-semibold text-sm hover:opacity-90 transition-opacity"
				on:click={onCtaClick}
			>
				{config.ctaLabel}
				<ArrowRight size={16} strokeWidth={2.5} />
			</a>
		{/if}
	</div>
</div>
