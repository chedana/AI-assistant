/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: "#0a0a0a",      // Deeper black for main background
        panel: "#141414",        // Slightly lighter for cards
        "panel-alt": "#111111",  // Subtle alternative for sidebar
        border: "#262626",       // More subtle borders
        muted: "#94a3b8",        // Slate-400 for better legibility
        text: "#f8fafc",         // Slate-50 for high contrast
        accent: "#10b981",       // Emerald-500 (vibrant green)
        "accent-dim": "#059669", // Emerald-600
      }
    },
  },
  plugins: [],
};
