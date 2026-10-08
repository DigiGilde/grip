import js from '@eslint/js';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import globals from 'globals';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  { ignores: ['dist', 'src/components/nldd/nldd-elements.d.ts'] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
      // A boolean expression passed straight to a boolean attribute of an
      // nldd-* custom element. React renders `false` as the literal attribute
      // `current="false"`, and a custom element reads mere presence as true,
      // so `current={false}` turns the thing ON. Write `current={orUndef(x)}`
      // (from components/nldd/events) instead.
      'no-restricted-syntax': [
        'error',
        {
          selector:
            'JSXElement[openingElement.name.name=/^nldd-/] > JSXOpeningElement >' +
            ' JSXAttribute[name.name=/^(checked|selected|expanded|expandable|invalid|valid|disabled|required|loading|current|navigation|button|sticky-header|sticky-footer|has-content|hide-back)$/]' +
            ' > JSXExpressionContainer >' +
            ' :matches(Identifier, MemberExpression, UnaryExpression, BinaryExpression, LogicalExpression)',
          message:
            'Boolean attributes on nldd-* elements must be `true | undefined`, never `false`. ' +
            'Wrap it: current={orUndef(x)}, see src/components/nldd/events.ts.',
        },
      ],
    },
  },
);
