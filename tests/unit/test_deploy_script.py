"""
Archivo: test_deploy_script.py
Fecha de modificación: 28/10/2026
Autor: Alex Prieto Romani <alexprieto1997@gmail.com>

Descripción:
Pruebas unitarias del script POSIX de despliegue a Hugging Face Spaces
(`scripts/deploy_hf.sh`): sintaxis, permisos, contexto Docker, validación de
`HF_TOKEN`, normalización de `HF_SPACE_ID`, `--dry-run` y restauración de
`README.md`. Los casos de ejecución usan una copia temporal del script para no
depender del `.env` ni del estado git del repositorio real.

Ejemplo de Integración:
    uv run python -m pytest tests/unit/test_deploy_script.py -q
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SCRIPT = REPO_ROOT / "scripts" / "deploy_hf.sh"
DOCKERIGNORE = REPO_ROOT / ".dockerignore"


def _copy_workspace(tmp_path: Path) -> Path:
    """Crea un repo mínimo temporal con el script y un README sin frontmatter."""
    workspace = tmp_path / "repo"
    (workspace / "scripts").mkdir(parents=True)
    shutil.copy2(DEPLOY_SCRIPT, workspace / "scripts" / "deploy_hf.sh")
    (workspace / "README.md").write_text("# AgroVisión\n", encoding="utf-8")
    return workspace


def _clean_env(**overrides: str) -> dict[str, str]:
    """Entorno sin credenciales heredadas, con overrides explícitos."""
    env = os.environ.copy()
    for key in ("HF_TOKEN", "HF_SPACE_ID"):
        env.pop(key, None)
    env.update(overrides)
    return env


def _run(
    workspace: Path, *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Ejecuta la copia temporal del script y captura stdout/stderr."""
    return subprocess.run(
        [str(workspace / "scripts" / "deploy_hf.sh"), *args],
        cwd=workspace,
        env=env if env is not None else _clean_env(),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_script_exists_with_executable_bit_and_strict_mode() -> None:
    """El script existe, es ejecutable y declara el modo estricto de Bash."""
    assert DEPLOY_SCRIPT.is_file()
    assert os.access(DEPLOY_SCRIPT, os.X_OK)
    source = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    assert "set -euo pipefail" in source
    assert "--dry-run" in source
    assert "scripts/build.sh" in source
    assert "trap cleanup EXIT" in source


@pytest.mark.parametrize(
    "script",
    sorted((REPO_ROOT / "scripts").glob("*.sh")),
    ids=lambda path: path.name,
)
def test_shell_scripts_pass_bash_syntax_check(script: Path) -> None:
    """Todos los scripts POSIX superan `bash -n` sin errores de sintaxis."""
    result = subprocess.run(
        ["bash", "-n", str(script)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_dockerignore_excludes_agent_workspaces() -> None:
    """El contexto Docker no incluye los directorios de agentes/herramientas."""
    ignored = {
        line.strip()
        for line in DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    assert ".opencode/" in ignored
    assert ".project-suite/" in ignored


def test_dry_run_succeeds_without_token_and_preserves_readme(tmp_path: Path) -> None:
    """Un dry-run sin token valida el entorno y no toca README ni compila."""
    workspace = _copy_workspace(tmp_path)
    readme_before = (workspace / "README.md").read_text(encoding="utf-8")

    result = _run(workspace, "--dry-run")

    assert result.returncode == 0, result.stderr
    assert "[dry-run]" in result.stdout
    assert "alexp97/agrovision" in result.stdout
    assert "HF_TOKEN: no configurado" in result.stdout
    assert "Se ejecutaría: ./scripts/build.sh" in result.stdout
    assert (workspace / "README.md").read_text(encoding="utf-8") == readme_before


def test_dry_run_does_not_leak_hf_token(tmp_path: Path) -> None:
    """El token configurado nunca aparece en la salida del dry-run."""
    workspace = _copy_workspace(tmp_path)
    token = "hf_supersecret_token_123"

    result = _run(workspace, "--dry-run", env=_clean_env(HF_TOKEN=token))

    assert result.returncode == 0, result.stderr
    combined = result.stdout + result.stderr
    assert token not in combined
    assert "HF_TOKEN: configurado (oculto)" in result.stdout


@pytest.mark.parametrize("legacy_space_id", ["", "alexprieto/agrovision"])
def test_dry_run_normalizes_default_space_id(
    tmp_path: Path, legacy_space_id: str
) -> None:
    """Un Space vacío o heredado se normaliza al id oficial por defecto."""
    workspace = _copy_workspace(tmp_path)

    result = _run(
        workspace,
        "--dry-run",
        env=_clean_env(HF_TOKEN="hf_fake", HF_SPACE_ID=legacy_space_id),
    )

    assert result.returncode == 0, result.stderr
    assert "alexp97/agrovision" in result.stdout
    assert "alexprieto/agrovision" not in result.stdout


def test_dry_run_honors_space_override_and_force(tmp_path: Path) -> None:
    """`--space` prevalece sobre HF_SPACE_ID y `--force` aparece en el plan."""
    workspace = _copy_workspace(tmp_path)

    result = _run(
        workspace,
        "--dry-run",
        "--force",
        "--space",
        "otro/space",
        env=_clean_env(HF_TOKEN="hf_fake", HF_SPACE_ID="ignorado/space"),
    )

    assert result.returncode == 0, result.stderr
    assert "otro/space" in result.stdout
    assert "ignorado/space" not in result.stdout
    assert "--force" in result.stdout


def test_missing_token_fails_with_controlled_error(tmp_path: Path) -> None:
    """Sin token y sin dry-run el script falla con un mensaje claro y sin tocar README."""
    workspace = _copy_workspace(tmp_path)
    readme_before = (workspace / "README.md").read_text(encoding="utf-8")

    result = _run(workspace)

    assert result.returncode == 1
    assert "falta HF_TOKEN" in result.stderr
    assert (workspace / "README.md").read_text(encoding="utf-8") == readme_before


def test_invalid_space_id_is_rejected(tmp_path: Path) -> None:
    """Un Space sin formato <usuario>/<space> se rechaza antes de construir."""
    workspace = _copy_workspace(tmp_path)

    result = _run(
        workspace,
        "--dry-run",
        "--space",
        "sin-slash",
        env=_clean_env(HF_TOKEN="hf_fake"),
    )

    assert result.returncode == 1
    assert "Space inválido" in result.stderr


def test_unknown_option_is_rejected(tmp_path: Path) -> None:
    """Una opción desconocida devuelve código 2 y muestra la ayuda."""
    workspace = _copy_workspace(tmp_path)

    result = _run(workspace, "--desconocida")

    assert result.returncode == 2
    assert "opción desconocida" in result.stderr
    assert "Uso:" in result.stderr
