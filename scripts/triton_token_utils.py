from typing import Any, Dict, List, Tuple


def count_tokens_from_outputs(outputs: List[Dict[str, Any]], text: str = "") -> int:
    """Best-effort token count from Triton outputs.

    Looks for common length fields; falls back to a rough text-length heuristic.
    """
    if outputs:
        for o in outputs:
            name = str(o.get("name", "")).lower()
            data = o.get("data")
            if name in ("sequence_length", "output_len", "output_lengths") and data:
                try:
                    return int(data[0])
                except Exception:
                    continue

    if isinstance(text, str) and text:
        return max(1, int(len(text) / 4))
    return 0


def update_tokens_from_stream_event(
    tokens_generated: int, prev_text_len: int, data: Dict[str, Any]
) -> Tuple[int, int]:
    """Update token counters based on a Triton SSE event payload.

    Returns the updated (tokens_generated, prev_text_len).
    """
    if not isinstance(data, dict):
        return tokens_generated, prev_text_len

    if "token_id" in data or "output_token" in data:
        tokens_generated += 1
        return tokens_generated, prev_text_len

    if "tokens_generated" in data:
        try:
            tokens_generated += int(data.get("tokens_generated", 0))
            return tokens_generated, prev_text_len
        except Exception:
            pass

    if "text" in data and isinstance(data.get("text"), str):
        txt = data.get("text")
        if len(txt) > prev_text_len:
            delta = len(txt) - prev_text_len
            tokens_generated += max(0, int(delta / 4))
            prev_text_len = len(txt)

    return tokens_generated, prev_text_len
