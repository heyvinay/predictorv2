<script lang="ts">
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';
	import type { FinalMatchOut } from '$lib/types/wrapup';

	export let finalMatch: FinalMatchOut | null;

	// Per-side seeded check (never binary) — a slot placeholder means that
	// side's lineup hasn't resolved yet, independent of the other side.
	const teamLabel = (team: string) => (team.startsWith('slot:') ? 'TBD' : team);
	const teamFlag = (team: string) =>
		!team.startsWith('slot:') && hasFlag(team) ? getFlagUrl(team, 'md') : null;

	const d = (iso: string | null) =>
		iso
			? new Intl.DateTimeFormat('en-GB', {
					weekday: 'short',
					day: 'numeric',
					month: 'short'
				}).format(new Date(iso))
			: '';
</script>

<div class="stadium-card no-glow flex h-full flex-col p-4">
	{#if finalMatch}
		<div class="flex items-center justify-between gap-2">
			<h2 class="font-display text-sm font-extrabold">The Final · {d(finalMatch.kickoff)}</h2>
			{#if finalMatch.venue}
				<span
					class="rounded-badge bg-base-100 px-2 py-0.5 text-[10px] uppercase tracking-wider text-base-content/50"
				>
					{finalMatch.venue}
				</span>
			{/if}
		</div>
		<div class="my-2.5 flex flex-wrap items-center justify-center gap-3">
			<span class="flex items-center gap-1.5 font-display font-extrabold">
				{#if teamFlag(finalMatch.home_team)}
					<img
						src={teamFlag(finalMatch.home_team)}
						alt=""
						class="h-[17px] w-6 flex-none rounded-sm object-cover ring-1 ring-black/30"
						loading="lazy"
					/>
				{/if}
				{teamLabel(finalMatch.home_team)}
			</span>
			<span class="whitespace-nowrap font-display text-2xl font-extrabold text-primary">
				{finalMatch.home_score ?? '–'} – {finalMatch.away_score ?? '–'}
			</span>
			<span class="flex items-center gap-1.5 font-display font-extrabold">
				{teamLabel(finalMatch.away_team)}
				{#if teamFlag(finalMatch.away_team)}
					<img
						src={teamFlag(finalMatch.away_team)}
						alt=""
						class="h-[17px] w-6 flex-none rounded-sm object-cover ring-1 ring-black/30"
						loading="lazy"
					/>
				{/if}
			</span>
		</div>
		{#if finalMatch.went_to_extra_time || finalMatch.penalties}
			<p class="text-center text-[11px] text-base-content/40">
				{finalMatch.went_to_extra_time ? 'after extra time' : ''}{finalMatch.penalties
					? ` · ${finalMatch.penalties} on penalties`
					: ''}
			</p>
		{/if}
		{#if finalMatch.narrative}
			<p class="mt-2 text-[13px] text-base-content/60">{finalMatch.narrative}</p>
		{/if}
	{:else}
		<p class="m-auto text-sm text-base-content/40">The Final hasn't been played yet.</p>
	{/if}
</div>
