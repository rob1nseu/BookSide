import { test, expect } from "@playwright/test";
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
test("upload -> learn -> question -> review -> companion -> reload", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await expect(page).toHaveTitle("LearNest · 极简学习");
  await page.getByRole("button", { name: "新建学习", exact: true }).click();
  await page
    .getByLabel("上传学习资料")
    .setInputFiles([
      path.join(fixtures, "calculus.pdf"),
      path.join(fixtures, "lecture.pptx"),
    ]);
  await expect(
    page.getByRole("button", { name: "创建学习空间" }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "创建学习空间" }).click();
  await page.getByRole("button", { name: "开始学习", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "先理解，再往前走" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "阅读资料" }).click();
  await expect(page.getByLabel("PDF 第 1 页")).toBeVisible();
  await page.getByRole("button", { name: "关闭阅读器" }).click();
  await page.getByRole("button", { name: "来试一道题" }).click();
  await page
    .getByLabel("主输入框")
    .fill("函数描述了输入和输出的对应关系，每一个输入只对应一个输出。");
  await page.getByRole("button", { name: "提交回答", exact: true }).click();
  await expect(page.getByRole("heading", { name: "理解得不错" })).toBeVisible();
  await page.getByRole("button", { name: "考前复习", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "返回章节学习" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "返回章节学习" }).click();
  await page.getByRole("button", { name: "打开小芽陪聊" }).click();
  await page.getByLabel("发送给小芽").fill("今天有点累。");
  await page.getByRole("button", { name: "发送陪聊", exact: true }).click();
  await expect(page.getByText(/【演示陪聊】我在这里/)).toBeVisible();
  await page.getByRole("button", { name: "关闭陪聊" }).click();
  await page.reload();
  await expect(page.getByRole("heading", { name: "理解得不错" })).toBeVisible();
  await page.screenshot({
    path: path.join(os.tmpdir(), "learnest-desktop.png"),
    fullPage: true,
  });
  expect(errors).toEqual([]);
});
test("mobile navigation and controls stay inside viewport", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "今天，想学懂什么？" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "展开导航" }).click();
  await page.getByRole("button", { name: "设置", exact: false }).click();
  await expect(page.getByRole("dialog", { name: "设置" })).toBeVisible();
  await page.getByRole("button", { name: "关闭", exact: true }).click();
  await page.getByRole("button", { name: "展开导航" }).click();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.locator(".space-open").first().click();
  await expect(page.getByLabel("主输入框")).toBeInViewport();
  await expect(page.getByRole("heading", { name: "理解得不错" })).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: path.join(os.tmpdir(), "learnest-mobile.png"),
    fullPage: true,
  });
});
