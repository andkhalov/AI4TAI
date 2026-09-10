"""Общие фикстуры тестов AI4TAI.

Слои:
- юнит-тесты без сети: test_helpers, test_skills, test_pdf, test_artifacts,
  test_site, test_sqlite, test_rag, test_cli, test_recipe, test_web_mocked;
- test_network — реальные сервисы, только при AI4TAI_TEST_NETWORK=1.

Сайт в тестах всегда в режиме mock, база — временная копия учебной,
RAG — hash-эмбеддер (без сети).
"""
from __future__ import annotations

import os
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# Окружение до импорта модуля: сайт в mock, эмбеддер hash.
os.environ.setdefault("AI4TAI_SITE_MODE", "mock")
os.environ.setdefault("AI4TAI_EMBEDDER", "hash")


def _build_minimal_pdf(text: str) -> bytes:
    parts: list[bytes] = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]"
        b"/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>",
    ]
    body = b"BT /F1 12 Tf 72 720 Td (" + text.encode("latin-1", "replace") + b") Tj ET"
    parts.append(b"<</Length " + str(len(body)).encode() + b">>\nstream\n" + body + b"\nendstream")
    parts.append(b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>")
    out = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    offsets: list[int] = []
    for i, segment in enumerate(parts, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + segment + b"\nendobj\n"
    xref_start = len(out)
    out += b"xref\n0 " + str(len(parts) + 1).encode() + b"\n"
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (
        b"trailer <</Size " + str(len(parts) + 1).encode() + b"/Root 1 0 R>>\n"
        b"startxref\n" + str(xref_start).encode() + b"\n%%EOF\n"
    )
    return out


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    p = tmp_path / "sample.pdf"
    p.write_bytes(_build_minimal_pdf("Hello backup regulation restore theorem"))
    return p


@pytest.fixture
def m():
    """Модуль ai4tai_mcp."""
    import ai4tai_mcp
    return ai4tai_mcp


@pytest.fixture
def skills_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, m):
    d = tmp_path / "skills"
    d.mkdir()
    (d / "python.md").write_text(textwrap.dedent("""\
        ---
        name: python
        description: Python execution loop and venv discipline
        triggers: python, .py, pytest
        combines_with: debug-loop, markdown
        ---
        # Python skill body
        Use venvs, write tests, run them.
        """), encoding="utf-8")
    (d / "powershell.md").write_text(textwrap.dedent("""\
        ---
        name: powershell
        description: PowerShell scripts for Windows Server
        triggers: powershell, ps1
        combines_with: debug-loop
        ---
        # PowerShell skill body
        """), encoding="utf-8")
    (d / "bare.md").write_text("# bare\nno frontmatter", encoding="utf-8")
    monkeypatch.setattr(m, "SKILLS_DIR", d)
    return d


@pytest.fixture
def demo_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, m) -> Path:
    """Временная копия учебной базы; модуль указывает на неё как на базу по умолчанию."""
    import demo_db as builder
    p = tmp_path / "demo.sqlite"
    builder.build(p)
    monkeypatch.setattr(m, "DB_PATH", p)
    return p


@pytest.fixture
def rag_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, m) -> Path:
    """RAG-индекс по tests/fixtures/docs с hash-эмбеддером во временной папке."""
    import rag_index
    p = tmp_path / "index.sqlite"
    rag_index.build_index(Path(__file__).resolve().parent / "fixtures" / "docs", p, rag_index.HashEmbedder())
    monkeypatch.setattr(m, "RAG_DB", p)
    return p


def pytest_collection_modifyitems(config, items):
    if os.environ.get("AI4TAI_TEST_NETWORK") == "1":
        return
    skip_network = pytest.mark.skip(reason="set AI4TAI_TEST_NETWORK=1 to run")
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip_network)
