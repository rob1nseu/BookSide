import { test, expect } from "@playwright/test";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import path from "node:path";
test.use({ headless: process.platform !== "win32" });

test("pet reuses a live page and releases it when the tab closes", async ({
  page,
  request,
}) => {
  await page.goto("/");
  const open = () =>
    request.post("http://127.0.0.1:8765/api/companion/open", {
      headers: { "X-LearNest": "1" },
    });
  await expect
    .poll(async () => (await (await open()).json()).existing)
    .toBe(true);
  await page.close();
  await expect
    .poll(async () => (await (await open()).json()).existing)
    .toBe(false);
});

test("temporary startup failure recovers without a red error banner", async ({
  page,
}) => {
  let attempts = 0;
  await page.route("**/api/settings", async (route) => {
    if (++attempts === 1)
      await route.fulfill({ status: 503, json: { detail: "temporary" } });
    else await route.continue();
  });
  await page.goto("/");
  await expect(page.getByText("有点小问题，等等哈...")).toBeVisible();
  await expect(page.getByText(/演示模式 ·/)).toBeVisible();
  await expect(page.locator(".error-banner")).toHaveCount(0);
  expect(attempts).toBe(2);
});

test.describe("Windows browser activation", () => {
  test("activates the existing browser window without creating another tab", async ({
    page,
    context,
  }) => {
    test.skip(process.platform !== "win32", "Windows native activation");
    await page.goto("/");
    const opened = context.waitForEvent("page");
    await page.evaluate(() => window.open("about:blank", "_blank"));
    const other = await opened;
    await other.bringToFront();
    try {
      await promisify(execFile)(
        "powershell.exe",
        [
          "-NoProfile",
          "-NonInteractive",
          "-WindowStyle",
          "Hidden",
          "-ExecutionPolicy",
          "Bypass",
          "-File",
          path.resolve("../desktop/focus-browser.ps1"),
        ],
        { timeout: 15000 },
      );
    } catch (error) {
      // Windows may refuse foreground activation while the user uses another app.
      // Only that explicit outcome is acceptable; missing windows/script failures fail.
      expect((error as { code: number }).code).toBe(2);
      const response = await page.request.post(
        "http://127.0.0.1:8765/api/companion/open",
        {
          headers: { "X-LearNest": "1" },
        },
      );
      expect((await response.json()).existing).toBe(true);
      expect(context.pages()).toHaveLength(2);
      return;
    }
    const foreground = async () => {
      const result = await promisify(execFile)(
        path.resolve("../.venv/Scripts/python.exe"),
        [
          "-c",
          "import ctypes,sys; from ctypes import wintypes; u=ctypes.windll.user32; u.GetForegroundWindow.restype=wintypes.HWND; u.GetWindowTextW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]; b=ctypes.create_unicode_buffer(512); u.GetWindowTextW(u.GetForegroundWindow(),b,512); print(str(b.value.startswith(sys.argv[1])))",
          await page.title(),
        ],
      );
      return result.stdout.trim();
    };
    await expect.poll(foreground).toBe("True");
    expect(context.pages()).toHaveLength(2);
  });
});
