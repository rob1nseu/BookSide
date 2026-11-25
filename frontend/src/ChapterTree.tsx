import type { Chapter } from "./types";

export default function ChapterTree({
  chapters,
  current,
  choose,
}: {
  chapters: Chapter[];
  current: string;
  choose: (id: string) => void;
}) {
  function children(parent: string | null): React.ReactNode {
    return chapters
      .filter((c) => c.parent_id === parent)
      .map((chapter) =>
        chapter.is_group ? (
          <details className="chapter-group" key={chapter.id} open>
            <summary>{chapter.title}</summary>
            <div>{children(chapter.id)}</div>
          </details>
        ) : (
          <button
            key={chapter.id}
            className={"chapter " + (chapter.id === current ? "selected" : "")}
            onClick={() => choose(chapter.id)}
          >
            <span>
              {chapter.title}
              <small>
                {chapter.preparation === "running"
                  ? "正在准备"
                  : chapter.preparation === "queued"
                    ? "等待准备"
                    : chapter.preparation === "failed"
                      ? "准备失败，可重试"
                      : chapter.preparation === "ready" &&
                          chapter.state === "未学习"
                        ? "讲解已准备"
                        : chapter.state}
              </small>
            </span>
          </button>
        ),
      );
  }
  return <>{children(null)}</>;
}
