import { expect, test } from "vitest";
import { learningStatus } from "./learningStatus";

test("old technical errors never appear in the learning UI", () => {
  for (const message of [
    "模型返回的 JSON 结构无效",
    "教学核验未通过",
    "正在修复 Schema",
    "超过预算",
  ]) {
    expect(learningStatus(message, true)).toBe("有点小问题，等等哈...");
    expect(learningStatus(message)).not.toMatch(/JSON|核验|Schema|预算/);
  }
  expect(learningStatus("DeepSeek 密钥无效，请检查设置")).toContain(
    "请检查设置",
  );
});
