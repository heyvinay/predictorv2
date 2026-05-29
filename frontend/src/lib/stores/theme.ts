import { writable } from 'svelte/store';
import { browser } from '$app/environment';

// Two themes: a light "hybrid" body wrapped in premium-night dark chrome
// (default) and full premium-night for dark mode.
export const THEMES = ['hybrid', 'premium-night'] as const;

export type Theme = (typeof THEMES)[number];

export const DEFAULT_THEME: Theme = 'hybrid';
const STORAGE_KEY = 'predictor:theme';

// Map legacy / removed theme keys to the survivor with the matching tone.
// Keep in sync with the FOUC migration in app.html.
const LEGACY_MAP: Record<string, Theme> = {
	light: 'hybrid',
	'premium-day': 'hybrid',
	'vin-light': 'hybrid',
	'vin-hybrid': 'hybrid',
	'vin-dark': 'premium-night'
};

function migrate(key: string | null): Theme {
	if (!key) return DEFAULT_THEME;
	if ((THEMES as readonly string[]).includes(key)) return key as Theme;
	return LEGACY_MAP[key] ?? DEFAULT_THEME;
}

// For the hybrid (light) theme the chrome (rail / topbars / bottom-nav)
// renders in premium-night so a dark broadcast chrome contrasts the light
// body. Returns null when the chrome should just inherit the body theme.
const CHROME_OVERRIDE: Partial<Record<Theme, Theme>> = {
	hybrid: 'premium-night'
};

export function chromeThemeFor(t: Theme): Theme | null {
	return CHROME_OVERRIDE[t] ?? null;
}

function readInitial(): Theme {
	if (!browser) return DEFAULT_THEME;
	return migrate(localStorage.getItem(STORAGE_KEY));
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
