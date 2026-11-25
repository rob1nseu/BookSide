from typing import Literal
from pydantic import BaseModel, Field, model_validator


class Question(BaseModel):
    kind: Literal["choice", "number", "short"] = "short"
    prompt: str = Field(min_length=3, max_length=4000)
    answer: str = Field(min_length=1, max_length=4000)
    rubric: str = Field(min_length=1, max_length=4000)
    hint: str = Field(min_length=1, max_length=2000)
    options: list[str] = Field(default_factory=list, max_length=6)
    tolerance: float = Field(default=0.001, ge=0, le=100)
    unit: str = Field(default="", max_length=40)
    sources: list[str] = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def valid(self):
        if self.kind == "choice" and (len(self.options) < 2 or self.answer not in self.options):
            raise ValueError("选择题答案必须属于选项")
        if self.kind == "number":
            value = float(self.answer)
            import math

            if not math.isfinite(value):
                raise ValueError("数值答案必须有限")
        return self


class Lesson(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    objective: str = Field(min_length=1, max_length=1000)
    explanation: str = Field(min_length=10, max_length=16000)
    example: str = Field(default="", max_length=6000)
    supplement: str = Field(default="", max_length=4000)
    sources: list[str] = Field(min_length=1, max_length=6)
    questions: list[Question] = Field(min_length=1, max_length=8)


class Feedback(BaseModel):
    verdict: Literal["correct", "partial", "incorrect", "uncertain"]
    explanation: str = Field(min_length=1, max_length=6000)
    missing: list[str] = Field(default_factory=list, max_length=10)
    next_step: str = Field(min_length=1, max_length=1000)
    sources: list[str] = Field(default_factory=list, max_length=6)


class Reply(BaseModel):
    text: str = Field(min_length=1, max_length=12000)
    sources: list[str] = Field(default_factory=list, max_length=6)
    supplement: bool = False


class Transcription(BaseModel):
    text: str = Field(max_length=10000)
    uncertain: bool = False
    note: str = Field(default="", max_length=1000)


class MemoryCandidate(BaseModel):
    text: str = Field(min_length=1, max_length=800)
    source_id: str
    replaces_id: str | None = None


class MemoryBatch(BaseModel):
    summary: str = Field(max_length=5000)
    source_ids: list[str] = Field(max_length=40)
    items: list[MemoryCandidate] = Field(default_factory=list, max_length=5)


class Action(BaseModel):
    action: Literal[
        "teach", "ask", "answer", "hint", "solution", "next", "skip", "retry_grade", "train", "partner"
    ]
    chapter_id: str | None = None
    text: str = Field(default="", max_length=10000)
    request_key: str = Field(min_length=8, max_length=120)
    private: bool = False
    selected_option: str | None = Field(default=None, max_length=4000)
    prepare_chapter: bool = False
