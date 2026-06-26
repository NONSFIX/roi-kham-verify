# Thai Word Splitter — Python Library Plan

**Goal:** A reusable Python module `thai_tokenizer` that any project can `import` and call.

---

## Phase 1 — Project Setup

- Create project folder `thai-tokenizer/`
- Create `pyproject.toml` with metadata and dependencies (`pythainlp`, `requests`)
- Create `requirements.txt` for quick install
- Create `.gitignore`

---

## Phase 2 — Core Module

Create `thai_tokenizer/__init__.py` that exposes the main API:

```
thai_tokenizer/
├── __init__.py        ← public API (what other projects import)
├── tokenizer.py       ← core split logic, engine selection
├── cleaner.py         ← strip whitespace, normalize before tokenizing
└── formatter.py       ← output as list / joined string / dict with positions
```

**Functions to expose:**

| Function | Returns | Description |
|---|---|---|
| `split(text, engine="newmm")` | `list[str]` | Split Thai text into words |
| `split_with_positions(text)` | `list[dict]` | Words with start/end character positions |
| `join(words, sep=" + ")` | `str` | Rejoin word list with separator |
| `available_engines()` | `list[str]` | List all supported engines |

---

## Phase 3 — Engine Support

Support these engines with graceful fallback:

| Engine | Type | Availability |
|---|---|---|
| `newmm` | Dictionary (default) | Built-in |
| `longest` | Dictionary | Built-in |
| `deepcut` | ML-based | Optional |
| `attacut` | Neural network | Optional |

If an optional engine is not installed → raise a clear `EngineNotInstalledError` with install instructions.

---

## Phase 4 — Tests

Create `tests/test_tokenizer.py`:

- Test basic split: `รถไฟ` → `["รถ", "ไฟ"]`
- Test sentence: `รถไฟวิ่งเร็วมาก` → `["รถไฟ", "วิ่ง", "เร็ว", "มาก"]`
- Test empty string
- Test non-Thai text passthrough
- Test each engine

Run with `pytest`

---

## Phase 5 — Usage Example File

Create `examples/basic_usage.py`:

```python
from thai_tokenizer import split, split_with_positions, join

# Basic split
words = split("รถไฟวิ่งเร็วมาก")
print(join(words))  # รถไฟ + วิ่ง + เร็ว + มาก

# With positions
positions = split_with_positions("รถไฟ")
# [{"word": "รถ", "start": 0, "end": 1}, {"word": "ไฟ", "start": 2, "end": 3}]

# Change engine
words = split("รถไฟ", engine="longest")

# List available engines
from thai_tokenizer import available_engines
print(available_engines())  # ["newmm", "longest", "deepcut", "attacut"]
```

---

## Phase 6 — README

`README.md` with:

- Install instructions
- Quick start code
- All function signatures
- Engine comparison table

---

## Deliverables

```
thai-tokenizer/
├── thai_tokenizer/
│   ├── __init__.py
│   ├── tokenizer.py
│   ├── cleaner.py
│   └── formatter.py
├── tests/
│   └── test_tokenizer.py
├── examples/
│   └── basic_usage.py
├── requirements.txt
├── pyproject.toml
└── README.md
```

---

## Prompt for Claude Code

> Build a Python library called `thai-tokenizer` following this plan. Use PyThaiNLP as the backend. The public API in `__init__.py` should export `split()`, `split_with_positions()`, `join()`, and `available_engines()`. Support engines: newmm (default), longest, deepcut, attacut — raise a clear error if an optional engine isn't installed. Include pytest tests and a `basic_usage.py` example. Use `pyproject.toml` for packaging.
