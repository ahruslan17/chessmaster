/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        sans: ["JetBrains Mono", "monospace"],
        coach: ["system-ui", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
      colors: {
        chess: {
          dark: "#2d2d2d",
          light: "#3d3d3d",
          highlight: "#4a7c59",
          best: "#22c55e",
          excellent: "#10b981",
          good: "#84cc16",
          theory: "#3b82f6",
          inaccuracy: "#eab308",
          mistake: "#f97316",
          blunder: "#ef4444",
        },
      },
    },
  },
  plugins: [],
};
