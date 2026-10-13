"""Tests for InfoQuest client and tools."""

import json
import logging
from unittest.mock import MagicMock, patch

from deerflow.community.infoquest import tools
from deerflow.community.infoquest.infoquest_client import InfoQuestClient


class TestInfoQuestClient:
    def test_infoquest_client_initialization(self):
        """Test InfoQuestClient initialization with different parameters."""
        # Test with default parameters
        client = InfoQuestClient()
        assert client.fetch_time == -1
        assert client.fetch_timeout == -1
        assert client.fetch_navigation_timeout == -1
        assert client.search_time_range == -1

        # Test with custom parameters
        client = InfoQuestClient(fetch_time=10, fetch_timeout=30, fetch_navigation_timeout=60, search_time_range=24)
        assert client.fetch_time == 10
        assert client.fetch_timeout == 30
        assert client.fetch_navigation_timeout == 60
        assert client.search_time_range == 24

    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_fetch_success(self, mock_post):
        """Test successful fetch operation."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = json.dumps({"reader_result": "<html><body>Test content</body></html>"})
        mock_post.return_value = mock_response

        client = InfoQuestClient()
        result = client.fetch("https://example.com")

        assert result == "<html><body>Test content</body></html>"
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "https://reader.infoquest.bytepluses.com"
        assert kwargs["json"]["url"] == "https://example.com"
        assert kwargs["json"]["format"] == "HTML"

    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_fetch_non_200_status(self, mock_post):
        """Test fetch operation with non-200 status code."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_post.return_value = mock_response

        client = InfoQuestClient()
        result = client.fetch("https://example.com")

        assert result == "Error: fetch API returned status 404: Not Found"

    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_fetch_empty_response(self, mock_post):
        """Test fetch operation with empty response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = ""
        mock_post.return_value = mock_response

        client = InfoQuestClient()
        result = client.fetch("https://example.com")

        assert result == "Error: no result found"

    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_web_search_raw_results_success(self, mock_post):
        """Test successful web_search_raw_results operation."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"search_result": {"results": [{"content": {"results": {"organic": [{"title": "Test Result", "desc": "Test description", "url": "https://example.com"}]}}}], "images_results": []}}
        mock_post.return_value = mock_response

        client = InfoQuestClient()
        result = client.web_search_raw_results("test query", "")

        assert "search_result" in result
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "https://search.infoquest.bytepluses.com"
        assert kwargs["json"]["query"] == "test query"

    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_web_search_success(self, mock_post):
        """Test successful web_search operation."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"search_result": {"results": [{"content": {"results": {"organic": [{"title": "Test Result", "desc": "Test description", "url": "https://example.com"}]}}}], "images_results": []}}
        mock_post.return_value = mock_response

        client = InfoQuestClient()
        result = client.web_search("test query")

        # Check if result is a valid JSON string with expected content
        result_data = json.loads(result)
        assert len(result_data) == 1
        assert result_data[0]["title"] == "Test Result"
        assert result_data[0]["url"] == "https://example.com"

    def test_clean_results(self):
        """Test clean_results method with sample raw results."""
        raw_results = [
            {
                "content": {
                    "results": {
                        "organic": [{"title": "Test Page", "desc": "Page description", "url": "https://example.com/page1"}],
                        "top_stories": {"items": [{"title": "Test News", "source": "Test Source", "time_frame": "2 hours ago", "url": "https://example.com/news1"}]},
                    }
                }
            }
        ]

        cleaned = InfoQuestClient.clean_results(raw_results)

        assert len(cleaned) == 2
        assert cleaned[0]["type"] == "page"
        assert cleaned[0]["title"] == "Test Page"
        assert cleaned[1]["type"] == "news"
        assert cleaned[1]["title"] == "Test News"

    @patch("deerflow.community.infoquest.tools._get_infoquest_client")
    def test_web_search_tool(self, mock_get_client):
        """Test web_search_tool function."""
        mock_client = MagicMock()
        mock_client.web_search.return_value = json.dumps([])
        mock_get_client.return_value = mock_client

        result = tools.web_search_tool.run("test query")

        assert result == json.dumps([])
        mock_get_client.assert_called_once()
        mock_client.web_search.assert_called_once_with("test query")

    @patch("deerflow.community.infoquest.tools._get_infoquest_client")
    def test_web_fetch_tool(self, mock_get_client):
        """Test web_fetch_tool function."""
        mock_client = MagicMock()
        mock_client.fetch.return_value = "<html><body>Test content</body></html>"
        mock_get_client.return_value = mock_client

        result = tools.web_fetch_tool.run("https://example.com")

        assert result == "# Untitled\n\nTest content"
        mock_get_client.assert_called_once()
        mock_client.fetch.assert_called_once_with("https://example.com")

    @patch("deerflow.community.infoquest.tools.get_app_config")
    def test_get_infoquest_client(self, mock_get_app_config):
        """Test _get_infoquest_client function with config."""
        mock_config = MagicMock()
        # Add image_search config to the side_effect
        mock_config.get_tool_config.side_effect = [
            MagicMock(model_extra={"search_time_range": 24}),  # web_search config
            MagicMock(model_extra={"fetch_time": 10, "timeout": 30, "navigation_timeout": 60}),  # web_fetch config
            MagicMock(model_extra={"image_search_time_range": 7, "image_size": "l"}),  # image_search config
        ]
        mock_get_app_config.return_value = mock_config

        client = tools._get_infoquest_client()

        assert client.search_time_range == 24
        assert client.fetch_time == 10
        assert client.fetch_timeout == 30
        assert client.fetch_navigation_timeout == 60
        assert client.image_search_time_range == 7
        assert client.image_size == "l"

    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_web_search_api_error(self, mock_post):
        """Test web_search operation with API error."""
        mock_post.side_effect = Exception("Connection error")

        client = InfoQuestClient()
        result = client.web_search("test query")

        assert "Error" in result

    def test_clean_results_with_image_search(self):
        """Test clean_results_with_image_search method with sample raw results."""
        raw_results = [{"content": {"results": {"images_results": [{"original": "https://example.com/image1.jpg", "title": "Test Image 1", "url": "https://example.com/page1"}]}}}]
        cleaned = InfoQuestClient.clean_results_with_image_search(raw_results)

        assert len(cleaned) == 1
        assert cleaned[0]["image_url"] == "https://example.com/image1.jpg"
        assert cleaned[0]["title"] == "Test Image 1"

    def test_clean_results_with_image_search_empty(self):
        """Test clean_results_with_image_search method with empty results."""
        raw_results = [{"content": {"results": {"images_results": []}}}]
        cleaned = InfoQuestClient.clean_results_with_image_search(raw_results)

        assert len(cleaned) == 0

    def test_clean_results_with_image_search_no_images(self):
        """Test clean_results_with_image_search method with no images_results field."""
        raw_results = [{"content": {"results": {"organic": [{"title": "Test Page"}]}}}]
        cleaned = InfoQuestClient.clean_results_with_image_search(raw_results)

        assert len(cleaned) == 0


class TestImageSearch:
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_image_search_raw_results_success(self, mock_post):
        """Test successful image_search_raw_results operation."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"search_result": {"results": [{"content": {"results": {"images_results": [{"original": "https://example.com/image1.jpg", "title": "Test Image", "url": "https://example.com/page1"}]}}}]}}
        mock_post.return_value = mock_response

        client = InfoQuestClient()
        result = client.image_search_raw_results("test query")

        assert "search_result" in result
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "https://search.infoquest.bytepluses.com"
        assert kwargs["json"]["query"] == "test query"

    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_image_search_raw_results_with_parameters(self, mock_post):
        """Test image_search_raw_results with all parameters."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"search_result": {"results": [{"content": {"results": {"images_results": [{"original": "https://example.com/image1.jpg"}]}}}]}}
        mock_post.return_value = mock_response

        client = InfoQuestClient(image_search_time_range=30, image_size="l")
        client.image_search_raw_results(query="cat", site="unsplash.com", output_format="JSON")

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert kwargs["json"]["query"] == "cat"
        assert kwargs["json"]["time_range"] == 30
        assert kwargs["json"]["site"] == "unsplash.com"
        assert kwargs["json"]["image_size"] == "l"
        assert kwargs["json"]["format"] == "JSON"

    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_image_search_raw_results_invalid_time_range(self, mock_post):
        """Test image_search_raw_results with invalid time_range parameter."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_response.json.return_value = {"search_result": {"results": [{"content": {"results": {"images_results": []}}}]}}
        mock_post.return_value = mock_response

        # Create client with invalid time_range (should be ignored)
        client = InfoQuestClient(image_search_time_range=400, image_size="x")
        client.image_search_raw_results(
            query="test",
            site="",
        )

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert kwargs["json"]["query"] == "test"
        assert "time_range" not in kwargs["json"]
        assert "image_size" not in kwargs["json"]

    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_image_search_success(self, mock_post):
        """Test successful image_search operation."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_response.json.return_value = {"search_result": {"results": [{"content": {"results": {"images_results": [{"original": "https://example.com/image1.jpg", "title": "Test Image", "url": "https://example.com/page1"}]}}}]}}
        mock_post.return_value = mock_response

        client = InfoQuestClient()
        result = client.image_search("cat")

        # Check if result is a valid JSON string with expected content
        result_data = json.loads(result)

        assert len(result_data) == 1

        assert result_data[0]["image_url"] == "https://example.com/image1.jpg"

        assert result_data[0]["title"] == "Test Image"

    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_image_search_with_all_parameters(self, mock_post):
        """Test image_search with all optional parameters."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_response.json.return_value = {"search_result": {"results": [{"content": {"results": {"images_results": [{"original": "https://example.com/image1.jpg"}]}}}]}}
        mock_post.return_value = mock_response

        # Create client with image search parameters
        client = InfoQuestClient(image_search_time_range=7, image_size="m")
        client.image_search(query="dog", site="flickr.com", output_format="JSON")

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert kwargs["json"]["query"] == "dog"
        assert kwargs["json"]["time_range"] == 7
        assert kwargs["json"]["site"] == "flickr.com"
        assert kwargs["json"]["image_size"] == "m"

    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_image_search_api_error(self, mock_post):
        """Test image_search operation with API error."""
        mock_post.side_effect = Exception("Connection error")

        client = InfoQuestClient()
        result = client.image_search("test query")

        assert "Error" in result

    @patch("deerflow.community.infoquest.tools._get_infoquest_client")
    def test_image_search_tool(self, mock_get_client):
        """Test image_search_tool function."""
        mock_client = MagicMock()
        mock_client.image_search.return_value = json.dumps([{"image_url": "https://example.com/image1.jpg"}])
        mock_get_client.return_value = mock_client

        result = tools.image_search_tool.run({"query": "test query"})

        # Check if result is a valid JSON string
        result_data = json.loads(result)
        assert len(result_data) == 1
        assert result_data[0]["image_url"] == "https://example.com/image1.jpg"
        mock_get_client.assert_called_once()
        mock_client.image_search.assert_called_once_with("test query")

    # In /Users/bytedance/python/deer-flowv2/deer-flow/backend/tests/test_infoquest_client.py

    @patch("deerflow.community.infoquest.tools._get_infoquest_client")
    def test_image_search_tool_with_parameters(self, mock_get_client):
        """Test image_search_tool function with all parameters (extra parameters will be ignored)."""
        mock_client = MagicMock()
        mock_client.image_search.return_value = json.dumps([{"image_url": "https://example.com/image1.jpg"}])
        mock_get_client.return_value = mock_client

        # Pass all parameters as a dictionary (extra parameters will be ignored)
        tools.image_search_tool.run({"query": "sunset", "time_range": 30, "site": "unsplash.com", "image_size": "l"})

        mock_get_client.assert_called_once()
        # image_search_tool only passes query to client.image_search
        # site parameter is empty string by default
        mock_client.image_search.assert_called_once_with("sunset")

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_success_path(self, mock_post):
        search_data = {"search_result": {"results": [{"content": {"results": {"images_results": [{"original": "https://img.jpg", "title": "Cat"}]}}}]}}
        mock_response = MagicMock()
        mock_response.json.return_value = search_data
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = InfoQuestClient()
        result = client.image_search("cats")
        parsed = json.loads(result)
        assert len(parsed) == 1
        assert parsed[0]["image_url"] == "https://img.jpg"

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_content_fallback_returns_error(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"content": "bad format"}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = InfoQuestClient()
        result = client.image_search("cats")
        assert result.startswith("Error:")
        assert "wrong format" in result

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_neither_field_returns_raw_json(self, mock_post):
        raw = {"other": "data"}
        mock_response = MagicMock()
        mock_response.json.return_value = raw
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = InfoQuestClient()
        result = client.image_search("cats")
        parsed = json.loads(result)
        assert parsed == raw

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_exception_returns_error(self, mock_post):
        mock_post.side_effect = RuntimeError("connection refused")

        client = InfoQuestClient()
        result = client.image_search("cats")
        assert result.startswith("Error:")
        assert "connection refused" in result

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_debug_logging_truncated_query(self, mock_post, caplog):
        mock_response = MagicMock()
        mock_response.json.return_value = {"search_result": {"results": [{"content": {"results": {}}}]}}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = InfoQuestClient()
        long_query = "x" * 100
        with caplog.at_level(logging.DEBUG, logger="deerflow.community.infoquest.infoquest_client"):
            client.image_search(long_query)
        assert "query_truncated=" in caplog.text

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_debug_logging_short_query(self, mock_post, caplog):
        mock_response = MagicMock()
        mock_response.json.return_value = {"search_result": {"results": [{"content": {"results": {}}}]}}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = InfoQuestClient()
        with caplog.at_level(logging.DEBUG, logger="deerflow.community.infoquest.infoquest_client"):
            client.image_search("short")
        assert "query_truncated=short" in caplog.text

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_with_site(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"search_result": {"results": [{"content": {"results": {}}}]}}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = InfoQuestClient()
        client.image_search("cats", site="example.com")

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_debug_logging_with_filters(self, mock_post, caplog):
        """Debug logging path with site and valid time_range."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"search_result": {"results": [{"content": {"results": {}}}]}}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = InfoQuestClient(image_search_time_range=14, image_size="l")
        with caplog.at_level(logging.DEBUG, logger="deerflow.community.infoquest.infoquest_client"):
            client.image_search("test", site="example.com")
        assert "has_site_filter=True" in caplog.text
        assert "image_search_time_range=14" in caplog.text

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_debug_logging_default_time_range(self, mock_post, caplog):
        """Debug logging with default (out of range) time_range shows 'default'."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"search_result": {"results": [{"content": {"results": {}}}]}}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = InfoQuestClient(image_search_time_range=-1)
        with caplog.at_level(logging.DEBUG, logger="deerflow.community.infoquest.infoquest_client"):
            client.image_search("test")
        assert "image_search_time_range=default" in caplog.text

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_debug_logging_out_of_range_time(self, mock_post, caplog):
        """Debug logging with time_range > 365 shows 'default'."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"search_result": {"results": [{"content": {"results": {}}}]}}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = InfoQuestClient(image_search_time_range=500)
        with caplog.at_level(logging.DEBUG, logger="deerflow.community.infoquest.infoquest_client"):
            client.image_search("test")
        assert "image_search_time_range=default" in caplog.text

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_debug_results_count(self, mock_post, caplog):
        """Debug logging reports results_count for image search."""
        search_data = {
            "search_result": {
                "results": [
                    {
                        "content": {
                            "results": {
                                "images_results": [
                                    {"original": "https://img.jpg"},
                                ]
                            }
                        }
                    }
                ]
            }
        }
        mock_response = MagicMock()
        mock_response.json.return_value = search_data
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = InfoQuestClient()
        with caplog.at_level(logging.DEBUG, logger="deerflow.community.infoquest.infoquest_client"):
            client.image_search("q")
        assert "results_count=" in caplog.text


# --- merged from test_infoquest_client.py (subdir-only tests; root copy is the dedup base) ---
def _make_raw_search_results(
    organic: list | None = None,
    top_stories: dict | None = None,
    images_results: list | None = None,
) -> list[dict]:
    """Build the nested structure expected by clean_results / clean_results_with_image_search."""
    results: dict = {}
    if organic is not None:
        results["organic"] = organic
    if top_stories is not None:
        results["top_stories"] = top_stories
    if images_results is not None:
        results["images_results"] = images_results

    return [{"content": {"results": results}}]


class TestInit:
    """Tests for InfoQuestClient.__init__."""

    @patch.dict("os.environ", {}, clear=True)
    def test_defaults(self):
        client = InfoQuestClient()
        assert client.fetch_time == -1
        assert client.fetch_timeout == -1
        assert client.fetch_navigation_timeout == -1
        assert client.search_time_range == -1
        assert client.image_search_time_range == -1
        assert client.image_size == "i"
        assert client.api_key_set is False

    @patch.dict("os.environ", {"INFOQUEST_API_KEY": "secret"}, clear=True)
    def test_api_key_set(self):
        client = InfoQuestClient()
        assert client.api_key_set is True

    def test_custom_params(self):
        client = InfoQuestClient(
            fetch_time=10,
            fetch_timeout=20,
            fetch_navigation_timeout=30,
            search_time_range=7,
            image_search_time_range=14,
            image_size="l",
        )
        assert client.fetch_time == 10
        assert client.fetch_timeout == 20
        assert client.fetch_navigation_timeout == 30
        assert client.search_time_range == 7
        assert client.image_search_time_range == 14
        assert client.image_size == "l"

    @patch.dict("os.environ", {"INFOQUEST_API_KEY": "key123"}, clear=True)
    def test_debug_logging_branch(self, caplog):
        """When DEBUG is enabled the detailed config block is logged."""
        with caplog.at_level(logging.DEBUG, logger="deerflow.community.infoquest.infoquest_client"):
            InfoQuestClient(
                fetch_time=5,
                fetch_timeout=10,
                fetch_navigation_timeout=15,
                search_time_range=3,
                image_search_time_range=7,
                image_size="m",
            )
        assert "Fetch time: 5" in caplog.text
        assert "API Key: " in caplog.text

    @patch.dict("os.environ", {}, clear=True)
    def test_debug_logging_branch_no_api_key(self, caplog):
        """Debug logging with no API key shows 'Not set'."""
        with caplog.at_level(logging.DEBUG, logger="deerflow.community.infoquest.infoquest_client"):
            InfoQuestClient(image_size="m")
        assert "Not set" in caplog.text


class TestPrepareHeaders:
    """Tests for InfoQuestClient._prepare_headers (static)."""

    @patch.dict("os.environ", {"INFOQUEST_API_KEY": "my-key"}, clear=True)
    def test_with_api_key(self):
        headers = InfoQuestClient._prepare_headers()
        assert headers["Content-Type"] == "application/json"
        assert headers["Authorization"] == "Bearer my-key"

    @patch.dict("os.environ", {}, clear=True)
    def test_without_api_key(self):
        headers = InfoQuestClient._prepare_headers()
        assert headers["Content-Type"] == "application/json"
        assert "Authorization" not in headers


class TestPrepareCrawlRequestData:
    """Tests for InfoQuestClient._prepare_crawl_request_data."""

    @patch.dict("os.environ", {}, clear=True)
    def test_basic_html_format(self):
        client = InfoQuestClient()
        data = client._prepare_crawl_request_data("https://example.com", "html")
        assert data == {"url": "https://example.com", "format": "HTML"}

    @patch.dict("os.environ", {}, clear=True)
    def test_non_html_format_preserved(self):
        client = InfoQuestClient()
        data = client._prepare_crawl_request_data("https://example.com", "markdown")
        assert data["format"] == "markdown"

    @patch.dict("os.environ", {}, clear=True)
    def test_uppercase_html_normalized(self):
        client = InfoQuestClient()
        data = client._prepare_crawl_request_data("https://example.com", "HTML")
        assert data["format"] == "HTML"

    @patch.dict("os.environ", {}, clear=True)
    def test_timeout_params_included_when_positive(self):
        client = InfoQuestClient(
            fetch_time=5,
            fetch_timeout=10,
            fetch_navigation_timeout=15,
        )
        data = client._prepare_crawl_request_data("https://example.com", "html")
        assert data["fetch_time"] == 5
        assert data["timeout"] == 10
        assert data["navi_timeout"] == 15

    @patch.dict("os.environ", {}, clear=True)
    def test_timeout_params_excluded_when_negative(self):
        client = InfoQuestClient(
            fetch_time=-1,
            fetch_timeout=-1,
            fetch_navigation_timeout=-1,
        )
        data = client._prepare_crawl_request_data("https://example.com", "html")
        assert "fetch_time" not in data
        assert "timeout" not in data
        assert "navi_timeout" not in data

    @patch.dict("os.environ", {}, clear=True)
    def test_mixed_timeout_params(self):
        """Only positive values should be added."""
        client = InfoQuestClient(fetch_time=3, fetch_timeout=-1, fetch_navigation_timeout=0)
        data = client._prepare_crawl_request_data("https://example.com", "html")
        assert data["fetch_time"] == 3
        assert "timeout" not in data
        assert "navi_timeout" not in data

    @patch.dict("os.environ", {}, clear=True)
    def test_empty_return_format(self):
        client = InfoQuestClient()
        data = client._prepare_crawl_request_data("https://example.com", "")
        # empty string is falsy so the else branch runs
        assert data["format"] == ""


class TestFetch:
    """Tests for InfoQuestClient.fetch."""

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_success_reader_result(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = json.dumps({"reader_result": "<html>OK</html>"})
        mock_post.return_value = mock_response

        client = InfoQuestClient()
        result = client.fetch("https://example.com")
        assert result == "<html>OK</html>"
        mock_post.assert_called_once()

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_success_content_fallback(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = json.dumps({"content": "page content"})
        mock_post.return_value = mock_response

        client = InfoQuestClient()
        result = client.fetch("https://example.com")
        assert result == "page content"

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_success_neither_field_returns_raw(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        raw = json.dumps({"other": "data"})
        mock_response.text = raw
        mock_post.return_value = mock_response

        client = InfoQuestClient()
        result = client.fetch("https://example.com")
        assert result == raw

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_non_200_status(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        client = InfoQuestClient()
        result = client.fetch("https://example.com")
        assert result.startswith("Error:")
        assert "status 500" in result

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_empty_response_text(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = ""
        mock_post.return_value = mock_response

        client = InfoQuestClient()
        result = client.fetch("https://example.com")
        assert "Error:" in result
        assert "no result found" in result

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_whitespace_only_response(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "   \n  "
        mock_post.return_value = mock_response

        client = InfoQuestClient()
        result = client.fetch("https://example.com")
        assert "Error:" in result
        assert "no result found" in result

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_json_decode_error_returns_raw_text(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "not-json"
        mock_post.return_value = mock_response

        client = InfoQuestClient()
        result = client.fetch("https://example.com")
        assert result == "not-json"

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_exception_returns_error(self, mock_post):
        mock_post.side_effect = ConnectionError("timeout")

        client = InfoQuestClient()
        result = client.fetch("https://example.com")
        assert result.startswith("Error:")
        assert "timeout" in result

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_debug_logging_truncated_url(self, mock_post, caplog):
        """Long URLs are truncated in debug logs."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = json.dumps({"reader_result": "ok"})
        mock_post.return_value = mock_response

        client = InfoQuestClient()
        long_url = "https://example.com/" + "a" * 100
        with caplog.at_level(logging.DEBUG, logger="deerflow.community.infoquest.infoquest_client"):
            client.fetch(long_url)
        assert "url_truncated=" in caplog.text

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_debug_logging_short_url(self, mock_post, caplog):
        """Short URLs are not truncated."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = json.dumps({"reader_result": "ok"})
        mock_post.return_value = mock_response

        client = InfoQuestClient()
        with caplog.at_level(logging.DEBUG, logger="deerflow.community.infoquest.infoquest_client"):
            client.fetch("https://ex.com")
        assert "url_truncated=https://ex.com" in caplog.text

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_fetch_with_custom_timeouts(self, mock_post):
        """Custom positive timeouts are passed through."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = json.dumps({"reader_result": "ok"})
        mock_post.return_value = mock_response

        client = InfoQuestClient(fetch_time=5, fetch_timeout=10, fetch_navigation_timeout=15)
        client.fetch("https://example.com")
        call_kwargs = mock_post.call_args
        data = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert data["fetch_time"] == 5
        assert data["timeout"] == 10
        assert data["navi_timeout"] == 15

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_fetch_debug_logging_with_timeouts(self, mock_post, caplog):
        """Debug logging path with positive timeout filters."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = json.dumps({"reader_result": "ok"})
        mock_post.return_value = mock_response

        client = InfoQuestClient(
            fetch_time=5,
            fetch_timeout=10,
            fetch_navigation_timeout=15,
        )
        with caplog.at_level(logging.DEBUG, logger="deerflow.community.infoquest.infoquest_client"):
            client.fetch("https://example.com")
        assert "has_timeout_filter=True" in caplog.text
        assert "has_fetch_time_filter=True" in caplog.text
        assert "has_navigation_timeout_filter=True" in caplog.text

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_fetch_debug_response_sample_long_text(self, mock_post, caplog):
        """The debug branch at lines 100-103 that logs partial response."""
        long_text = json.dumps({"unknown_field": "x" * 300})
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = long_text
        mock_post.return_value = mock_response

        client = InfoQuestClient()
        with caplog.at_level(logging.DEBUG, logger="deerflow.community.infoquest.infoquest_client"):
            result = client.fetch("https://example.com")
        assert result == long_text
        assert "Successfully received response" in caplog.text

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_fetch_debug_response_sample_short_text(self, mock_post, caplog):
        """Short response text does not trigger truncation."""
        short_text = json.dumps({"unknown_field": "short"})
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = short_text
        mock_post.return_value = mock_response

        client = InfoQuestClient()
        with caplog.at_level(logging.DEBUG, logger="deerflow.community.infoquest.infoquest_client"):
            result = client.fetch("https://example.com")
        assert result == short_text
        assert "Successfully received response" in caplog.text


class TestWebSearchRawResults:
    """Tests for InfoQuestClient.web_search_raw_results."""

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_basic_search(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": []}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = InfoQuestClient()
        result = client.web_search_raw_results("python", "")
        assert result == {"results": []}

        call_kwargs = mock_post.call_args
        params = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert params["query"] == "python"
        assert params["format"] == "JSON"
        assert "site" not in params
        assert "time_range" not in params

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_with_site(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": []}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = InfoQuestClient()
        client.web_search_raw_results("python", "example.com")

        call_kwargs = mock_post.call_args
        params = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert params["site"] == "example.com"

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_with_time_range(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": []}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = InfoQuestClient(search_time_range=7)
        client.web_search_raw_results("python", "")

        call_kwargs = mock_post.call_args
        params = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert params["time_range"] == 7

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_debug_logging(self, mock_post, caplog):
        mock_response = MagicMock()
        mock_response.json.return_value = {"key": "value"}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = InfoQuestClient()
        with caplog.at_level(logging.DEBUG, logger="deerflow.community.infoquest.infoquest_client"):
            client.web_search_raw_results("test query", "")
        assert "Search API request completed successfully" in caplog.text

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_debug_logging_long_response(self, mock_post, caplog):
        """Debug logging truncates long JSON response samples."""
        long_data = {"key": "x" * 300}
        mock_response = MagicMock()
        mock_response.json.return_value = long_data
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = InfoQuestClient()
        with caplog.at_level(logging.DEBUG, logger="deerflow.community.infoquest.infoquest_client"):
            client.web_search_raw_results("q", "")
        assert "response_sample=" in caplog.text


class TestCleanResults:
    """Tests for InfoQuestClient.clean_results (static)."""

    def test_organic_results(self):
        raw = _make_raw_search_results(
            organic=[
                {"title": "Page 1", "desc": "Description 1", "url": "https://a.com"},
                {"title": "Page 2", "desc": "Description 2", "url": "https://b.com"},
            ]
        )
        results = InfoQuestClient.clean_results(raw)
        assert len(results) == 2
        assert results[0]["type"] == "page"
        assert results[0]["title"] == "Page 1"
        assert results[0]["desc"] == "Description 1"
        assert results[0]["snippet"] == "Description 1"
        assert results[0]["url"] == "https://a.com"

    def test_deduplication(self):
        """Duplicate URLs are skipped."""
        raw = _make_raw_search_results(
            organic=[
                {"title": "P1", "desc": "D1", "url": "https://same.com"},
                {"title": "P2", "desc": "D2", "url": "https://same.com"},
            ]
        )
        results = InfoQuestClient.clean_results(raw)
        assert len(results) == 1

    def test_top_stories(self):
        raw = _make_raw_search_results(
            top_stories={
                "items": [
                    {"title": "News 1", "url": "https://news1.com", "time_frame": "2h", "source": "Reuters"},
                    {"title": "News 2", "url": "https://news2.com"},
                ]
            }
        )
        results = InfoQuestClient.clean_results(raw)
        assert len(results) == 2
        assert results[0]["type"] == "news"
        assert results[0]["time_frame"] == "2h"
        assert results[0]["source"] == "Reuters"
        assert results[1]["type"] == "news"
        assert "time_frame" not in results[1]
        assert "source" not in results[1]

    def test_mixed_organic_and_top_stories(self):
        raw = _make_raw_search_results(
            organic=[{"title": "P1", "url": "https://p1.com"}],
            top_stories={"items": [{"title": "N1", "url": "https://n1.com"}]},
        )
        results = InfoQuestClient.clean_results(raw)
        assert len(results) == 2

    def test_missing_optional_fields(self):
        """Results missing title/desc/url should still process without errors."""
        raw = _make_raw_search_results(
            organic=[
                {},  # completely empty
                {"title": "Only title"},
                {"desc": "Only desc"},
            ]
        )
        results = InfoQuestClient.clean_results(raw)
        # Only entries with a valid, non-empty, non-duplicate url are kept
        assert len(results) == 0

    def test_empty_url_skipped(self):
        raw = _make_raw_search_results(
            organic=[
                {"title": "T", "url": ""},
            ]
        )
        results = InfoQuestClient.clean_results(raw)
        assert len(results) == 0

    def test_non_string_url_skipped(self):
        raw = _make_raw_search_results(
            organic=[
                {"title": "T", "url": 123},
            ]
        )
        results = InfoQuestClient.clean_results(raw)
        assert len(results) == 0

    def test_news_without_title_or_url_skipped(self):
        raw = _make_raw_search_results(
            top_stories={
                "items": [
                    {},  # no title, no url
                    {"title": "Only title"},  # title but no url
                    {"url": "https://x.com"},  # url but no title
                ]
            }
        )
        results = InfoQuestClient.clean_results(raw)
        # Only items with both title and valid url are kept
        assert len(results) == 0

    def test_news_deduplication(self):
        raw = _make_raw_search_results(
            top_stories={
                "items": [
                    {"title": "N1", "url": "https://dup.com"},
                    {"title": "N2", "url": "https://dup.com"},
                ]
            }
        )
        results = InfoQuestClient.clean_results(raw)
        assert len(results) == 1

    def test_multiple_content_lists(self):
        """Multiple items in raw_results list are all processed."""
        raw = [
            {"content": {"results": {"organic": [{"title": "P1", "url": "https://a.com"}]}}},
            {"content": {"results": {"organic": [{"title": "P2", "url": "https://b.com"}]}}},
        ]
        results = InfoQuestClient.clean_results(raw)
        assert len(results) == 2

    def test_no_organic_no_top_stories(self):
        raw = _make_raw_search_results()
        results = InfoQuestClient.clean_results(raw)
        assert results == []

    def test_empty_raw_list(self):
        results = InfoQuestClient.clean_results([])
        assert results == []


class TestWebSearch:
    """Tests for InfoQuestClient.web_search."""

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_success_path(self, mock_post):
        search_data = {"search_result": {"results": [{"content": {"results": {"organic": [{"title": "T", "desc": "D", "url": "https://x.com"}]}}}]}}
        mock_response = MagicMock()
        mock_response.json.return_value = search_data
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = InfoQuestClient()
        result = client.web_search("python")
        parsed = json.loads(result)
        assert len(parsed) == 1
        assert parsed[0]["title"] == "T"

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_content_fallback_returns_error(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"content": "bad format"}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = InfoQuestClient()
        result = client.web_search("python")
        assert result.startswith("Error:")
        assert "wrong format" in result

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_neither_field_returns_raw_json(self, mock_post):
        raw = {"other": "data"}
        mock_response = MagicMock()
        mock_response.json.return_value = raw
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = InfoQuestClient()
        result = client.web_search("python")
        parsed = json.loads(result)
        assert parsed == raw

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_exception_returns_error(self, mock_post):
        mock_post.side_effect = RuntimeError("network down")

        client = InfoQuestClient()
        result = client.web_search("python")
        assert result.startswith("Error:")
        assert "network down" in result

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_debug_logging_truncated_query(self, mock_post, caplog):
        mock_response = MagicMock()
        mock_response.json.return_value = {"search_result": {"results": [{"content": {"results": {}}}]}}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = InfoQuestClient()
        long_query = "x" * 100
        with caplog.at_level(logging.DEBUG, logger="deerflow.community.infoquest.infoquest_client"):
            client.web_search(long_query)
        assert "query_truncated=" in caplog.text

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_debug_logging_short_query(self, mock_post, caplog):
        mock_response = MagicMock()
        mock_response.json.return_value = {"search_result": {"results": [{"content": {"results": {}}}]}}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = InfoQuestClient()
        with caplog.at_level(logging.DEBUG, logger="deerflow.community.infoquest.infoquest_client"):
            client.web_search("short")
        assert "query_truncated=short" in caplog.text

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_with_site_and_time_range(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"search_result": {"results": [{"content": {"results": {}}}]}}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = InfoQuestClient(search_time_range=7)
        client.web_search("python", site="github.com")

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_debug_logging_with_filters(self, mock_post, caplog):
        """Debug logging path with time and site filters."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"search_result": {"results": [{"content": {"results": {}}}]}}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = InfoQuestClient(search_time_range=7)
        with caplog.at_level(logging.DEBUG, logger="deerflow.community.infoquest.infoquest_client"):
            client.web_search("test", site="github.com")
        assert "has_time_filter=True" in caplog.text
        assert "has_site_filter=True" in caplog.text

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_debug_results_count(self, mock_post, caplog):
        """Debug logging reports results_count after cleaning."""
        search_data = {
            "search_result": {
                "results": [
                    {
                        "content": {
                            "results": {
                                "organic": [
                                    {"title": "T", "url": "https://x.com"},
                                ]
                            }
                        }
                    }
                ]
            }
        }
        mock_response = MagicMock()
        mock_response.json.return_value = search_data
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = InfoQuestClient()
        with caplog.at_level(logging.DEBUG, logger="deerflow.community.infoquest.infoquest_client"):
            client.web_search("q")
        assert "results_count=" in caplog.text


class TestCleanResultsWithImageSearch:
    """Tests for InfoQuestClient.clean_results_with_image_search (static)."""

    def test_image_results(self):
        raw = _make_raw_search_results(
            images_results=[
                {"original": "https://img1.jpg", "title": "Image 1"},
                {"original": "https://img2.jpg", "title": "Image 2"},
            ]
        )
        results = InfoQuestClient.clean_results_with_image_search(raw)
        assert len(results) == 2
        assert results[0]["image_url"] == "https://img1.jpg"
        assert results[0]["title"] == "Image 1"

    def test_deduplication(self):
        raw = _make_raw_search_results(
            images_results=[
                {"original": "https://same.jpg", "title": "I1"},
                {"original": "https://same.jpg", "title": "I2"},
            ]
        )
        results = InfoQuestClient.clean_results_with_image_search(raw)
        assert len(results) == 1

    def test_missing_original_skipped(self):
        raw = _make_raw_search_results(
            images_results=[
                {"title": "No original"},
            ]
        )
        results = InfoQuestClient.clean_results_with_image_search(raw)
        assert len(results) == 0

    def test_empty_original_skipped(self):
        raw = _make_raw_search_results(
            images_results=[
                {"original": ""},
            ]
        )
        results = InfoQuestClient.clean_results_with_image_search(raw)
        assert len(results) == 0

    def test_non_string_original_skipped(self):
        raw = _make_raw_search_results(
            images_results=[
                {"original": 123},
            ]
        )
        results = InfoQuestClient.clean_results_with_image_search(raw)
        assert len(results) == 0

    def test_no_images_results(self):
        raw = _make_raw_search_results()
        results = InfoQuestClient.clean_results_with_image_search(raw)
        assert results == []

    def test_title_without_original(self):
        """Title added to clean_result dict but result not appended (no valid url)."""
        raw = _make_raw_search_results(
            images_results=[
                {"title": "Only title"},
            ]
        )
        results = InfoQuestClient.clean_results_with_image_search(raw)
        assert len(results) == 0

    def test_multiple_content_lists(self):
        raw = [
            {"content": {"results": {"images_results": [{"original": "https://a.jpg"}]}}},
            {"content": {"results": {"images_results": [{"original": "https://b.jpg"}]}}},
        ]
        results = InfoQuestClient.clean_results_with_image_search(raw)
        assert len(results) == 2

    def test_empty_raw_list(self):
        results = InfoQuestClient.clean_results_with_image_search([])
        assert results == []


class TestImageSearchRawResults:
    """Tests for InfoQuestClient.image_search_raw_results."""

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_basic_search(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": []}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = InfoQuestClient()
        result = client.image_search_raw_results("cats", "")
        assert result == {"results": []}

        call_kwargs = mock_post.call_args
        params = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert params["search_type"] == "Images"
        assert params["query"] == "cats"
        assert "site" not in params

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_with_site(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": []}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = InfoQuestClient()
        client.image_search_raw_results("cats", "example.com")

        call_kwargs = mock_post.call_args
        params = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert params["site"] == "example.com"

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_time_range_in_range(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": []}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = InfoQuestClient(image_search_time_range=30)
        client.image_search_raw_results("cats", "")

        call_kwargs = mock_post.call_args
        params = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert params["time_range"] == 30

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_time_range_out_of_range_warning(self, mock_post, caplog):
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": []}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = InfoQuestClient(image_search_time_range=400)
        with caplog.at_level(logging.WARNING, logger="deerflow.community.infoquest.infoquest_client"):
            client.image_search_raw_results("cats", "")

        call_kwargs = mock_post.call_args
        params = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert "time_range" not in params
        assert "out of valid range" in caplog.text

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_time_range_zero_not_added(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": []}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = InfoQuestClient(image_search_time_range=0)
        client.image_search_raw_results("cats", "")

        call_kwargs = mock_post.call_args
        params = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert "time_range" not in params

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_time_range_boundary_365(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": []}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = InfoQuestClient(image_search_time_range=365)
        client.image_search_raw_results("cats", "")

        call_kwargs = mock_post.call_args
        params = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert params["time_range"] == 365

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_time_range_boundary_1(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": []}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = InfoQuestClient(image_search_time_range=1)
        client.image_search_raw_results("cats", "")

        call_kwargs = mock_post.call_args
        params = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert params["time_range"] == 1

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_image_size_valid(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": []}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        for size in ("l", "m", "i"):
            client = InfoQuestClient(image_size=size)
            client.image_search_raw_results("cats", "")
            call_kwargs = mock_post.call_args
            params = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
            assert params["image_size"] == size

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_image_size_invalid_warning(self, mock_post, caplog):
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": []}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = InfoQuestClient(image_size="x")
        with caplog.at_level(logging.WARNING, logger="deerflow.community.infoquest.infoquest_client"):
            client.image_search_raw_results("cats", "")

        call_kwargs = mock_post.call_args
        params = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert "image_size" not in params
        assert "is not valid" in caplog.text

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_image_size_empty_string(self, mock_post):
        """Empty image_size is falsy, so it should not be added."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": []}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = InfoQuestClient(image_size="")
        client.image_search_raw_results("cats", "")

        call_kwargs = mock_post.call_args
        params = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert "image_size" not in params

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_debug_logging(self, mock_post, caplog):
        mock_response = MagicMock()
        mock_response.json.return_value = {"key": "value"}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = InfoQuestClient()
        with caplog.at_level(logging.DEBUG, logger="deerflow.community.infoquest.infoquest_client"):
            client.image_search_raw_results("test", "")
        assert "Image Search API request completed successfully" in caplog.text

    @patch.dict("os.environ", {}, clear=True)
    @patch("deerflow.community.infoquest.infoquest_client.requests.post")
    def test_debug_logging_long_response(self, mock_post, caplog):
        """Debug logging truncates long JSON response samples for image search."""
        long_data = {"key": "x" * 300}
        mock_response = MagicMock()
        mock_response.json.return_value = long_data
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = InfoQuestClient()
        with caplog.at_level(logging.DEBUG, logger="deerflow.community.infoquest.infoquest_client"):
            client.image_search_raw_results("q", "")
        assert "response_sample=" in caplog.text
