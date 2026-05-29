<!--
	HowItWorks — three numbered cards explaining the player journey.
	Per the handoff: Predict the Games / Score as the tournament unfolds
	/ Become a Champion. Each card has a big gold Bebas numeral, a
	Lucide icon top-right, a bold title, and a one-sentence body.

	Visual: equal-width 3-col grid on lg+, stacking to a single column
	on mobile. Cards use the gradient surface from `match-card` styling
	(via inline Tailwind so the landing components stay self-contained).
-->
<script lang="ts">
	import ListChecks from 'lucide-svelte/icons/list-checks';
	import GitFork from 'lucide-svelte/icons/git-fork';
	import Trophy from 'lucide-svelte/icons/trophy';

	const steps = [
		{
			num: '01',
			title: 'Predict the Games',
			body: 'Pick every group-stage match score and call who advances.',
			Icon: ListChecks
		},
		{
			num: '02',
			title: 'Score as the tournament unfolds',
			body: '5 pts for the right outcome, +10 for the exact score, plus a rarity bonus when you go against the crowd.',
			Icon: GitFork
		},
		{
			num: '03',
			title: 'Become a Champion',
			body: 'Prize after the group stage. Grand prize after the Final!',
			Icon: Trophy
		}
	];
</script>

<div class="bg-base-100">
	<div class="max-w-[1200px] mx-auto mobile-padding py-20 sm:py-24">
		<header class="mb-10">
			<h2 class="font-hero text-3xl sm:text-4xl tracking-wide inline-block">HOW IT WORKS</h2>
			<div class="h-0.5 w-24 bg-primary mt-2"></div>
		</header>

		<div class="grid grid-cols-1 lg:grid-cols-3 gap-5">
			{#each steps as step (step.num)}
				<article
					class="relative bg-gradient-to-br from-base-200 to-base-300/70 rounded-2xl p-7
						border border-base-100/50 shadow-card overflow-hidden"
				>
					<!-- Big gold numeral, top-left -->
					<p class="font-hero text-5xl text-primary leading-none mb-4">{step.num}</p>

					<!-- Lucide icon, top-right -->
					<svelte:component
						this={step.Icon}
						size={22}
						strokeWidth={1.75}
						class="absolute top-6 right-6 text-primary/40"
					/>

					<h3 class="font-display text-lg mb-2 text-base-content">{step.title}</h3>
					<p class="text-sm text-base-content/70 leading-relaxed">{step.body}</p>
				</article>
			{/each}
		</div>
	</div>
</div>
