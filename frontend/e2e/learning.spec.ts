import { test, expect, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import os from "node:os";
import path from "node:path";
let fixtures: string;
test.beforeAll(() => {
  fixtures = mkdtempSync(path.join(os.tmpdir(), "learnest-fixtures-"));
  const python = path.resolve(
    "..",
    ".venv",
    process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
  );
  execFileSync(python, ["../scripts/make_samples.py", "--output", fixtures]);
});
test.afterAll(() => rmSync(fixtures, { recursive: true, force: true }));

test("verified resources match each textbook, allow correction and use local editorial fonts", async ({
  page,
}) => {
  const errors = watchErrors(page);
  await createSpace(page, "calculus.pdf");
  const separator = page.getByRole("separator", { name: "调整侧栏宽度" });
  const beforeWidth = Number(await separator.getAttribute("aria-valuenow"));
  await separator.focus();
  await separator.press("ArrowLeft");
  await expect(separator).toHaveAttribute(
    "aria-valuenow",
    String(beforeWidth + 20),
  );
  await page.reload();
  await expect(separator).toHaveAttribute(
    "aria-valuenow",
    String(beforeWidth + 20),
  );
  await page.getByText("教材之外", { exact: false }).click();
  await expect(page.getByRole("link", { name: /MIT 18.01SC/ })).toHaveAttribute(
    "href",
    "https://ocw.mit.edu/courses/18-01sc-single-variable-calculus-fall-2010/",
  );
  await page.getByLabel("拓展方向").focus();
  await page.getByLabel("拓展方向").selectOption("机器学习");
  await expect(page.getByRole("link", { name: /跟李沐学 AI/ })).toBeVisible();
  await expect(page.getByLabel("拓展方向")).toBeFocused();
  await page.getByRole("button", { name: "阅读资料" }).click();
  await expect(page.getByLabel("教材拓展")).toBeHidden();
  await page.getByRole("button", { name: "关闭阅读器" }).click();
  await expect(page.getByLabel("拓展方向")).toHaveValue("机器学习");
  await expect(page.getByRole("link", { name: /跟李沐学 AI/ })).toHaveAttribute(
    "href",
    "https://space.bilibili.com/1567748478",
  );
  await expect(
    page.getByRole("link", { name: /动手学深度学习/ }),
  ).toHaveAttribute("rel", "noopener noreferrer");
  await page
    .locator(".resource-row")
    .first()
    .getByText("学习建议与来源")
    .click();
  await expect(page.locator(".resource-row").first()).toContainText(
    "2026-11-26",
  );
  await page.evaluate(() => document.fonts.ready);
  expect(
    await page.evaluate(() =>
      document.fonts.check('16px "Noto Serif SC Variable"', "学习"),
    ),
  ).toBeTruthy();
  await screenshot(page, "resources-desktop");
  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(async () =>
      page
        .locator(".sidebar")
        .evaluate((el) => el.getBoundingClientRect().right),
    )
    .toBeLessThanOrEqual(0);
  await page
    .locator(".resources")
    .evaluate((el) => el.scrollIntoView({ block: "start" }));
  await viewportFits(page);
  await screenshot(page, "resources-mobile");
  expect(errors).toEqual([]);
});

function watchErrors(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (e) => {
    if (e.type() === "error") errors.push(e.text());
  });
  return errors;
}
async function createSpace(page: Page, file = "hierarchy.pdf") {
  await page.goto("/");
  await expect(page).toHaveTitle("LearNest · 极简学习");
  await page.getByRole("button", { name: "新建学习", exact: true }).click();
  await page
    .getByLabel("上传学习资料")
    .setInputFiles(path.join(fixtures, file));
  await page.getByRole("button", { name: "创建学习空间" }).click();
  await expect(
    page.getByRole("button", { name: "开始学习", exact: true }),
  ).toBeVisible();
}
async function learn(page: Page) {
  await page.getByRole("button", { name: "开始学习", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "先理解，再往前走" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "来试一道题" }).click();
}

test("lost action response reuses the same run and temporary page failure keeps the learning position", async ({
  page,
}) => {
  await createSpace(page, "calculus.pdf");
  const keys: string[] = [];
  const runs: string[] = [];
  await page.route("**/api/spaces/*/actions", async (route) => {
    keys.push(route.request().postDataJSON().request_key);
    const response = await route.fetch();
    runs.push((await response.json()).id);
    if (keys.length === 1) await route.abort("connectionreset");
    else await route.fulfill({ response });
  });
  await learn(page);
  expect(keys).toHaveLength(2);
  expect(keys[0]).toBe(keys[1]);
  expect(runs[0]).toBe(runs[1]);
  const spaceId = await page.evaluate(() =>
    localStorage.getItem("learnest:space"),
  );
  let loads = 0;
  await page.route(`**/api/spaces/${spaceId}?compact=true`, async (route) => {
    if (++loads === 1) await route.fulfill({ status: 503 });
    else await route.continue();
  });
  await page.reload();
  await expect(page.getByLabel("作答输入框")).toBeVisible();
  expect(
    await page.evaluate(() => localStorage.getItem("learnest:space")),
  ).toBe(spaceId);
  await expect(page.locator(".error-banner")).toHaveCount(0);
});
async function viewportFits(page: Page) {
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
}
async function screenshot(page: Page, name: string) {
  await page.screenshot({
    path: path.join(os.tmpdir(), `learnest-${name}.png`),
    fullPage: true,
  });
}

test("an old chapter error is hidden and chapter preparation restarts automatically", async ({
  page,
}) => {
  await createSpace(page, "calculus.pdf");
  const id = await page.evaluate(() => localStorage.getItem("learnest:space"));
  let injected = false,
    submissions = 0;
  await page.route(`**/api/spaces/${id}?compact=true`, async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    if (!injected) {
      const chapter = data.chapters.find(
        (c: { id: string }) => c.id === data.current_chapter,
      );
      chapter.preparation = "failed";
      chapter.preparation_error = "模型返回的 JSON 结构无效，教学核验未通过";
      injected = true;
    }
    await route.fulfill({ response, json: data });
  });
  await page.route(`**/api/spaces/${id}/actions`, async (route) => {
    submissions++;
    const response = await route.fetch();
    await new Promise((resolve) => setTimeout(resolve, 800));
    await route.fulfill({ response });
  });
  await page.reload();
  await expect(page.locator(".run-progress")).toContainText(
    "有点小问题，等等哈...",
  );
  await expect(page.getByText(/JSON|教学核验/)).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "先理解，再往前走" }),
  ).toBeVisible();
  expect(submissions).toBe(1);
});

test("lecture help, question help and answer drafts remain independent across reload", async ({
  page,
}) => {
  const errors = watchErrors(page);
  await createSpace(page);
  await learn(page);
  await page
    .getByLabel("作答输入框")
    .fill("我的作答草稿：定义、适用条件和例子。");
  await page.getByRole("button", { name: "问这道题", exact: true }).click();
  await expect(page.getByLabel("作答输入框")).toHaveCount(0);
  await page.getByLabel("题目提问输入框").fill("题目草稿：解释一下题意");
  await page.getByRole("button", { name: /^问讲义/ }).click();
  await expect(page.getByLabel("题目提问输入框")).toHaveCount(0);
  await page.getByLabel("讲义提问输入框").fill("讲义草稿：定义域是什么？");
  await page.getByRole("button", { name: "发送讲义问题" }).click();
  await expect(page.locator(".lecture-dock .reply")).toBeVisible();
  await expect(page.locator(".feedback")).toHaveCount(0);
  await page.getByRole("button", { name: /关闭讲义提问/ }).click();
  await expect(page.getByLabel("作答输入框")).toHaveValue(
    "我的作答草稿：定义、适用条件和例子。",
  );
  await page.getByRole("button", { name: "问这道题", exact: true }).click();
  await expect(page.getByLabel("题目提问输入框")).toHaveValue(
    "题目草稿：解释一下题意",
  );
  await page.getByRole("button", { name: "发送题目问题" }).click();
  await expect(page.locator(".question .reply")).toBeVisible();
  await expect(page.locator(".feedback")).toHaveCount(0);
  await screenshot(page, "question-help");
  await page.getByRole("button", { name: "返回作答", exact: true }).click();
  await page.reload();
  await expect(page.getByLabel("作答输入框")).toHaveValue(
    "我的作答草稿：定义、适用条件和例子。",
  );
  await page.getByRole("button", { name: "提交答案", exact: true }).click();
  await expect(page.locator(".feedback")).toContainText("辅助");
  await page.getByRole("button", { name: "打开小芽陪聊" }).click();
  await page.getByLabel("发送给小芽").fill("今天有点累。");
  await page.getByRole("button", { name: "发送陪聊", exact: true }).click();
  await expect(page.getByText(/【演示陪聊】我在这里/)).toBeVisible();
  await page.getByRole("button", { name: "关闭陪聊" }).click();
  expect(errors).toEqual([]);
});

test("original answer image persists, gives feedback and never leaks to the next question", async ({
  page,
}) => {
  const errors = watchErrors(page);
  await createSpace(page);
  await learn(page);
  await page.getByLabel("上传答案图片", { exact: true }).setInputFiles({
    name: "bad.gif",
    mimeType: "image/gif",
    buffer: Buffer.from("invalid"),
  });
  await expect(page.getByText("请选择 PNG 或 JPEG 图片。")).toBeVisible();
  await page
    .getByLabel("上传答案图片", { exact: true })
    .setInputFiles(path.join(fixtures, "answer.png"));
  await expect(page.getByText("已附原图 · 可提交判分")).toBeVisible();
  await expect(page.getByText(/有不清晰的内容，请核对原图/)).toBeVisible();
  await expect(page.locator(".feedback")).toHaveCount(0);
  await page.getByText("查看 / 修改识别文字", { exact: true }).click();
  await expect(page.getByLabel("核对识别结果")).toHaveValue(/x = 2/);
  // Confirmation is optional: the original attachment itself must enable grading.
  await expect(page.getByLabel("作答输入框")).toHaveValue("");
  await page.reload();
  await expect(page.getByAltText("当前题目的答案图片")).toBeVisible();
  const request = page.waitForRequest(
    (r) => r.url().endsWith("/actions") && r.method() === "POST",
  );
  await page.getByRole("button", { name: "提交答案", exact: true }).click();
  expect((await request).postDataJSON().attachment_id).toBeTruthy();
  await expect(page.locator(".feedback")).toBeVisible();
  await screenshot(page, "image-answer");
  await page.getByRole("button", { name: "继续下一题", exact: true }).click();
  await expect(page.getByAltText("当前题目的答案图片")).toHaveCount(0);
  await page.getByRole("radio", { name: "只背一个词" }).check();
  await page
    .getByLabel("作答输入框")
    .fill("我觉得只要背下名词就足够了，不需要考虑适用条件。");
  await page.reload();
  await expect(page.getByRole("radio", { name: "只背一个词" })).toBeChecked();
  await expect(page.getByLabel("作答输入框")).toHaveValue(/不需要考虑适用条件/);
  await page.getByRole("button", { name: "提交答案", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "一起检查一下" }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test("chapter map -> cited concept -> review questions -> weak node -> saved session and summary", async ({
  page,
}) => {
  const errors = watchErrors(page);
  await createSpace(page);
  await page.getByRole("button", { name: /1.3 Inverse/ }).click();
  await page.getByRole("button", { name: "考前复习", exact: true }).click();
  await page.getByRole("button", { name: "生成章节思维导图" }).click();
  await expect(page.locator(".react-flow__node")).toHaveCount(5);
  await page.getByRole("button", { name: "放大查看" }).click();
  const enlarged = page.getByRole("dialog", { name: "章节思维导图" });
  await expect(enlarged).toBeVisible();
  await screenshot(page, "map-expanded-close");
  await expect(page.getByText("退出放大")).toHaveCount(0);
  await enlarged.getByRole("button", { name: "关闭思维导图" }).click();
  await expect(enlarged).toHaveCount(0);
  await expect(page.getByRole("button", { name: "放大查看" })).toBeFocused();
  await page.getByRole("button", { name: "放大查看" }).click();
  await page.keyboard.press("Escape");
  await expect(enlarged).toHaveCount(0);
  await page.getByRole("button", { name: "折叠Chapter 1 Functions" }).click();
  await expect(page.locator(".react-flow__node")).toHaveCount(1);
  await page.getByRole("button", { name: "展开Chapter 1 Functions" }).click();
  await expect(page.locator(".react-flow__node")).toHaveCount(5);
  await page
    .locator(".react-flow__node")
    .filter({ hasText: "1.3 Inverse" })
    .click();
  await expect(page.locator(".concept-detail .katex")).toHaveCount(1);
  await screenshot(page, "review-map");
  await page.getByRole("button", { name: "查看讲义原页" }).click();
  await expect(page.getByLabel("PDF 第 3 页")).toBeVisible();
  await page.getByRole("button", { name: "关闭阅读器" }).click();
  await page.getByRole("button", { name: "本章练一轮" }).click();
  await expect(page.locator(".review-position")).toContainText("第 1 / 3 题");
  await page.getByLabel("作答输入框").fill("短答案");
  await page.getByRole("button", { name: "提交答案", exact: true }).click();
  await expect(page.locator(".feedback")).toBeVisible();
  await page.getByRole("button", { name: "回导图补习这个知识点" }).click();
  await expect(page.locator(".concept-node.selected")).toContainText("需巩固");
  await page.getByRole("button", { name: "继续本轮练习" }).click();
  await page.getByRole("button", { name: "继续下一题", exact: true }).click();
  await page.getByRole("button", { name: "问这道题", exact: true }).click();
  await page.getByLabel("题目提问输入框").fill("请给我一点方向");
  await page.getByRole("button", { name: "发送题目问题" }).click();
  await expect(page.locator(".question .reply")).toBeVisible();
  await page.getByRole("button", { name: "返回作答", exact: true }).click();
  await page
    .getByLabel("作答输入框")
    .fill("这里给出一个完整的定义和成立条件，然后举例。");
  await page.reload();
  await expect(page.locator(".review-position")).toContainText("第 2 / 3 题");
  await expect(page.getByLabel("作答输入框")).toHaveValue(/完整的定义/);
  await page.getByRole("button", { name: "提交答案", exact: true }).click();
  await expect(page.locator(".feedback")).toContainText("辅助完成");
  await page.getByRole("button", { name: "继续下一题", exact: true }).click();
  await page.getByRole("button", { name: "跳过，保持未验证" }).click();
  await expect(
    page.getByRole("heading", { name: "本轮复习完成" }),
  ).toBeVisible();
  await screenshot(page, "review-summary");
  await page.getByRole("button", { name: "返回章节学习" }).click();
  await expect(
    page.getByRole("heading", { name: "1.3 Inverse", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "开始学习", exact: true }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test("mobile math, image feedback and review outline fit the viewport; idle pages do not reload lessons", async ({
  page,
}) => {
  const errors = watchErrors(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await createSpace(page);
  await page.route(/\/api\/spaces\/[^/?]+\?compact=true$/, async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    const chapter = data.chapters.find(
      (c: { id: string }) => c.id === data.current_chapter,
    );
    if (chapter?.lesson)
      chapter.lesson.explanation = String.raw`函数的变化率 \(f'(x)=2x\)。

\[\begin{aligned}f(x)&=x^2 \\ f'(x)&=2x\end{aligned}\]

\[\begin{bmatrix}1&2\\3&4\end{bmatrix}\]`;
    await route.fulfill({ response, json: data });
  });
  await page.getByRole("button", { name: "开始学习", exact: true }).click();
  await expect(page.locator(".lesson .katex")).toHaveCount(3);
  await expect(page.locator(".katex-error")).toHaveCount(0);
  await viewportFits(page);
  await screenshot(page, "math-mobile");
  await page.getByRole("button", { name: "换个解释", exact: true }).click();
  await expect(page.locator(".lecture-dock .reply")).toBeVisible();
  await page.getByRole("button", { name: /关闭讲义提问/ }).click();
  let fullRefreshes = 0;
  page.on("request", (r) => {
    if (/\/spaces\/[^/?]+\?compact=true$/.test(r.url())) fullRefreshes++;
  });
  await page.waitForTimeout(3000);
  expect(fullRefreshes).toBe(0);
  await page.getByRole("button", { name: "来试一道题" }).click();
  await page
    .getByLabel("上传答案图片", { exact: true })
    .setInputFiles(path.join(fixtures, "answer.png"));
  await expect(page.getByText("已附原图 · 可提交判分")).toBeVisible();
  await page
    .getByRole("button", { name: "提交答案", exact: true })
    .scrollIntoViewIfNeeded();
  await expect(
    page.getByRole("button", { name: "提交答案", exact: true }),
  ).toBeInViewport();
  await viewportFits(page);
  await screenshot(page, "answer-mobile");
  await page.getByRole("button", { name: "考前复习", exact: true }).click();
  await page.getByRole("button", { name: "生成章节思维导图" }).click();
  await expect(page.locator(".map-outline")).toBeVisible();
  await page
    .locator(".map-outline")
    .getByRole("button", { name: /1.1 Sets/ })
    .click();
  await expect(page.locator(".concept-detail")).toBeVisible();
  await viewportFits(page);
  await screenshot(page, "review-mobile");
  expect(errors).toEqual([]);
});
