<script lang="ts">
	import { onMount } from 'svelte';
	import {
		getUsageReport,
		getUsageFeatureAdopters,
		type UsageReport,
		type UsageRange,
		type UsageGranularity,
		type UsageSegment,
		type UsageFeatureAdoption,
		type UsagePowerUser,
		type UsageFeatureAdopter
	} from '$lib/api/admin';

	// v2.212.0 — Usage & Adoption dashboard. A deliberately separate,
	// more analytical surface from the Site Pulse panel on the Overview
	// tab (which stays narrow/operational per its own design doc). See
	// docs/superpowers/specs/2026-07-13-usage-adoption-dashboard-design.md.

	let report: UsageReport | null = null;
	let loading = true;
	let error: string | null = null;

	let range: UsageRange = '7d';
	let granularity: UsageGranularity | undefined = undefined;
	let segment: UsageSegment = 'all';
	let compareOn = true;

	const RANGE_OPTIONS: { key: UsageRange; label: string }[] = [
		{ key: '1h', label: 'Last hour' },
		{ key: '24h', label: '24h' },
		{ key: '7d', label: '7 days' },
		{ key: '30d', label: '30 days' },
		{ key: 'all', label: 'Tournament' }
	];
	const GRAN_OPTIONS: { key: UsageGranularity; label: string }[] = [
		{ key: 'hour', label: 'Hourly' },
		{ key: 'day', label: 'Daily' },
		{ key: 'week', label: 'Weekly' }
	];
	const SEGMENT_OPTIONS: { key: UsageSegment; label: string }[] = [
		{ key: 'all', label: 'All' },
		{ key: 'atlas', label: 'Atlas' },
		{ key: 'jmfa', label: 'JMFA' },
		{ key: 'neither', label: 'Guests' }
	];

	async function loadReport() {
		loading = true;
		error = null;
		try {
			report = await getUsageReport({ range, granularity, segment });
			// Reflect the backend's per-range default granularity back
			// into the control so the Granularity pills stay in sync
			// (e.g. picking "Tournament" auto-selects Weekly).
			granularity = report.granularity;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load the usage report.';
		} finally {
			loading = false;
		}
	}

	function pickRange(r: UsageRange) {
		range = r;
		granularity = undefined;
		loadReport();
	}
	function pickGranularity(g: UsageGranularity) {
		granularity = g;
		loadReport();
	}
	function pickSegment(s: UsageSegment) {
		segment = s;
		loadReport();
	}

	onMount(loadReport);

	// ── KPI display helpers ──────────────────────────────────────────
	function kpiDisplayValue(value: number | null, key: string): string {
		if (value === null) return key === 'stickiness' ? 'needs a day+' : '—';
		if (key === 'stickiness' || key === 'sessions_per_user') return value.toFixed(1);
		return String(Math.round(value));
	}
	function deltaClass(delta: number | null): string {
		if (delta === null) return 'text-base-content/40';
		if (delta > 0) return 'text-success';
		if (delta < 0) return 'text-warning-text';
		return 'text-base-content/55';
	}
	function deltaLabel(delta: number | null, key: string): string {
		if (delta === null) return '';
		const unit = key === 'stickiness' ? ' pts' : '%';
		const sign = delta > 0 ? '↑ +' : delta < 0 ? '↓ ' : '→ ';
		return `${sign}${Math.abs(delta)}${unit}`;
	}

	// ── Time-of-day peak ─────────────────────────────────────────────
	$: todMax = report ? Math.max(1, ...report.time_of_day) : 1;
	$: todPeakHour = report
		? report.time_of_day.indexOf(Math.max(...report.time_of_day))
		: null;
	$: todHasData = report ? report.time_of_day.some((v) => v > 0) : false;

	function hourLabel(h: number): string {
		return h < 10 ? `0${h}` : String(h);
	}

	// ── Retention heatmap coloring ────────────────────────────────────
	// Two-segment diverging blend through DaisyUI's own theme tokens
	// (error → warning → success) so the ramp is theme-aware without
	// hardcoding hex — mirrors the "route every value through hsl(var(--p))"
	// convention used elsewhere (Group Stage Winner Card).
	function retentionCellStyle(pct: number): string {
		if (pct <= 50) {
			const t = Math.round((pct / 50) * 100);
			return `background: color-mix(in srgb, hsl(var(--wa)) ${t}%, hsl(var(--er)) ${100 - t}%);`;
		}
		const t = Math.round(((pct - 50) / 50) * 100);
		return `background: color-mix(in srgb, hsl(var(--su)) ${t}%, hsl(var(--wa)) ${100 - t}%);`;
	}
	function retentionTextClass(pct: number): string {
		// The amber midrange renders light enough for dark ink; the
		// churned (low) and fully-retained (high) ends are dark/
		// saturated enough to need white. Spot-checked against the
		// design wireframe's measured ramp.
		return pct < 35 || pct > 85 ? 'text-white' : 'text-[#0B1020]';
	}

	// ── Frequency histogram ──────────────────────────────────────────
	$: freqMax = report ? Math.max(1, ...report.frequency_buckets.map((b) => b.count)) : 1;

	// ── Power users table: mode + client-side sort ───────────────────
	type PowerMode = 'most' | 'least' | 'never';
	type SortKey = 'logins' | 'active_days' | 'sessions' | 'last_seen_at';
	let powerMode: PowerMode = 'most';
	let sortKey: SortKey = 'active_days';
	let sortDir: 'asc' | 'desc' = 'desc';

	function pickPowerMode(m: PowerMode) {
		powerMode = m;
		sortKey = m === 'never' ? 'logins' : 'active_days';
		sortDir = m === 'least' ? 'asc' : 'desc';
	}
	function sortBy(key: SortKey) {
		if (sortKey === key) {
			sortDir = sortDir === 'asc' ? 'desc' : 'asc';
		} else {
			sortKey = key;
			sortDir = 'desc';
		}
	}

	$: powerRowsRaw = !report
		? []
		: powerMode === 'most'
			? report.power_users_most_active
			: powerMode === 'least'
				? report.power_users_least_active
				: report.power_users_never_engaged;

	$: powerRows = [...powerRowsRaw].sort((a, b) => {
		const av = a[sortKey];
		const bv = b[sortKey];
		if (av === bv) return 0;
		if (av === null) return 1;
		if (bv === null) return -1;
		const cmp = av < bv ? -1 : 1;
		return sortDir === 'asc' ? cmp : -cmp;
	});

	function relativeTime(iso: string | null): string {
		if (!iso) return 'never';
		const diffMs = Date.now() - new Date(iso).getTime();
		const min = Math.floor(diffMs / 60000);
		if (min < 1) return 'just now';
		if (min < 60) return `${min}m ago`;
		const hr = Math.floor(min / 60);
		if (hr < 24) return `${hr}h ago`;
		const day = Math.floor(hr / 24);
		if (day < 30) return `${day}d ago`;
		return new Date(iso).toLocaleDateString();
	}

	// ── Drawer (feature-adopter drill-down + user summary) ───────────
	let drawerOpen = false;
	let drawerMode: 'feature' | 'user' | null = null;
	let drawerFeature: UsageFeatureAdoption | null = null;
	let drawerAdopters: UsageFeatureAdopter[] = [];
	let drawerAdoptersLoading = false;
	let drawerUser: UsagePowerUser | null = null;

	async function openFeatureDrawer(f: UsageFeatureAdoption) {
		drawerMode = 'feature';
		drawerFeature = f;
		drawerOpen = true;
		drawerAdopters = [];
		drawerAdoptersLoading = true;
		try {
			drawerAdopters = await getUsageFeatureAdopters(f.key, { range, segment });
		} catch {
			drawerAdopters = [];
		} finally {
			drawerAdoptersLoading = false;
		}
	}
	function openUserDrawer(u: UsagePowerUser) {
		drawerMode = 'user';
		drawerUser = u;
		drawerOpen = true;
	}
	function closeDrawer() {
		drawerOpen = false;
	}
</script>

<div class="max-w-[1200px] mx-auto px-4 sm:px-6 py-6 space-y-5">
	<div>
		<p class="text-[10px] font-mono uppercase tracking-[0.2em] text-primary">
			Usage &amp; Adoption
		</p>
		<h1 class="font-display font-bold text-xl mt-1">Who's using what, and who isn't</h1>
		<p class="text-sm text-base-content/55 mt-1">
			Every widget below responds to the time range, granularity, and segment picked here.
		</p>
	</div>

	<!-- ============ GLOBAL CONTROL BAR ============ -->
	<div
		class="card bg-base-200/60 border border-base-300/30 p-3 flex flex-row flex-wrap items-end gap-4"
	>
		<div class="flex flex-col gap-1.5">
			<span class="text-[9px] font-mono uppercase tracking-[0.14em] text-base-content/40"
				>Time range</span
			>
			<div class="inline-flex bg-base-100 border border-base-300/40 rounded-full p-1 gap-0.5">
				{#each RANGE_OPTIONS as opt}
					<button
						type="button"
						class="px-3 py-1.5 rounded-full text-xs font-semibold whitespace-nowrap transition-colors {range ===
						opt.key
							? 'bg-primary text-primary-content'
							: 'text-base-content/60'}"
						on:click={() => pickRange(opt.key)}
					>
						{opt.label}
					</button>
				{/each}
			</div>
		</div>

		<div class="flex flex-col gap-1.5">
			<span class="text-[9px] font-mono uppercase tracking-[0.14em] text-base-content/40"
				>Granularity</span
			>
			<div class="inline-flex bg-base-100 border border-base-300/40 rounded-full p-1 gap-0.5">
				{#each GRAN_OPTIONS as opt}
					<button
						type="button"
						class="px-3 py-1.5 rounded-full text-xs font-semibold whitespace-nowrap transition-colors {granularity ===
						opt.key
							? 'bg-primary-soft text-primary'
							: 'text-base-content/60'}"
						on:click={() => pickGranularity(opt.key)}
					>
						{opt.label}
					</button>
				{/each}
			</div>
		</div>

		<div class="flex flex-col gap-1.5">
			<span class="text-[9px] font-mono uppercase tracking-[0.14em] text-base-content/40"
				>Segment</span
			>
			<div class="inline-flex bg-base-100 border border-base-300/40 rounded-full p-1 gap-0.5">
				{#each SEGMENT_OPTIONS as opt}
					<button
						type="button"
						class="px-3 py-1.5 rounded-full text-xs font-semibold whitespace-nowrap transition-colors {segment ===
						opt.key
							? 'bg-primary-soft text-primary'
							: 'text-base-content/60'}"
						on:click={() => pickSegment(opt.key)}
					>
						{opt.label}
					</button>
				{/each}
			</div>
		</div>

		<div class="flex-1"></div>

		<label class="inline-flex items-center gap-2 text-xs font-semibold text-base-content pb-1.5">
			<input type="checkbox" class="toggle toggle-primary toggle-sm" bind:checked={compareOn} />
			Compare to previous period
		</label>
	</div>

	{#if loading && !report}
		<p class="text-sm text-base-content/55">Loading usage report…</p>
	{:else if error}
		<p class="text-sm text-error">Couldn't load the usage report: {error}</p>
	{:else if report}
		{#if !report.posthog_available}
			<div
				class="rounded-box bg-warning/10 border border-warning/30 px-4 py-2.5 text-sm text-warning-text"
			>
				PostHog is unavailable — set <code class="font-mono text-xs"
					>POSTHOG_PERSONAL_API_KEY</code
				>
				+ <code class="font-mono text-xs">POSTHOG_PROJECT_ID</code>. The funnel below still reflects
				live database counts; every PostHog-sourced widget shows an empty state.
			</div>
		{/if}

		<!-- ============ FUNNEL STRIP ============ -->
		<div class="grid grid-cols-2 sm:grid-cols-5 gap-2.5">
			<div class="card bg-base-200/60 border border-base-300/30 p-3.5">
				<span class="font-display font-bold text-2xl text-success">{report.funnel.submitters}</span
				>
				<p class="text-xs text-base-content/55 font-semibold mt-0.5">Submitters</p>
			</div>
			<div class="card bg-base-200/60 border border-base-300/30 p-3.5">
				<span class="font-display font-bold text-2xl">{report.funnel.no_entry}</span>
				<p class="text-xs text-base-content/55 font-semibold mt-0.5">No entry yet</p>
			</div>
			<div class="card bg-base-200/60 border border-base-300/30 p-3.5">
				<span class="font-display font-bold text-2xl">{report.funnel.draft_holders}</span>
				<p class="text-xs text-base-content/55 font-semibold mt-0.5">Draft only</p>
			</div>
			<div class="card bg-base-200/60 border border-base-300/30 p-3.5">
				<span class="font-display font-bold text-2xl text-warning-text"
					>{report.funnel.lapsing}</span
				>
				<p class="text-xs text-base-content/55 font-semibold mt-0.5">Lapsing (3–7d)</p>
			</div>
			<div class="card bg-base-200/60 border border-base-300/30 p-3.5">
				<span class="font-display font-bold text-2xl text-error">{report.funnel.pool_ghost}</span>
				<p class="text-xs text-base-content/55 font-semibold mt-0.5">Pool ghost</p>
			</div>
		</div>

		<!-- ============ KPI SCORECARD ============ -->
		<div class="grid grid-cols-2 lg:grid-cols-4 gap-2.5">
			{#each report.kpis as kpi, i}
				<div
					class="card border border-base-300/30 p-3.5 {i === 0 ? 'bg-primary/5' : 'bg-base-200'}"
				>
					<span class="text-xs text-base-content/55 font-semibold">{kpi.label}</span>
					<div class="flex items-baseline gap-1.5 mt-1">
						<span
							class="font-display font-bold text-2xl"
							class:text-primary={i === 0}
						>
							{kpiDisplayValue(kpi.value, kpi.key)}{kpi.value !== null ? kpi.suffix : ''}
						</span>
					</div>
					{#if compareOn}
						<span class="text-[11px] font-mono font-semibold {deltaClass(kpi.delta_pct)}"
							>{deltaLabel(kpi.delta_pct, kpi.key)}</span
						>
					{/if}
					{#if kpi.sparkline.length > 0}
						<div class="flex items-end gap-0.5 h-6 mt-2">
							{#each kpi.sparkline as v}
								<span
									class="flex-1 bg-primary/50 rounded-sm min-h-[2px]"
									style="height: {Math.max(8, (v / Math.max(1, Math.max(...kpi.sparkline))) * 100)}%"
								></span>
							{/each}
						</div>
					{/if}
				</div>
			{/each}
		</div>

		<!-- ============ TREND + TIME OF DAY ============ -->
		<div class="grid grid-cols-1 lg:grid-cols-2 gap-3">
			<div class="card bg-base-200/60 border border-base-300/30 p-4">
				<div class="flex items-baseline justify-between mb-2">
					<h2 class="font-display font-bold text-base">Active users over time</h2>
					<span class="text-[10px] text-base-content/40 font-mono"
						>{report.granularity} · {report.range}</span
					>
				</div>
				{#if report.active_users_series.length === 0}
					<p class="text-sm text-base-content/50">PostHog data unavailable.</p>
				{:else}
					{@const maxCount = Math.max(1, ...report.active_users_series.map((p) => p.count))}
					<div class="flex items-end gap-1.5 h-32 border-b border-base-300/30 pt-2">
						{#each report.active_users_series as point}
							<div class="flex-1 flex flex-col items-center justify-end gap-1 h-full">
								<span class="text-[10px] text-base-content/55 font-mono">{point.count}</span>
								<div
									class="w-full max-w-[40px] bg-primary/60 rounded-t-sm min-h-[2px]"
									style="height: {Math.max(8, (point.count / maxCount) * 100)}%"
								></div>
							</div>
						{/each}
					</div>
					<div class="flex gap-1.5 mt-1">
						{#each report.active_users_series as point}
							<span class="flex-1 max-w-[40px] text-center text-[9px] text-base-content/40 font-mono truncate"
								>{point.bucket}</span
							>
						{/each}
					</div>
				{/if}
			</div>

			<div class="card bg-base-200/60 border border-base-300/30 p-4">
				<div class="flex items-baseline justify-between mb-2">
					<h2 class="font-display font-bold text-base">Time of day</h2>
					<span class="text-[10px] text-base-content/40 font-mono">within {report.range}</span>
				</div>
				{#if !todHasData}
					<p class="text-sm text-base-content/50">
						No hourly data in this range — try a wider window.
					</p>
				{:else}
					<div class="flex items-end gap-[3px] h-32 border-b border-base-300/30 pt-2">
						{#each report.time_of_day as v, h}
							<div class="flex-1 h-full flex items-end">
								<div
									class="w-full rounded-t-sm min-h-[2px] {h === todPeakHour
										? 'bg-primary'
										: 'bg-primary/40'}"
									style="height: {v === 0 ? 0 : Math.max(4, (v / todMax) * 100)}%"
									title="{hourLabel(h)}:00 · {v} active"
								></div>
							</div>
						{/each}
					</div>
					<div class="flex gap-[3px] mt-1">
						{#each report.time_of_day as _, h}
							<span class="flex-1 text-center text-[9px] text-base-content/40 font-mono"
								>{h % 6 === 0 ? hourLabel(h) : ''}</span
							>
						{/each}
					</div>
					{#if todPeakHour !== null}
						<p class="text-xs text-base-content/55 mt-2">
							Peak check-in window <b class="text-primary">{hourLabel(todPeakHour)}:00</b> —
							schedule broadcasts around this hour.
						</p>
					{/if}
				{/if}
			</div>
		</div>

		<!-- ============ RETENTION + FREQUENCY ============ -->
		<div class="grid grid-cols-1 lg:grid-cols-2 gap-3">
			<div class="card bg-base-200/60 border border-base-300/30 p-4">
				<h2 class="font-display font-bold text-base mb-2">Weekly retention</h2>
				{#if report.retention_cohorts.length === 0}
					<p class="text-sm text-base-content/50">Not enough weekly history yet.</p>
				{:else}
					<div class="grid gap-1" style="grid-template-columns: auto repeat(5, 1fr);">
						<div></div>
						{#each ['W0', 'W1', 'W2', 'W3', 'W4'] as h}
							<div class="text-center text-[9px] font-mono text-base-content/40 uppercase">
								{h}
							</div>
						{/each}
						{#each report.retention_cohorts as row}
							<div
								class="text-right text-[10px] font-mono text-base-content/55 pr-2 flex items-center justify-end"
							>
								{row.cohort_week}
							</div>
							{#each row.pct_by_offset as pct}
								{#if pct === null}
									<div></div>
								{:else}
									<div
										class="rounded text-center font-mono font-semibold text-xs py-1.5 {retentionTextClass(
											pct
										)}"
										style={retentionCellStyle(pct)}
									>
										{pct}%
									</div>
								{/if}
							{/each}
						{/each}
					</div>
					<p class="text-xs text-base-content/55 mt-2">
						Read across a row: of everyone first seen that week, how many came back.
					</p>
				{/if}
			</div>

			<div class="card bg-base-200/60 border border-base-300/30 p-4">
				<h2 class="font-display font-bold text-base mb-2">Engagement frequency</h2>
				{#if report.frequency_buckets.length === 0}
					<p class="text-sm text-base-content/50">PostHog data unavailable.</p>
				{:else}
					<div class="flex items-end gap-2.5 h-32 border-b border-base-300/30 pt-2">
						{#each report.frequency_buckets as bucket}
							<div class="flex-1 flex flex-col items-center justify-end gap-1 h-full">
								<span class="text-[11px] text-base-content/55 font-mono">{bucket.count}</span>
								<div
									class="w-full rounded-t-sm min-h-[2px] {bucket.is_dormant
										? 'bg-error/55'
										: bucket.is_power
											? 'bg-primary'
											: 'bg-success/55'}"
									style="height: {Math.max(4, (bucket.count / freqMax) * 100)}%"
								></div>
							</div>
						{/each}
					</div>
					<div class="flex gap-2.5 mt-1">
						{#each report.frequency_buckets as bucket}
							<span class="flex-1 text-center text-[10px] text-base-content/40 font-mono"
								>{bucket.label}</span
							>
						{/each}
					</div>
					<div class="flex items-center gap-4 mt-2 text-[10px] font-mono text-base-content/50">
						<span class="flex items-center gap-1.5"
							><span class="w-3.5 h-2 rounded-sm bg-error/55 inline-block"></span> dormant</span
						>
						<span class="flex items-center gap-1.5"
							><span class="w-3.5 h-2 rounded-sm bg-success/55 inline-block"></span> casual</span
						>
						<span class="flex items-center gap-1.5"
							><span class="w-3.5 h-2 rounded-sm bg-primary inline-block"></span> power (8+ days)</span
						>
					</div>
				{/if}
			</div>
		</div>

		<!-- ============ FEATURE ADOPTION ============ -->
		<div class="card bg-base-200/60 border border-base-300/30 p-4">
			<div class="flex items-baseline justify-between mb-3 flex-wrap gap-2">
				<h2 class="font-display font-bold text-base">Feature adoption</h2>
				<span class="text-[10px] font-mono text-base-content/40"
					>% of {report.funnel.submitters} submitters · click a row → who uses it</span
				>
			</div>
			<div class="flex flex-col gap-1.5">
				{#each report.feature_adoption as f}
					<button
						type="button"
						class="grid grid-cols-[1fr_auto] sm:grid-cols-[180px_1fr_120px_16px] items-center gap-3 w-full text-left rounded-btn px-2 py-1.5 hover:bg-primary/[0.06] transition-colors"
						on:click={() => openFeatureDrawer(f)}
					>
						<span class="flex flex-col gap-0.5">
							<span class="text-sm font-semibold">{f.name}</span>
							<span class="text-[10px] text-base-content/40">{f.sub}</span>
							<span class="flex items-center gap-1.5 mt-0.5">
								{#if f.rarely_used}
									<span
										class="text-[9px] font-bold uppercase tracking-wide text-warning-text bg-warning/15 border border-warning-text/40 rounded-full px-1.5 py-0.5"
										>rarely used</span
									>
								{/if}
								{#if f.frozen}
									<span
										class="text-[9px] font-bold uppercase tracking-wide text-warning-text bg-warning/15 border border-warning-text/40 rounded-full px-1.5 py-0.5"
										>❄ frozen{f.last_used ? ` · ${relativeTime(f.last_used)}` : ''}</span
									>
								{:else}
									<span class="text-[9px] font-mono text-base-content/40"
										>last used {relativeTime(f.last_used)}</span
									>
								{/if}
							</span>
						</span>
						<span class="hidden sm:block h-2.5 rounded-full bg-base-300/40 overflow-hidden">
							<span
								class="block h-full rounded-full {f.rarely_used ? 'bg-warning-text/70' : 'bg-primary'}"
								style="width: {f.pct}%"
							></span>
						</span>
						<span class="text-right font-mono text-sm">
							{f.pct}%
							<span class="block text-[10px] text-base-content/40">{f.users} of {report.funnel.submitters}</span>
						</span>
						<span class="text-base-content/40 text-center">›</span>
					</button>
				{/each}
			</div>

			{#if report.uncategorized_events.length > 0}
				<div class="border-t border-dashed border-base-300/40 mt-3 pt-3">
					<h3 class="text-xs font-bold text-base-content/60 flex items-center gap-1.5">
						⚠ Uncategorized events
						<span class="font-normal text-base-content/40"
							>(fired, not mapped to a feature — a new feature's event lands here until
							added to FEATURE_GROUPS)</span
						>
					</h3>
					<div class="flex flex-wrap gap-1.5 mt-2">
						{#each report.uncategorized_events as u}
							<span
								class="font-mono text-[11px] px-2 py-1 rounded-full bg-warning/15 text-warning-text border border-warning-text/40"
								title={u.last_seen ? `last seen ${relativeTime(u.last_seen)}` : ''}
								>{u.name}<span class="opacity-60 ml-1">{u.count}</span></span
							>
						{/each}
					</div>
				</div>
			{/if}
		</div>

		<!-- ============ POWER USERS TABLE ============ -->
		<div class="card bg-base-200/60 border border-base-300/30 p-4">
			<div class="flex items-baseline justify-between mb-3 flex-wrap gap-2">
				<h2 class="font-display font-bold text-base">
					{#if powerMode === 'most'}Power users
					{:else if powerMode === 'least'}Least active — engaged, but barely
					{:else}Never engaged — paid in, never came back{/if}
				</h2>
				<div class="inline-flex bg-base-100 border border-base-300/40 rounded-full p-1 gap-0.5">
					<button
						type="button"
						class="px-3 py-1 rounded-full text-xs font-semibold {powerMode === 'most'
							? 'bg-primary text-primary-content'
							: 'text-base-content/60'}"
						on:click={() => pickPowerMode('most')}>⚡ Most active</button
					>
					<button
						type="button"
						class="px-3 py-1 rounded-full text-xs font-semibold {powerMode === 'least'
							? 'bg-primary text-primary-content'
							: 'text-base-content/60'}"
						on:click={() => pickPowerMode('least')}>🥱 Least active</button
					>
					<button
						type="button"
						class="px-3 py-1 rounded-full text-xs font-semibold {powerMode === 'never'
							? 'bg-error text-white'
							: 'text-base-content/60'}"
						on:click={() => pickPowerMode('never')}>⚠ Never engaged</button
					>
				</div>
			</div>

			{#if !report.posthog_available}
				<p class="text-sm text-base-content/50">
					PostHog data unavailable — this table needs live session data.
				</p>
			{:else if powerRows.length === 0}
				<p class="text-sm text-base-content/50">No users in this view.</p>
			{:else}
				<div class="overflow-x-auto rounded-btn border border-base-300/30">
					<table class="w-full text-sm">
						<thead>
							<tr class="bg-base-100/60">
								<th class="text-left font-mono text-[10px] uppercase text-base-content/40 px-3 py-2 w-8"
									>#</th
								>
								<th class="text-left font-mono text-[10px] uppercase text-base-content/40 px-3 py-2"
									>Name</th
								>
								<th class="text-left px-3 py-2">
									<button
										type="button"
										class="font-mono text-[10px] uppercase {sortKey === 'logins'
											? 'text-primary'
											: 'text-base-content/40'}"
										on:click={() => sortBy('logins')}>Logins</button
									>
								</th>
								<th class="text-left px-3 py-2">
									<button
										type="button"
										class="font-mono text-[10px] uppercase {sortKey === 'active_days'
											? 'text-primary'
											: 'text-base-content/40'}"
										on:click={() => sortBy('active_days')}>Active days</button
									>
								</th>
								<th class="text-left px-3 py-2">
									<button
										type="button"
										class="font-mono text-[10px] uppercase {sortKey === 'sessions'
											? 'text-primary'
											: 'text-base-content/40'}"
										on:click={() => sortBy('sessions')}>Sessions</button
									>
								</th>
								<th class="text-left px-3 py-2">
									<button
										type="button"
										class="font-mono text-[10px] uppercase {sortKey === 'last_seen_at'
											? 'text-primary'
											: 'text-base-content/40'}"
										on:click={() => sortBy('last_seen_at')}>Last seen</button
									>
								</th>
								<th class="w-6"></th>
							</tr>
						</thead>
						<tbody>
							{#each powerRows as row, i}
								<tr
									class="border-t border-base-300/20 hover:bg-primary/[0.06] cursor-pointer"
									on:click={() => openUserDrawer(row)}
								>
									<td class="px-3 py-2 font-mono text-xs text-base-content/40">{i + 1}</td>
									<td class="px-3 py-2 font-semibold">{row.name}</td>
									<td class="px-3 py-2 font-mono">{row.logins}</td>
									<td class="px-3 py-2 font-mono">{row.active_days}</td>
									<td class="px-3 py-2 font-mono">{row.sessions}</td>
									<td class="px-3 py-2">
										<span
											class="text-[11px] font-semibold px-2 py-0.5 rounded-full {powerMode ===
											'never'
												? 'bg-error/15 text-error'
												: 'bg-success/15 text-success'}"
											>{relativeTime(row.last_seen_at)}</span
										>
									</td>
									<td class="px-3 py-2 text-base-content/40">›</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/if}
		</div>
	{/if}
</div>

<!-- ============ DRAWER (feature adopters / user summary) ============ -->
{#if drawerOpen}
	<div
		class="fixed inset-0 bg-black/50 z-40"
		role="button"
		tabindex="0"
		on:click={closeDrawer}
		on:keydown={(e) => e.key === 'Escape' && closeDrawer()}
	></div>
	<aside
		class="fixed top-0 right-0 h-full w-full sm:w-[420px] bg-base-200 border-l border-base-300/40 z-50 flex flex-col shadow-2xl"
	>
		<div class="flex items-start justify-between gap-3 p-4 border-b border-base-300/30">
			<div>
				{#if drawerMode === 'feature' && drawerFeature}
					<p class="text-[10px] font-mono uppercase tracking-widest text-primary">
						Feature · who uses it
					</p>
					<h3 class="font-display font-bold text-lg mt-1">{drawerFeature.name}</h3>
					<p class="text-xs text-base-content/55 mt-1">
						{drawerFeature.pct}% breadth · {drawerFeature.users} of {report?.funnel.submitters} submitters
					</p>
				{:else if drawerMode === 'user' && drawerUser}
					<p class="text-[10px] font-mono uppercase tracking-widest text-primary">
						User · usage summary
					</p>
					<h3 class="font-display font-bold text-lg mt-1">{drawerUser.name}</h3>
					<p class="text-xs text-base-content/55 mt-1">Since tournament kickoff</p>
				{/if}
			</div>
			<button
				type="button"
				class="w-7 h-7 rounded-btn bg-base-100 border border-base-300/40 text-base-content/55 hover:text-base-content"
				on:click={closeDrawer}>✕</button
			>
		</div>

		<div class="flex-1 overflow-y-auto p-4 space-y-4">
			{#if drawerMode === 'feature' && drawerFeature}
				<div class="grid grid-cols-3 gap-2">
					<div class="bg-base-100 border border-base-300/30 rounded-btn p-2.5">
						<span class="block font-display font-bold text-lg">{drawerFeature.users}</span>
						<span class="text-[10px] text-base-content/40 uppercase">adopters</span>
					</div>
					<div class="bg-base-100 border border-base-300/30 rounded-btn p-2.5">
						<span class="block font-display font-bold text-lg">{drawerFeature.pct}%</span>
						<span class="text-[10px] text-base-content/40 uppercase">breadth</span>
					</div>
					<div class="bg-base-100 border border-base-300/30 rounded-btn p-2.5">
						<span class="block font-display font-bold text-lg"
							>{Math.max(0, (report?.funnel.submitters ?? 0) - drawerFeature.users)}</span
						>
						<span class="text-[10px] text-base-content/40 uppercase">not yet</span>
					</div>
				</div>
				<div>
					<span class="text-[10px] font-mono uppercase tracking-wide text-base-content/40"
						>Recent adopters</span
					>
					{#if drawerAdoptersLoading}
						<p class="text-sm text-base-content/50 mt-2">Loading…</p>
					{:else if drawerAdopters.length === 0}
						<p class="text-sm text-base-content/50 mt-2">
							No adopters in this window {report?.posthog_available ? '' : '(PostHog unavailable)'}.
						</p>
					{:else}
						<div class="border border-base-300/30 rounded-btn overflow-hidden mt-2">
							{#each drawerAdopters as a, i}
								<div
									class="flex items-center justify-between px-3 py-2 text-sm {i > 0
										? 'border-t border-base-300/20'
										: ''}"
								>
									<span class="font-semibold">{a.name}</span>
									<span class="font-mono text-xs text-base-content/50">{relativeTime(a.last_used)}</span
									>
								</div>
							{/each}
						</div>
					{/if}
				</div>
			{:else if drawerMode === 'user' && drawerUser}
				<div class="grid grid-cols-3 gap-2">
					<div class="bg-base-100 border border-base-300/30 rounded-btn p-2.5">
						<span class="block font-display font-bold text-lg">{drawerUser.active_days}</span>
						<span class="text-[10px] text-base-content/40 uppercase">active days</span>
					</div>
					<div class="bg-base-100 border border-base-300/30 rounded-btn p-2.5">
						<span class="block font-display font-bold text-lg">{drawerUser.logins}</span>
						<span class="text-[10px] text-base-content/40 uppercase">logins</span>
					</div>
					<div class="bg-base-100 border border-base-300/30 rounded-btn p-2.5">
						<span class="block font-display font-bold text-lg">{drawerUser.sessions}</span>
						<span class="text-[10px] text-base-content/40 uppercase">sessions</span>
					</div>
				</div>
				<p class="text-sm text-base-content/60">
					Last seen {relativeTime(drawerUser.last_seen_at)}.
				</p>
				<a
					class="block text-center rounded-btn bg-primary text-primary-content font-bold text-sm py-2.5 hover:brightness-105"
					href="/admin/users/{drawerUser.user_id}"
				>
					Open full profile →
				</a>
			{/if}
		</div>
	</aside>
{/if}
