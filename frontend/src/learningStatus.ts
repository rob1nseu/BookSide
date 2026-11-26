export const recovering = "有点小问题，等等哈...";

// Also cover saved errors/progress from earlier app versions.
export function learningStatus(text: string, working = false) {
  if (
    /JSON|Schema|核验|校验|格式|结构|预算|自动重试|修复|连接中断|恢复.*连接/i.test(
      text,
    )
  ) {
    return working ? recovering : "这次还没准备好，请稍后再试。学习记录还在。";
  }
  return text;
}
