import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        dark: {
          DEFAULT: '#0C0C0C',
          elevated: '#161616',
          border: '#252525',
          hover: '#1E1E1E',
        },
        cream: {
          DEFAULT: '#F5F0EB',
          muted: '#E8E2DB',
          border: '#D4CEC7',
        },
        gold: {
          DEFAULT: '#C8A97E',
          dim: 'rgba(200, 169, 126, 0.15)',
        },
      },
      fontFamily: {
        serif: ['var(--font-dm-serif)', 'Georgia', 'serif'],
        sans: ['var(--font-jakarta)', '-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
      },
      fontSize: {
        'hero': 'clamp(56px, 8vw, 96px)',
        'section': 'clamp(36px, 5vw, 56px)',
        'subsection': 'clamp(20px, 3vw, 28px)',
      },
      letterSpacing: {
        'tight-hero': '-0.03em',
        'tight-section': '-0.02em',
        'wide-label': '0.15em',
      },
      borderRadius: {
        'image': '16px',
        'card': '20px',
        'pill': '100px',
        'notification': '14px',
      },
      maxWidth: {
        'container': '1280px',
      },
    },
  },
  plugins: [],
};
export default config;
