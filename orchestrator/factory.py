# orchestrator/factory.py
from __future__ import annotations

import os
from dataclasses import dataclass, field
from fnmatch import fnmatch
from typing import Any
from urllib.parse import urlparse

import yaml
from jinja2 import Template


class ValidationError(Exception):
    pass


@dataclass
class InputDef:
    name: str
    type: str
    required: bool = True
    default: Any = None
    values: list[str] | None = None


@dataclass
class ConfirmationGate:
    action_types: list[str]
    require: str
    message_template: str


@dataclass
class RenderedAgent:
    """An agent template with inputs resolved."""
    name: str
    app_name: str
    start_url: str
    allowed_url_patterns: list[str]
    system_prompt: str
    instructions: str
    confirmation_gates: list[ConfirmationGate]
    evidence_capture_points: list[str]
    timeout_seconds: int
    max_steps: int


@dataclass
class AgentTemplate:
    name: str
    version: str
    app_name: str
    start_url: str
    allowed_url_patterns: list[str]
    inputs: list[InputDef]
    system_prompt_template: str
    instructions_template: str
    confirmation_gates: list[ConfirmationGate]
    evidence_capture_points: list[str]
    capture_every_step: bool
    timeout_seconds: int
    max_steps: int

    def render(self, **kwargs: Any) -> RenderedAgent:
        resolved = {}
        for inp in self.inputs:
            if inp.name in kwargs:
                value = kwargs[inp.name]
                if inp.values and value not in inp.values:
                    raise ValidationError(
                        f"Input '{inp.name}' must be one of {inp.values}, got '{value}'"
                    )
                resolved[inp.name] = value
            elif inp.default is not None:
                resolved[inp.name] = inp.default
            elif inp.required:
                raise ValidationError(f"Required input '{inp.name}' not provided")

        resolved["app_name"] = self.app_name

        instructions = Template(self.instructions_template).render(**resolved)
        system_prompt = Template(self.system_prompt_template).render(**resolved)

        rendered_gates = []
        for gate in self.confirmation_gates:
            rendered_gates.append(ConfirmationGate(
                action_types=gate.action_types,
                require=gate.require,
                message_template=Template(gate.message_template).render(**resolved),
            ))

        return RenderedAgent(
            name=self.name,
            app_name=self.app_name,
            start_url=self.start_url,
            allowed_url_patterns=self.allowed_url_patterns,
            system_prompt=system_prompt,
            instructions=instructions,
            confirmation_gates=rendered_gates,
            evidence_capture_points=self.evidence_capture_points,
            timeout_seconds=self.timeout_seconds,
            max_steps=self.max_steps,
        )

    def is_url_allowed(self, url: str) -> bool:
        hostname = urlparse(url).hostname or ""
        return any(fnmatch(hostname, pattern) for pattern in self.allowed_url_patterns)


class AgentFactory:
    def __init__(self, agents_dir: str):
        self.agents_dir = agents_dir

    def load(self, name: str) -> AgentTemplate:
        path = os.path.join(self.agents_dir, f"{name}.yaml")
        if not os.path.exists(path):
            raise FileNotFoundError(f"Agent template not found: {path}")

        with open(path) as f:
            data = yaml.safe_load(f)

        inputs = []
        for inp in data.get("inputs", []):
            inputs.append(InputDef(
                name=inp["name"],
                type=inp["type"],
                required=inp.get("required", True),
                default=inp.get("default"),
                values=inp.get("values"),
            ))

        gates = []
        for gate in data.get("confirmation_gates", []):
            gates.append(ConfirmationGate(
                action_types=gate["action_types"],
                require=gate["require"],
                message_template=gate["message"],
            ))

        evidence = data.get("evidence", {})
        capture_points = [cp["on"] for cp in evidence.get("capture_points", [])]

        return AgentTemplate(
            name=data["name"],
            version=data.get("version", "1.0"),
            app_name=data["app"]["name"],
            start_url=data["app"]["start_url"],
            allowed_url_patterns=data["app"].get("allowed_url_patterns", []),
            inputs=inputs,
            system_prompt_template=data.get("system_prompt", ""),
            instructions_template=data.get("instructions", ""),
            confirmation_gates=gates,
            evidence_capture_points=capture_points,
            capture_every_step=evidence.get("capture_every_step", False),
            timeout_seconds=data.get("timeout_seconds", 300),
            max_steps=data.get("max_steps", 30),
        )

    def list(self) -> list[str]:
        names = []
        for f in os.listdir(self.agents_dir):
            if f.endswith(".yaml"):
                names.append(f.removesuffix(".yaml"))
        return sorted(names)
