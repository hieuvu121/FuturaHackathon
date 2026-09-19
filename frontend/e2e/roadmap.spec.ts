import { expect, test } from "@playwright/test";

test.describe("roadmap diagram", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/roadmap");
    await expect(page.getByTestId("roadmap-diagram")).toBeVisible();
  });

  test("draws a spine of concept boxes", async ({ page }) => {
    const concepts = page.getByTestId("concept-node");
    expect(await concepts.count()).toBeGreaterThan(1);

    // The spine itself is a drawn connector, not decoration we can skip.
    const spine = await page.evaluate(() => {
      const diagram = document.querySelector(".roadmap-diagram");
      return diagram ? getComputedStyle(diagram, "::before").width : null;
    });
    expect(spine).not.toBeNull();
  });

  test("a concept box carries the concept only, never the detail", async ({ page }) => {
    const collapsed = page.getByTestId("concept-node").filter({ hasText: /Show \d+ skill/ }).first();

    await expect(collapsed).toHaveAttribute("aria-expanded", "false");
    await expect(collapsed).not.toContainText("New ground");
    await expect(collapsed).not.toContainText("to fix it");
    await expect(collapsed.locator("h3")).toBeVisible();
  });

  test("clicking a concept reveals its personalised detail", async ({ page }) => {
    // Pin the node by id before clicking: a hasText filter stops matching once
    // the label flips to "Hide detail".
    const collapsed = page.getByTestId("concept-node").filter({ hasText: /Show \d+ skill/ }).first();
    const conceptId = await collapsed.getAttribute("data-concept");
    const panelId = await collapsed.getAttribute("aria-controls");
    const node = page.locator(`[data-concept="${conceptId}"]`);

    await node.click();

    await expect(node).toHaveAttribute("aria-expanded", "true");
    const panel = page.locator(`#${panelId}`);
    await expect(panel).toBeVisible();

    const firstSkill = panel.getByTestId("skill-node").first();
    await expect(firstSkill).toBeVisible();
    await expect(firstSkill.locator("h4")).not.toBeEmpty();
    // Every leaf carries a next step written for this user, not a generic blurb.
    await expect(firstSkill.locator(".skill-focus")).toContainText(
      /Proven in|Prove it|Builds on|New ground|Optimise it|Harden it|to fix it/
    );
  });

  test("clicking an open concept closes it again", async ({ page }) => {
    const opened = page.getByTestId("concept-node").filter({ hasText: "Hide detail" }).first();
    const conceptId = await opened.getAttribute("data-concept");
    const panelId = await opened.getAttribute("aria-controls");
    const node = page.locator(`[data-concept="${conceptId}"]`);

    await node.click();

    await expect(node).toHaveAttribute("aria-expanded", "false");
    await expect(page.locator(`#${panelId}`)).toHaveCount(0);
  });

  test("only one concept is open at a time", async ({ page }) => {
    const collapsed = page.getByTestId("concept-node").filter({ hasText: /Show \d+ skill/ }).first();

    await collapsed.click();

    await expect(page.getByTestId("concept-node").filter({ hasText: "Hide detail" })).toHaveCount(1);
  });

  test("software engineer is the only role offered", async ({ page }) => {
    await expect(page.getByText("Software engineer", { exact: true })).toBeVisible();

    for (const dropped of ["Backend engineer", "Data engineer", "ML engineer"]) {
      await expect(page.getByText(dropped, { exact: true })).toHaveCount(0);
    }
  });

  test("the roadmap looks forward: no revise bucket", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "Revise" })).toHaveCount(0);
    await expect(page.getByText("Touched in your code, not yet verified")).toHaveCount(0);
  });

  test("every skill node states where the user stands", async ({ page }) => {
    const statuses = page.locator(".skill-node .skill-status");
    expect(await statuses.count()).toBeGreaterThan(0);

    for (const text of await statuses.allTextContents()) {
      expect(["Verified", "Basics", "New"]).toContain(text);
    }
  });

  test("survives a phone-width viewport", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(page.getByTestId("roadmap-diagram")).toBeVisible();

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth
    );
    expect(overflow).toBeLessThanOrEqual(1);
  });

  test("every node carries a percentage bar, parent and child alike", async ({ page }) => {
    const concept = page.getByTestId("concept-node").first();
    await expect(concept.locator(".mastery b")).toHaveText(/^\d+%$/);

    const panel = page.locator(".concept-detail").first();
    const bars = panel.locator(".skill-node .mastery b");
    expect(await bars.count()).toBeGreaterThan(0);
    for (const text of await bars.allTextContents()) {
      expect(text).toMatch(/^\d+%$/);
    }
  });

  test("a concept's bar is the mean of the bars beneath it", async ({ page }) => {
    const concept = page.getByTestId("concept-node").first();
    const parent = Number((await concept.locator(".mastery b").textContent())!.replace("%", ""));

    const children = await page.locator(".concept-detail .skill-node .mastery b").allTextContents();
    const mean = children.reduce((sum, t) => sum + Number(t.replace("%", "")), 0) / children.length;

    expect(Math.abs(parent - mean)).toBeLessThanOrEqual(1);
  });

  test("evidence opens source in place instead of navigating away", async ({ page }) => {
    await page.locator(".evidence-link").first().click();

    await expect(page.getByTestId("evidence-dialog")).toBeVisible();
    expect(new URL(page.url()).pathname).toBe("/roadmap");

    await page.keyboard.press("Escape");
    await expect(page.getByTestId("evidence-dialog")).toHaveCount(0);
  });

  test("the profile page is gone from the shell", async ({ page }) => {
    await expect(page.locator(".nav-link", { hasText: "Profile" })).toHaveCount(0);
  });
});
