import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist"] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": [
        "warn",
        { allowConstantExport: true },
      ],
    },
  },
  {
    files: ["src/agent/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              group: [
                "../../components/*",
                "../../domain/*",
                "../../mock/*",
                "../../pages/*",
                "../../state/*",
                "../../workflow/*",
                "../../workflow/**",
              ],
              message: "Agent Mode must not import Workflow modules.",
            },
          ],
        },
      ],
    },
  },
  {
    files: [
      "src/components/**/*.{ts,tsx}",
      "src/domain/**/*.{ts,tsx}",
      "src/mock/**/*.{ts,tsx}",
      "src/pages/**/*.{ts,tsx}",
      "src/state/**/*.{ts,tsx}",
    ],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              group: ["../agent/*", "../../agent/*"],
              message: "Workflow Mode must not import Agent modules.",
            },
          ],
        },
      ],
    },
  },
  {
    files: ["src/workflow/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              group: [
                "../../agent/*",
                "../../agent/**",
                "../../../agent/*",
                "../../../agent/**",
              ],
              message: "Workflow Mode must not import Agent modules.",
            },
          ],
        },
      ],
    },
  },
  {
    files: ["src/ui/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              group: [
                "../agent/*",
                "../agent/**",
                "../../agent/*",
                "../../agent/**",
                "../workflow/*",
                "../workflow/**",
                "../../workflow/*",
                "../../workflow/**",
              ],
              message: "Shared UI must remain presentational and mode-neutral.",
            },
          ],
        },
      ],
    },
  },
);
