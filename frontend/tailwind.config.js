/** @type {import('tailwindcss').Config} */
export default {
	content: ['./src/**/*.{html,js,svelte,ts}'],
	theme: {
		extend: {
			fontFamily: {
				'display': ['Manrope', 'system-ui', 'sans-serif'],
				'sans': ['Inter', 'system-ui', 'sans-serif'],
				'mono': ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
				// Editorial hero font — landing page hero headlines only.
				// Manrope remains the system display font; reach for `font-hero`
				// when you want a loud, broadcast-poster moment.
				'hero': ['"Bebas Neue"', 'Impact', 'sans-serif'],
			},
			backgroundImage: {
				// Subtle 50px vertical stripes — barely-visible texture for
				// hero canvases. Theme-neutral (white at 2% alpha).
				'pitch-pattern': 'repeating-linear-gradient(90deg, transparent, transparent 50px, rgba(255,255,255,0.02) 50px, rgba(255,255,255,0.02) 100px)',
				// Ambient gold radial — soft champagne wash from the top.
				// Matches the new premium-night/day aesthetic.
				'stadium-glow': 'radial-gradient(ellipse at top, rgba(212, 175, 55, 0.10) 0%, transparent 50%)',
			},
			boxShadow: {
				// Champagne-gold glow — primary accent halo on CTAs and
				// "you" highlights. Hex matches premium-night primary (#D4AF37).
				'glow-gold': '0 0 20px rgba(212, 175, 55, 0.30)',
				'card': '0 4px 20px rgba(0, 0, 0, 0.4)',
			},
			animation: {
				'slide-up': 'slide-up 0.4s ease-out',
				'fade-in': 'fade-in 0.3s ease-out',
				'pulse-soft': 'pulse-soft 2s ease-in-out infinite',
				'score-pop': 'score-pop 0.2s ease-out',
				'shimmer': 'shimmer 2s linear infinite',
			},
			keyframes: {
				'slide-up': {
					'0%': { opacity: '0', transform: 'translateY(10px)' },
					'100%': { opacity: '1', transform: 'translateY(0)' },
				},
				'fade-in': {
					'0%': { opacity: '0' },
					'100%': { opacity: '1' },
				},
				'pulse-soft': {
					'0%, 100%': { opacity: '1' },
					'50%': { opacity: '0.7' },
				},
				'score-pop': {
					'0%': { transform: 'scale(1)' },
					'50%': { transform: 'scale(1.1)' },
					'100%': { transform: 'scale(1)' },
				},
				'shimmer': {
					'0%': { backgroundPosition: '-200% 0' },
					'100%': { backgroundPosition: '200% 0' },
				},
			},
		}
	},
	plugins: [require('daisyui')],
	daisyui: {
		themes: [
			{
				// Dark theme — sports-broadcast editorial.
				// Gold-on-navy, mint success, amber/red urgency.
				'premium-night': {
					'primary': '#D4AF37',           // gold — CTAs, brand, accents
					'primary-content': '#0B1329',   // ink on gold
					'secondary': '#1C2541',         // premium navy (used by DaisyUI btn-secondary)
					'secondary-content': '#E2E8F0',
					'accent': '#D4AF37',            // same gold for accent semantics
					'accent-content': '#0B1329',
					'neutral': '#1E293B',           // tooltip / btn-neutral bg
					'neutral-content': '#E2E8F0',
					'info': '#3B82F6',
					'info-content': '#F8FAFC',
					'success': '#059669',           // mint — exact score
					'success-content': '#F8FAFC',
					'warning': '#D97706',           // amber — lock / outcome
					'warning-content': '#F8FAFC',
					'error':   '#B91C1C',           // red — miss
					'error-content': '#F8FAFC',
					'base-100': '#0B1329',          // canvas
					'base-200': '#1C2541',          // surface / cards
					'base-300': '#2A3552',          // divider / borders
					'base-content': '#E2E8F0',     // body ink
					'--rounded-box': '0.875rem',   // 14px cards
					'--rounded-btn': '0.625rem',   // 10px buttons
					'--rounded-badge': '0.5rem',   // 8px pills
					'--border-btn': '1px',
				},
			},
			{
				// Light theme — same voice, lighter canvas.
				// Deeper gold (B8941F) for AA contrast on ice — use #D4AF37
				// only for large fills/marks.
				'premium-day': {
					'primary': '#B8941F',
					'primary-content': '#0B1329',
					'secondary': '#1C2541',         // premium navy headers / chrome
					'secondary-content': '#F8FAFC',
					'accent': '#B8941F',
					'accent-content': '#F8FAFC',
					'neutral': '#1E293B',           // dark tooltip bg even on light canvas
					'neutral-content': '#F8FAFC',
					'info': '#3B82F6',
					'info-content': '#F8FAFC',
					'success': '#059669',
					'success-content': '#F8FAFC',
					'warning': '#B45309',
					'warning-content': '#F8FAFC',
					'error':   '#B91C1C',
					'error-content': '#F8FAFC',
					'base-100': '#F8FAFC',          // ice canvas — NEVER pure #FFFFFF
					'base-200': '#FFFFFF',          // surface / cards
					'base-300': '#E2E8F0',          // slate-200 divider / borders
					'base-content': '#0B1329',     // navy ink
					'--rounded-box': '0.875rem',
					'--rounded-btn': '0.625rem',
					'--rounded-badge': '0.5rem',
					'--border-btn': '1px',
				},
			},
		],
		darkTheme: 'premium-night'
	}
};
