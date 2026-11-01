---
name: subprocess-cli-runner
description: >-
  Recipes for safe AI subprocess execution and output parsing in NutriPilot:
  command templates for agy/claude/codex, stdin piping, Windows process-tree termination,
  and non-greedy DOTALL regex parsing.
---

# AI Subprocess Runner & Output Protocol Parser

This skill governs the execution of local AI CLI tools and the parsing of structured tags in NutriPilot v1.

## 1. Subprocess Execution (`app/ai_runner.py`)

### 1.1 Invariants
- **Never `shell=True`**. Always pass an argument vector list.
- Use `shlex.split` safely on Windows and POSIX.
- Working directory must be `DATA_DIR` so CLI tools can read referenced markdown sources and example plans.
- Substitute `{prompt}` in argv if present; otherwise stream UTF-8 bytes to the child process's **stdin**.
- Strip ANSI escape sequences from output before returning.

### 1.2 Windows Process-Tree Termination
When a timeout occurs, kill the entire process tree to prevent orphan processes:
```python
import sys
import subprocess

def terminate_process_tree(proc: subprocess.Popen):
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    else:
        import os
        import signal
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
```

## 2. Default CLI Templates (`app/defaults.py`)

Templates must be non-interactive, read-only, and produce plain text:
- **`agy`**:
  ```text
  agy --print --sandbox --disable-slash-commands --output-format text
  ```
- **`claude`**:
  ```text
  claude -p --allowedTools "Read,Glob,Grep"
  ```
- **`codex`**:
  ```text
  codex exec --sandbox read-only -
  ```

## 3. Pure Block Parsers (`app/parsers.py`)

### 3.1 Non-Greedy DOTALL Regex
Extract `<meta>...</meta>` and `<plan>...</plan>`:
```python
import re
import json

META_REGEX = re.compile(r"<meta>(.*?)</meta>", re.DOTALL)
PLAN_REGEX = re.compile(r"<plan>(.*?)</plan>", re.DOTALL)

def split_blocks(text: str) -> tuple[str, list[dict], str | None, list[str]]:
    errors = []
    meta_dicts = []
    
    # Extract meta blocks
    for match in META_REGEX.finditer(text):
        raw_json = match.group(1).strip()
        try:
            data = json.loads(raw_json)
            if isinstance(data, dict):
                meta_dicts.append(data)
            else:
                errors.append(f"Meta block contains non-dict JSON: {raw_json}")
        except json.JSONDecodeError as e:
            errors.append(f"Malformed JSON in <meta>: {e}")

    # Extract plan blocks (last one wins)
    plan_matches = list(PLAN_REGEX.finditer(text))
    plan_md = plan_matches[-1].group(1).strip() if plan_matches else None

    # Strip blocks from visible conversational text
    visible_text = PLAN_REGEX.sub("", META_REGEX.sub("", text)).strip()

    # Rule: If parse failed, ensure raw text remains visible so nothing is silently lost
    if errors and not visible_text:
        visible_text = text.strip()

    return visible_text, meta_dicts, plan_md, errors
```

### 3.2 Metadata Filtering (`filter_meta`)
- Keep only defined, live keys.
- Strip string values; drop empty values.
- Compare with current client meta: drop keys whose values are unchanged.
- Return format: `{key: {"new": str, "old": str | None}}`.
