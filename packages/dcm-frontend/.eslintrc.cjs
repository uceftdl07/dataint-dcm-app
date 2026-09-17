module.exports = {
  root: true,
  env: { browser: true, es2020: true, node: true },
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/recommended',
    'plugin:react-hooks/recommended',
  ],
  ignorePatterns: ['dist', '.eslintrc.cjs', 'node_modules'],
  parser: '@typescript-eslint/parser',
  parserOptions: {
    ecmaVersion: 'latest',
    sourceType: 'module',
    ecmaFeatures: { jsx: true },
  },
  plugins: ['react-refresh', '@typescript-eslint'],
  overrides: [
    {
      files: ['src/**/*.test.{ts,tsx}', 'src/test/**/*.{ts,tsx}'],
      rules: {
        'react-refresh/only-export-components': 'off',
      },
    },
  ],
  rules: {
    'react-refresh/only-export-components': 'warn',
  },
}
