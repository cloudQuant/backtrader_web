module.exports = {
  root: true,
  env: {
    node: true
  },
  extends: [
    'eslint:recommended',
    'plugin:vue/vue3-essential'
  ],
  parser: 'vue-eslint-parser',  // Vue文件解析器
  parserOptions: {
    ecmaVersion: 2020,
    sourceType: 'module',
    parser: '@typescript-eslint/parser'  // TypeScript解析器（用于<script lang="ts">）
  },
  rules: {
    'no-console': process.env.NODE_ENV === 'production' ? 'warn' : 'off',
    'no-debugger': process.env.NODE_ENV === 'production' ? 'warn' : 'off',
    'prefer-const': 'error',
    'no-var': 'error',
    'no-unused-vars': 'off',
    'no-case-declarations': 'off'  // 允许case中声明变量
  },
  ignorePatterns: [
    '*.cjs',
    'dist',
    'node_modules',
    'coverage',
    'e2e/**/*.ts'
  ],
  overrides: [
    {
      files: ['**/*.ts', '**/*.tsx'],
      parser: '@typescript-eslint/parser',
      plugins: ['@typescript-eslint'],
      extends: [
        'eslint:recommended',
        'plugin:@typescript-eslint/recommended'
      ],
      rules: {
        '@typescript-eslint/no-explicit-any': 'off',
        '@typescript-eslint/no-unused-vars': 'off',
        '@typescript-eslint/ban-types': 'off'  // 允许Function类型
      }
    }
  ]
}
