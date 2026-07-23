#!/usr/bin/env python3
"""Capture a fully rendered Streamlit page through an existing Chrome CDP port.

Start Chrome with:
  google-chrome --headless --no-sandbox --remote-debugging-port=9223 about:blank
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import urllib.request
from pathlib import Path

import websockets


async def command(socket, message_id: int, method: str, params: dict | None = None):
    await socket.send(json.dumps({"id": message_id, "method": method, "params": params or {}}))
    while True:
        response = json.loads(await socket.recv())
        if response.get("id") == message_id:
            if "error" in response:
                raise RuntimeError(response["error"])
            return response.get("result", {})


async def capture(
    cdp_port: int,
    url: str,
    output: Path,
    width: int,
    height: int,
    wait_s: float,
    click_text: str | None,
):
    request = urllib.request.Request(
        f"http://127.0.0.1:{cdp_port}/json/new?{url}",
        method="PUT",
    )
    with urllib.request.urlopen(request) as response:
        target = json.load(response)

    async with websockets.connect(target["webSocketDebuggerUrl"], max_size=10_000_000) as socket:
        await command(socket, 1, "Page.enable")
        await command(
            socket,
            2,
            "Emulation.setDeviceMetricsOverride",
            {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": width < 768},
        )
        await command(socket, 3, "Page.navigate", {"url": url})
        await asyncio.sleep(wait_s)
        message_id = 4
        if click_text:
            text_literal = json.dumps(click_text)
            expression = (
                "Array.from(document.querySelectorAll('button,[role=\"tab\"],a'))"
                f".find(el => el.innerText.trim().includes({text_literal}))?.click()"
            )
            await command(
                socket,
                message_id,
                "Runtime.evaluate",
                {"expression": expression, "returnByValue": True},
            )
            message_id += 1
            await asyncio.sleep(2)
        result = await command(
            socket,
            message_id,
            "Page.captureScreenshot",
            {"format": "png", "captureBeyondViewport": False},
        )
        output.write_bytes(base64.b64decode(result["data"]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("output", type=Path)
    parser.add_argument("--cdp-port", type=int, default=9223)
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=1200)
    parser.add_argument("--wait", type=float, default=6)
    parser.add_argument("--click-text")
    args = parser.parse_args()
    asyncio.run(
        capture(
            args.cdp_port,
            args.url,
            args.output,
            args.width,
            args.height,
            args.wait,
            args.click_text,
        )
    )


if __name__ == "__main__":
    main()
