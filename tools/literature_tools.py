# Author: Saytoblue <Saytoblue@gmail.com>
# Copyright (c) 2026-05-06 Saytoblue


"""
Literature search tools.
Supports Semantic Scholar API and arXiv API.
"""

from __future__ import annotations
import hashlib
import io
import os
import re
import tempfile
from pathlib import Path
import time
import json
import xml.etree.ElementTree as ET
from typing import Optional
from utils.operations import request_key, load_result, save_result
from utils.storage import atomic_write_text, named_lock


def _search_cache(source, params):
    try:
        ttl = max(0.0, float(os.environ.get("RESEARCH_AGENT_SEARCH_CACHE_TTL", "3600")))
    except ValueError:
        ttl = 3600.0
    key = request_key(["search-v1", source, params])
    found, papers = load_result(key, max_age=ttl) if ttl else (False, None)
    return key, ttl, found, papers


def _stable_id(*parts: str) -> str:
    raw = "||".join(p.strip() for p in parts if p and isinstance(p, str))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _arxiv_abs_to_pdf_url(url: str) -> str | None:
    if not url:
        return None
    if "arxiv.org/abs/" in url:
        return url.replace("arxiv.org/abs/", "arxiv.org/pdf/") + ".pdf"
    if "arxiv.org/pdf/" in url:
        return url if url.endswith(".pdf") else (url + ".pdf")
    return None


def _semantic_open_access_pdf_url(p: dict) -> str | None:
    oa = p.get("openAccessPdf") or {}
    url = oa.get("url") if isinstance(oa, dict) else None
    return url or None


# ──────────────────────────────────────────────
# Semantic Scholar
# ──────────────────────────────────────────────

def search_semantic_scholar(
    query: str,
    limit: int = 10,
    fields: str = "paperId,title,abstract,year,authors,citationCount,externalIds,openAccessPdf",
    min_citation: int = 0,
) -> list[dict]:
    """
    Search papers via the Semantic Scholar public API (no API key required).

    Returns a list of papers with title/abstract/year/citationCount/url.
    """
    base_url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {"query": query, "limit": min(limit, 100), "fields": fields}
    cache_key, ttl, found, cached = _search_cache("semantic_scholar", [params, min_citation])
    if found:
        return cached

    try:
        import requests
        headers = {"User-Agent": "Aporia/1.0"}
        api_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY") or os.environ.get("S2_API_KEY")
        if api_key:
            headers["x-api-key"] = api_key
        resp = requests.get(base_url, params=params, timeout=10, headers=headers)
        if resp.status_code == 429:
            time.sleep(1.5)
            resp = requests.get(base_url, params=params, timeout=10, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        
        papers = []
        for p in data.get("data", []):
            citations = p.get("citationCount", 0) or 0
            if citations < min_citation:
                continue
            ext = p.get("externalIds") or {}
            pdf_url = _semantic_open_access_pdf_url(p)
            if not pdf_url and isinstance(ext, dict) and ext.get("ArXiv"):
                pdf_url = _arxiv_abs_to_pdf_url(f"https://arxiv.org/abs/{ext['ArXiv']}")
            pid = p.get("paperId") or _stable_id("s2", query, p.get("title", ""))
            papers.append({
                "paper_id": pid,
                "title": p.get("title", ""),
                "abstract": p.get("abstract", "") or "",
                "year": p.get("year", ""),
                "authors": [a.get("name", "") for a in (p.get("authors") or [])[:3]],
                "citation_count": citations,
                "url": f"https://www.semanticscholar.org/paper/{p.get('paperId','')}",
                "pdf_url": pdf_url,
                "external_ids": ext,
                "source": "semantic_scholar",
            })
    except Exception as e:
        status = getattr(getattr(e, "response", None), "status_code", None)
        detail = ""
        r = getattr(e, "response", None)
        if r is not None:
            try:
                detail = (r.text or "")[:200]
            except Exception:
                detail = ""
        msg = f"{status} {detail}".strip() if status else str(e)
        print(f"  [WARNING] Semantic Scholar search failed: {msg}")
        return []
    if ttl:
        save_result(cache_key, papers)
    return papers


# ──────────────────────────────────────────────
# arXiv
# ──────────────────────────────────────────────

def search_arxiv_recent(
    query: str,
    limit: int = 10,
    sort_by: str = "submittedDate",  # relevance | submittedDate | lastUpdatedDate
) -> list[dict]:
    """
    Search arXiv via the public API (no API key required).
    """
    base_url = "https://export.arxiv.org/api/query"
    params = {
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": limit,
        "sortBy": sort_by,
        "sortOrder": "descending",
    }
    cache_key, ttl, found, cached = _search_cache("arxiv", params)
    if found:
        return cached

    try:
        import requests
        resp = requests.get(base_url, params=params, timeout=10, headers={"User-Agent": "Aporia/1.0"})
        resp.raise_for_status()
        content = resp.content

        root = ET.fromstring(content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        papers = []

        for entry in root.findall("atom:entry", ns):
            title = entry.findtext("atom:title", default="", namespaces=ns).strip().replace("\n", " ")
            abstract = entry.findtext("atom:summary", default="", namespaces=ns).strip().replace("\n", " ")
            published = entry.findtext("atom:published", default="", namespaces=ns)[:4]  # year
            paper_id = entry.findtext("atom:id", default="", namespaces=ns)
            pdf_url = _arxiv_abs_to_pdf_url(paper_id)
            arxiv_id = ""
            if "arxiv.org/abs/" in paper_id:
                arxiv_id = paper_id.split("arxiv.org/abs/")[-1].strip()

            authors = [
                a.findtext("atom:name", default="", namespaces=ns)
                for a in entry.findall("atom:author", ns)
            ]

            papers.append({
                "paper_id": arxiv_id or _stable_id("arxiv", query, title),
                "arxiv_id": arxiv_id,
                "title": title,
                "abstract": abstract,
                "year": published,
                "authors": authors[:3],
                "url": paper_id,
                "pdf_url": pdf_url,
                "source": "arxiv",
            })

    except Exception as e:
        print(f"  [WARNING] arXiv search failed: {e}")
        return []
    if ttl:
        save_result(cache_key, papers)
    return papers


# ──────────────────────────────────────────────
# Quick scan
# ──────────────────────────────────────────────

def quick_literature_scan(topic: str, top_k: int = 20) -> list[dict]:
    """
    Quick literature scan: Semantic Scholar + arXiv, merged and de-duplicated.
    """
    classic = search_semantic_scholar(topic, limit=top_k // 2, min_citation=10)
    recent = search_arxiv_recent(topic, limit=top_k // 2)

    seen, merged = set(), []
    for p in classic + recent:
        t = p.get("title", "").lower()
        if t and t not in seen:
            seen.add(t)
            merged.append(p)

    merged.sort(key=lambda x: x.get("citation_count", 0), reverse=True)
    return merged[:top_k]


def _valid_pdf(content: bytes) -> bool:
    if not content.startswith(b"%PDF-") or b"%%EOF" not in content[-1024:]:
        return False
    try:
        from pypdf import PdfReader
        return len(PdfReader(io.BytesIO(content)).pages) > 0
    except Exception:
        return False


def download_pdf(pdf_url: str, cache_dir: str | Path, filename_hint: str | None = None) -> Path | None:
    if not pdf_url:
        return None
    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)
    hint = re.sub(r"[^A-Za-z0-9._-]", "_", filename_hint or "paper")[:80].strip(".") or "paper"
    name = f"{hint}-{hashlib.sha256(pdf_url.encode('utf-8')).hexdigest()[:16]}.pdf"
    out = cache_path / name

    try:
        if out.exists() and _valid_pdf(out.read_bytes()):
            return out
        import requests
        r = requests.get(pdf_url, timeout=30, headers={"User-Agent": "Aporia/1.0"})
        if r.status_code != 200 or not _valid_pdf(r.content):
            return None
        fd, tmp_name = tempfile.mkstemp(prefix=f".{out.name}.", dir=str(cache_path))
        try:
            with os.fdopen(fd, "wb") as tmp:
                tmp.write(r.content)
                tmp.flush()
                os.fsync(tmp.fileno())
            os.replace(tmp_name, out)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
        return out
    except Exception:
        return None


def extract_pdf_pages(pdf_path: str | Path, max_pages: int | None = 6, max_chars: int = 12000) -> list[dict]:
    try:
        from pypdf import PdfReader
    except Exception:
        return []

    path = Path(pdf_path)
    if not path.exists():
        return []

    try:
        reader = PdfReader(str(path))
        if max_pages is None or (isinstance(max_pages, int) and max_pages <= 0):
            pages = reader.pages
        else:
            pages = reader.pages[:max_pages]
        chunks = []
        total = 0
        for page_number, p in enumerate(pages, 1):
            txt = (p.extract_text() or "").strip()
            if not txt:
                continue
            if total + len(txt) > max_chars:
                txt = txt[: max(0, max_chars - total)]
            chunks.append({"page": page_number, "text": txt})
            total += len(txt)
            if total >= max_chars:
                break
        return chunks
    except Exception:
        return []


def extract_text_from_pdf(pdf_path: str | Path, max_pages: int | None = 6, max_chars: int = 12000) -> str:
    return "\n\n".join(p["text"] for p in extract_pdf_pages(pdf_path, max_pages, max_chars))


def fetch_fulltext_excerpt(
    paper: dict,
    cache_root: str | Path | None = None,
    max_pages: int | None = None,
    max_chars: int | None = None,
) -> dict:
    cache_root = Path(cache_root or os.environ.get("RESEARCH_AGENT_CACHE_DIR", ".research_agent_cache"))
    pdf_dir = cache_root / "pdfs"
    pdf_url = paper.get("pdf_url") or _arxiv_abs_to_pdf_url(paper.get("url", ""))
    pdf_path = download_pdf(
        pdf_url,
        pdf_dir,
        filename_hint=(paper.get("paper_id") or paper.get("arxiv_id") or _stable_id(paper.get("title", ""))),
    )
    if not pdf_path:
        return {"ok": False, "pdf_url": pdf_url, "pdf_path": None, "text_excerpt": ""}
    try:
        mp = int(os.environ.get("RESEARCH_AGENT_PDF_MAX_PAGES", "12")) if max_pages is None else max_pages
    except Exception:
        mp = 12 if max_pages is None else max_pages
    try:
        mc = int(os.environ.get("RESEARCH_AGENT_PDF_MAX_CHARS", "30000")) if max_chars is None else max_chars
    except Exception:
        mc = 30000 if max_chars is None else max_chars
    pages = extract_pdf_pages(pdf_path, max_pages=mp, max_chars=mc)
    excerpt = "\n\n".join(p["text"] for p in pages)
    return {"ok": bool(excerpt), "pdf_url": pdf_url, "pdf_path": str(pdf_path), "text_excerpt": excerpt, "pages": pages}


def load_paper_library(cache_root: str | Path | None = None) -> dict:
    cache_root = Path(cache_root or os.environ.get("RESEARCH_AGENT_CACHE_DIR", ".research_agent_cache"))
    path = cache_root / "paper_library.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Invalid paper library: {path}. Expected a JSON object; restore the file before retrying.")
    return data


def save_paper_library(library: dict, cache_root: str | Path | None = None) -> None:
    cache_root = Path(cache_root or os.environ.get("RESEARCH_AGENT_CACHE_DIR", ".research_agent_cache"))
    cache_root.mkdir(parents=True, exist_ok=True)
    path = cache_root / "paper_library.json"
    with named_lock("paper-library:" + str(path.resolve()), blocking=True):
        merged = load_paper_library(cache_root)
        for pid, entry in library.items():
            previous = merged.get(pid) or {}
            # A stale session must not erase another session's downloaded text.
            merged[pid] = {**previous, **{key: value for key, value in entry.items()
                                        if value or key not in previous}}
        atomic_write_text(path, json.dumps(merged, ensure_ascii=False, indent=2))
