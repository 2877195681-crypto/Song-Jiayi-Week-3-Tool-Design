# Keyword Extractor Tool & Agent Demo

## What the tool does

This project provides a **keyword extractor** exposed as an agent tool that an LLM can call. The core is a small framework in `tool.py`:

- **`Tool`** – Wrapper class: name, description, callable, and optional JSON Schema parameters. Tools expose `execute()` / `run()` and `to_dict()` for LLM APIs.
- **`KeywordExtractorTool`** – Extracts top-N keywords from text using word frequency (no external NLP). Returns a JSON-serializable dict: `{"keywords": [...], "count": N}`.
- **Helpers** – `tools_to_dict()`, `build_tool_selection_prompt()`, `parse_tool_call()` / `parse_tool_calls()`, and `execute_tool_call()` for registering tools, building prompts, parsing LLM output, and running tools with structured success/error responses.

## How to run the demo

```bash
pip install -r requirements.txt
python demo.py
```

- **With `DEEPSEEK_API_KEY` set** (e.g. via `.env`): Uses the DeepSeek API; the LLM chooses when to call the keyword tool and the demo executes it and shows the result, then runs error-handling examples.
- **Without the key**: Runs in simulation mode with hardcoded tool calls and the same error cases. A message indicates simulation mode.

## Injecting the API key

- **Option A – `.env` (recommended)**  
  Create a `.env` in the project root with:
  ```env
  DEEPSEEK_API_KEY=your-key-here
  ```
  `demo.py` calls `load_dotenv()`, so the key is loaded automatically.

- **Option B – Environment variable**  
  Set before running:
  - Windows (PowerShell): `$env:DEEPSEEK_API_KEY = "your-key-here"`
  - Linux/macOS: `export DEEPSEEK_API_KEY=your-key-here`

## Realistic use case

**Summarizing support tickets:** An agent has access to the keyword extractor. A user says: “What are the main topics in this ticket?” The agent calls `extract_keywords` on the ticket body, gets a list of terms (e.g. `["login", "password", "reset", "error"]`), and uses them to give a short summary or to route the ticket. The same tool can drive tagging, search indexing, or trend reports over many documents.

## Design decisions and limitations

- **Tool interface**: A single `Tool` class wraps any callable; no abstract base. This keeps the API minimal and makes it easy to add more tools (e.g. search, calculator) with the same pattern.
- **Return shape**: `execute_tool_call()` always returns `{"success": bool, "result": ...}` or `{"success": False, "error": str}` so the agent gets a consistent, JSON-serializable response.
- **Keyword logic**: Extraction is frequency-based on alphanumeric tokens; no stemming or stop-word list. Good for demos and simple use cases; for production you may plug in an NLP library or external API.
- **Demo modes**: DeepSeek is used when the key is present; otherwise the demo simulates the workflow so it runs without network or credentials. Error handling (bad input, unknown tool) is shared between both modes.
