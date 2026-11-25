import io
import time

import pymupdf
import pytest
from fastapi.testclient import TestClient
from pptx import Presentation

from backend.app.main import create_app
from backend.app.model import Provider


def pdf_bytes():
    doc = pymupdf.open()
    for i, title in enumerate(["Chapter 1 Functions", "Chapter 2 Derivatives"]):
        page = doc.new_page()
        page.insert_text((60, 70), title, fontsize=22)
        page.insert_text(
            (60, 120),
            "A function maps each input to one output.\nThe derivative measures the rate of change.\nFor f(x)=x squared, the derivative is 2x.\nAlways check the domain before applying a definition.",
            fontsize=13,
        )
    doc.set_toc([[1, "Chapter 1 Functions", 1], [1, "Chapter 2 Derivatives", 2]])
    return doc.tobytes()


def pptx_bytes():
    doc = Presentation()
    slide = doc.slides.add_slide(doc.slide_layouts[1])
    slide.shapes.title.text = "Chapter 1 Functions"
    slide.placeholders[1].text = "A function maps one input to exactly one output."
    slide.notes_slide.notes_text_frame.text = "Remember to check the domain."
    output = io.BytesIO()
    doc.save(output)
    return output.getvalue()


@pytest.fixture
def client(tmp_path):
    provider = Provider(tmp_path, demo=True)
    with TestClient(create_app(tmp_path, provider)) as client:
        client.headers["X-LearNest"] = "1"
        yield client


def upload(client, content=None, name="course.pdf"):
    response = client.post("/api/documents", files={"file": (name, content or pdf_bytes())})
    assert response.status_code == 201, response.text
    doc = response.json()
    for _ in range(100):
        found = next(d for d in client.get("/api/documents").json() if d["id"] == doc["id"])
        if found["status"] in ("ready", "partial", "failed"):
            assert found["status"] != "failed", found
            return found
        time.sleep(0.02)
    raise AssertionError("Parser timed out")


def space(client, document=None):
    doc = document or upload(client)
    response = client.post("/api/spaces", json={"name": "Calculus", "document_ids": [doc["id"]]})
    assert response.status_code == 201, response.text
    return client.get("/api/spaces/" + response.json()["id"]).json()


def action(client, space_id, action="teach", **kwargs):
    import uuid

    response = client.post(
        f"/api/spaces/{space_id}/actions", json={"action": action, "request_key": str(uuid.uuid4()), **kwargs}
    )
    assert response.status_code == 202, response.text
    return finish(client, response.json()["id"])


def finish(client, run_id):
    for _ in range(150):
        result = client.get("/api/runs/" + run_id).json()
        if result["status"] != "running":
            return result
        time.sleep(0.02)
    raise AssertionError("Run timed out")
