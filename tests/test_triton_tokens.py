import importlib.util
import pathlib


def import_utils():
    path = pathlib.Path("scripts/triton_token_utils.py")
    spec = importlib.util.spec_from_file_location("triton_token_utils", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


def test_count_tokens_from_outputs_length_fields():
    utils = import_utils()
    outputs = [
        {"name": "output_lengths", "data": [17]},
        {"name": "text_output", "data": ["hello"]},
    ]
    assert utils.count_tokens_from_outputs(outputs) == 17


def test_count_tokens_from_outputs_text_fallback():
    utils = import_utils()
    outputs = [{"name": "text_output", "data": ["hello world!"]}]
    # 12 chars -> ~3 tokens
    assert utils.count_tokens_from_outputs(outputs, "hello world!") >= 2


def test_update_tokens_from_stream_event_token_id():
    utils = import_utils()
    tokens, prev = utils.update_tokens_from_stream_event(0, 0, {"token_id": 123})
    assert tokens == 1 and prev == 0


def test_update_tokens_from_stream_event_text_growth():
    utils = import_utils()
    tokens, prev = utils.update_tokens_from_stream_event(0, 0, {"text": "abcd"})
    # 4 chars -> ~1 token
    assert tokens >= 1 and prev == 4
