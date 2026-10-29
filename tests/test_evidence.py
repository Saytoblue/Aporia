"""Evidence location and honest claim classification without network calls."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from tools.literature_tools import extract_pdf_pages, fetch_fulltext_excerpt, load_paper_library, save_paper_library
from utils.evidence import build_catalog, attach_evidence


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        env = patch.dict(os.environ, {"RESEARCH_AGENT_CACHE_DIR": self.temp.name})
        env.start()
        self.addCleanup(env.stop)

    def test_page_numbers_survive_blank_pages_and_text_budget(self):
        path = self.root / "paper.pdf"
        path.touch()
        reader = SimpleNamespace(pages=[Mock(extract_text=lambda: ""), Mock(extract_text=lambda: "actual text on page two")])
        with patch("pypdf.PdfReader", return_value=reader), patch("tools.literature_tools.download_pdf", return_value=path):
            result = fetch_fulltext_excerpt({"paper_id": "paper", "pdf_url": "https://example.test/paper.pdf"}, max_pages=2, max_chars=11)
        self.assertEqual(result["pages"], [{"page": 2, "text": "actual text"}])
        self.assertEqual(result["text_excerpt"], "actual text")

    def test_catalog_is_session_scoped_and_legacy_text_has_no_invented_page(self):
        state = {"raw_papers": [{"paper_id": "p1", "title": "A", "abstract": "Abstract."}, {"paper_id": "p2", "title": "B"}],
                 "paper_library": {"p1": {"fulltext_pages": [{"page": 3, "text": "Exact quote."}]},
                                   "p2": {"fulltext_excerpt": "Old text."},
                                   "unrelated": {"fulltext_excerpt": "Do not use."}}}
        catalog = build_catalog(state)
        self.assertEqual(catalog, build_catalog(state))
        self.assertFalse(any(e["paper_id"] == "unrelated" for e in catalog))
        located = next(e for e in catalog if e["source_type"] == "fulltext")
        self.assertEqual((located["page"], located["quote"]), (3, "Exact quote."))
        old = next(e for e in catalog if e["paper_id"] == "p2")
        self.assertIsNone(old["page"])
        self.assertEqual(old["source_type"], "fulltext_unlocated")

    def test_claims_link_only_known_sources_and_distinguish_hypotheses(self):
        catalog = build_catalog({"raw_papers": [{"paper_id": "p", "abstract": "Source."}]})
        eid = catalog[0]["evidence_id"]
        claims = [{"claim": "Literature says X.", "kind": "literature_claim", "evidence_ids": [eid]},
                  {"claim": "We expect Y.", "kind": "hypothesis", "evidence_ids": []},
                  {"claim": "Unsupported Z.", "kind": "literature_claim", "evidence_ids": ["E-invented"]}]
        content = "Literature says X. We expect Y. Unsupported Z.\n```json\n" + json.dumps({"evidence_claims": claims}) + "\n```"
        result = attach_evidence({}, content, catalog)
        self.assertEqual([c["status"] for c in result["claim_evidence"]], ["linked", "hypothesis", "unverified"])
        self.assertEqual(result["claim_evidence"][2]["evidence_ids"], [])
        self.assertTrue(result["evidence_warnings"])
        self.assertNotIn("evidence_claims", result["research_proposal"])
        missing = attach_evidence({}, "No provenance", [])
        self.assertGreaterEqual(len(missing["evidence_warnings"]), 2)

    def test_library_merges_parallel_updates_and_reports_storage_failures(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(save_paper_library, [{"a": {"title": "A", "fulltext_excerpt": "text"}}, {"b": {"title": "B"}}]))
        save_paper_library({"a": {"title": "A", "fulltext_excerpt": ""}})
        library = load_paper_library()
        self.assertEqual(set(library), {"a", "b"})
        self.assertEqual(library["a"]["fulltext_excerpt"], "text")
        with patch("tools.literature_tools.atomic_write_text", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(OSError, "disk full"):
                save_paper_library({"c": {"title": "C"}})
        self.assertEqual(load_paper_library(), library)
        (self.root / "paper_library.json").write_text("broken JSON")
        with self.assertRaises(json.JSONDecodeError):
            load_paper_library()
        with self.assertRaises(json.JSONDecodeError):
            save_paper_library({})


if __name__ == "__main__":
    unittest.main()
