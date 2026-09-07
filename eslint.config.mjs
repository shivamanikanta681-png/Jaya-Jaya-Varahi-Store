import js from "@eslint/js";
import globals from "globals";

export default [
  js.configs.recommended,
  {
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: {
        ...globals.browser,
        ...globals.node,
        ...globals.es2021,
        firebase: "readonly",
        supabase: "readonly",
        escapeHTML: "readonly",
        bootstrap: "readonly"
      }
    },
    rules: {
      "no-unused-vars": [
        "warn",
        {
          "argsIgnorePattern": "^_",
          "varsIgnorePattern": "^_",
          "caughtErrors": "none"
        }
      ],
      "no-useless-assignment": "warn",
      "no-undef": "warn",
      "no-console": "off",
      "no-empty": ["error", { "allowEmptyCatch": true }]
    }
  },
  {
    ignores: [
      "node_modules/",
      ".git/",
      ".firebase/",
      "__pycache__/",
      "dist/",
      "build/"
    ]
  }
];
