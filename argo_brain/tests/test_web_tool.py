"""Tests for the hardened WebAccessTool."""

from __future__ import annotations

import unittest
from unittest import mock

from argo_brain.security import TrustLevel
from argo_brain.tools.base import ToolExecutionError, ToolRequest
from argo_brain.tools.web import WebAccessTool


class _FakeIngestionManager:
    def __init__(self) -> None:
        self.calls = []

    def ingest_document(self, doc, session_mode):
        self.calls.append((doc, session_mode))


class WebToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ingestion = _FakeIngestionManager()
        self.tool = WebAccessTool(ingestion_manager=self.ingestion)

    def test_invalid_scheme_rejected(self) -> None:
        with self.assertRaises(ToolExecutionError):
            self.tool._validate_url("ftp://example.com")

    @mock.patch("argo_brain.tools.web.trafilatura.extract", return_value="clean content")
    @mock.patch("argo_brain.tools.web.requests.get")
    def test_trust_metadata_set_on_result(self, mock_get, mock_extract) -> None:
        class _Resp:
            status_code = 200
            text = "<html>content</html>"
            url = "http://example.com/page"

            def raise_for_status(self) -> None:
                return None

        mock_get.return_value = _Resp()
        request = ToolRequest(session_id="s1", query="http://example.com/page")
        result = self.tool.run(request)
        self.assertEqual(result.metadata.get("trust_level"), TrustLevel.WEB_UNTRUSTED.value)
        self.assertTrue(self.ingestion.calls)
        doc, _ = self.ingestion.calls[-1]
        self.assertEqual(doc.metadata.get("trust_level"), TrustLevel.WEB_UNTRUSTED.value)


if __name__ == "__main__":
    unittest.main()
