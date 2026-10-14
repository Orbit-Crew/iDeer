"""Tool registry for iDeer software factory.

Provides a unified view of all registered tools with metadata,
used by the tools API router.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ToolInfo:
    name: str
    description: str
    group: str
    requires_network: bool = False
    configurable: bool = False
    config_schema: dict = field(default_factory=dict)
    param_schema: dict = field(default_factory=dict)
    config: dict = field(default_factory=dict)


class ToolRegistry:
    """Central registry of all available tools."""

    def __init__(self):
        self._tools: dict[str, ToolInfo] = {}

    def register(self, tool: ToolInfo):
        if tool.name in self._tools:
            logger.warning("Overwriting existing tool registration: %s", tool.name)
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolInfo | None:
        return self._tools.get(name)

    def list_all(self) -> list[ToolInfo]:
        return list(self._tools.values())

    def list_by_group(self, group: str) -> list[ToolInfo]:
        return [t for t in self._tools.values() if t.group == group]

    def search(self, query: str) -> list[ToolInfo]:
        q = query.lower()
        return [t for t in self._tools.values() if q in t.name.lower() or q in t.description.lower()]

    def update_config(self, name: str, config: dict) -> bool:
        """Update a tool's configuration. Returns True if successful."""
        tool = self._tools.get(name)
        if tool is None:
            return False
        if not tool.configurable:
            logger.warning("Tool %s is not configurable", name)
            return False
        # Validate keys against config_schema if provided
        if tool.config_schema:
            properties = tool.config_schema.get("properties")
            if properties is not None:
                allowed_keys = set(properties.keys())
                unexpected = set(config.keys()) - allowed_keys
                if unexpected:
                    logger.warning("Unexpected config keys for %s: %s", name, unexpected)
                    return False
                # BUG-18: Validate values against schema types. bool is a subclass
                # of int in Python, so it must be excluded explicitly wherever
                # the schema does not ask for a boolean (report 02-L4).
                for key, value in config.items():
                    prop_schema = properties.get(key, {})
                    expected_type = prop_schema.get("type")
                    value_is_bool = isinstance(value, bool)
                    if expected_type == "boolean":
                        type_valid = value_is_bool
                    elif expected_type == "integer":
                        type_valid = isinstance(value, int) and not value_is_bool
                    elif expected_type == "number":
                        type_valid = isinstance(value, (int, float)) and not value_is_bool
                    else:
                        type_map = {
                            "string": str,
                            "array": list,
                            "object": dict,
                            "null": type(None),
                        }
                        expected_python_type = type_map.get(expected_type)
                        type_valid = bool(expected_python_type and isinstance(value, expected_python_type))
                    if expected_type and not type_valid:
                        logger.warning(
                            "Config value type mismatch for %s.%s: expected %s, got %s",
                            name,
                            key,
                            expected_type,
                            type(value).__name__,
                        )
                        return False
                    # Check enum constraints
                    enum_values = prop_schema.get("enum")
                    if enum_values and value not in enum_values:
                        logger.warning(
                            "Config value for %s.%s not in allowed enum: %s",
                            name,
                            key,
                            enum_values,
                        )
                        return False
        tool.config.update(config)
        return True


# Global registry instance
_registry = ToolRegistry()


def get_tool_registry() -> ToolRegistry:
    return _registry
