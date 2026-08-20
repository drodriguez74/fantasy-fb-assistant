import { defineConfig } from '@tailwindcss/postcss'

// NOTE: Tailwind v4 (via `@tailwindcss/postcss`) does not load this file
// unless a stylesheet adds `@config "./tailwind.config.js";` -- this
// project doesn't, so `theme` here is not the source of truth. The actual
// design tokens live in `src/index.css`'s `@theme` block (see the comment
// there for the full palette rationale). This file mirrors the same
// `ink` / `accent` / `success` / `warning` / `danger` values so the
// palette is discoverable from config the way most Tailwind projects
// expect, and so a future `@config` wire-up would "just work" with
// matching values.
export default defineConfig({
  content: ['./src/**/*.{html,js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: {
          50: '#f4f5f7',
          100: '#e4e6eb',
          200: '#cbced8',
          300: '#a3a9b8',
          400: '#7d8598',
          500: '#5b6478',
          600: '#3d4557',
          700: '#29303f',
          800: '#1b212d',
          900: '#12161f',
          950: '#0a0d14',
        },
        accent: {
          50: '#fdf3ed',
          100: '#fbe1d0',
          200: '#f5be9c',
          300: '#ec9764',
          400: '#dd7638',
          500: '#c2560b',
          600: '#a0470a',
          700: '#7a3708',
          800: '#562705',
          900: '#351803',
        },
        success: {
          50: '#f0fdf4',
          100: '#dcfce7',
          500: '#22c55e',
          600: '#16a34a',
          700: '#15803d',
          800: '#166534',
        },
        warning: {
          50: '#fffbeb',
          100: '#fef3c7',
          500: '#f59e0b',
          600: '#d97706',
          700: '#b45309',
          800: '#92400e',
        },
        danger: {
          50: '#fef2f2',
          100: '#fee2e2',
          500: '#ef4444',
          600: '#dc2626',
          700: '#b91c1c',
          800: '#991b1b',
        },
      },
    },
  },
  plugins: {
    '@tailwindcss/typography': {},
  },
})
