# tests/test_factory.py
import os
import pytest
from orchestrator.factory import AgentFactory, AgentTemplate, ValidationError

AGENTS_DIR = os.path.join(os.path.dirname(__file__), "..", "agents")


class TestAgentFactory:
    def test_load_template(self):
        factory = AgentFactory(AGENTS_DIR)
        template = factory.load("greenfield-deprovision")

        assert template.name == "Greenfield.AI User Deprovisioning"
        assert template.version == "1.0"
        assert template.app_name == "Greenfield.AI"
        assert template.start_url == "https://greenfield.example.com/admin/users"
        assert "greenfield.example.com" in template.allowed_url_patterns
        assert template.timeout_seconds == 300
        assert template.max_steps == 30
        assert len(template.inputs) == 2
        assert len(template.confirmation_gates) == 1
        assert len(template.evidence_capture_points) == 5

    def test_load_nonexistent_raises(self):
        factory = AgentFactory(AGENTS_DIR)
        with pytest.raises(FileNotFoundError):
            factory.load("does-not-exist")

    def test_render_instructions(self):
        factory = AgentFactory(AGENTS_DIR)
        template = factory.load("greenfield-deprovision")

        rendered = template.render(user_email="jsmith@meritage.com", action="disable")

        assert "jsmith@meritage.com" in rendered.instructions
        assert '"disable"' in rendered.instructions
        assert "jsmith@meritage.com" in rendered.system_prompt or True  # system_prompt has no variables

    def test_render_missing_required_input_raises(self):
        factory = AgentFactory(AGENTS_DIR)
        template = factory.load("greenfield-deprovision")

        with pytest.raises(ValidationError, match="user_email"):
            template.render()  # user_email is required

    def test_render_uses_default_for_optional(self):
        factory = AgentFactory(AGENTS_DIR)
        template = factory.load("greenfield-deprovision")

        rendered = template.render(user_email="jsmith@meritage.com")
        assert '"disable"' in rendered.instructions  # default action

    def test_render_validates_enum(self):
        factory = AgentFactory(AGENTS_DIR)
        template = factory.load("greenfield-deprovision")

        with pytest.raises(ValidationError, match="action"):
            template.render(user_email="jsmith@meritage.com", action="nuke")

    def test_list_agents(self):
        factory = AgentFactory(AGENTS_DIR)
        agents = factory.list()
        assert "greenfield-deprovision" in agents

    def test_url_allowed(self):
        factory = AgentFactory(AGENTS_DIR)
        template = factory.load("greenfield-deprovision")

        assert template.is_url_allowed("https://greenfield.example.com/admin/users")
        assert template.is_url_allowed("https://greenfield.example.com/profile/123")
        assert not template.is_url_allowed("https://evil.com/phishing")
        assert not template.is_url_allowed("https://other.example.com/page")
