/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // As três cores do semáforo, iguais em todo o dashboard.
        sinal: { verde: "#16a34a", amarelo: "#eab308", vermelho: "#dc2626", apagado: "#334155" },
      },
    },
  },
  plugins: [],
};
