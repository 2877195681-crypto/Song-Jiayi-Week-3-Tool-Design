"""
Demo: Tool called by an agent/workflow, successful execution, and error handling.

Supports two modes:
- If DEEPSEEK_API_KEY is set: use DeepSeek API for a real LLM agent that selects and calls the tool.
- If not set: run simulation workflow with hardcoded tool calls and error cases.
"""

import json
import os

from dotenv import load_dotenv

load_dotenv()

from tool import (
    KeywordExtractorTool,
    build_tool_selection_prompt,
    execute_tool_call,
    tools_to_dict,
)


def setup_tools():
    """Create tools and tool registry. Shared by both modes."""
    keyword_tool = KeywordExtractorTool()
    tools = [keyword_tool]
    tools_by_name = {t.name: t for t in tools}
    return tools, tools_by_name


def run_deepseek_agent() -> None:
    """
    Use DeepSeek API: send a user message and let the LLM decide to call the tool.
    Then execute the tool and show the result.
    """
    from openai import OpenAI

    tools, tools_by_name = setup_tools()
    tool_defs = tools_to_dict(tools)

    print("=== Mode: DeepSeek API (real LLM agent) ===\n")
    print("Registered tools (for LLM API):")
    for d in tool_defs:
        print(f"  - {d['function']['name']}: {d['function']['description'][:50]}...")
    print()

    client = OpenAI(
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url="https://api.deepseek.com",
    )

    user_message = (
        "Please extract the top 5 keywords from this text: "
        "'Python is great. Python is easy. Learn Python and have fun with Python.'"
    )
    print(f"User: {user_message}\n")

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": user_message}],
        tools=tool_defs,
        tool_choice="auto",
    )

    message = response.choices[0].message
    if not message.tool_calls:
        print("LLM did not call a tool. Reply:")
        print(message.content or "(empty)\n")
        return

    for tc in message.tool_calls:
        name = tc.function.name
        try:
            arguments = json.loads(tc.function.arguments) if tc.function.arguments else {}
        except ValueError:
            arguments = {}
        print(f"Agent receives tool call: {name}(...)")
        result = execute_tool_call(tools_by_name, name, arguments)
        if result["success"]:
            r = result["result"]
            print(f"Success. Keywords: {r.get('keywords', r)}")
            print(f"Count: {r.get('count', 'N/A')}\n")
        else:
            print(f"Error: {result['error']}\n")

    # Error handling (bad input) — same as simulation
    print("=== Error handling (bad input) ===\n")
    bad_cases = [
        {"text": "", "top_n": 5},
        {"text": "   ", "top_n": 5},
        {"text": "Hello world", "top_n": -1},
    ]
    for i, arguments in enumerate(bad_cases, 1):
        print(f"Bad input {i}: arguments = {arguments}")
        resp = execute_tool_call(tools_by_name, "extract_keywords", arguments)
        print(f"  Error: {resp['error']}\n")
    print("Unknown tool call:")
    resp = execute_tool_call(tools_by_name, "nonexistent_tool", {"x": 1})
    print(f"  Error: {resp['error']}\n")


def run_simulation_workflow() -> None:
    """
    Simulate an agent/workflow with hardcoded tool calls.
    No API key required. Same tool setup, success, and error handling as before.
    """
    tools, tools_by_name = setup_tools()
    tool_defs = tools_to_dict(tools)
    prompt = build_tool_selection_prompt(tools)

    print("=== 1. Tool used by agent/workflow ===\n")
    print("Registered tools (for LLM API):")
    for d in tool_defs:
        print(f"  - {d['function']['name']}: {d['function']['description'][:50]}...")
    print("\nTool selection prompt (first 3 lines):")
    for line in prompt.split("\n")[:3]:
        print(f"  {line}")
    print("  ...\n")

    print("=== 2. Successful execution ===\n")
    tool_call = {
        "name": "extract_keywords",
        "arguments": {
            "text": "Python is great. Python is easy. Learn Python and have fun with Python.",
            "top_n": 5,
        },
    }
    print(f"Agent receives tool call: {tool_call['name']}(...)")
    response = execute_tool_call(
        tools_by_name,
        tool_call["name"],
        tool_call["arguments"],
    )
    if response["success"]:
        result = response["result"]
        print(f"Success. Keywords: {result['keywords']}")
        print(f"Count: {result['count']}\n")
    else:
        print(f"Error: {response['error']}\n")

    print("=== 3. Error handling (bad input) ===\n")
    bad_cases = [
        {"text": "", "top_n": 5},
        {"text": "   ", "top_n": 5},
        {"text": "Hello world", "top_n": -1},
        {"text": "Hello world", "top_n": 99999},
    ]
    for i, arguments in enumerate(bad_cases, 1):
        print(f"Bad input {i}: arguments = {arguments}")
        response = execute_tool_call(tools_by_name, "extract_keywords", arguments)
        if response["success"]:
            print(f"  Result: {response['result']}")
        else:
            print(f"  Error: {response['error']}")
        print()

    print("Unknown tool call:")
    response = execute_tool_call(tools_by_name, "nonexistent_tool", {"x": 1})
    print(f"  Error: {response['error']}\n")


if __name__ == "__main__":
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if api_key and api_key.strip():
        run_deepseek_agent()
    else:
        print("DEEPSEEK_API_KEY not set - running in simulation mode (no API calls).\n")
        run_simulation_workflow()
