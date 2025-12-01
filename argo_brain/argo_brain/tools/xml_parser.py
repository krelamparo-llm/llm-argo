"""XML-based tool call parser inspired by Qwen3-Coder architecture.

This module provides utilities for parsing tool calls in XML format, following
the patterns established by Qwen3-Coder-30B model architecture.

Format:
    <tool_call>
    <function=function_name>
    <parameter=param1>
    value1
    </parameter>
    <parameter=param2>
    value2
    </parameter>
    </function>
    </tool_call>
"""

from __future__ import annotations

import ast
import json
import re
from typing import Any, Dict, List, Optional

import logging


class XMLToolParser:
    """Parse XML-formatted tool calls from LLM output.

    Based on Qwen3-Coder tool parser architecture but adapted for Argo Brain.
    """

    def __init__(self) -> None:
        self.logger = logging.getLogger("argo_brain.xml_parser")

        # XML markers
        self.tool_call_start = "<tool_call>"
        self.tool_call_end = "</tool_call>"
        self.function_prefix = "<function="
        self.function_end = "</function>"
        self.parameter_prefix = "<parameter="
        self.parameter_end = "</parameter>"

        # Regex patterns for extraction
        self.tool_call_regex = re.compile(
            r"<tool_call>(.*?)</tool_call>|<tool_call>(.*?)$", re.DOTALL
        )
        self.function_regex = re.compile(
            r"<function=(.*?)</function>|<function=(.*)$", re.DOTALL
        )
        self.parameter_regex = re.compile(
            r"<parameter=(.*?)(?:</parameter>|(?=<parameter=)|(?=</function>)|$)", re.DOTALL
        )

    def extract_tool_calls(self, text: str) -> List[Dict[str, Any]]:
        """Extract all tool calls from LLM output.

        Args:
            text: Raw text output from LLM

        Returns:
            List of parsed tool calls with structure:
            [{"tool": "name", "arguments": {"arg1": val1, ...}}, ...]
        """
        # Quick check to avoid unnecessary processing
        if self.function_prefix not in text:
            return []

        try:
            tool_calls = self._get_tool_calls(text)
            parsed_calls = []

            for tool_call_text in tool_calls:
                parsed = self._parse_function_call(tool_call_text)
                if parsed:
                    parsed_calls.append(parsed)

            return parsed_calls

        except Exception:
            self.logger.exception("Error extracting XML tool calls from output")
            return []

    def _get_tool_calls(self, text: str) -> List[str]:
        """Extract raw tool call blocks from text."""
        matches = self.tool_call_regex.findall(text)
        raw_calls = [match[0] if match[0] else match[1] for match in matches]

        # Fallback: if no tool_call tags found, try the whole text
        if not raw_calls:
            raw_calls = [text]

        return raw_calls

    def _parse_function_call(self, call_text: str) -> Optional[Dict[str, Any]]:
        """Parse a single function call block.

        Args:
            call_text: Content inside <tool_call>...</tool_call>

        Returns:
            {"tool": "function_name", "arguments": {...}} or None
        """
        # Extract function blocks
        function_matches = self.function_regex.findall(call_text)
        if not function_matches:
            return None

        function_blocks = [m[0] if m[0] else m[1] for m in function_matches]
        if not function_blocks:
            return None

        # Parse first function block (multi-function not supported yet)
        function_text = function_blocks[0]

        # Extract function name (everything before first >)
        end_index = function_text.find(">")
        if end_index == -1:
            return None

        function_name = function_text[:end_index].strip()
        parameters_text = function_text[end_index + 1:]

        # Parse parameters
        param_dict = self._parse_parameters(parameters_text, function_name)

        return {"tool": function_name, "arguments": param_dict}

    def _parse_parameters(self, params_text: str, function_name: str) -> Dict[str, Any]:
        """Parse parameter blocks within a function.

        Args:
            params_text: Text containing parameter blocks
            function_name: Name of function (for logging)

        Returns:
            Dictionary of parameter name -> value
        """
        param_dict = {}

        for match_text in self.parameter_regex.findall(params_text):
            idx = match_text.find(">")
            if idx == -1:
                continue

            param_name = match_text[:idx].strip()
            param_value = match_text[idx + 1:].strip()

            # Clean up leading/trailing newlines
            if param_value.startswith("\n"):
                param_value = param_value[1:]
            if param_value.endswith("\n"):
                param_value = param_value[:-1]

            # Store the parameter
            param_dict[param_name] = param_value

        return param_dict

    def convert_param_value(
        self,
        param_value: str,
        param_name: str,
        param_config: Dict[str, Any],
        function_name: str,
    ) -> Any:
        """Convert parameter value based on type schema.

        Inspired by Qwen3-Coder type conversion logic.

        Args:
            param_value: Raw string value from XML
            param_name: Parameter name
            param_config: Schema configuration with 'type' field
            function_name: Function name for logging

        Returns:
            Converted value (string, int, float, bool, dict, list, etc.)
        """
        # Handle null
        if param_value.lower() == "null":
            return None

        # If no config available, return as-is
        if param_name not in param_config:
            if param_config:
                self.logger.warning(
                    f"Parameter '{param_name}' not defined in schema for '{function_name}'"
                )
            return param_value

        # Get type from schema
        param_type = param_config.get(param_name, {}).get("type", "string")
        if isinstance(param_type, dict):
            param_type = param_type.get("type", "string")
        param_type = str(param_type).strip().lower()

        # String types - return as-is
        if param_type in ["string", "str", "text", "varchar", "char", "enum"]:
            return param_value

        # Integer types
        if any(
            param_type.startswith(prefix)
            for prefix in ["int", "uint", "long", "short", "unsigned"]
        ):
            try:
                return int(param_value)
            except ValueError:
                self.logger.warning(
                    f"Cannot convert '{param_value}' to int for '{param_name}' "
                    f"in '{function_name}', using string"
                )
                return param_value

        # Float types
        if param_type.startswith("num") or param_type.startswith("float"):
            try:
                float_value = float(param_value)
                # Return int if no decimal part
                return int(float_value) if float_value == int(float_value) else float_value
            except ValueError:
                self.logger.warning(
                    f"Cannot convert '{param_value}' to float for '{param_name}' "
                    f"in '{function_name}', using string"
                )
                return param_value

        # Boolean types
        if param_type in ["boolean", "bool", "binary"]:
            lower_val = param_value.lower()
            if lower_val not in ["true", "false"]:
                self.logger.warning(
                    f"Invalid boolean '{param_value}' for '{param_name}' "
                    f"in '{function_name}', using false"
                )
            return lower_val == "true"

        # Complex types (object, array)
        if param_type in ["object", "array", "arr"] or param_type.startswith(
            ("dict", "list")
        ):
            try:
                return json.loads(param_value)
            except json.JSONDecodeError:
                self.logger.warning(
                    f"Cannot parse JSON for '{param_name}' in '{function_name}', "
                    "trying ast.literal_eval"
                )
                try:
                    return ast.literal_eval(param_value)
                except (ValueError, SyntaxError):
                    self.logger.warning(
                        f"Cannot evaluate '{param_value}' for '{param_name}' "
                        f"in '{function_name}', using string"
                    )
                    return param_value

        # Default: try literal_eval for safety
        try:
            return ast.literal_eval(param_value)
        except (ValueError, SyntaxError):
            return param_value

    def format_tool_for_prompt(
        self, tool_name: str, description: str, parameters: Dict[str, Any]
    ) -> str:
        """Format a tool definition for XML-based prompts.

        Args:
            tool_name: Name of the tool
            description: Tool description
            parameters: JSON schema parameters dict

        Returns:
            XML-formatted tool definition
        """
        lines = [
            "<function>",
            f"<name>{tool_name}</name>",
        ]

        if description:
            lines.append(f"<description>{description}</description>")

        lines.append("<parameters>")

        # Extract properties from schema
        properties = parameters.get("properties", {})
        for param_name, param_fields in properties.items():
            lines.append("<parameter>")
            lines.append(f"<name>{param_name}</name>")

            if "type" in param_fields:
                lines.append(f"<type>{param_fields['type']}</type>")

            if "description" in param_fields:
                lines.append(f"<description>{param_fields['description']}</description>")

            lines.append("</parameter>")

        lines.append("</parameters>")
        lines.append("</function>")

        return "\n".join(lines)
