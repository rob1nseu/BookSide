"""Opt-in live map, review and original-image grading smoke test using synthetic material."""

import argparse
import json
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pymupdf
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.model import Provider


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--live", action="store_true", help="Allow real provider calls with synthetic fixtures"
    )
    if not parser.parse_args().live:
        raise SystemExit("Skipped: pass --live to use the locally configured provider.")
    provider = Provider(Path(os.getenv("LEARNEST_DATA_DIR", "data")), demo=False)
    if not provider.public()["configured"]:
        raise SystemExit("Local provider is not configured.")
    report = {"model": provider.public()["model"], "checks": []}
    with tempfile.TemporaryDirectory(prefix="learnest-live-review-") as temporary:
        with TestClient(create_app(Path(temporary), provider)) as client:
            client.headers["X-LearNest"] = "1"
            pdf = pymupdf.open()
            page = pdf.new_page()
            page.insert_text((50, 50), "Chapter 1 Derivatives", fontsize=18)
            page.insert_text(
                (50, 100),
                "The derivative measures instantaneous rate of change.\nFor f(x)=x squared, the derivative is f'(x)=2x.\nAt x=3, the slope equals 6.\nA function must be differentiable at the point.",
                fontsize=14,
            )
            pdf.set_toc([[1, "Chapter 1 Derivatives", 1]])
            response = client.post("/api/documents", files={"file": ("original-calculus.pdf", pdf.tobytes())})
            response.raise_for_status()
            document_id = response.json()["id"]
            for _ in range(100):
                doc = next(d for d in client.get("/api/documents").json() if d["id"] == document_id)
                if doc["status"] in ("ready", "partial"):
                    break
                time.sleep(0.1)
            response = client.post(
                "/api/spaces", json={"name": "Synthetic live review", "document_ids": [document_id]}
            )
            response.raise_for_status()
            space_id = response.json()["id"]
            initial = client.get(f"/api/spaces/{space_id}").json()
            chapter_id = initial["current_chapter"]

            def run(kind, **kwargs):
                started = time.monotonic()
                response = client.post(
                    f"/api/spaces/{space_id}/actions",
                    json={
                        "action": kind,
                        "chapter_id": chapter_id,
                        "request_key": str(uuid.uuid4()),
                        **kwargs,
                    },
                )
                response.raise_for_status()
                run_id = response.json()["id"]
                while time.monotonic() - started < 195:
                    result = client.get(f"/api/runs/{run_id}").json()
                    if result["status"] != "running":
                        report["checks"].append(
                            {
                                "action": kind,
                                "status": result["status"],
                                "elapsed_seconds": round(time.monotonic() - started, 2),
                                "usage": result["usage"],
                            }
                        )
                        print(json.dumps(report["checks"][-1]), flush=True)
                        if result["status"] != "done":
                            raise RuntimeError(f"{kind}: {result['error']}")
                        return result
                    time.sleep(0.25)
                raise RuntimeError(f"{kind}: local smoke wait exceeded")

            def review():
                return client.get(f"/api/spaces/{space_id}/review", params={"chapter_id": chapter_id}).json()

            run("review_map")
            report["map_nodes"] = len(review()["map"]["nodes"])
            run("review_start")
            session = review()["session"]
            questions = json.loads(
                client.app.state.store.one(
                    "SELECT questions FROM review_sessions WHERE id=?", (session["id"],)
                )["questions"]
            )
            q = questions[0]
            image_doc = pymupdf.open()
            answer_page = image_doc.new_page(width=700, height=500)
            answer_page.insert_textbox((25, 25, 675, 475), q["answer"][:700], fontsize=16, fontname="china-s")
            png = answer_page.get_pixmap().tobytes("png")
            response = client.post(
                f"/api/spaces/{space_id}/answer-image",
                params={"target": session["question"]["id"], "recognize": False},
                files={"file": ("synthetic-answer.png", png)},
            )
            response.raise_for_status()
            attachment_id = response.json()["id"]
            response = client.post(f"/api/spaces/{space_id}/attachments/{attachment_id}/transcribe")
            response.raise_for_status()
            assert response.json()["text"].strip(), "Image transcription was empty"
            report["transcription"] = {"nonempty": True, "uncertain": response.json()["uncertain"]}
            result = run(
                "review_answer",
                session_id=session["id"],
                question_id=session["question"]["id"],
                attachment_id=attachment_id,
                selected_option=q["answer"] if q["kind"] == "choice" else None,
            )
            report["image_grade_verdict"] = result["result"]["feedback"]["verdict"]
            assert report["image_grade_verdict"] == "correct", (
                "Reference answer image was not graded correctly"
            )
            final = client.get(f"/api/spaces/{space_id}").json()
            assert final["chapters"] == initial["chapters"], "Review changed normal learning progress"
            report["learning_progress_preserved"] = True
    print(json.dumps({"ok": True, **report}, ensure_ascii=False))


if __name__ == "__main__":
    main()
