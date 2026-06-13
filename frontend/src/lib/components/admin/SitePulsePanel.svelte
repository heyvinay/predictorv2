<script lang="ts">
	/**
	 * SitePulsePanel — at-a-glance engagement panel for /admin Overview.
	 *
	 * v2.176.0. Renders 4 widgets in a 2×2 grid (stacks on mobile):
	 *  1. DAU sparkline (last 14 days) + today's count
	 *  2. Top 5 pages (rolling 7d w/ week-over-week trend)
	 *  3. Top 5 events (rolling 7d w/ trend)
	 *  4. Last 20 logins across the pool
	 *
	 * Partial-failure UX: PostHog widgets render a placeholder if their
	 * data list is empty (PostHog disabled or unreachable). The audit-
	 * backed Recent Logins widget always loads.
	 */
	import { onMount } from 'svelte';
	import { getSitePulse, type SitePulse } from '$lib/api/admin';

	let pulse: SitePulse | null = null;
	let loading = true;
	let error: string | null = null;

	onMount(async () => {
		try {
			pulse = await getSitePulse();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load site pulse';
		} finally {
			loading = false;
		}
	});

	// ── Sparkline divisor (max-of-counts, guarded against all-zero) ────
	$: sparkMax = pulse
		? Math.max(1, ...pulse.dau_sparkline.map((p) => p.count))
		: 1;

	// Today's DAU = last bar in the sparkline (newest is last).
	$: todayDau = pulse && pulse.dau_sparkline.length
		? pulse.dau_sparkline[pulse.dau_sparkline.length - 1].count
		: 0;

	// ── Trend indicator (shared by Top Pages + Top Events) ─────────────
	type TrendKind = 'up' | 'down' | 'flat' | 'new' | 'gone';
	interface TrendIndicator {
		kind: TrendKind;
		label: string;
		color: string;
	}

	function trendIndicator(current: number, prior: number): TrendIndicator {
		if (prior === 0 && current > 0) {
			return { kind: 'new', label: 'new', color: 'text-success' };
		}
		if (prior > 0 && current === 0) {
			return { kind: 'gone', label: 'gone', color: 'text-error' };
		}
		const delta = current - prior;
		if (delta === 0) {
			return { kind: 'flat', label: '→ flat', color: 'text-base-content/55' };
		}
		// Use percentage when prior has enough mass; absolute otherwise.
		if (prior >= 10) {
			const pct = Math.round((delta / prior) * 100);
			if (Math.abs(pct) < 5) {
				return { kind: 'flat', label: '→ flat', color: 'text-base-content/55' };
			}
			return delta > 0
				? { kind: 'up', label: `↑ +${pct}%`, color: 'text-success' }
				: { kind: 'down', label: `↓ ${pct}%`, color: 'text-warning-text' };
		}
		return delta > 0
			? { kind: 'up', label: `↑ +${delta}`, color: 'text-success' }
			: { kind: 'down', label: `↓ ${delta}`, color: 'text-warning-text' };
	}

	// ── Event-name friendly labels (Top Events widget) ─────────────────
	// Maps cryptic event names (smartfill_applied) to human-readable
	// labels (Smart Fill applied). Unknown events fall back to the raw
	// name so newly-added events still render even before this map is
	// updated.
	const EVENT_LABELS: Record<string, string> = {
		// Landing-page funnel
		landing_view: 'Landing page view',
		section_viewed: 'Landing section viewed',
		cta_clicked: 'CTA button clicked',
		news_card_clicked: 'News card clicked',
		rules_link_clicked: 'Rules link clicked',
		countdown_phase: 'Countdown phase shift',
		// Sign-in flow
		signin_email_focused: 'Sign-in email focused',
		signin_email_submitted: 'Sign-in email submitted',
		signin_google_clicked: 'Google sign-in clicked',
		signin_abandoned: 'Sign-in abandoned',
		user_signed_in: 'Signed in',
		user_onboarded: 'Completed onboarding',
		// Smart Fill
		smartfill_opened: 'Smart Fill opened',
		smartfill_applied: 'Smart Fill applied',
		// Entry lifecycle
		entry_created: 'Entry created',
		entry_submitted: 'Entry submitted',
		entry_unlocked: 'Entry unlocked',
		prediction_saved: 'Prediction saved',
		// V4 surfaces
		dashboard_view: 'Dashboard viewed'
	};

	function eventLabel(raw: string): string {
		return EVENT_LABELS[raw] ?? raw;
	}

	// ── Relative time formatter for the Recent Logins widget ───────────
	function relativeTime(iso: string): string {
		const ts = new Date(iso).getTime();
		const diffMs = Date.now() - ts;
		const min = Math.floor(diffMs / 60000);
		if (min < 1) return 'just now';
		if (min < 60) return `${min}m ago`;
		const hr = Math.floor(min / 60);
		if (hr < 24) return `${hr}h ago`;
		const day = Math.floor(hr / 24);
		if (day < 30) return `${day}d ago`;
		return new Date(iso).toLocaleDateString();
	}
</script>

<section class="card bg-base-200/60 border border-base-300/30 mb-5">
	<div class="card-body">
		<div class="flex items-baseline justify-between gap-3 mb-3">
			<div>
				<p class="text-[10px] font-mono uppercase tracking-[0.2em] text-primary">
					Site Pulse · last 14 days · PostHog + audit
				</p>
				<h2 class="font-display font-bold text-lg mt-1">Engagement at a glance</h2>
			</div>
			<span class="text-[11px] text-base-content/40 font-mono">cached 5 min</span>
		</div>

		{#if loading}
			<p class="text-sm text-base-content/55">Loading site pulse…</p>
		{:else if error}
			<p class="text-sm text-error">Couldn't load site pulse: {error}</p>
		{:else if pulse}
			<div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
				<!-- Widget 1: DAU sparkline -->
				<div class="rounded-box bg-base-100/40 border border-base-300/20 p-4">
					<div class="flex items-baseline justify-between mb-2">
						<span class="text-[10px] uppercase tracking-widest text-base-content/40 font-mono">
							Daily active users
						</span>
						<span class="text-[10px] text-base-content/40">14d</span>
					</div>
					{#if pulse.dau_sparkline.length === 0}
						<p class="text-sm text-base-content/50">
							PostHog data unavailable — set <code class="font-mono text-xs">POSTHOG_PERSONAL_API_KEY</code>
							+ <code class="font-mono text-xs">POSTHOG_PROJECT_ID</code>.
						</p>
					{:else}
						<div class="flex items-baseline gap-3 mb-3">
							<div class="font-display font-bold text-3xl">{todayDau}</div>
							<div class="text-xs text-base-content/55">today</div>
						</div>
						<div class="flex items-end gap-1 h-12" title="14-day DAU, oldest left → newest right">
							{#each pulse.dau_sparkline as point}
								<div
									class="flex-1 bg-primary/70 rounded-sm"
									style="height: {Math.max(8, (point.count / sparkMax) * 100)}%; min-height: 2px;"
									title="{point.date}: {point.count} users"
								></div>
							{/each}
						</div>
					{/if}
				</div>

				<!-- Widget 2: Top 5 pages -->
				<div class="rounded-box bg-base-100/40 border border-base-300/20 p-4">
					<div class="flex items-baseline justify-between mb-2">
						<span class="text-[10px] uppercase tracking-widest text-base-content/40 font-mono">
							Top pages
						</span>
						<span class="text-[10px] text-base-content/40">last 7d · vs prior 7d</span>
					</div>
					{#if pulse.top_pages.length === 0}
						<p class="text-sm text-base-content/50">PostHog data unavailable.</p>
					{:else}
						<ul class="space-y-1.5">
							{#each pulse.top_pages as p (p.path)}
								{@const trend = trendIndicator(p.current_7d, p.prior_7d)}
								<li class="flex items-center justify-between gap-3 text-sm">
									<span class="font-mono text-xs truncate flex-1" title={p.path}>{p.path}</span>
									<span class="font-display font-bold text-sm tabular-nums">{p.current_7d}</span>
									<span class="font-mono text-[11px] {trend.color} w-16 text-right">{trend.label}</span>
								</li>
							{/each}
						</ul>
					{/if}
				</div>

				<!-- Widget 3: Top 5 events -->
				<div class="rounded-box bg-base-100/40 border border-base-300/20 p-4">
					<div class="flex items-baseline justify-between mb-2">
						<span class="text-[10px] uppercase tracking-widest text-base-content/40 font-mono">
							Top events
						</span>
						<span class="text-[10px] text-base-content/40">last 7d · vs prior 7d</span>
					</div>
					{#if pulse.top_events.length === 0}
						<p class="text-sm text-base-content/50">PostHog data unavailable.</p>
					{:else}
						<ul class="space-y-1.5">
							{#each pulse.top_events as e (e.event_name)}
								{@const trend = trendIndicator(e.current_7d, e.prior_7d)}
								<li class="flex items-center justify-between gap-3 text-sm">
									<span class="truncate flex-1" title={e.event_name}>{eventLabel(e.event_name)}</span>
									<span class="font-display font-bold text-sm tabular-nums">{e.current_7d}</span>
									<span class="font-mono text-[11px] {trend.color} w-16 text-right">{trend.label}</span>
								</li>
							{/each}
						</ul>
					{/if}
				</div>

				<!-- Widget 4: Last 20 logins -->
				<div class="rounded-box bg-base-100/40 border border-base-300/20 p-4">
					<div class="flex items-baseline justify-between mb-2">
						<span class="text-[10px] uppercase tracking-widest text-base-content/40 font-mono">
							Recent logins
						</span>
						<span class="text-[10px] text-base-content/40">last 20 · pool-wide</span>
					</div>
					{#if pulse.recent_logins.length === 0}
						<p class="text-sm text-base-content/50">No recent logins.</p>
					{:else}
						<ul class="space-y-1 max-h-44 overflow-y-auto pr-1">
							{#each pulse.recent_logins as login (login.user_id + login.login_at)}
								<li class="flex items-center justify-between gap-2 text-xs">
									<span class="truncate flex-1">{login.name || '(no name)'}</span>
									<span class="text-base-content/40 font-mono tabular-nums">{relativeTime(login.login_at)}</span>
								</li>
							{/each}
						</ul>
					{/if}
				</div>
			</div>
		{/if}
	</div>
</section>
