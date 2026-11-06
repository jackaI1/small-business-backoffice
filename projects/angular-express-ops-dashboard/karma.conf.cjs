module.exports = (config) =>
  config.set({
    frameworks: ["jasmine"],
    plugins: [require("karma-jasmine"), require("karma-chrome-launcher")],
    // GitHub Ubuntu runners restrict user namespaces for downloaded Chromium.
    browsers: [process.env.CI ? "CIChromeHeadless" : "ChromeHeadless"],
    customLaunchers: {
      CIChromeHeadless: { base: "ChromeHeadless", flags: ["--no-sandbox"] },
    },
    singleRun: true,
    reporters: ["dots"],
    browserNoActivityTimeout: 30000,
    client: { jasmine: { random: false } },
  });
