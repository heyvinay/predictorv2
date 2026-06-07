<!--
  DevPhaseSwitcher — floating pill that overrides $uxPhase at runtime.
  Mounts ONLY when `dev` from $app/environment is true (Vite tree-shakes
  the {#if dev} branch out of prod builds, so this component never reaches
  the production bundle as long as the mount site is similarly gated).

  Two ways to set the override:
    - URL param ?uxPhase=during_tournament (wired in +layout.svelte; one-shot)
    - This pill: click a phase button to set; "Auto" clears the override

  Persists to sessionStorage['predictor:uxPhase'] so the choice survives
  HMR but resets on tab close.

  Adapted from upstream's PnDevPhasePill; collapsed 5→3 phases (Phase 2
  dormant in our fork).
-->
<script lang="ts">
	import { dev } from '$app/environment';
	import { uxPhase, uxPhaseOverride } from '$stores/phase';
	import type { UxPhase } from '$types';

	const PHASES: { id: UxPhase; label: string }[] = [
		{ id: 'pre_tournament', label: 'Pre' },
		{ id: 'during_tournament', label: 'During' },
		{ id: 'post_competition', label: 'Post' }
	];

	let open = false;

	function set(phase: UxPhase | null) {
		uxPhaseOverride.set(phase);
		try {
			if (phase) sessionStorage.setItem('predictor:uxPhase', phase);
			else sessionStorage.removeItem('predictor:uxPhase');
		} catch {
			// sessionStorage may be unavailable in privacy modes; ignore
		}
		open = false;
	}

	function label(p: UxPhase): string {
		return p.replace(/_/g, ' ');
	}
</script>

{#if dev}
	<div class="fixed bottom-3 right-3 z-50 font-mono text-[11px] leading-none" class:open>
		{#if open}
			<ul
				role="menu"
				class="mb-1.5 stadium-card no-glow p-1 flex flex-col gap-0.5 min-w-[180px]"
			>
				<li>
					<button
						type="button"
						class="btn btn-xs btn-ghost w-full justify-start text-left"
						class:btn-active={$uxPhaseOverride === null}
						on:click={() => set(null)}
					>
						Auto-derive
					</button>
				</li>
				{#each PHASES as p}
					<li>
						<button
							type="button"
							class="btn btn-xs btn-ghost w-full justify-start text-left"
							class:btn-active={$uxPhaseOverride === p.id}
							on:click={() => set(p.id)}
						>
							{p.label}
						</button>
					</li>
				{/each}
			</ul>
		{/if}
		<button
			type="button"
			class="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-full font-bold uppercase tracking-[0.06em] cursor-pointer transition-all"
			style:background="var(--b2, #1C2541)"
			style:color="var(--bc, #E2E8F0)"
			style:border="1px solid var(--p, #D4AF37)"
			style:box-shadow="2px 2px 0 rgba(0,0,0,.5)"
			aria-expanded={open}
			on:click={() => (open = !open)}
		>
			<span
				class="inline-block w-1.5 h-1.5 rounded-full"
				style:background={$uxPhaseOverride !== null ? 'var(--p, #D4AF37)' : 'rgba(226,232,240,0.4)'}
			></span>
			DEV · {label($uxPhase)}
		</button>
	</div>
{/if}
