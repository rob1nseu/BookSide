from urllib.parse import urlparse
from backend.app.resources import recommend, CATALOG
from conftest import space


def test_topics_use_subject_evidence_not_incidental_substrings():
    assert recommend("Linear Algebra", "Eigenvalue", "")["matched_topics"][0] == "线性代数"
    assert recommend("现代文学史", "第一章", "人物与叙事")["items"] == []
    assert recommend("LLM", "", "attention")["matched_topics"] == ["大语言模型"]
    assert recommend("small molecules", "", "")["items"] == []  # no llm substring match
    assert recommend("unknown", "", "", "机器人")["items"][0]["id"] == "robotics"


def test_resources_are_scoped_and_allow_topic_correction(client):
    s = space(client)
    doc = s["documents"][0]["id"]
    response = client.get(f"/api/spaces/{s['id']}/resources", params={"document_id": doc})
    assert response.status_code == 200
    assert response.json()["items"] and "reason" in response.json()["items"][0]
    response = client.get(
        f"/api/spaces/{s['id']}/resources", params={"document_id": doc, "topic": "大语言模型"}
    )
    assert {r["id"] for r in response.json()["items"]} == {"hf-llm", "llm-scratch"}
    assert (
        client.get(f"/api/spaces/{s['id']}/resources", params={"document_id": "foreign"}).status_code == 404
    )
    assert (
        client.get(
            f"/api/spaces/{s['id']}/resources", params={"document_id": doc, "topic": "invalid"}
        ).status_code
        == 422
    )


def test_catalog_has_reviewable_provenance_and_safe_unique_links():
    assert len({r["id"] for r in CATALOG}) == len(CATALOG)
    for r in CATALOG:
        assert urlparse(r["url"]).scheme == "https"
        assert urlparse(r["source_url"]).scheme == "https"
        assert r["author"] and r["prerequisite"] and r["checked_on"]
