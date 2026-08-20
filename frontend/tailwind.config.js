import { defineConfig } from '@tailwindcss/postcss'

export default defineConfig({
  content: ['./src/**/*.{html,js,ts,jsx,tsx}'],
  plugins: {
    '@tailwindcss/typography': {},
  },
})