from orchestrator.tools import get_tool_definitions, TOOL_NAMES


def test_tool_definitions_are_valid():
    tools = get_tool_definitions()
    assert isinstance(tools, list)
    assert len(tools) == len(TOOL_NAMES)

    for tool in tools:
        assert "name" in tool
        assert "description" in tool
        assert "input_schema" in tool
        assert tool["input_schema"]["type"] == "object"


def test_all_expected_tools_present():
    tools = get_tool_definitions()
    names = {t["name"] for t in tools}
    expected = {
        "navigate", "screenshot", "click", "type_text",
        "select_option", "scroll", "read_page",
        "task_complete", "request_confirmation",
    }
    assert names == expected


def test_navigate_tool_has_url_param():
    tools = get_tool_definitions()
    nav = next(t for t in tools if t["name"] == "navigate")
    assert "url" in nav["input_schema"]["properties"]
    assert "url" in nav["input_schema"]["required"]


def test_click_tool_has_description_param():
    tools = get_tool_definitions()
    click = next(t for t in tools if t["name"] == "click")
    assert "description" in click["input_schema"]["properties"]


def test_type_text_tool_has_both_params():
    tools = get_tool_definitions()
    type_tool = next(t for t in tools if t["name"] == "type_text")
    props = type_tool["input_schema"]["properties"]
    assert "description" in props
    assert "text" in props
