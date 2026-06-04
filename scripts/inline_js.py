"""
Archivo: inline_js.py
Fecha de modificación: 04/06/2026
Autor: Equipo AgroVisión

Descripción:
Post-procesa el HTML del build de Astro para que funcione bajo **sub-paths dinámicos**
(como los slugs `/_w_xxxx/` de ShinyApps.io). Inyecta inline los scripts que Astro
hubiera emitido en `/_astro/*.js` y normaliza las rutas de assets (favicon, JS) de
**absolutas a relativas**, ya que el host sirve la app desde una ruta distinta de la raíz.
Es la implementación de la "Regla de Oro" de `docs/doc_guia/plan_replication.md`.

Nota: nuestra UI ya usa scripts `is:inline` y `inlineStylesheets: 'always'`, por lo que
normalmente no hay `/_astro/*.js` externos; este script es idempotente y a prueba de
futuro (si se añade una isla/componente que genere JS externo, queda inlineado).

Acciones Principales:
    - Inyecta el contenido de los scripts `/_astro/*.js` directamente en el HTML.
    - Convierte las rutas absolutas de favicon a relativas.
    - Normaliza cualquier referencia absoluta restante a `/_astro/`.

Estructura Interna:
    - `inline_scripts`: inyecta el código JS externo inline.
    - `fix_favicon_paths`: relativiza las rutas de iconos.
    - `fix_absolute_asset_refs`: relativiza las rutas absolutas restantes.
    - `main`: orquesta el post-proceso sobre `frontend/dist/index.html`.

Entradas / Dependencias:
    - Biblioteca estándar (`re`, `pathlib`).

Salidas / Efectos:
    - Reescribe `frontend/dist/index.html` in place.

Ejecución:
    uv run python scripts/inline_js.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

DIST = Path("frontend/dist")
HTML_FILE = DIST / "index.html"


def inline_scripts(html: str) -> str:
    """
    Reemplaza cada `<script ... src="/_astro/...">` por su contenido inline.

    Args:
        html (str): HTML de entrada.

    Returns:
        str: HTML con los scripts de Astro embebidos inline.
    """

    def _replace(match: re.Match) -> str:  # type: ignore[type-arg]
        src = match.group(1)
        rel = src.lstrip("/")  # la URL parte de "/"; el archivo es relativo a DIST
        js_path = DIST / rel
        if js_path.exists():
            content = js_path.read_text(encoding="utf-8")
            return f'<script type="module">{content}</script>'
        print(f"  [WARN] JS no encontrado: {js_path}", file=sys.stderr)
        return match.group(0)

    pattern = (
        r'<script\s[^>]*type=["\']module["\'][^>]*'
        r'src=["\'](\/_astro\/[^"\']+)["\'][^>]*>\s*</script>'
    )
    return re.sub(pattern, _replace, html)


def fix_favicon_paths(html: str) -> str:
    """Convierte rutas absolutas `/favicon.*` a relativas `./favicon.*`."""
    html = re.sub(r'href="\/favicon\.', 'href="./favicon.', html)
    html = re.sub(r"href='\/favicon\.", "href='./favicon.", html)
    return html


def fix_absolute_asset_refs(html: str) -> str:
    """Convierte cualquier referencia absoluta restante a `/_astro/` en relativa."""
    html = html.replace('href="/_astro/', 'href="./_astro/')
    html = html.replace("href='/_astro/", "href='./_astro/")
    html = html.replace('src="/_astro/', 'src="./_astro/')
    html = html.replace("src='/_astro/", "src='./_astro/")
    return html


def main() -> None:
    """
    Aplica el post-proceso sobre `frontend/dist/index.html` in place.

    Raises:
        SystemExit: si no existe el HTML del build (código 1).
    """
    if not HTML_FILE.exists():
        print(f"[ERROR] No se encontró {HTML_FILE}. Ejecuta 'pnpm build' (en frontend/) primero.")
        sys.exit(1)

    html = HTML_FILE.read_text(encoding="utf-8")
    original_len = len(html)

    html = inline_scripts(html)
    html = fix_favicon_paths(html)
    html = fix_absolute_asset_refs(html)

    HTML_FILE.write_text(html, encoding="utf-8")

    remaining = re.findall(r'["\']/_astro/', html)
    if remaining:
        print(f"[WARN] Aún quedan {len(remaining)} referencias a /_astro/ sin convertir.")
    else:
        print(f"[OK] inline_js.py completado ({original_len} -> {len(html)} bytes).")
        print("     No quedan referencias absolutas a /_astro/ en index.html.")


if __name__ == "__main__":
    main()
