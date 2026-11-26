"""Deterministic, explainable recommendations from an editorially verified catalog.

No textbook text is sent to a search provider; no model-created URLs are accepted.
"""

import json
import re
from pathlib import Path

CATALOG = json.loads(Path(__file__).with_name("resources.json").read_text(encoding="utf-8"))
TOPICS = {
    "微积分": [
        "微积分",
        "高等数学",
        "数学分析",
        "导数",
        "积分",
        "calculus",
        "derivative",
        "derivatives",
        "limits",
    ],
    "线性代数": ["线性代数", "矩阵", "特征值", "linear algebra", "matrix", "matrices", "eigenvalue"],
    "概率统计": ["概率", "统计", "随机变量", "probability", "statistics", "random variable"],
    "机器学习": ["机器学习", "深度学习", "神经网络", "machine learning", "deep learning", "neural network"],
    "大语言模型": [
        "大语言模型",
        "大模型",
        "语言模型",
        "transformer",
        "transformers",
        "llm",
        "language model",
    ],
    "机器人": ["机器人", "具身智能", "运动学", "robotics", "robot", "kinematics", "embodied"],
    "物理": ["物理", "电磁", "量子", "physics", "mechanics", "electromagnetism", "quantum"],
    "计算机科学": ["计算机", "数据结构", "操作系统", "算法", "computer science", "algorithms", "programming"],
}


def matches(word, text):
    if word.isascii():
        return bool(re.search(r"(?<![a-z])" + re.escape(word) + r"(?![a-z])", text.lower()))
    return word in text


def recommend(name, titles, excerpt, topic=None):
    hits = {}
    scores = {}
    for subject, words in TOPICS.items():
        found = [w for w in words if matches(w, name + " " + titles + " " + excerpt)]
        scores[subject] = sum(
            5 * matches(w, name) + 3 * matches(w, titles) + matches(w, excerpt) for w in words
        )
        if found:
            hits[subject] = found
    selected = [topic] if topic else sorted(hits, key=lambda t: -scores[t])[:2]
    items = []
    for subject in selected:
        for item in CATALOG:
            if item["topic"] == subject:
                items.append(
                    {
                        **item,
                        "reason": "你选择了「" + subject + "」方向"
                        if topic
                        else "教材标题、目录或正文出现：" + "、".join(hits[subject][:3]),
                    }
                )
    return {
        "topics": list(TOPICS),
        "matched_topics": selected,
        "items": items[:5],
        "method": "curated-topic-match",
    }
