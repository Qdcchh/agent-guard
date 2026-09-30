"""Check documentation examples and local links, not protocol correctness."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = [ROOT / name for name in ("README.md", "AGENT.md", "AGENTS.md")]
DOCUMENTS += sorted((ROOT / "docs").glob("*.md"))


def test_local_markdown_links_resolve():
    for document in DOCUMENTS:
        text = document.read_text(encoding="utf-8")
        for link in re.findall(r"\[[^\]]*\]\(([^)]+)\)", text):
            if link.startswith(("https://", "http://", "mailto:", "#")):
                continue
            target = link.split("#", 1)[0]
            assert (document.parent / target).exists(), f"{document.name}: {link}"


def test_fenced_json_examples_parse():
    for document in DOCUMENTS:
        text = document.read_text(encoding="utf-8")
        for example in re.findall(r"```json\s*\n(.*?)\n```", text, re.DOTALL):
            json.loads(example)
