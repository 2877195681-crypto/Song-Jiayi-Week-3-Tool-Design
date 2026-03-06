"""
Keyword extractor tool and agent tool base for LLM tool calling.

Provides a Tool wrapper class, helpers to convert tools to LLM API format,
build tool selection prompts, parse tool calls from LLM output, and execute
tools with structured JSON-serializable results and error handling.
"""

import json
import re
from typing import Any, Callable, Optional


# --- 1. Base class for agent tool ---

class Tool:
    """
    Wrapper for a callable that the agent (LLM) can invoke by name.

    Attributes:
        name: Unique identifier for the tool, used in tool calls.
        description: Human-readable description for the LLM to decide when to use the tool.
        fn: Callable to run when the tool is executed (e.g. function or method).
        parameters: JSON Schema for the tool's arguments (used for LLM API and prompts).
    """

    def __init__(self, name: str, description: str, fn: Callable[..., Any]) -> None:
        """
        Create a tool.

        Args:
            name: Tool name. Must be a non-empty string.
            description: Tool description. Must be a string.
            fn: Callable to execute (e.g. a function). Must be callable.

        Raises:
            TypeError: If name or description is not a string, or fn is not callable.
            ValueError: If name is empty or only whitespace.
        """
        if not isinstance(name, str):
            raise TypeError("name must be a string")
        if not isinstance(description, str):
            raise TypeError("description must be a string")
        if not callable(fn):
            raise TypeError("fn must be callable")
        name_stripped = name.strip()
        if not name_stripped:
            raise ValueError("name must not be empty")
        self.name = name_stripped
        self.description = description.strip()
        self.fn = fn
        self.parameters: dict[str, Any] = {"type": "object", "properties": {}, "required": []}

    def execute(self, **kwargs: Any) -> Any:
        """
        Run the tool with the given keyword arguments.

        Args:
            **kwargs: Arguments passed through to the underlying callable.

        Returns:
            Whatever the underlying callable returns.
        """
        return self.fn(**kwargs)

    def run(self, **kwargs: Any) -> Any:
        """
        Alias for execute. Run the tool with the given keyword arguments.

        Args:
            **kwargs: Arguments passed through to the underlying callable.

        Returns:
            Whatever the underlying callable returns.
        """
        return self.execute(**kwargs)

    def to_dict(self) -> dict[str, Any]:
        """
        Convert tool to dictionary for LLM (OpenAI-style function/tool format).

        Returns:
            A dict with "type" and "function" keys suitable for LLM tool/function APIs.
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


def tools_to_dict(tools: list[Tool]) -> list[dict[str, Any]]:
    """
    Convert a list of Tool instances to list of dicts for LLM API.

    Args:
        tools: List of Tool instances.

    Returns:
        List of tool dicts in OpenAI-style function format.

    Raises:
        TypeError: If tools is not a list or an element is not a Tool.
    """
    if not isinstance(tools, list):
        raise TypeError("tools must be a list")
    for t in tools:
        if not isinstance(t, Tool):
            raise TypeError("tools must contain only Tool instances")
    return [t.to_dict() for t in tools]


# --- 2. Tool selection prompt ---

def build_tool_selection_prompt(tools: list[Tool]) -> str:
    """
    Build a text prompt that lists available tools for the LLM to choose from.

    Args:
        tools: List of Tool instances to include in the prompt.

    Returns:
        A single string containing instructions and a list of tools with names,
        descriptions, and parameter info.

    Raises:
        TypeError: If tools is not a list or an element is not a Tool.
        ValueError: If tools is empty.
    """
    if not isinstance(tools, list):
        raise TypeError("tools must be a list")
    if not tools:
        raise ValueError("tools must not be empty")
    for t in tools:
        if not isinstance(t, Tool):
            raise TypeError("tools must contain only Tool instances")
    lines = [
        "You have access to the following tools. Use them when needed.",
        "Reply with a tool call in the format below when you want to use a tool.",
        "",
        "Format:",
        '{"name": "<tool_name>", "arguments": <json_object>}',
        "",
        "Available tools:",
    ]
    for t in tools:
        lines.append(f"- {t.name}: {t.description}")
        if t.parameters.get("properties"):
            lines.append("  Parameters:")
            for param_name, param_info in t.parameters["properties"].items():
                desc = param_info.get("description", "")
                lines.append(f"    - {param_name}: {desc}")
    return "\n".join(lines)


# --- 3. Parsing tool calls ---

def parse_tool_call(response_text: str) -> Optional[dict[str, Any]]:
    """
    Parse LLM response text to extract a single tool call.

    Expects JSON like: {"name": "tool_name", "arguments": {"key": "value"}}.
    Handles surrounding text and extracts the first JSON object found.

    Args:
        response_text: Raw string from the LLM (may contain extra text).

    Returns:
        A dict with "name" (str) and "arguments" (dict), or None if no valid
        tool call could be parsed.
    """
    if not isinstance(response_text, str):
        raise TypeError("response_text must be a string")
    text = response_text.strip()
    if not text:
        return None
    match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group())
        if not isinstance(data, dict):
            return None
        name = data.get("name")
        arguments = data.get("arguments")
        if name is None or not isinstance(name, str) or not name.strip():
            return None
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                return None
        if arguments is None or not isinstance(arguments, dict):
            arguments = {}
        return {"name": name.strip(), "arguments": arguments}
    except (json.JSONDecodeError, TypeError):
        return None


def parse_tool_calls(response_text: str) -> list[dict[str, Any]]:
    """
    Parse LLM response to extract multiple tool calls.

    First tries to parse a single JSON object; if that returns one result,
    returns it. Otherwise looks for ```json ... ``` code blocks and parses
    each as a tool call.

    Args:
        response_text: Raw string from the LLM.

    Returns:
        List of dicts, each with "name" (str) and "arguments" (dict).
        Empty list if none found.

    Raises:
        TypeError: If response_text is not a string.
    """
    if not isinstance(response_text, str):
        raise TypeError("response_text must be a string")
    results: list[dict[str, Any]] = []
    single = parse_tool_call(response_text)
    if single:
        results.append(single)
        return results
    pattern = r"```(?:json)?\s*(\{[\s\S]*?\})\s*```"
    for match in re.finditer(pattern, response_text):
        try:
            data = json.loads(match.group(1))
            if not isinstance(data, dict):
                continue
            name = data.get("name")
            arguments = data.get("arguments", {})
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    continue
            if name and isinstance(name, str) and isinstance(arguments, dict):
                results.append({"name": name.strip(), "arguments": arguments})
        except (json.JSONDecodeError, TypeError):
            continue
    return results


def execute_tool_call(
    tools_by_name: dict[str, Tool],
    name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """
    Execute a tool by name with the given arguments.

    Returns a JSON-serializable dict with either success and result, or
    success and error. Exceptions from the tool are caught and returned
    as structured errors.

    Args:
        tools_by_name: Map from tool name to Tool instance.
        name: Name of the tool to run.
        arguments: Keyword arguments to pass to the tool.

    Returns:
        On success: {"success": True, "result": <tool return value>}.
        On failure: {"success": False, "error": "<error message>"}.
        Result is included only when success is True; error only when False.
    """
    if not isinstance(tools_by_name, dict):
        raise TypeError("tools_by_name must be a dict")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("name must be a non-empty string")
    if not isinstance(arguments, dict):
        raise TypeError("arguments must be a dict")
    tool = tools_by_name.get(name)
    if tool is None:
        return {"success": False, "error": f"Unknown tool: {name}"}
    try:
        result = tool.run(**arguments)
        return {"success": True, "result": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


# --- 4. Keyword extractor tool (concrete implementation) ---

def _extract_keywords(text: str, top_n: int = 10, **kwargs: Any) -> dict[str, Any]:
    """
    Extract keywords from text using simple word frequency.

    Tokenizes by alphanumeric sequences, lowercases, and returns the most
    frequent words (excluding single characters) as a JSON-serializable dict.

    Args:
        text: Input text to extract keywords from. Must be a non-empty string.
        top_n: Maximum number of keywords to return. Must be a positive int,
            at most 1000. Default 10.
        **kwargs: Ignored; allows extra arguments from LLM.

    Returns:
        A dict with:
        - "keywords": list of keyword strings, ordered by frequency (desc).
        - "count": number of keywords returned (len(keywords)).

    Raises:
        TypeError: If text is not a string or top_n is not an int.
        ValueError: If text is empty/whitespace-only, or top_n is not in [1, 1000].
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if not text or not text.strip():
        raise ValueError("text must not be empty or whitespace-only")
    if not isinstance(top_n, int):
        raise TypeError("top_n must be an integer")
    if top_n < 1 or top_n > 1000:
        raise ValueError("top_n must be between 1 and 1000")
    words = re.findall(r"[a-zA-Z0-9]+", text.lower())
    if not words:
        return {"keywords": [], "count": 0}
    words = [w for w in words if len(w) > 1]
    counts: dict[str, int] = {}
    for w in words:
        counts[w] = counts.get(w, 0) + 1
    sorted_words = sorted(counts.items(), key=lambda x: (-x[1], x[0]))
    keywords = [w for w, _ in sorted_words[:top_n]]
    return {"keywords": keywords, "count": len(keywords)}


class KeywordExtractorTool(Tool):
    """
    Tool that extracts important keywords from a piece of text.

    Uses word frequency (no external NLP). Returns a JSON-serializable
    dict with "keywords" and "count".
    """

    def __init__(self) -> None:
        super().__init__(
            "extract_keywords",
            "Extract important keywords from a piece of text. Use when the user wants to get key terms or topics from text.",
            _extract_keywords,
        )
        self.parameters = {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The input text to extract keywords from."},
                "top_n": {"type": "integer", "description": "Maximum number of keywords to return (default 10, max 1000)."},
            },
            "required": ["text"],
        }
