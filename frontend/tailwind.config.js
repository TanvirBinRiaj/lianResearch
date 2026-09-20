/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html","./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0a0a0f",
        brand: { 500:"#6366f1", 600:"#4f46e5" },
      },
      fontFamily: { sans: ["Inter","system-ui","sans-serif"], mono: ["JetBrains Mono","monospace"] }
    },
  },
  plugins: [require('@tailwindcss/typography')],
}

