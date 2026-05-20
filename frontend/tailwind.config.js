/** @type {import('tailwindcss').Config} */
export default {
	content: ['./src/**/*.{html,js,svelte,ts}'],
	theme: {
		extend: {
			fontFamily: {
				'display': ['"Bebas Neue"', 'Impact', 'sans-serif'],
				'sans': ['"DM Sans"', 'system-ui', 'sans-serif'],
			},
			colors: {
				// Custom colors for win/loss indicators
				'win': '#22c55e',
				'loss': '#ef4444',
				'draw': '#f59e0b',
				// Stadium/sports palette
				'turf': '#0D9748',
				'pitch': '#0A7B3A',
				'gold': '#FFD700',
				'trophy': '#F5A623',
				'navy': '#1E3A5F',
			},
			backgroundImage: {
				'pitch-pattern': 'repeating-linear-gradient(90deg, transparent, transparent 50px, rgba(255,255,255,0.02) 50px, rgba(255,255,255,0.02) 100px)',
				'stadium-glow': 'radial-gradient(ellipse at top, rgba(13, 151, 72, 0.15) 0%, transparent 50%)',
				'hero-gradient': 'linear-gradient(135deg, rgba(13, 151, 72, 0.1) 0%, rgba(30, 58, 95, 0.1) 100%)',
			},
			boxShadow: {
				'glow-green': '0 0 20px rgba(13, 151, 72, 0.3)',
				'glow-gold': '0 0 20px rgba(245, 166, 35, 0.3)',
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
				predictor: {
					'primary': '#0D9748',           // Stadium turf green
					'primary-content': '#ffffff',
					'secondary': '#1E3A5F',         // Deep navy (night stadium)
					'secondary-content': '#ffffff',
					'accent': '#F5A623',            // Trophy gold/amber
					'accent-content': '#000000',
					'neutral': '#0F1419',           // Deep black
					'neutral-content': '#ffffff',
					'base-100': '#0A0E13',          // Stadium night sky
					'base-200': '#141B24',          // Darker seats
					'base-300': '#1E2832',          // Lighter seats
					'base-content': '#E8EAED',      // Light gray text
					'info': '#3ABFF8',
					'info-content': '#000000',
					'success': '#22C55E',           // Win green
					'success-content': '#000000',
					'warning': '#F59E0B',           // Draw amber
					'warning-content': '#000000',
					'error': '#EF4444',             // Loss red
					'error-content': '#000000',
				}
			},
			{
				premium: {
					// Editorial light palette — cream paper, bordeaux ink, bronze
					// highlights. Cartier catalogue, not casino. Burgundy carries
					// the "expensive" weight that gold carries on dark themes.
					'primary': '#6B1F2E',           // Deep bordeaux — the headline color
					'primary-content': '#F5F0E6',
					'secondary': '#1E2A3A',         // Ink navy (deep emphasis)
					'secondary-content': '#F5F0E6',
					'accent': '#9C7B3D',            // Antiqued bronze (rare highlights)
					'accent-content': '#F5F0E6',
					'neutral': '#2A2520',           // Espresso ink (borders, body text)
					'neutral-content': '#F5F0E6',
					'base-100': '#F5F0E6',          // Cream paper — NEVER pure white
					'base-200': '#EDE6D6',          // Buff paper (panel)
					'base-300': '#DDD3BD',          // Aged paper (raised)
					'base-content': '#2A2520',      // Espresso text (NEVER pure black)
					'info': '#3C5A7A',              // Slate blue
					'info-content': '#F5F0E6',
					'success': '#3D6B4E',           // Forest, never neon
					'success-content': '#F5F0E6',
					'warning': '#9C7B3D',           // Reuse the bronze for cohesion
					'warning-content': '#F5F0E6',
					'error': '#7A2530',             // Burgundy red (primary family)
					'error-content': '#F5F0E6',
				}
			},
			'light', 'dark', 'cupcake', 'bumblebee', 'emerald', 'corporate',
			'synthwave', 'retro', 'cyberpunk', 'valentine', 'halloween',
			'garden', 'forest', 'aqua', 'lofi', 'pastel', 'fantasy',
			'wireframe', 'black', 'luxury', 'dracula', 'cmyk', 'autumn',
			'business', 'acid', 'lemonade', 'night', 'coffee', 'winter',
			'dim', 'nord', 'sunset'
		],
		darkTheme: 'predictor'
	}
};
