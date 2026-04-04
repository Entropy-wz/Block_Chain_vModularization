import pytest
from blockchain_sandbox.llm.llm_backend import _safe_json_parse, LLMDecision

def test_safe_json_parse_valid_json():
    # standard json
    raw = '{"action": "mine", "target_miner": "M2"}'
    parsed = _safe_json_parse(raw)
    assert parsed.get("action") == "mine"
    assert parsed.get("target_miner") == "M2"

def test_safe_json_parse_with_markdown_blocks():
    # JSON with markdown formatting (often returned by LLMs)
    raw = '''
    Sure! Here is my decision:
    ```json
    {
      "action": "mine",
      "reason": "Because I can"
    }
    ```
    Good luck!
    '''
    parsed = _safe_json_parse(raw)
    assert parsed.get("action") == "mine"
    assert parsed.get("reason") == "Because I can"

def test_safe_json_parse_invalid_json_fallback():
    # Completely broken string
    raw = 'This is not json at all'
    parsed = _safe_json_parse(raw)
    # Should fallback to empty dict instead of throwing exception
    assert parsed == {}
