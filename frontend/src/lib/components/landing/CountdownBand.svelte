<!--
	CountdownBand — live countdown to Phase 1 lock with urgency tiers
	that escalate as the deadline approaches. Same component, four
	visually-distinct states driven by time remaining:

	  calm      — > 7 days  → mint green, "Pools locks in"
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
	import { derivePhase, countdownCopy, type CountdownPhase } from '$lib/utils/countdownPhase';

	export let phase1Deadline: string | null = null;
	/** Where this countdown is rendered — passed to the auth CTA for
	 *  consistent analytics tagging. */
	export let ctaHref: string = '/login';
	export let ctaPlacement: string = 'countdown';
	/** 'band' (default) renders the full-width chrome with top/bottom
	 *  border lines. 'card' drops the chrome so the component fits in a
	 *  narrower grid column alongside other content. */
	export let variant: 'band' | 'card' = 'band';

	type Phase = CountdownPhase;

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
	// Dynamic label + subline derived from time-remaining, not the
	// phase tier. Phase still drives colour / pulse / CTA, but the
	// words update every tick within a tier (e.g. heads_up spans
	// 2–7d but the label flips from "Last week" to "Final days" at
	// the 3-day boundary). Sub-second updates are cheap — same
	// shape on every render.
	$: copy = countdownCopy(secondsRemaining);

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
		ctaLabel: string | null;
	};

	// PHASE_CONFIG now owns ONLY colour / pulse / CTA — the visual
	// escalation. Wording (label + subline) is computed dynamically by
	// `countdownCopy(secondsRemaining)` in countdownPhase.ts so the text
	// stays accurate within each tier (heads_up spans 2–7d but the words
	// flip between "Last week" and "Final days" inside that range).
	const PHASE_CONFIG: Record<Phase, PhaseConfig> = {
		calm: {
			colorClass: 'text-success',
			pulseClass: '',
			ctaLabel: null
		},
		heads_up: {
			colorClass: 'text-warning-text',
			pulseClass: 'animate-pulse-soft',
			ctaLabel: null
		},
		urgent: {
			colorClass: 'text-error',
			pulseClass: 'animate-pulse-soft',
			ctaLabel: 'Lock in'
		},
		critical: {
			colorClass: 'text-error',
			pulseClass: 'animate-pulse-soft',
			ctaLabel: 'Quick fill'
		},
		locked: {
			colorClass: 'text-success',
			pulseClass: '',
			ctaLabel: null
		},
		unknown: {
			colorClass: 'text-base-content/60',
			pulseClass: '',
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

{#if variant === 'band'}
	<div class="bg-base-300/40 border-y border-primary noise">
		<div class="max-w-[1200px] mx-auto mobile-padding py-10 sm:py-12 text-center">
			<p class="text-xs sm:text-sm font-mono uppercase tracking-[0.18em] {config.colorClass} mb-3">
				{copy.label}
			</p>
			<div
				class="font-hero tabular-nums whitespace-nowrap {config.colorClass} {config.pulseClass}
					text-[clamp(36px,10vw,124px)] leading-none tracking-tight"
			>
				{#if parts}
					<span>{parts.dd}</span>
					<span class="opacity-60 px-1 sm:px-2">:</span>
					<span>{parts.hh}</span>
					<span class="opacity-60 px-1 sm:px-2">:</span>
					<span>{parts.mm}</span>
					<span class="opacity-60 px-1 sm:px-2">:</span>
					<span>{parts.ss}</span>
				{:else}
					<span>—</span>
					<span class="opacity-60 px-1 sm:px-2">:</span>
					<span>—</span>
					<span class="opacity-60 px-1 sm:px-2">:</span>
					<span>—</span>
					<span class="opacity-60 px-1 sm:px-2">:</span>
					<span>—</span>
				{/if}
			</div>
			<p class="text-sm text-base-content/70 mt-4 max-w-2xl mx-auto leading-relaxed">
				{copy.subline}
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
{:else}
	<!-- 'card' variant — fits in a grid column next to other content -->
	<div class="text-center">
		<p class="text-xs sm:text-sm font-mono uppercase tracking-[0.18em] {config.colorClass} mb-3">
			{copy.label}
		</p>
		<div
			class="font-hero tabular-nums whitespace-nowrap {config.colorClass} {config.pulseClass}
				text-[clamp(32px,7vw,72px)] leading-none tracking-tight"
		>
			{#if parts}
				<span>{parts.dd}</span>
				<span class="opacity-60 px-1 sm:px-2">:</span>
				<span>{parts.hh}</span>
				<span class="opacity-60 px-1 sm:px-2">:</span>
				<span>{parts.mm}</span>
				<span class="opacity-60 px-1 sm:px-2">:</span>
				<span>{parts.ss}</span>
			{:else}
				<span>—</span>
				<span class="opacity-60 px-1 sm:px-2">:</span>
				<span>—</span>
				<span class="opacity-60 px-1 sm:px-2">:</span>
				<span>—</span>
				<span class="opacity-60 px-1 sm:px-2">:</span>
				<span>—</span>
			{/if}
		</div>
		<p class="text-sm text-base-content/70 mt-4 leading-relaxed">
			{copy.subline}
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
{/if}
