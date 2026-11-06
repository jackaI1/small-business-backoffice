import js from "@eslint/js";
import tseslint from "typescript-eslint";
import angular from "angular-eslint";
import globals from "globals";
export default tseslint.config(
  {
    ignores: [
      "node_modules/**",
      "web/**",
      "server/src/**",
      "server/test/**",
      "server/dist/**",
      "dist/**",
      ".angular/**",
      "coverage/**",
      "playwright-report/**",
      "test-results/**",
      ".runtime/**",
    ],
  },
  {
    files: ["**/*.mjs", "**/*.cjs"],
    extends: [js.configs.recommended],
    languageOptions: { globals: globals.node },
  },
  {
    files: ["scripts/browser-check.mjs"],
    languageOptions: { globals: globals.browser },
  },
  {
    files: ["**/*.ts"],
    extends: [
      ...tseslint.configs.recommended,
      ...angular.configs.tsRecommended,
    ],
    processor: angular.processInlineTemplates,
  },
  {
    files: ["**/*.html"],
    extends: [
      ...angular.configs.templateRecommended,
      ...angular.configs.templateAccessibility,
    ],
  },
);
