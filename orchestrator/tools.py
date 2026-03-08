"""Browser tool definitions sent to Claude as function calling tools.

Claude uses these to control the browser. Tool names are verbs describing
browser actions. Claude provides natural language descriptions of elements
(not CSS selectors) -- the orchestrator resolves them via Playwright.
"""
from __future__ import annotations

TOOL_NAMES = [
    "navigate", "screenshot", "click", "type_text",
    "select_option", "scroll", "read_page",
    "task_complete", "request_confirmation",
]


def get_tool_definitions() -> list[dict]:
    return [
        {
            "name": "navigate",
            "description": "Navigate the browser to a URL. Only URLs matching the allowed patterns for this agent are permitted.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to navigate to.",
                    }
                },
                "required": ["url"],
            },
        },
        {
            "name": "screenshot",
            "description": "Take a screenshot of the current page. Use this to see what is on screen before deciding your next action.",
            "input_schema": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
        {
            "name": "click",
            "description": "Click on an element described in natural language. Describe the element by its visible text, label, role, or position on the page.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "Natural language description of the element to click, e.g. 'the Submit button', 'the search input field', 'the user row for jsmith'.",
                    }
                },
                "required": ["description"],
            },
        },
        {
            "name": "type_text",
            "description": "Type text into an input field described in natural language. The field will be cleared before typing.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "Natural language description of the input field, e.g. 'the email search box', 'the Name field'.",
                    },
                    "text": {
                        "type": "string",
                        "description": "The text to type into the field.",
                    },
                },
                "required": ["description", "text"],
            },
        },
        {
            "name": "select_option",
            "description": "Select an option from a dropdown/select element described in natural language.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "Natural language description of the dropdown, e.g. 'the Role dropdown', 'the Status select'.",
                    },
                    "value": {
                        "type": "string",
                        "description": "The visible text of the option to select.",
                    },
                },
                "required": ["description", "value"],
            },
        },
        {
            "name": "scroll",
            "description": "Scroll the page up or down to see more content.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": ["up", "down"],
                        "description": "Direction to scroll.",
                    }
                },
                "required": ["direction"],
            },
        },
        {
            "name": "read_page",
            "description": "Extract all visible text content from the current page. Use this when you need to read data from the page without relying on a screenshot.",
            "input_schema": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
        {
            "name": "task_complete",
            "description": "Signal that the task is complete. Provide a summary of what was accomplished.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Summary of what was accomplished during this task.",
                    }
                },
                "required": ["summary"],
            },
        },
        {
            "name": "request_confirmation",
            "description": "Request human confirmation before proceeding with a destructive or important action. Describe what you are about to do.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Description of the action you want to take and why it needs confirmation.",
                    }
                },
                "required": ["summary"],
            },
        },
    ]
