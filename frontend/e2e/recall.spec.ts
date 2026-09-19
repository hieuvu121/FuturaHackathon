import { expect, test, type Page } from "@playwright/test";

/**
 * The loop under test: an answer decides the next question.
 *
 * Grading runs on the deterministic key-point path here (blank API keys in
 * playwright.config.ts), so a "good" answer is one that names the rubric and a
 * "poor" one is anything else.
 *
 * These tests share one backend, one demo user and one attempt log, so they run
 * serially and in a deliberate order: the session is fresh when the file starts
 * and every later assertion is relative to where the previous test left it.
 */

const GOOD: Record<string, string> = {
  "natural key":
    "A natural key can change, carries business meaning and is wide, so a surrogate key is stable.",
  "normalising":
    "It removes duplication so one fact lives in one place, avoiding update anomalies and keeping consistency.",
  "collides across repositories":
    "Use a composite key that includes the repo id with a unique constraint, to scope the identity.",
  "function name":
    "It says what it does, starts with a verb, holds no surprise, so there is no need to read the body.",
  "computes metrics":
    "It has one reason to change, so it is hard to test and hard to reuse; split by responsibility.",
};

const level = async (page: Page) =>
  Number(await page.getByTestId("drill-card").getAttribute("data-level"));

const skill = async (page: Page) => (await page.locator(".drill-skill").textContent())!;

/**
 * Click through to the next drill and wait for the card to actually swap.
 * AnimatePresence keeps the outgoing card mounted during its exit, so reading
 * the level straight after the click can still see the old one.
 */
async function advance(page: Page) {
  const leaving = (await page.getByTestId("drill-prompt").first().textContent()) ?? "";
  await page.getByTestId("drill-next").click();
  await expect(page.getByTestId("drill-card")).toHaveCount(1);
  await expect(page.getByTestId("drill-prompt")).not.toHaveText(leaving);
}

async function answerCurrent(page: Page, quality: "good" | "poor") {
  const prompt = ((await page.getByTestId("drill-prompt").textContent()) ?? "").toLowerCase();
  const key = Object.keys(GOOD).find((phrase) => prompt.includes(phrase));
  await page
    .getByTestId("drill-answer")
    .fill(quality === "good" && key ? GOOD[key] : "I do not know this one.");
  await page.getByTestId("drill-check").click();
  await expect(page.getByTestId("drill-result")).toBeVisible();
}

test.describe("adaptive recall", () => {
  test.describe.configure({ mode: "serial" });

  test.beforeEach(async ({ page }) => {
    await page.goto("/recall");
    await expect(page.getByTestId("drill-card")).toBeVisible();
  });

  test("an answer decides the next question", async ({ page }) => {
    // One walk from a genuinely fresh session, because each move sets up the
    // next: a pass raises the level, the fail above it brackets the skill, and
    // the fresh skill that follows can then be eased downward. Splitting these
    // into separate tests would have them fight over one shared attempt log.
    expect(await level(page)).toBe(2);
    await expect(page.getByTestId("drill-reason")).toContainText("find your level");
    await expect(page.locator(".drill-progress")).toContainText("0 answered");

    // A pass goes harder, staying on the same skill.
    const first = await skill(page);
    await answerCurrent(page, "good");
    await expect(page.getByTestId("drill-result")).toContainText("That holds up");
    await expect(page.getByTestId("drill-move")).toHaveText("Going one level harder");
    await advance(page);
    expect(await skill(page)).toBe(first);
    // Harder, though not always by exactly one: the bank may lack the adjacent level.
    expect(await level(page)).toBeGreaterThan(2);

    // Failing the level above a pass is the gap, so the skill is done.
    await answerCurrent(page, "poor");
    await expect(page.getByTestId("drill-move")).toHaveText("Moving to the next skill");
    await advance(page);
    const second = await skill(page);
    expect(second).not.toBe(first);
    expect(await level(page)).toBe(2);

    // On that fresh skill, a miss eases off instead.
    await answerCurrent(page, "poor");
    await expect(page.getByTestId("drill-result")).toContainText("Not there yet");
    // A miss must leave something behind, or the session only measures.
    await expect(page.locator(".drill-model-answer")).not.toBeEmpty();
    await expect(page.getByTestId("drill-move")).toHaveText("Easing off one level");
    await advance(page);
    expect(await skill(page)).toBe(second);
    expect(await level(page)).toBeLessThan(2);
  });

  test("a question is short and states its kind and level", async ({ page }) => {
    const prompt = (await page.getByTestId("drill-prompt").textContent()) ?? "";
    expect(prompt.length).toBeLessThan(140);

    await expect(page.locator(".drill-kind")).toHaveText(/Concept|Coding task/);
    await expect(page.locator(".level-pips i.on")).toHaveCount(await level(page));
  });

  test("progress counts up as the session goes", async ({ page }) => {
    const read = async () =>
      Number(((await page.locator(".drill-progress").textContent()) ?? "").match(/(\d+) answered/)![1]);
    const before = await read();

    await answerCurrent(page, "good");
    await advance(page);

    await expect.poll(read).toBe(before + 1);
  });

  test("what the loop promises is what it delivers", async ({ page }) => {
    // Whatever question the session has reached by now, the promised move and
    // the question that actually arrives must agree. This holds without the
    // test knowing the answer to the question in front of it.
    for (let turn = 0; turn < 4; turn++) {
      const subject = await skill(page);
      const from = await level(page);

      await answerCurrent(page, turn % 2 === 0 ? "good" : "poor");
      const move = await page.getByTestId("drill-move").textContent().catch(() => null);
      if (!move) break; // the session ended

      await advance(page);
      const nextSubject = await skill(page);
      const to = await level(page);

      if (move === "Moving to the next skill") {
        expect(nextSubject).not.toBe(subject);
      } else if (move === "Going one level harder") {
        expect(nextSubject).toBe(subject);
        expect(to).toBeGreaterThan(from);
      } else if (move === "Easing off one level") {
        expect(nextSubject).toBe(subject);
        expect(to).toBeLessThan(from);
      }
    }
  });

  test("the session survives a phone-width viewport", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(page.getByTestId("drill-card")).toBeVisible();

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth
    );
    expect(overflow).toBeLessThanOrEqual(1);
  });
});
