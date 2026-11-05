import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp")
pytest.importorskip("PIL")

EX = Path(__file__).parent.parent / "examples"


async def _run(tmp_path):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(command=sys.executable, args=["-m", "scenelang.mcp_server"], cwd=str(tmp_path),
                                  env={**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent)})
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = {t.name for t in (await s.list_tools()).tools}
            text = (EX / "pixel_heroi.yaml").read_text(encoding="utf-8")

            async def call(name, **kw):
                res = await s.call_tool(name, kw)
                return res.content[0].text

            v = json.loads(await call("scenelang_validate", scene_yaml=text))
            c = json.loads(await call("scenelang_compile", scene_yaml=text))
            bad = json.loads(await call("scenelang_validate", scene_yaml="scene: x\nentities: [oi]"))
            p = json.loads(await call("scenelang_pack", scene_yaml=text, out_dir=str(tmp_path / "o"), only="text"))
            return tools, v, c, bad, p


def test_servidor_mcp_stdio_de_ponta_a_ponta(tmp_path):
    tools, v, c, bad, p = asyncio.run(_run(tmp_path))
    assert {"scenelang_primer", "scenelang_validate", "scenelang_compile", "scenelang_pack", "scenelang_measure", "scenelang_locate"} <= tools
    assert v["ok"] is True and c["ok"] is True and c["output"]
    assert bad["ok"] is False and bad["errors"]
    assert p["ok"] and p["prompt"] and (tmp_path / "o" / "prompt.txt").exists()
