"""Playwright browser controller that resolves natural language element
descriptions to Playwright locators.

Claude describes elements like "the Submit button" or "the email input field".
This module tries multiple locator strategies in order of reliability:
1. get_by_role (accessibility-first)
2. get_by_text (visible text match)
3. get_by_placeholder (input fields)
4. get_by_label (form labels)
"""
from __future__ import annotations

from fnmatch import fnmatch
from urllib.parse import urlparse

from playwright.async_api import Page


class BrowserController:
    def __init__(self, page: Page, allowed_url_patterns: list[str]):
        self.page = page
        self.allowed_url_patterns = allowed_url_patterns

    def _is_url_allowed(self, url: str) -> bool:
        hostname = urlparse(url).hostname or ""
        return any(fnmatch(hostname, p) for p in self.allowed_url_patterns)

    async def navigate(self, url: str) -> dict:
        if not self._is_url_allowed(url):
            return {"status": "blocked", "reason": f"URL not in allowlist: {url}"}
        await self.page.goto(url, wait_until="networkidle")
        return {"status": "navigated", "url": url, "title": await self.page.title()}

    async def take_screenshot(self) -> bytes:
        return await self.page.screenshot(full_page=False)

    async def click(self, description: str) -> dict:
        locator = await self._resolve_locator(description)
        await locator.click()
        return {"status": "clicked", "description": description}

    async def type_text(self, description: str, text: str) -> dict:
        locator = await self._resolve_locator(description)
        await locator.fill(text)
        return {"status": "typed", "description": description, "text": text}

    async def select_option(self, description: str, value: str) -> dict:
        locator = await self._resolve_locator(description)
        await locator.select_option(label=value)
        return {"status": "selected", "description": description, "value": value}

    async def scroll(self, direction: str) -> dict:
        delta = -500 if direction == "up" else 500
        await self.page.evaluate(f"window.scrollBy(0, {delta})")
        return {"status": "scrolled", "direction": direction}

    async def read_page(self) -> str:
        return await self.page.evaluate("document.body.innerText")

    async def _resolve_locator(self, description: str):
        """Try multiple Playwright locator strategies to find the element
        described in natural language. Falls back through strategies until
        one finds a match."""
        desc_lower = description.lower()

        # Strategy 1: Role-based (buttons, links, textboxes, etc.)
        role_keywords = {
            "button": "button",
            "link": "link",
            "input": "textbox",
            "field": "textbox",
            "text box": "textbox",
            "search box": "searchbox",
            "search": "searchbox",
            "checkbox": "checkbox",
            "radio": "radio",
            "tab": "tab",
            "row": "row",
            "heading": "heading",
        }

        for keyword, role in role_keywords.items():
            if keyword in desc_lower:
                # Extract the name part (remove the role keyword)
                name_part = description
                for kw in role_keywords:
                    name_part = (
                        name_part.replace(kw, "")
                        .replace(kw.title(), "")
                        .replace(kw.upper(), "")
                    )
                name_part = name_part.replace("the", "").replace("The", "").strip()

                if name_part:
                    locator = self.page.get_by_role(role, name=name_part)
                else:
                    locator = self.page.get_by_role(role)

                if await locator.count() > 0:
                    return locator.first
                break

        # Strategy 2: Text-based
        locator = self.page.get_by_text(description, exact=False)
        if await locator.count() > 0:
            return locator.first

        # Strategy 3: Placeholder
        locator = self.page.get_by_placeholder(description, exact=False)
        if await locator.count() > 0:
            return locator.first

        # Strategy 4: Label
        locator = self.page.get_by_label(description, exact=False)
        if await locator.count() > 0:
            return locator.first

        raise ElementNotFoundError(f"Could not find element: {description}")


class ElementNotFoundError(Exception):
    pass
