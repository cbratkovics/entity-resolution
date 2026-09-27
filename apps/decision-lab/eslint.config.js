import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import reactHooks from 'eslint-plugin-react-hooks';

const nodeGlobals = { console: 'readonly', process: 'readonly', Buffer: 'readonly', URL: 'readonly' };
const browserGlobals = {
  window: 'readonly', document: 'readonly', fetch: 'readonly', Response: 'readonly', Blob: 'readonly', File: 'readonly', FileReader: 'readonly',
  URL: 'readonly', URLSearchParams: 'readonly', localStorage: 'readonly', crypto: 'readonly', performance: 'readonly', setTimeout: 'readonly',
  DecompressionStream: 'readonly', HTMLDialogElement: 'readonly', Storage: 'readonly', console: 'readonly',
};

export default tseslint.config(
  { ignores: ['dist/**', 'node_modules/**', 'public/**', 'playwright-report/**', 'test-results/**'] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ['src/**/*.{ts,tsx}'],
    languageOptions: { globals: browserGlobals },
    plugins: { 'react-hooks': reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
    },
  },
  {
    files: ['scripts/**/*.{mjs,ts}', 'tests/**/*.ts', '*.ts', '*.js'],
    languageOptions: { globals: { ...nodeGlobals, ...browserGlobals } },
    rules: { '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }] },
  },
);
