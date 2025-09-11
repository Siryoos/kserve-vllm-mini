#!/usr/bin/env python3
"""
OpenAI API parity probe.
Checks support for tools/function-calling, parallel tool calls, JSON mode,
logprobs, and streaming shape quirks for an OpenAI-compatible endpoint.

Outputs a capability matrix JSON and optional HTML summary.
"""

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx


@dataclass
class ProbeResult:
    supported: bool
    details: Optional[str] = None


class ParityProber:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: Optional[str] = None,
        insecure: bool = False,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.verify = not insecure

    def _headers(self) -> Dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    async def _post(self, path: str, payload: Dict[str, Any], stream: bool = False):
        url = f"{self.base_url}{path}"
        async with httpx.AsyncClient(
            verify=self.verify, http2=False, timeout=60
        ) as client:
            if stream:
                return await client.stream(
                    "POST", url, headers=self._headers(), json=payload
                )
            else:
                return await client.post(url, headers=self._headers(), json=payload)

    async def probe_tools(self) -> ProbeResult:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": "What is the weather in San Francisco?"}
            ],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "get_current_weather",
                        "description": "Get the current weather",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "location": {"type": "string"},
                                "unit": {
                                    "type": "string",
                                    "enum": ["celsius", "fahrenheit"],
                                },
                            },
                            "required": ["location"],
                        },
                    },
                }
            ],
            "tool_choice": "auto",
        }
        try:
            resp = await self._post("/v1/chat/completions", payload)
            ok = resp.status_code == 200
            data = resp.json() if ok else {}
            choice = (data.get("choices") or [{}])[0]
            tool_calls = choice.get("message", {}).get("tool_calls")
            supported = ok and isinstance(tool_calls, list)
            return ProbeResult(
                supported=supported,
                details=(
                    None
                    if supported
                    else f"status={resp.status_code}, tool_calls={tool_calls}"
                ),
            )
        except Exception as e:
            return ProbeResult(False, str(e))

    async def probe_parallel_tools(self) -> ProbeResult:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": "For NYC and SF, get weather and timezone."}
            ],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "parameters": {
                            "type": "object",
                            "properties": {"city": {"type": "string"}},
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "get_timezone",
                        "parameters": {
                            "type": "object",
                            "properties": {"city": {"type": "string"}},
                        },
                    },
                },
            ],
            "tool_choice": "auto",
        }
        try:
            resp = await self._post("/v1/chat/completions", payload)
            if resp.status_code != 200:
                return ProbeResult(False, f"status={resp.status_code}")
            data = resp.json()
            tool_calls = (data.get("choices") or [{}])[0].get("message", {}).get(
                "tool_calls"
            ) or []
            supported = len(tool_calls) >= 2
            return ProbeResult(supported, details=f"tool_calls={len(tool_calls)}")
        except Exception as e:
            return ProbeResult(False, str(e))

    async def probe_json_mode(self) -> ProbeResult:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": "Return a JSON with keys city and temp."}
            ],
            "response_format": {"type": "json_object"},
        }
        try:
            resp = await self._post("/v1/chat/completions", payload)
            if resp.status_code != 200:
                return ProbeResult(False, f"status={resp.status_code}")
            data = resp.json()
            content = (
                (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
            )
            # Validate that content parses as JSON
            try:
                json.loads(content)
                return ProbeResult(True)
            except Exception as e:
                return ProbeResult(False, f"not json: {e}")
        except Exception as e:
            return ProbeResult(False, str(e))

    async def probe_logprobs(self) -> ProbeResult:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": "Say: test"}],
            "max_tokens": 4,
            "logprobs": True,
        }
        try:
            resp = await self._post("/v1/chat/completions", payload)
            if resp.status_code != 200:
                return ProbeResult(False, f"status={resp.status_code}")
            data = resp.json()
            choice = (data.get("choices") or [{}])[0]
            # OpenAI streams logprobs differently across models; check presence of any logprobs field
            has_lp = bool(
                choice.get("logprobs")
                or choice.get("top_logprobs")
                or choice.get("delta", {}).get("logprobs")
            )
            return ProbeResult(
                has_lp, details=None if has_lp else "no logprobs in response"
            )
        except Exception as e:
            return ProbeResult(False, str(e))

    async def probe_streaming(self) -> ProbeResult:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": "Stream 10 words numbered 1..10."}
            ],
            "stream": True,
            "max_tokens": 80,
        }
        try:
            async with await self._post(
                "/v1/chat/completions", payload, stream=True
            ) as resp:
                if resp.status_code != 200:
                    return ProbeResult(False, f"status={resp.status_code}")
                chunks = 0
                first_chunk_ms = None
                import time

                t0 = time.time()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    if first_chunk_ms is None:
                        first_chunk_ms = (time.time() - t0) * 1000
                    chunks += 1
                # Expect multiple SSE chunks and reasonable TTFT
                ok = chunks >= 2 and (first_chunk_ms is None or first_chunk_ms < 5000)
                return ProbeResult(
                    ok,
                    details=f"chunks={chunks}, ttft_ms={first_chunk_ms:.1f} if first_chunk_ms else 'n/a'",
                )
        except Exception as e:
            return ProbeResult(False, str(e))

    async def run(self) -> Dict[str, Any]:
        tools = await self.probe_tools()
        parallel = await self.probe_parallel_tools()
        json_mode = await self.probe_json_mode()
        logprobs = await self.probe_logprobs()
        streaming = await self.probe_streaming()

        return {
            "endpoint": self.base_url,
            "model": self.model,
            "capabilities": {
                "tools_function_calling": tools.__dict__,
                "parallel_tool_calls": parallel.__dict__,
                "json_mode": json_mode.__dict__,
                "logprobs": logprobs.__dict__,
                "streaming": streaming.__dict__,
            },
            "summary": {
                "supported_count": sum(
                    1
                    for p in [tools, parallel, json_mode, logprobs, streaming]
                    if p.supported
                ),
                "total": 5,
            },
        }


def main():
    ap = argparse.ArgumentParser(description="OpenAI API parity probe")
    ap.add_argument(
        "--url", required=True, help="Base URL of endpoint (OpenAI-compatible)"
    )
    ap.add_argument("--model", required=True)
    ap.add_argument("--api-key", default=None)
    ap.add_argument("--insecure", action="store_true")
    ap.add_argument("--out", default="capability_matrix.json")
    ap.add_argument("--html", default=None, help="Optional HTML report path")
    args = ap.parse_args()

    async def run_and_write():
        prober = ParityProber(args.url, args.model, args.api_key, args.insecure)
        res = await prober.run()
        with open(args.out, "w") as f:
            json.dump(res, f, indent=2)
        print(f"✅ Capability matrix written to {args.out}")

        if args.html:
            html = f"""
<!DOCTYPE html>
<html><head><meta charset='utf-8'><title>Capability Matrix</title>
<style>body{{font-family:Arial;padding:20px}} .ok{{color:green}} .no{{color:red}}</style>
</head><body>
<h1>OpenAI Parity Capability Matrix</h1>
<p><b>Endpoint:</b> {res["endpoint"]} &nbsp; <b>Model:</b> {res["model"]}</p>
<ul>
  <li>Tools/function-calling: <span class='{"ok" if res["capabilities"]["tools_function_calling"]["supported"] else "no"}'>{res["capabilities"]["tools_function_calling"]["supported"]}</span></li>
  <li>Parallel tool calls: <span class='{"ok" if res["capabilities"]["parallel_tool_calls"]["supported"] else "no"}'>{res["capabilities"]["parallel_tool_calls"]["supported"]}</span></li>
  <li>JSON mode: <span class='{"ok" if res["capabilities"]["json_mode"]["supported"] else "no"}'>{res["capabilities"]["json_mode"]["supported"]}</span></li>
  <li>Logprobs: <span class='{"ok" if res["capabilities"]["logprobs"]["supported"] else "no"}'>{res["capabilities"]["logprobs"]["supported"]}</span></li>
  <li>Streaming: <span class='{"ok" if res["capabilities"]["streaming"]["supported"] else "no"}'>{res["capabilities"]["streaming"]["supported"]}</span></li>
</ul>
</body></html>
"""
            with open(args.html, "w") as f:
                f.write(html)
            print(f"📄 HTML report written to {args.html}")

    asyncio.run(run_and_write())


if __name__ == "__main__":
    sys.exit(main())
