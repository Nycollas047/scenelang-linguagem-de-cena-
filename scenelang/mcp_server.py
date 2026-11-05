"""Servidor MCP (stdio) do scenelang: o modelo escreve a cena em YAML e chama estas ferramentas, sem copiar arquivos à mão.

Uso: `scenelang-mcp` (ou `python -m scenelang.mcp_server`). Requer `pip install "scenelang[mcp]"`.
Todas as ferramentas recebem o texto da cena (YAML) e devolvem JSON; arquivos são gravados em `out_dir`
(padrão: ./scenelang_out) e os caminhos voltam no resultado.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from . import api

DEFAULT_OUT = "scenelang_out"


def _j(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, default=api.plain)


def build():
    try:
        from mcp.server.mcpserver import MCPServer
    except ImportError:   # mcp 1.x
        try:
            from mcp.server.fastmcp import FastMCP as MCPServer
        except ImportError:
            sys.exit('falta o pacote mcp: pip install "scenelang[mcp]"')

    mcp = MCPServer("scenelang")

    @mcp.tool()
    def scenelang_primer() -> str:
        """Cartilha de uma página: como escrever uma cena em scenelang (YAML). Chame antes de escrever a primeira cena."""
        return api.primer()

    @mcp.tool()
    def scenelang_vocab() -> str:
        """Vocabulários fechados aceitos pela linguagem (direções, planos, âncoras, juntas de pose, etc.)."""
        return _j(api.vocab())

    @mcp.tool()
    def scenelang_new(template: str = "") -> str:
        """Cena inicial pronta para editar. Sem `template`, lista os modelos disponíveis."""
        if not template:
            from .templates import TEMPLATES

            return _j(sorted(TEMPLATES))
        return api.new(template)

    @mcp.tool()
    def scenelang_validate(scene_yaml: str, fix: bool = False) -> str:
        """Valida a cena e devolve todos os erros de uma vez (com caminho, valores aceitos e dica). Com fix=true aplica as correções seguras e devolve o YAML novo."""
        return _j(api.fix(scene_yaml) if fix else api.validate(scene_yaml))

    @mcp.tool()
    def scenelang_compile(scene_yaml: str, target: str = "prose", size: str = "") -> str:
        """Compila a cena em prompt. target: prose (texto para qualquer gerador) | json | regions (prompt por regiões). Devolve também o que o backend perde."""
        res = api.compile_scene(scene_yaml, target, size or None)
        if res.get("ok"):
            res["loss"] = api.loss_report(scene_yaml, target).get("items", [])
        return _j(res)

    @mcp.tool()
    def scenelang_check_layout(scene_yaml: str) -> str:
        """Roda os `asserts` (acima, esquerda de, dentro de, etc.) sobre as caixas declaradas, sem imagem."""
        return _j(api.check_layout(scene_yaml))

    @mcp.tool()
    def scenelang_render_schema(scene_yaml: str, out_dir: str = DEFAULT_OUT, width: int = 960) -> str:
        """Desenha o esquema 2D da cena (SVG/PNG) para conferir a composição antes de gerar a imagem."""
        return _j(api.render_schema(scene_yaml, out_dir, width))

    @mcp.tool()
    def scenelang_pose_sheet(scene_yaml: str, entity: str, out_path: str = f"{DEFAULT_OUT}/pose.svg", style: str = "mannequin") -> str:
        """Manequim ou folha de construção (caixas, cilindros, esferas) da `pose` em graus de uma entidade. style: mannequin | construction."""
        return _j(api.pose_sheet(scene_yaml, entity, out_path, style))

    @mcp.tool()
    def scenelang_pack(scene_yaml: str, out_dir: str = DEFAULT_OUT, only: str = "", guide_style: str = "blocks") -> str:
        """Gera os arquivos para o gerador de imagem: prompt.txt (sempre), guia.png (composição) e cena_unica.png (para chats com visão).
        only: text | guide | single (vazio = prompt.txt + guia + prompt_com_guia.txt). guide_style: blocks | seg (mapa de segmentação, sem borda nem texto).
        Para geradores só de prompt use o campo `prompt` devolvido."""
        return _j(api.pack_files(scene_yaml, out_dir, only or None, guide_style))

    @mcp.tool()
    def scenelang_measure(scene_yaml: str, image_path: str, out_dir: str = f"{DEFAULT_OUT}/rodada", boxes_json: str = "") -> str:
        """Mede a imagem gerada contra a cena (verificadores, posição, espelhamento) e devolve achados, correções, a cena da próxima rodada e o prompt_next.
        boxes_json (opcional): {"id": [x,y,w,h]} em frações 0..1 informadas por você olhando a imagem — mais confiável que a medição por cor."""
        boxes = json.loads(boxes_json) if boxes_json else None
        return _j(api.correct_round(scene_yaml, image_path, out_dir, boxes))

    @mcp.tool()
    def scenelang_locate(scene_yaml: str, image_path: str = "", boxes_json: str = "") -> str:
        """Onde cada entidade ficou na imagem e se a cena saiu espelhada. Sem image_path devolve o pedido (form) para você olhar a imagem e informar as caixas."""
        if not image_path:
            return _j(api.locate_form(scene_yaml))
        return _j(api.locate_image(scene_yaml, image_path, json.loads(boxes_json) if boxes_json else None))

    @mcp.tool()
    def scenelang_verify(scene_yaml: str, image_path: str) -> str:
        """Roda os `verify` da cena (paleta, grade de pixels, nº de cores, fundo, etc.) sobre a imagem gerada."""
        return _j(api.verify_image(scene_yaml, image_path))

    return mcp


def main() -> None:
    Path(DEFAULT_OUT)  # só documenta o padrão; as pastas são criadas pelas ferramentas
    build().run()


if __name__ == "__main__":
    main()
