"""RAG-индекс по локальным документам: нарезка → эмбеддинги → SQLite → поиск.

Используется MCP-сервером (rag_search / rag_status) и как CLI:

    python src/rag_index.py index data/docs --db .rag/index.sqlite
    python src/rag_index.py search "регламент выдачи СИЗ" --db .rag/index.sqlite
    python src/rag_index.py stats --db .rag/index.sqlite

Эмбеддеры:
    yandex  — Yandex AI Studio, /v1/embeddings (OpenAI-совместимый):
              документы  emb://<folder>/text-search-doc/latest
              запросы    emb://<folder>/text-search-query/latest
    hash    — локальный детерминированный bag-of-words (без сети; для тестов
              и для работы без ключа). Качество ниже, зато воспроизводимо.

Выбор: AI4TAI_EMBEDDER=yandex|hash, по умолчанию yandex при наличии
YANDEX_CLOUD_API_KEY и YANDEX_CLOUD_FOLDER, иначе hash. Имя эмбеддера
записывается в индекс, поиск использует тот же.

Формат индекса (SQLite):
    meta(key TEXT PRIMARY KEY, value TEXT)
    docs(id INTEGER PK, path TEXT, mtime REAL, nchunks INTEGER)
    chunks(id INTEGER PK, doc_id INTEGER, idx INTEGER, start_line INTEGER,
           end_line INTEGER, text TEXT, vec BLOB)  -- float32 little-endian
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sqlite3
import struct
import sys
import time
from pathlib import Path

# Windows: консоль по умолчанию cp1252/cp866 — принудительно UTF-8 для кириллицы.
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

TEXT_SUFFIXES = {".md", ".txt", ".csv", ".json", ".log", ".ps1", ".py", ".sql", ".bsl", ".yaml", ".yml", ".ini"}
PDF_SUFFIXES = {".pdf"}
DEFAULT_CHUNK_CHARS = 900
DEFAULT_OVERLAP_LINES = 2
HASH_DIM = 512


# ---------------------------------------------------------------- reading

def read_document(path: Path) -> str:
    suf = path.suffix.lower()
    if suf in PDF_SUFFIXES:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        pages = []
        for i, page in enumerate(reader.pages):
            try:
                pages.append(page.extract_text() or "")
            except Exception:
                pages.append("")
        return "\n".join(pages)
    for enc in ("utf-8", "utf-8-sig", "cp1251"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def iter_documents(root: Path) -> list[Path]:
    out = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if any(part.startswith(".") for part in p.relative_to(root).parts):
            continue
        if p.suffix.lower() in TEXT_SUFFIXES | PDF_SUFFIXES:
            out.append(p)
    return out


# ---------------------------------------------------------------- chunking

def chunk_text(text: str, chunk_chars: int = DEFAULT_CHUNK_CHARS,
               overlap_lines: int = DEFAULT_OVERLAP_LINES) -> list[dict]:
    """Нарезка по строкам: набираем строки, пока объём < chunk_chars.
    Абзацы не рвём посередине строки; между фрагментами перекрытие в строках."""
    lines = text.replace("\r\n", "\n").split("\n")
    chunks: list[dict] = []
    i = 0
    n = len(lines)
    while i < n:
        j = i
        size = 0
        while j < n and (size + len(lines[j]) + 1 <= chunk_chars or j == i):
            size += len(lines[j]) + 1
            j += 1
        body = "\n".join(lines[i:j]).strip()
        if body:
            chunks.append({"start_line": i + 1, "end_line": j, "text": body})
        if j >= n:
            break
        i = max(j - overlap_lines, i + 1)
    return chunks


# ---------------------------------------------------------------- embedders

def _l2(v: list[float]) -> list[float]:
    s = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / s for x in v]


def _tokenize(text: str) -> list[str]:
    return [t for t in re.split(r"[^\wёЁ]+", text.casefold()) if len(t) > 1]


class HashEmbedder:
    name = "hash"

    def __init__(self, dim: int = HASH_DIM):
        self.dim = dim

    def _embed_one(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        toks = _tokenize(text)
        # униграммы + биграммы, sqrt-tf
        grams = toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:])]
        counts: dict[str, int] = {}
        for g in grams:
            counts[g] = counts.get(g, 0) + 1
        for g, c in counts.items():
            h = hashlib.blake2b(g.encode("utf-8"), digest_size=8).digest()
            idx = int.from_bytes(h[:4], "little") % self.dim
            sign = 1.0 if h[4] % 2 == 0 else -1.0
            v[idx] += sign * math.sqrt(c)
        return _l2(v)

    def embed_docs(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed_one(text)


class YandexEmbedder:
    name = "yandex"

    def __init__(self, api_key: str, folder: str,
                 doc_model: str = "text-search-doc/latest",
                 query_model: str = "text-search-query/latest",
                 base_url: str = "https://llm.api.cloud.yandex.net"):
        self.api_key = api_key
        self.folder = folder
        self.doc_model = doc_model
        self.query_model = query_model
        self.base_url = base_url.rstrip("/")
        self.dim = 0

    def _call(self, model: str, text: str) -> list[float]:
        import requests
        r = requests.post(
            f"{self.base_url}/v1/embeddings",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={"model": f"emb://{self.folder}/{model}", "input": text[:8000]},
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        vec = data["data"][0]["embedding"]
        self.dim = len(vec)
        return _l2([float(x) for x in vec])

    def embed_docs(self, texts: list[str]) -> list[list[float]]:
        out = []
        for i, t in enumerate(texts):
            out.append(self._call(self.doc_model, t))
            if (i + 1) % 20 == 0:
                time.sleep(0.2)
        return out

    def embed_query(self, text: str) -> list[float]:
        return self._call(self.query_model, text)


def get_embedder(name: str | None = None):
    name = (name or os.environ.get("AI4TAI_EMBEDDER") or "").lower()
    key = os.environ.get("YANDEX_CLOUD_API_KEY", "")
    folder = os.environ.get("YANDEX_CLOUD_FOLDER", "")
    if name == "hash":
        return HashEmbedder()
    if name == "yandex" or (not name and key and folder):
        if not (key and folder):
            raise RuntimeError("Для эмбеддера yandex нужны YANDEX_CLOUD_API_KEY и YANDEX_CLOUD_FOLDER")
        return YandexEmbedder(key, folder)
    return HashEmbedder()


# ---------------------------------------------------------------- storage

def _pack(vec: list[float]) -> bytes:
    return struct.pack(f"<{len(vec)}f", *vec)


def _unpack(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"<{n}f", blob))


def _open(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db_path))
    con.execute("CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT)")
    con.execute("CREATE TABLE IF NOT EXISTS docs(id INTEGER PRIMARY KEY, path TEXT UNIQUE, mtime REAL, nchunks INTEGER)")
    con.execute(
        "CREATE TABLE IF NOT EXISTS chunks(id INTEGER PRIMARY KEY, doc_id INTEGER, idx INTEGER, "
        "start_line INTEGER, end_line INTEGER, text TEXT, vec BLOB)"
    )
    return con


def build_index(docs_dir: Path, db_path: Path, embedder=None,
                chunk_chars: int = DEFAULT_CHUNK_CHARS, verbose: bool = False) -> dict:
    docs_dir = Path(docs_dir)
    if not docs_dir.is_dir():
        raise FileNotFoundError(f"папка не найдена: {docs_dir}")
    embedder = embedder or get_embedder()
    if db_path.exists():
        db_path.unlink()
    con = _open(db_path)
    files = iter_documents(docs_dir)
    total_chunks = 0
    dim = 0
    for f in files:
        text = read_document(f)
        chunks = chunk_text(text, chunk_chars=chunk_chars)
        if not chunks:
            continue
        vecs = embedder.embed_docs([c["text"] for c in chunks])
        dim = len(vecs[0]) if vecs else dim
        rel = f.relative_to(docs_dir).as_posix()
        cur = con.execute("INSERT INTO docs(path, mtime, nchunks) VALUES (?,?,?)",
                          (rel, f.stat().st_mtime, len(chunks)))
        doc_id = cur.lastrowid
        con.executemany(
            "INSERT INTO chunks(doc_id, idx, start_line, end_line, text, vec) VALUES (?,?,?,?,?,?)",
            [(doc_id, i, c["start_line"], c["end_line"], c["text"], _pack(v))
             for i, (c, v) in enumerate(zip(chunks, vecs))],
        )
        total_chunks += len(chunks)
        if verbose:
            print(f"  {rel}: {len(chunks)} фрагментов")
    meta = {
        "embedder": embedder.name,
        "dim": str(dim),
        "docs_dir": str(docs_dir.resolve()),
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "chunk_chars": str(chunk_chars),
    }
    con.executemany("INSERT OR REPLACE INTO meta(key, value) VALUES (?,?)", meta.items())
    con.commit()
    con.close()
    return {"docs": len(files), "chunks": total_chunks, "embedder": embedder.name, "dim": dim}


def index_stats(db_path: Path) -> dict:
    con = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
    try:
        meta = dict(con.execute("SELECT key, value FROM meta").fetchall())
        docs = con.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
        chunks = con.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    finally:
        con.close()
    return {
        "docs": docs, "chunks": chunks,
        "embedder": meta.get("embedder", "?"), "dim": meta.get("dim", "?"),
        "created": meta.get("created", "?"), "docs_dir": meta.get("docs_dir", "?"),
    }


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))  # оба вектора нормированы


def search(db_path: Path, query: str, top_k: int = 5, embedder=None) -> list[dict]:
    con = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
    try:
        meta = dict(con.execute("SELECT key, value FROM meta").fetchall())
        name = meta.get("embedder", "hash")
        if embedder is None:
            embedder = HashEmbedder() if name == "hash" else get_embedder(name)
        q = embedder.embed_query(query)
        rows = con.execute(
            "SELECT c.id, d.path, c.idx, c.start_line, c.end_line, c.text, c.vec "
            "FROM chunks c JOIN docs d ON d.id = c.doc_id"
        ).fetchall()
    finally:
        con.close()
    scored = []
    for cid, path, idx, s, e, text, blob in rows:
        v = _unpack(blob)
        if len(v) != len(q):
            continue
        scored.append((_cosine(q, v), cid, path, idx, s, e, text))
    scored.sort(key=lambda x: -x[0])
    return [
        {"score": sc, "chunk_id": cid, "path": path, "idx": idx,
         "start_line": s, "end_line": e, "text": text}
        for sc, cid, path, idx, s, e, text in scored[:top_k]
    ]


# ---------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="AI4TAI RAG index")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_idx = sub.add_parser("index", help="построить индекс по папке")
    p_idx.add_argument("docs_dir")
    p_idx.add_argument("--db", default=os.environ.get("AI4TAI_RAG_DB", ".rag/index.sqlite"))
    p_idx.add_argument("--embedder", choices=["yandex", "hash"], default=None)
    p_idx.add_argument("--chunk-chars", type=int, default=DEFAULT_CHUNK_CHARS)
    p_s = sub.add_parser("search", help="поиск по индексу")
    p_s.add_argument("query")
    p_s.add_argument("--db", default=os.environ.get("AI4TAI_RAG_DB", ".rag/index.sqlite"))
    p_s.add_argument("-k", "--top-k", type=int, default=5)
    p_st = sub.add_parser("stats", help="состояние индекса")
    p_st.add_argument("--db", default=os.environ.get("AI4TAI_RAG_DB", ".rag/index.sqlite"))
    args = ap.parse_args(argv)

    if args.cmd == "index":
        # .env из корня репозитория, чтобы ключ Yandex был виден без export
        _load_dotenv(Path(__file__).resolve().parent.parent / ".env")
        emb = get_embedder(args.embedder)
        print(f"Индексирую {args.docs_dir} → {args.db} (эмбеддер: {emb.name})")
        st = build_index(Path(args.docs_dir), Path(args.db), emb, args.chunk_chars, verbose=True)
        print(f"Готово: документов {st['docs']}, фрагментов {st['chunks']}, dim={st['dim']}")
        return 0
    if args.cmd == "search":
        _load_dotenv(Path(__file__).resolve().parent.parent / ".env")
        for h in search(Path(args.db), args.query, args.top_k):
            print(f"[{h['score']:.3f}] {h['path']} ({h['start_line']}–{h['end_line']})")
            print("   " + h["text"][:300].replace("\n", " ") + "\n")
        return 0
    if args.cmd == "stats":
        st = index_stats(Path(args.db))
        for k, v in st.items():
            print(f"{k}: {v}")
        return 0
    return 1


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
            v = v[1:-1]
        os.environ.setdefault(k, v)


if __name__ == "__main__":
    sys.exit(main())
