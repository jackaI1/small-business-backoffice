import { test, expect } from "@playwright/test";
import { readFile } from "node:fs/promises";
test("real API charts, responsive layout, and accessible chart values", async ({
  page,
}, testInfo) => {
  await page.goto("/venue/");
  await expect(page).toHaveURL(/\/overview$/);
  await expect(page.getByTestId("total-volume")).toHaveText("23,325");
  await expect(page.locator(".hour-chart li")).toHaveCount(12);
  await expect(page.locator(".station-row")).toHaveCount(4);
  await page.getByText("View hourly values", { exact: true }).click();
  await expect(page.locator("details tbody tr")).toHaveCount(12);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.getByText("View hourly values", { exact: true }).click();
  await page.screenshot({
    path: testInfo.outputPath("dashboard.png"),
    fullPage: true,
  });
});
test("typed filters update all panels, persist across routes, and survive reload", async ({
  page,
}) => {
  await page.goto("/venue/overview");
  await page.getByLabel("From", { exact: true }).fill("2026-10-30");
  await page.getByLabel("To", { exact: true }).fill("2026-10-30");
  await page
    .getByRole("combobox", { name: "Station", exact: true })
    .selectOption("north");
  await page.getByRole("button", { name: "Apply filters" }).click();
  await expect(page).toHaveURL(/station=north/);
  await expect(page.locator(".station-row")).toHaveCount(1);
  const expected = await (
    await page.request.get(
      "/api/volume?from=2026-10-30&to=2026-10-30&station=north",
    )
  ).json();
  await expect(page.getByTestId("total-volume")).toHaveText(
    expected.total.toLocaleString("en-US"),
  );
  await page.getByRole("link", { name: "Anomaly review", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Anomaly review" }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("combobox", { name: "Station", exact: true }),
  ).toHaveValue("north");
  await expect(page.locator("tbody tr")).toHaveCount(1);
  await expect(page.locator("tbody")).toContainText("127.8%");
});
test("CSV contains only the applied station and date, not unsubmitted edits", async ({
  page,
}) => {
  await page.goto(
    "/venue/overview?from=2026-10-30&to=2026-10-30&station=north",
  );
  await page
    .getByRole("combobox", { name: "Station", exact: true })
    .selectOption("south");
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export CSV", exact: true }).click();
  const download = await downloadPromise;
  const path = await download.path();
  const csv = await readFile(path!, "utf8");
  expect(download.suggestedFilename()).toBe(
    "venue-2026-10-30-to-2026-10-30.csv",
  );
  expect(csv.trim().split("\r\n")).toHaveLength(13);
  expect(csv).toContain('"north"');
  expect(csv).not.toContain('"south"');
});
for (const [endpoint, retry, healthy] of [
  ["volume", "hourly volume", ".station-row"],
  ["stations", "station utilisation", '[data-testid="total-volume"]'],
  ["anomalies", "anomalies", '[data-testid="total-volume"]'],
])
  test(`${endpoint} panel fails independently and retries`, async ({
    page,
  }) => {
    let fail = true;
    await page.route(`**/api/${endpoint}?*`, (route) =>
      fail
        ? route.fulfill({ status: 503, json: { message: "Unavailable" } })
        : route.continue(),
    );
    await page.goto("/venue/overview");
    await expect(
      page.getByRole("button", { name: `Retry ${retry}`, exact: true }),
    ).toBeVisible();
    await expect(page.locator(healthy).first()).toBeVisible();
    fail = false;
    await page
      .getByRole("button", { name: `Retry ${retry}`, exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: `Retry ${retry}`, exact: true }),
    ).toHaveCount(0);
    await expect(
      page.getByText("Loading " + retry + "…", { exact: true }),
    ).toHaveCount(0);
  });
test("each panel announces loading while its own request is pending", async ({
  page,
}) => {
  const releases: (() => void)[] = [];
  await page.route(/\/api\/(volume|stations|anomalies)\?/, async (route) => {
    await new Promise<void>((resolve) => releases.push(resolve));
    await route.continue();
  });
  try {
    await page.goto("/venue/overview", { waitUntil: "domcontentloaded" });
    for (const label of ["hourly volume", "station utilisation", "anomalies"]) {
      await expect(
        page.getByText(`Loading ${label}…`, { exact: true }),
      ).toBeVisible();
    }
  } finally {
    releases.forEach((release) => release());
  }
  await expect(page.getByTestId("total-volume")).toBeVisible();
});
test("empty dates and invalid date ranges have useful states", async ({
  page,
}) => {
  await page.goto("/venue/overview?from=2026-12-01&to=2026-12-01&station=all");
  await expect(
    page.getByText("No interactions in this range.", { exact: false }),
  ).toBeVisible();
  await expect(
    page.getByText("No station activity in this range.", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("No anomalies match these filters.", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("To", { exact: true }).fill("2026-10-01");
  await expect(
    page.getByRole("button", { name: "Apply filters" }),
  ).toBeDisabled();
  await expect(page.getByRole("alert")).toContainText("Choose valid dates");
});
test("review filters quiet hours and direct route works", async ({ page }) => {
  await page.goto("/venue/anomalies");
  await page
    .getByRole("combobox", { name: "Show", exact: true })
    .selectOption("quiet");
  await expect(page.locator("tbody tr")).toHaveCount(1);
  await expect(page.locator("tbody")).toContainText("Information desk");
});
test("filter metadata and CSV errors recover without a reload", async ({
  page,
}) => {
  await page.route("**/api/metadata", (route) =>
    route.fulfill({ status: 503, json: {} }),
  );
  await page.goto("/venue/overview");
  await expect(
    page.getByRole("button", { name: "Retry filter options" }),
  ).toBeVisible();
  await page.unroute("**/api/metadata");
  await page.getByRole("button", { name: "Retry filter options" }).click();
  await page.route("**/api/export.csv?*", (route) =>
    route.fulfill({ status: 503, json: {} }),
  );
  await page.getByRole("button", { name: "Export CSV", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("CSV export failed");
  await expect(
    page.getByRole("button", { name: "Export CSV", exact: true }),
  ).toBeEnabled();
});

test("production and venue dashboards link to each other on the same host", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Production overview", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Venue shiftboard", exact: true })
    .click();
  await expect(page).toHaveURL(/\/venue\/overview$/);
  await expect(page.getByTestId("total-volume")).toHaveText("23,325");
  await page
    .getByRole("link", { name: "Production overview", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Production overview", exact: true }),
  ).toBeVisible();
});
