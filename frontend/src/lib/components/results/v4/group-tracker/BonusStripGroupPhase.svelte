<script lang="ts">
	import type { GroupPhaseBonusPickState, BonusLeaderStatus } from '$lib/utils/groupTracker';
	import { getFlagUrl, hasFlag } from '$lib/utils/flags';
	import { displayTeamName } from '$lib/utils/teamName';

	export let mostScored: GroupPhaseBonusPickState | null;
	export let mostConceded: GroupPhaseBonusPickState | null;

	const STATUS_CLASS: Record<BonusLeaderStatus, string> = {
		leading: 'bg-success/20 text-success',
		alive: 'bg-success/20 text-success',
		fading: 'bg-warning/20 text-warning-text',
		missed: 'bg-error/20 text-error'
	};
	const STATUS_LABEL: Record<BonusLeaderStatus, string> = {
		leading: 'Leading',
		alive: 'Alive',
		fading: 'Fading',
		missed: 'Missed'
	};
</script>

{#if mostScored || mostConceded}
	<div class="mt-6">
		<header class="mb-3">
			<h2 class="font-display text-xl tracking-wide">
				Group-phase bonus picks · <span class="text-primary">still your team?</span>
			</h2>
			<p class="mt-1 max-w-prose text-xs text-base-content/55">
				Your two group-stage bonus answers settle when the group stage ends. Also visible on the
				Standings · Insights tab — mirrored here so the group-phase story reads in one place.
			</p>
		</header>

		<div class="grid gap-4 sm:grid-cols-2">
			{#each [{ title: 'Which team scores the most goals in the group stage?', state: mostScored, unit: 'scored' }, { title: 'Which team concedes the most goals in the group stage?', state: mostConceded, unit: 'conceded' }] as card}
				{#if card.state}
					<div class="stadium-card no-glow flex flex-col gap-2.5 p-4">
						<div class="flex items-center justify-between">
							<span class="text-[10px] font-bold uppercase tracking-wide text-base-content/45">
								Bonus question
							</span>
							<span class="rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide {STATUS_CLASS[card.state.status]}">
								{STATUS_LABEL[card.state.status]}
							</span>
						</div>
						<h3 class="font-display text-sm font-semibold">{card.title}</h3>
						<div class="flex items-center gap-2 rounded-lg bg-base-300/40 px-3 py-2">
							{#if card.state.userPick && hasFlag(card.state.userPick)}
								<img src={getFlagUrl(card.state.userPick, 'sm')} alt="" class="h-4 w-6 rounded-sm" />
							{/if}
							<span class="font-semibold">
								{card.state.userPick ? displayTeamName(card.state.userPick) : '—'}
							</span>
							<span class="ml-auto font-mono text-xs text-base-content/55">
								{card.state.userTally} {card.unit}
							</span>
						</div>
						<p class="text-xs text-base-content/55">
							{#if card.state.status === 'leading'}
								Your pick is the current leader.
							{:else}
								Currently led by
								<strong class="text-base-content">{card.state.leaders.map(displayTeamName).join(', ')}</strong>
								with {card.state.leaderTally} {card.unit}.
							{/if}
						</p>
					</div>
				{/if}
			{/each}
		</div>
	</div>
{/if}
