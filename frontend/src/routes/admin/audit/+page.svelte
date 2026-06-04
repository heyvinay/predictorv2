<script lang="ts">
	/** /admin/audit — global audit feed (v2.156.0).
	 *
	 * Compact 100/page feed grouped client-side by day. Free-text
	 * search matches actor email / name / event type via the backend's
	 * ILIKE-on-JOIN query. Namespace chips filter by event_type prefix.
	 */
	import { onMount } from 'svelte';
	import { getAuditFeed, type AuditEventPage, type AuditEventRead } from '$lib/api/admin';

	let pageData: AuditEventPage = { rows: [], total: 0 };
	let search = '';
	let namespace = '';
	let eventType = '';
	let offset = 0;
	const LIMIT = 100;

	async function refresh(): Promise<void> {
		pageData = await getAuditFeed({
			search: search || undefined,
			namespace: namespace || undefined,
			event_type: eventType || undefined,
			limit: LIMIT,
			offset,
		});
	}

	function formatTime(iso: string): string {
		const d = new Date(iso);
		return new Intl.DateTimeFormat(undefined, {
			hour: '2-digit',
			minute: '2-digit',
			second: '2-digit',
		}).format(d);
	}

	function dayHeader(iso: string): string {
		const d = new Date(iso);
		const today = new Date();
		const yest = new Date(today);
		yest.setDate(yest.getDate() - 1);
		const sameDay = (a: Date, b: Date) =>
			a.getFullYear() === b.getFullYear() &&
			a.getMonth() === b.getMonth() &&
			a.getDate() === b.getDate();
		if (sameDay(d, today)) return 'Today';
		if (sameDay(d, yest)) return 'Yesterday';
		return new Intl.DateTimeFormat(undefined, {
			day: 'numeric',
			month: 'short',
			year: 'numeric',
		}).format(d);
	}

	function groupByDay(rows: AuditEventRead[]): { day: string; events: AuditEventRead[] }[] {
		const groups: { day: string; events: AuditEventRead[] }[] = [];
		for (const r of rows) {
			const day = dayHeader(r.created_at);
			const last = groups[groups.length - 1];
			if (last && last.day === day) last.events.push(r);
			else groups.push({ day, events: [r] });
		}
		return groups;
	}

	$: groups = groupByDay(pageData.rows);

	onMount(refresh);
</script>

<div class="max-w-[1280px] mx-auto px-4 sm:px-6 py-6">
	<header class="flex flex-wrap items-end justify-between gap-4 mb-5">
		<div>
			<p class="text-[10px] font-mono uppercase tracking-[0.2em] text-primary font-medium">Append-only · tx-coupled to state</p>
			<h1 class="font-display font-extrabold text-3xl sm:text-4xl mt-2">Audit log</h1>
			<p class="text-base-content/60 text-sm mt-2 max-w-2xl">
				Every user-attributable action across the system, newest first.
				Now includes <span class="font-mono text-xs text-primary">auth.login_succeeded</span>
				on magic-link verify and <span class="font-mono text-xs text-primary">user.profile_updated</span>
				on profile edits.
			</p>
		</div>
	</header>

	<!-- Filter bar -->
	<div class="flex flex-wrap gap-2 items-center mb-3">
		<input
			type="search"
			bind:value={search}
			on:input={() => { offset = 0; refresh(); }}
			placeholder="Filter by actor email, name, or event"
			class="input input-bordered input-sm max-w-xs flex-1"
		/>
		<select bind:value={eventType} on:change={() => { offset = 0; refresh(); }} class="select select-bordered select-sm">
			<option value="">All event types</option>
			<option value="auth.login_succeeded">auth.login_succeeded</option>
			<option value="auth.login_failed">auth.login_failed</option>
			<option value="user.profile_updated">user.profile_updated</option>
			<option value="entry.created">entry.created</option>
			<option value="entry.phase_submitted">entry.phase_submitted</option>
		</select>
		<div class="flex gap-1.5 flex-wrap">
			{#each [['','All'],['auth','Auth'],['entry','Entries'],['prediction','Predictions'],['competition','Competition']] as [ns, label]}
				<button
					class="badge badge-sm gap-1.5 px-3 py-3 cursor-pointer"
					class:badge-primary={namespace === ns}
					class:badge-outline={namespace !== ns}
					on:click={() => { namespace = ns; offset = 0; refresh(); }}
				>{label}</button>
			{/each}
		</div>
	</div>

	<!-- Feed -->
	<div class="rounded-2xl border border-base-300/30 bg-base-200/40 overflow-hidden">
		{#each groups as group (group.day)}
			<div class="flex items-center gap-3 px-5 py-2.5 bg-primary/[0.03]">
				<span class="font-mono text-[10px] uppercase tracking-widest text-primary font-medium">{group.day}</span>
				<span class="flex-1 h-px bg-gradient-to-r from-primary/15 to-transparent"></span>
				<span class="text-[11px] text-base-content/40">{group.events.length} events</span>
			</div>
			{#each group.events as e (e.id)}
				<div class="audit-feed-row">
					<span class="font-mono text-[11px] text-base-content/40 whitespace-nowrap" title={e.created_at}>{formatTime(e.created_at)}</span>
					<div class="text-sm">
						<span class="status-pill" class:s-info={e.event_type.startsWith('auth.')} class:s-primary={e.event_type.startsWith('entry.')} class:s-warning={e.event_type.startsWith('competition.')} class:s-error={e.event_type.endsWith('_failed')} class:s-ghost={e.event_type.startsWith('prediction.')}>
							<span class="dot"></span>{e.event_type}
						</span>
					</div>
					<div class="text-sm min-w-0 truncate">
						{#if e.actor_user_id}
							<a href={`/admin/users/${e.actor_user_id}`} class="hover:text-primary">{e.actor_name ?? e.actor_email ?? '?'}</a>
							<span class="text-[10px] text-base-content/40 ml-1 uppercase">{e.actor_role}</span>
						{:else}
							<span class="italic text-base-content/40">unauthenticated</span>
							<span class="text-[10px] text-base-content/40 ml-1 uppercase">system</span>
						{/if}
					</div>
					<div class="text-xs text-base-content/60 min-w-0 truncate">
						{#if e.subject_type}<span class="font-mono text-[10.5px] bg-base-content/[0.04] border border-base-300/30 rounded px-1.5 py-0.5 mr-1">{e.subject_type}</span>{/if}
						{#if e.subject_id}<span class="font-mono text-[10.5px] text-base-content/40">{String(e.subject_id).slice(0,8)}</span>{/if}
						{#if e.reason}<span class="italic ml-1">"{e.reason}"</span>{/if}
						{#if e.event_metadata}<code class="font-mono text-[10px] text-base-content/40 ml-1">{JSON.stringify(e.event_metadata)}</code>{/if}
					</div>
				</div>
			{/each}
		{/each}
		<div class="flex items-center justify-between px-4 py-3 border-t border-base-300/30 text-xs text-base-content/40">
			<span>Showing {offset + 1}–{Math.min(offset + LIMIT, pageData.total)} of {pageData.total} events</span>
			<div class="flex gap-2">
				<button class="btn btn-outline btn-xs" disabled={offset === 0} on:click={() => { offset = Math.max(0, offset - LIMIT); refresh(); }}>Prev</button>
				<button class="btn btn-outline btn-xs" disabled={offset + LIMIT >= pageData.total} on:click={() => { offset += LIMIT; refresh(); }}>Next</button>
			</div>
		</div>
	</div>
</div>
