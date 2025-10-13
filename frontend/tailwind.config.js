/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        // 背景色系
        'primary-bg': '#0A0E1A',
        'secondary-bg': '#131829',
        'elevated-bg': '#1A1F35',
        'border-color': '#2A3048',

        // 前景色系
        'primary-text': '#E8EAF6',
        'secondary-text': '#A8B2D1',
        'muted-text': '#6B7694',
        'placeholder': '#4A5578',

        // 功能色
        'accent-primary': '#6366F1',
        'accent-secondary': '#8B5CF6',
        'success': '#10B981',
        'warning': '#F59E0B',
        'error': '#EF4444',
        'info': '#3B82F6',

        // 霓虹高光色
        'neon-purple': '#A78BFA',
        'neon-blue': '#60A5FA',
        'neon-cyan': '#22D3EE',
      },
      backgroundImage: {
        'gradient-primary': 'linear-gradient(135deg, #6366F1 0%, #8B5CF6 100%)',
        'gradient-secondary': 'linear-gradient(135deg, #3B82F6 0%, #6366F1 100%)',
        'glow-effect': 'radial-gradient(circle, rgba(99,102,241,0.15) 0%, transparent 70%)',
      },
      boxShadow: {
        'glow-sm': '0 0 10px rgba(99,102,241,0.3)',
        'glow-md': '0 0 20px rgba(99,102,241,0.4)',
        'glow-lg': '0 0 30px rgba(99,102,241,0.5)',
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'glow': 'glow 2s ease-in-out infinite',
        'gradient-shift': 'gradient-shift 3s ease infinite',
      },
      keyframes: {
        glow: {
          '0%, 100%': {
            boxShadow: '0 0 5px rgba(99,102,241,0.5), 0 0 10px rgba(99,102,241,0.3)',
          },
          '50%': {
            boxShadow: '0 0 10px rgba(99,102,241,0.8), 0 0 20px rgba(99,102,241,0.5), 0 0 30px rgba(99,102,241,0.3)',
          },
        },
        'gradient-shift': {
          '0%': { backgroundPosition: '0% 50%' },
          '50%': { backgroundPosition: '100% 50%' },
          '100%': { backgroundPosition: '0% 50%' },
        },
      },
    },
  },
  plugins: [],
};
