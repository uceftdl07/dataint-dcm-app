/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        background: 'var(--background)',
        foreground: 'var(--foreground)',
        card: {
          DEFAULT: 'var(--card)',
          foreground: 'var(--card-foreground)',
        },
        popover: {
          DEFAULT: 'var(--popover)',
          foreground: 'var(--popover-foreground)',
        },
        primary: {
          DEFAULT: 'var(--primary)',
          foreground: 'var(--primary-foreground)',
        },
        secondary: {
          DEFAULT: 'var(--secondary)',
          foreground: 'var(--secondary-foreground)',
        },
        muted: {
          DEFAULT: 'var(--muted)',
          foreground: 'var(--muted-foreground)',
        },
        accent: {
          DEFAULT: 'var(--accent)',
          foreground: 'var(--accent-foreground)',
        },
        destructive: {
          DEFAULT: 'var(--destructive)',
          foreground: 'var(--destructive-foreground)',
        },
        success: {
          DEFAULT: 'var(--success)',
          foreground: 'var(--success-foreground)',
          subtle: 'var(--success-subtle)',
          border: 'var(--success-border)',
        },
        warning: {
          DEFAULT: 'var(--warning)',
          foreground: 'var(--warning-foreground)',
          subtle: 'var(--warning-subtle)',
          border: 'var(--warning-border)',
        },
        danger: {
          DEFAULT: 'var(--danger)',
          foreground: 'var(--danger-foreground)',
          subtle: 'var(--danger-subtle)',
          border: 'var(--danger-border)',
        },
        info: {
          DEFAULT: 'var(--info)',
          foreground: 'var(--info-foreground)',
          subtle: 'var(--info-subtle)',
          border: 'var(--info-border)',
        },
        purple: {
          DEFAULT: 'var(--purple)',
          foreground: 'var(--purple-foreground)',
          subtle: 'var(--purple-subtle)',
          border: 'var(--purple-border)',
        },
        border: 'var(--border)',
        input: 'var(--input)',
        ring: 'var(--ring)',
        sidebar: {
          DEFAULT: 'var(--sidebar)',
          foreground: 'var(--sidebar-foreground)',
          primary: 'var(--sidebar-primary)',
          'primary-foreground': 'var(--sidebar-primary-foreground)',
          accent: 'var(--sidebar-accent)',
          'accent-foreground': 'var(--sidebar-accent-foreground)',
          border: 'var(--sidebar-border)',
          ring: 'var(--sidebar-ring)',
        },
        tdf: {
          blue: 'var(--tdf-blue)',
          'blue-subtle': 'var(--tdf-blue-subtle)',
          'blue-border': 'var(--tdf-blue-border)',
          'blue-foreground': 'var(--tdf-blue-foreground)',
          grey: 'var(--tdf-grey)',
          'grey-foreground': 'var(--tdf-grey-foreground)',
          red: 'var(--tdf-red)',
          'red-foreground': 'var(--tdf-red-foreground)',
          green: 'var(--tdf-green)',
          'green-foreground': 'var(--tdf-green-foreground)',
          pink: 'var(--tdf-pink)',
          'pink-foreground': 'var(--tdf-pink-foreground)',
          purple: 'var(--tdf-purple)',
          'purple-foreground': 'var(--tdf-purple-foreground)',
          teal: 'var(--tdf-teal)',
          'teal-foreground': 'var(--tdf-teal-foreground)',
        },
      },
      borderRadius: {
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)',
        xl: 'calc(var(--radius) + 4px)',
      },
      fontFamily: {
        sans: ['var(--font-sans)'],
      },
    },
  },
  plugins: [],
};
