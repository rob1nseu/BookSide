export type Document = {
  id: string;
  name: string;
  kind: string;
  status: string;
  error?: string;
};
export type Page = {
  id: string;
  document_id: string;
  number: number;
  title: string;
  text: string;
  notes: string;
  warning: string;
};
export type Feedback = {
  verdict: string;
  explanation: string;
  missing: string[];
  next_step: string;
  sources: string[];
};
export type Attempt = {
  id: string;
  question_id: string;
  answer: string;
  feedback: Feedback;
  assisted: number;
  disputed: number;
};
export type Lesson = {
  title: string;
  objective: string;
  explanation: string;
  example: string;
  supplement: string;
  sources: string[];
};
export type Question = {
  id: string;
  kind: string;
  prompt: string;
  options?: string[];
  unit?: string;
  position: number;
};
export type Chapter = {
  concepts?: { concept: string; state: string; independent: number; assisted: number; errors: string[] }[];
  id: string;
  document_id: string;
  title: string;
  start_page: number;
  end_page: number;
  state: string;
  lesson: Lesson | null;
  question: Question | null;
  question_count: number;
  question_index: number;
  attempts: Attempt[];
  hint_used: number;
  revealed: number;
  parent_id: string | null;
  is_group: number;
  level: number;
  preparation: string;
  preparation_error: string | null;
};
export type Space = {
  id: string;
  name: string;
  archived: number;
  chapter_count?: number;
  current_chapter: string;
  mode: string;
  review_queue: string[];
  chapters: Chapter[];
  documents: Document[];
  active_run: string | null;
  legacy_outline: boolean;
};
export type Message = {
  id: string;
  role: string;
  text: string;
  private: number;
};
export type Run = {
  id: string;
  status: string;
  partial: string;
  error: string;
  result: {
    text?: string;
    feedback?: Feedback;
    supplement?: boolean;
    sources?: string[];
  } | null;
};
export type Settings = {
  provider: string;
  model: string;
  configured: boolean;
  demo: boolean;
  memory_paused: boolean;
  retrieval: string;
};
