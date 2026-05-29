import { writable } from 'svelte/store';
import { browser } from '$app/environment';

// Order matters — this is the picker order in +layout.svelte.
export const THEMES = [
	'premium-night',
	'premium-day',
	'hybrid',
	'vin-dark',
	'vin-light',
	'vin-hybrid'
] as const;

export type Theme = (typeof THEMES)[number];

export const DEFAULT_THEME: Theme = 'premium-night';
const STORAGE_KEY = 'predictor:theme';

export const THEME_LABELS: Record<Theme, string> = {
	'premium-night': 'Night',
	'premium-day': 'Day',
	'hybrid': 'Hybrid',
	'vin-dark': 'VinDark',
	'vin-light': 'VinLight',
	'vin-hybrid': 'VinHybrid'
};

// For hybrid themes the chrome (rail / topbars / bottom-nav) renders in a
// DARK theme while the body stays light. Returns null when the chrome should
// just inherit the body theme.
const CHROME_OVERRIDE: Partial<Record<Theme, Theme>> = {
	'hybrid': 'premium-night',
	'vin-hybrid': 'vin-dark'
};

export function chromeThemeFor(t: Theme): Theme | null {
	return CHROME_OVERRIDE[t] ?? null;
}

function readInitial(): Theme {
	if (!browser) return DEFAULT_THEME;
	const saved = localStorage.getItem(STORAGE_KEY);
	return saved && (THEMES as readonly string[]).includes(saved) ? (saved as Theme) : DEFAULT_THEME;
}

export const theme = writable<Theme>(readInitial());

if (browser) {
	theme.subscribe((value) => {
		document.documentElement.setAttribute('data-theme', value);
		try {
			localStorage.setItem(STORAGE_KEY, value);
		} catch {
			// localStorage unavailable (private mode etc.) — theme still applies for this session
		}
	});
}
