<script lang="ts">
	/** Most-Exposed Entries — names + points, not just counts.
	 *
	 *  The Implications card answers "how many"; this answers "who." Names +
	 *  a short subtitle of the stages-at-stake gives the social hooks that
	 *  make a contrarian bet feel personal. */
	import { goto } from '$app/navigation';
	import type { Fixture } from '$types';
	import type {
		KoExposedEntry,
		KoMatchDetailResponse
	} from '$lib/types/results';
	import TeamName from '$lib/components/TeamName.svelte';

	export let fixture: Fixture;
	export let bundle: KoMatchDetailResponse;

	const STAGE_SHORT: Record<string, string> = {
		round_of_32: 'R32',
		round_of_16: 'R16',
		quarter_final: 'QF',
		semi_final: 'SF',
		final: 'F',
		winner: 'W'
	};

	function stagesLabel(stages: string[]): string {
		const codes = stages.map((s) => STAGE_SHORT[s] ?? s);
		return codes.join(' + ');
	}

	function openEntry(entryId: string) {
		void goto(`/leaderboard?entry=${entryId}`);
	}

	$: hasAny =
		bundle.most_exposed.home.length > 0 || bundle.most_exposed.away.length > 0;
</script>

{#if hasAny}
	<div class="rounded-box border border-base-300/60 bg-base-200 p-4">
		<div class="mb-3 flex items-center justify-between">
			<span class="font-display text-[15px]">Most exposed entries</span>
			<span class="text-[10.5px] font-bold uppercase tracking-[0.14em] text-base-content/55"
				>who has the most to win</span
			>
		</div>

		<div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
			{#each [{ side: bundle.most_exposed.home, team: bundle.home_team }, { side: bundle.most_exposed.away, team: bundle.away_team }] as col}
				<div>
					<h4 class="mb-2 text-[11.5px] font-semibold text-base-content/65">
						If <TeamName name={col.team} /> advances ↑
					</h4>
					{#if col.side.length === 0}
						<div class="rounded-btn bg-base-300/15 px-3 py-3 text-[11.5px] text-base-content/45">
							No entries on this side at later stages.
						</div>
					{:else}
						<div class="flex flex-col gap-1.5">
							{#each col.side as entry (entry.entry_id)}
								<button
									type="button"
									on:click={() => openEntry(entry.entry_id)}
									class="flex items-center justify-between gap-2 rounded-btn bg-base-300/20 px-2.5 py-2 text-left transition hover:bg-base-300/35"
								>
									<div class="min-w-0 flex-1">
										<div class="truncate text-[12.5px] font-semibold">
											{#if entry.rank !== null && entry.rank <= 10}<span
													class="text-primary"
													title="Top-10 leaderboard entry">★</span
												>{' '}{/if}{entry.user_name}
											{#if entry.entry_name && entry.entry_name !== 'Entry 1'}<span
													class="text-[10.5px] text-base-content/45">
													— {entry.entry_name}</span
												>{/if}
										</div>
										<div class="truncate text-[10.5px] text-base-content/55">
											{stagesLabel(entry.stages_at_stake)}
											{#if entry.rank !== null}<span class="text-base-content/35">
													· #{entry.rank}</span
												>{/if}
										</div>
									</div>
									<span class="font-mono text-[13px] font-bold text-success"
										>+{entry.points_at_stake}</span
									>
								</button>
							{/each}
						</div>
					{/if}
				</div>
			{/each}
		</div>

		<div class="mt-3 text-[11px] text-base-content/45">
			★ = current top-10 entry · tap a row to open that entry's full bracket
		</div>
	</div>
{/if}
