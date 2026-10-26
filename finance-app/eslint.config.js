// https://docs.expo.dev/guides/using-eslint/
const { defineConfig } = require('eslint/config');
const expoConfig = require("eslint-config-expo/flat");

module.exports = defineConfig([
  expoConfig,
  {
    ignores: ["dist/*"],
    rules: {
      // Screens legitimately fetch external API state after mounting.
      // The starter template's web color-scheme hook has the same pattern.
      "react-hooks/set-state-in-effect": "off",
    },
  }
]);
