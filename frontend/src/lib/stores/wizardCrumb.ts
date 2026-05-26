import { writable } from 'svelte/store';

/**
 * Label of the wizard's currently-active section ("Groups" / "Knockout" /
 * "Bonus" / "Submit"), published by the entry wizard page and read by the
 * root layout's breadcrumb. `null` when not on the wizard (the page resets
 * it on destroy). Mirrors the `pageTitle` store's page-publishes/layout-reads
 * pattern.
 */
export const wizardSectionLabel = writable<string | null>(null);
