"""Test suite for .env.example — validación de variables, ejemplos y rutas paso a paso.

Este test verifica que .env.example:
1. Contiene todas las variables de entorno necesarias documentadas.
2. No expone secretos reales (solo placeholders/dummies seguros).
3. Incluye instrucciones paso a paso y ejemplos de formato para cada plataforma
   (Supabase, Copernicus, Groq, Hugging Face).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# Ruta relativa al repositorio (el test se ejecuta desde la raíz)
ENV_EXAMPLE_PATH = Path(".env.example")

# ── Expected variables and their expected placeholder format ───────────────────

ENV_EXPECTED: dict[str, str] = {
    # General
    "APP_ENV": "development | production",
    "LOG_LEVEL": "info | debug | warning | error",
    # UI / Backend
    "SHINY_HOST": "127.0.0.1 | localhost",
    "SHINY_PORT": "8001 | 8000",
    "API_HOST": "127.0.0.1 | localhost",
    "API_PORT": "8000",
    "API_BASE_URL": "http://127.0.0.1:8000 | https://<tu-app>.hf.space",
    "ALLOWED_ORIGINS": "http://127.0.0.1:8001,http://localhost:8001,https://<tu-app>.shinyapps.io",
    "CONFIDENCE_THRESHOLD": "0.0.0-1.0 (float)",
    "MAX_UPLOAD_MB": "50",
    # Hugging Face Spaces
    "HF_SPACE_ID": "<usuario>/<space>, p. ej. alexprieto/agrovision",
    "HF_TOKEN": "hf_xxxxxxxx (token write)",
    # Deployment alternatives
    "RENDER_API_KEY": "",
    "RENDER_SERVICE_ID": "",
    "SHINYAPPS_ACCOUNT": "",
    "SHINYAPPS_TOKEN": "",
    "SHINYAPPS_SECRET": "",
    # Model counting
    "COUNTING_ENABLED": "true | false",
    "MODEL_BACKEND": "mock | onnx",
    "MODEL_PATH": "/app/models/agrovision-plantcount-v2.0.0.onnx",
    "MODEL_VERSION": "2.0.0",
    "MODEL_ARCHITECTURE": "yolo26n | rfdetr_nano",
    "HF_MODEL_REPO": "<org>/agrovision-plantcount",
    # Telemetry
    "EVENTS_PERSIST": "true | false",
    "RATE_LIMIT_PER_MIN": "120 | 0",
    # Supabase
    "SUPABASE_URL": "https://<proyecto>.supabase.co",
    "SUPABASE_ANON_KEY": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9. ... (jwt placeholder)",
    "SUPABASE_SERVICE_ROLE_KEY": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9. ... (jwt placeholder)",
    "SUPABASE_STORAGE_BUCKET": "drone-images",
    "DATABASE_URL": "postgresql+asyncpg://postgres.<proyecto>:<pwd>@<host>:5432/postgres",
    # Groq
    "DEV_GROQ_API_KEY": "gsk_... (clave Groq)",
    # Copernicus
    "DEV_COPERNICUS_CLIENT_ID": "ID OAuth en dataspace.copernicus.eu",
    "DEV_COPERNICUS_CLIENT_SECRET": "Secret OAuth en dataspace.copernicus.eu",
}


# ── Helper: extract inline examples from .env.example comments ─────────────────

def _extract_examples(content: str) -> dict[str, str]:
    """Parse comments in .env.example that follow the pattern:
       # VARIABLE=value            # <descripción>

    Also handles plain VAR=value lines without comments.

    Returns a dict mapping variable name -> example/description text.
    """
    examples: dict[str, str] = {}
    for line in content.splitlines():
        # Match lines like: VAR=value         # description
        m = re.match(r"^([A-Z_]+)=(.+?)\s+#\s+(.+)$", line)
        if m:
            var_name = m.group(1)
            example_val = m.group(2).strip()
            description = m.group(3).strip()
            examples[var_name] = f"{example_val} — {description}"
            continue
        # Also match plain VAR=value lines (no comment)
        m2 = re.match(r"^([A-Z_]+)=(.+?)$", line)
        if m2:
            var_name = m2.group(1)
            example_val = m2.group(2).strip()
            # Only add if not already added by the commented version
            if var_name not in examples:
                examples[var_name] = example_val
    return examples


# ── Helper: detect real-looking secrets ───────────────────────────────────────

_SECRETS_PATTERNS = [
    r"(?i) eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",  # JWT placeholder (acceptable as dummy)
    r"^[a-zA-Z0-9]{8,}$",  # generic long alphanumeric (could be real, flag it)
    r"gsk_",  # Groq key prefix
    r"sk-",  # OpenAI-style key prefix
]


def _has_real_secret(value: str) -> bool:
    """Return True if the value looks like a real secret (not a dummy placeholder)."""
    # Strip common dummy markers
    v = value.strip()
    # Acceptable dummy patterns: starts with "placeholder_", ends with "...", is empty
    if v.startswith("placeholder_") or v.endswith("..."):
        return False
    if not v or v in {"", "<todo>", "<pending>"}:
        return False
    # Check against known secret patterns
    for pat in _SECRETS_PATTERNS:
        if re.search(pat, v):
            # But allow if it's clearly a placeholder (contains "placeholder" or "...")
            if "placeholder" in v.lower() or v.endswith("..."):
                return False
            return True
    # If it's a long alphanumeric without a known prefix, flag it
    if re.match(r"^[a-zA-Z0-9]{20,}$", v):
        return True
    return False


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestEnvExampleHasAllVariables:
    """Verifica que .env.example contenga todas las variables esperadas."""

    @pytest.fixture(autouse=True)
    def _require_env_example(self):
        assert ENV_EXAMPLE_PATH.exists(), f"Falta .env.example en {ENV_EXAMPLE_PATH}"
        with open(ENV_EXAMPLE_PATH, encoding="utf-8") as f:
            self.content = f.read()
        with open(ENV_EXAMPLE_PATH, encoding="utf-8") as f:
            self.examples = _extract_examples(self.content)

    def test_all_expected_variables_present(self):
        """Cada variable definida en ENV_EXPECTED debe aparecer en .env.example."""
        for var in ENV_EXPECTED:
            assert var in self.content, f"Variable faltante en .env.example: {var}"

    def test_no_real_secrets_exposed(self):
        """Ninguna variable debe contener secretos reales (solo placeholders/dummies)."""
        for line in self.content.splitlines():
            m = re.match(r"^([A-Z_]+)=(.+?)\s*$", line)
            if m:
                var_name = m.group(1)
                val = m.group(2).strip()
                # Skip comment-only lines and empty values
                if not val or val.startswith("#"):
                    continue
                # Check if the value looks like a real secret
                if _has_real_secret(val):
                    pytest.fail(
                        f"Posible secreto real detectado en .env.example para '{var_name}': {val}. "
                        "Usa solo placeholders/dummies seguros."
                    )


class TestEnvExampleExamplesAndSteps:
    """Verifica que .env.example tenga ejemplos de formato y rutas paso a paso."""

    @pytest.fixture(autouse=True)
    def _require_env_example(self):
        assert ENV_EXAMPLE_PATH.exists()
        with open(ENV_EXAMPLE_PATH, encoding="utf-8") as f:
            self.content = f.read()

    def test_supabase_connection_string_steps_present(self):
        """DOC: .env.example debe documentar cómo obtener DATABASE_URL en Supabase
        via Connect -> Connection String -> pooler -> postgresql+asyncpg://."""
        content_lower = self.content.lower()
        supabase_steps = [
            "connect",
            "connection string",
            "session pooler",
            "transaction pooler",
            "postgresql+asyncpg",
            "supabase",
        ]
        found = all(step in content_lower for step in supabase_steps)
        assert found, (
            "Faltan pasos documentados de Supabase (Connect -> Connection String -> "
            "pooler -> postgresql+asyncpg://) en .env.example. "
            "Añade los comentarios de instrucción paso a paso."
        )

    def test_supabase_step_zero_project_creation_present(self):
        """DOC: .env.example debe documentar el Paso 0 para crear un proyecto desde cero."""
        content_lower = self.content.lower()
        assert "new project" in content_lower, "Falta instrucción 'New project' en .env.example"
        assert "database password" in content_lower, (
            "Falta mención a guardar 'Database Password' en .env.example"
        )

    def test_supabase_url_steps_present(self):
        """DOC: .env.example debe explicar cómo llegar a SUPABASE_URL (Settings -> Data API)."""
        content_lower = self.content.lower()
        url_steps = ["project settings", "data api", "project url", "copy"]
        for step in url_steps:
            assert step in content_lower, f"Paso faltante para SUPABASE_URL: '{step}'"

    def test_supabase_anon_key_steps_present(self):
        """DOC: .env.example debe explicar cómo llegar a SUPABASE_ANON_KEY (anon public)."""
        content_lower = self.content.lower()
        anon_steps = ["project settings", "api keys", "anon", "public", "copy"]
        for step in anon_steps:
            assert step in content_lower, f"Paso faltante para SUPABASE_ANON_KEY: '{step}'"

    def test_supabase_service_role_key_steps_present(self):
        """DOC: .env.example debe explicar cómo llegar a SUPABASE_SERVICE_ROLE_KEY (Reveal)."""
        content_lower = self.content.lower()
        sr_steps = ["service_role", "secret", "reveal", "copy"]
        for step in sr_steps:
            assert step in content_lower, f"Paso faltante para SUPABASE_SERVICE_ROLE_KEY: '{step}'"

    def test_supabase_storage_bucket_steps_present(self):
        """DOC: .env.example debe documentar la creación del bucket drone-images en Storage."""
        content_lower = self.content.lower()
        storage_steps = ["storage", "new bucket", "drone-images"]
        for step in storage_steps:
            assert step in content_lower, f"Paso faltante para SUPABASE_STORAGE_BUCKET: '{step}'"

    def test_supabase_url_anon_key_service_role_present(self):
        """DOC: SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY deben aparecer."""
        for var in ["SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY"]:
            assert var in self.content, f"Variable faltante: {var}"

    def test_copernicus_steps_present(self):
        """DOC: .env.example debe documentar cómo obtener credenciales de Copernicus CDSE."""
        content_lower = self.content.lower()
        copernicus_steps = [
            "copernicus",
            "dataspace",
            "client id",
            "client secret",
        ]
        found = all(step in content_lower for step in copernicus_steps)
        assert found, (
            "Faltan pasos documentados de Copernicus CDSE en .env.example. "
            "Añade los comentarios de instrucción paso a paso."
        )

    def test_groq_api_key_steps_present(self):
        """DOC: .env.example debe documentar cómo obtener la API key de Groq."""
        content_lower = self.content.lower()
        groq_steps = ["groq", "console.groq.com/keys", "create key"]
        found = all(step in content_lower for step in groq_steps)
        assert found, (
            "Faltan pasos documentados de Groq en .env.example. "
            "Añade los comentarios de instrucción paso a paso."
        )

    def test_hf_space_id_token_steps_present(self):
        """DOC: .env.example debe documentar HF_SPACE_ID y HF_TOKEN."""
        content_lower = self.content.lower()
        hf_steps = ["huggingface", "hf_space_id", "hf_token", "settings/tokens"]
        found = all(step in content_lower for step in hf_steps)
        assert found, (
            "Faltan pasos documentados de Hugging Face en .env.example. "
            "Añade los comentarios de instrucción paso a paso."
        )


class TestEnvExampleFormatExamples:
    """Verifica que cada variable tenga un ejemplo de formato realista (dummy seguro)."""

    @pytest.fixture(autouse=True)
    def _require_env_example(self):
        assert ENV_EXAMPLE_PATH.exists()
        with open(ENV_EXAMPLE_PATH, encoding="utf-8") as f:
            self.content = f.read()
        self.examples = _extract_examples(self.content)

    # Supabase examples
    def test_supabase_url_example_safe(self):
        """SUPABASE_URL debe tener un ejemplo con formato realista pero seguro."""
        ex = self.examples.get("SUPABASE_URL", "")
        assert "supabase.co" in ex.lower() or "https://" in ex, (
            f"SUPABASE_URL example missing realistic format: {ex}"
        )
        assert not _has_real_secret(ex), f"SUPABASE_URL example parece secreto real: {ex}"

    def test_supabase_anon_key_example_safe(self):
        """SUPABASE_ANON_KEY debe tener un ejemplo JWT placeholder (no secreto real)."""
        ex = self.examples.get("SUPABASE_ANON_KEY", "")
        assert "eyJhbGci" in ex or "placeholder" in ex.lower(), (
            f"SUPABASE_ANON_KEY example missing JWT format: {ex}"
        )
        assert not _has_real_secret(ex), f"SUPABASE_ANON_KEY example parece secreto real: {ex}"

    def test_database_url_example_safe(self):
        """DATABASE_URL debe tener un ejemplo con prefijo postgresql+asyncpg:// y host seguro."""
        ex = self.examples.get("DATABASE_URL", "")
        assert "postgresql+asyncpg://" in ex, (
            f"DATABASE_URL example missing postgresql+asyncpg:// prefix: {ex}"
        )
        assert not _has_real_secret(ex), f"DATABASE_URL example parece secreto real: {ex}"

    def test_groq_key_example_safe(self):
        """DEV_GROQ_API_KEY debe tener ejemplo gsk_... (formato Groq)."""
        ex = self.examples.get("DEV_GROQ_API_KEY", "")
        assert "gsk_" in ex.lower() or "placeholder" in ex.lower(), (
            f"DEV_GROQ_API_KEY example missing gsk_ format: {ex}"
        )
        assert not _has_real_secret(ex), f"DEV_GROQ_API_KEY example parece secreto real: {ex}"

    def test_copernicus_client_id_example_safe(self):
        """DEV_COPERNICUS_CLIENT_ID debe tener ejemplo de ID OAuth placeholder."""
        ex = self.examples.get("DEV_COPERNICUS_CLIENT_ID", "")
        assert "placeholder" in ex.lower() or "id" in ex.lower()
        assert "id" in ex.lower() or "placeholder" in ex.lower()
        assert not _has_real_secret(ex)

    def test_copernicus_client_secret_example_safe(self):
        """DEV_COPERNICUS_CLIENT_SECRET debe tener ejemplo de secreto placeholder."""
        ex = self.examples.get("DEV_COPERNICUS_CLIENT_SECRET", "")
        assert "placeholder" in ex.lower() or "secret" in ex.lower()
        assert not _has_real_secret(ex)

    def test_hf_space_id_example_safe(self):
        """HF_SPACE_ID debe tener ejemplo <usuario>/<space>."""
        ex = self.examples.get("HF_SPACE_ID", "")
        assert "/" in ex and (" " in ex or "user" in ex.lower() or "space" in ex.lower()), (
            f"HF_SPACE_ID example missing <usuario>/<space> format: {ex}"
        )
        assert not _has_real_secret(ex), f"HF_SPACE_ID ejemplo parece secreto real: {ex}"

    def test_hf_token_example_safe(self):
        """HF_TOKEN debe tener ejemplo hf_... placeholder."""
        ex = self.examples.get("HF_TOKEN", "")
        assert "hf_" in ex.lower() or "placeholder" in ex.lower(), (
            f"HF_TOKEN example missing hf_ format: {ex}"
        )
        assert not _has_real_secret(ex), f"HF_TOKEN ejemplo parece secreto real: {ex}"