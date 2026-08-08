"""Tests for memory.search_utils module."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestSearchUtils:
    """Tests for search utilities."""

    @patch("memory.search_utils._get_embed_model")
    def test_embed_documents(self, mock_get_model):
        from memory.search_utils import _embed_documents

        mock_model = MagicMock()
        mock_model.encode.return_value.tolist.return_value = [[0.1, 0.2, 0.3]]
        mock_get_model.return_value = mock_model

        result = _embed_documents(["test query"])

        assert len(result) == 1
        assert result[0] == [0.1, 0.2, 0.3]
        mock_model.encode.assert_called_once_with(["test query"], normalize_embeddings=True)

    def test_search_table_with_project_filter(self):
        from memory.search_utils import _search_table

        mock_table = MagicMock()
        mock_query = MagicMock()
        mock_table.search.return_value = mock_query
        mock_query.where.return_value = mock_query
        mock_query.limit.return_value = mock_query

        mock_df = MagicMock()
        mock_query.to_pandas.return_value = mock_df

        with patch("memory.search_utils._embed_documents", return_value=[[0.1] * 384]):
            result = _search_table(mock_table, "test query", limit=5, project_id="my-project")

        mock_table.search.assert_called_once()
        mock_query.where.assert_called_once_with("project_id = 'my-project'")
        mock_query.limit.assert_called_once_with(5)

    def test_search_table_without_project_filter(self):
        from memory.search_utils import _search_table

        mock_table = MagicMock()
        mock_query = MagicMock()
        mock_table.search.return_value = mock_query
        mock_query.limit.return_value = mock_query

        mock_df = MagicMock()
        mock_query.to_pandas.return_value = mock_df

        with patch("memory.search_utils._embed_documents", return_value=[[0.1] * 384]):
            result = _search_table(mock_table, "test query", limit=10, project_id="")

        mock_table.search.assert_called_once()
        mock_query.where.assert_not_called()
        mock_query.limit.assert_called_once_with(10)
