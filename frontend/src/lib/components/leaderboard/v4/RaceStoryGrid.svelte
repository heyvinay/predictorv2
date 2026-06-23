<script lang="ts">
	import { onMount, createEventDispatcher } from 'svelte';
	import { getRaceStories } from '$lib/api/leaderboard';
	import type { RaceStory } from '$lib/types/leaderboard';
	import RaceStoryCard from './RaceStoryCard.svelte';

	const dispatch = createEventDispatcher<{ open: { entry_id: string; compare_id: string | null } }>();

	let stories: RaceStory[] = [];
	let loading = true;
	let failed = false;

	onMount(async () => {
		try {
			const data = await getRaceStories();
			stories = data.stories;
		} catch {
			failed = true;
		} finally {
			loading = false;
		}
	});
</script>

{#if !loading && !failed && stories.length > 0}
	<div class="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
		{#each stories as story (story.kind)}
			<RaceStoryCard {story} on:open={e => dispatch('open', e.detail)} />
		{/each}
	</div>
{/if}
