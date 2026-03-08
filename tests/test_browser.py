import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from orchestrator.browser import BrowserController


@pytest.fixture
def mock_page():
    page = AsyncMock()
    page.screenshot = AsyncMock(return_value=b"fake-png-bytes")
    page.goto = AsyncMock()
    page.evaluate = AsyncMock(return_value="Page text content here")
    page.url = "https://greenfield.example.com/admin/users"
    return page


class TestBrowserController:
    @pytest.mark.asyncio
    async def test_navigate(self, mock_page):
        allowed = ["greenfield.example.com"]
        ctrl = BrowserController(mock_page, allowed)

        result = await ctrl.navigate("https://greenfield.example.com/admin/users")
        mock_page.goto.assert_called_once_with(
            "https://greenfield.example.com/admin/users",
            wait_until="networkidle",
        )
        assert result["status"] == "navigated"

    @pytest.mark.asyncio
    async def test_navigate_blocked_url(self, mock_page):
        allowed = ["greenfield.example.com"]
        ctrl = BrowserController(mock_page, allowed)

        result = await ctrl.navigate("https://evil.com/phishing")
        mock_page.goto.assert_not_called()
        assert result["status"] == "blocked"

    @pytest.mark.asyncio
    async def test_take_screenshot(self, mock_page):
        ctrl = BrowserController(mock_page, ["*"])
        png_bytes = await ctrl.take_screenshot()
        assert png_bytes == b"fake-png-bytes"
        mock_page.screenshot.assert_called_once_with(full_page=False)

    @pytest.mark.asyncio
    async def test_click(self, mock_page):
        locator = AsyncMock()
        mock_page.get_by_role = MagicMock(return_value=locator)
        locator.first = locator
        locator.count = AsyncMock(return_value=1)
        locator.click = AsyncMock()

        ctrl = BrowserController(mock_page, ["*"])
        result = await ctrl.click("the Submit button")
        assert result["status"] == "clicked"

    @pytest.mark.asyncio
    async def test_type_text(self, mock_page):
        locator = AsyncMock()
        mock_page.get_by_role = MagicMock(return_value=locator)
        locator.first = locator
        locator.count = AsyncMock(return_value=1)
        locator.fill = AsyncMock()

        ctrl = BrowserController(mock_page, ["*"])
        result = await ctrl.type_text("the search box", "jsmith@meritage.com")
        assert result["status"] == "typed"

    @pytest.mark.asyncio
    async def test_read_page(self, mock_page):
        ctrl = BrowserController(mock_page, ["*"])
        text = await ctrl.read_page()
        assert "Page text content here" in text

    @pytest.mark.asyncio
    async def test_scroll(self, mock_page):
        ctrl = BrowserController(mock_page, ["*"])
        result = await ctrl.scroll("down")
        assert result["status"] == "scrolled"
