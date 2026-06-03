"""
Archivo: app.py
Fecha de modificación: 03/06/2026
Autor: Equipo AgroVisión

Descripción:
Interfaz Shiny for Python del MVP de AgroVisión. Presenta dos pestañas: "Conteo
por Dron" (en **standby** hasta que el modelo de conteo esté publicado) y
"Credenciales & APIs" (estado **efímero** en memoria de sesión, nunca persistido).
Consume el backend FastAPI vía HTTP y respeta la bandera de conteo del backend.

Acciones Principales:
    - Renderiza la SPA de 2 pestañas con estado reactivo por sesión.
    - Consulta `/api/status` para decidir si el conteo está activo o en standby.

Estructura Interna:
    - `app_ui`: definición declarativa de la interfaz (navbar + paneles).
    - `server`: lógica reactiva (estado de backend, conteo, credenciales efímeras).

Entradas / Dependencias:
    - `shiny`, `httpx`; variable de entorno `API_BASE_URL`.

Salidas / Efectos:
    - Ninguno persistente; todo el estado vive en la sesión y se borra al refrescar.

Integración UI:
    - Este archivo renderiza la app completa del MVP.
    - Se ejecuta con `shiny run frontend/app.py` o se despliega en ShinyApps.io.
"""

from __future__ import annotations

import base64
import os

import httpx
from dotenv import load_dotenv
from shiny import App, reactive, render, ui

load_dotenv()  # carga variables desde .env en desarrollo local

API_BASE_URL: str = os.getenv("API_BASE_URL", "http://localhost:8000")
REQUEST_TIMEOUT_SECONDS: float = 120.0

_EPHEMERAL_NOTICE: str = (
    "⚠️ <b>Tus credenciales se usan solo en esta sesión. No se guardan ni "
    "almacenan. Si actualizas o cierras la página, todo se borrará.</b>"
)

app_ui = ui.page_navbar(
    ui.nav_panel(
        "Conteo por Dron",
        ui.output_ui("counting_banner"),
        ui.input_file(
            "orthomosaic",
            "Subir ortomosaico (JPG/PNG/TIFF)",
            accept=[".jpg", ".jpeg", ".png", ".tif", ".tiff"],
            multiple=False,
        ),
        ui.input_numeric("area_ha", "Área del lote (Ha)", value=1.0, min=0.01, step=0.1),
        ui.input_action_button("run_count", "▶ Iniciar Conteo", class_="btn-success"),
        ui.output_ui("count_metrics"),
        ui.output_image("count_overlay"),
    ),
    ui.nav_panel(
        "Credenciales & APIs",
        ui.HTML(f'<div class="alert alert-warning">{_EPHEMERAL_NOTICE}</div>'),
        ui.input_password("groq_key", "Groq API Key (módulos futuros)"),
        ui.input_password("copernicus_secret", "Copernicus / Sentinel Hub Secret (futuro)"),
        ui.input_action_button("save_credentials", "Usar en esta sesión"),
        ui.output_text("credentials_state"),
    ),
    title="AgroVisión MVP",
)


def server(input, output, session) -> None:  # noqa: ANN001 - firma fijada por Shiny
    """
    Define la lógica reactiva del MVP (estado de backend, conteo y credenciales).

    Args:
        input: Espacio de entradas reactivas de Shiny.
        output: Espacio de salidas renderizadas de Shiny.
        session: Sesión activa (aislada por conexión WebSocket).
    """
    backend_status = reactive.value({"counting_enabled": None})
    count_result = reactive.value(None)
    credentials = reactive.value({})  # estado EFÍMERO: vive solo en esta sesión

    @reactive.effect
    def _load_backend_status() -> None:
        """Consulta el estado del backend una vez al iniciar la sesión."""
        try:
            response = httpx.get(f"{API_BASE_URL}/api/status", timeout=30.0)
            backend_status.set(response.json())
        except httpx.HTTPError:
            backend_status.set({"counting_enabled": False, "error": "backend no disponible"})

    @render.ui
    def counting_banner():
        """Muestra el aviso de standby cuando el conteo no está habilitado."""
        status_info = backend_status.get()
        if status_info.get("counting_enabled"):
            return ui.HTML(
                '<div class="alert alert-success">Modelo de conteo activo. '
                "Sube un ortomosaico para contar.</div>"
            )
        return ui.HTML(
            '<div class="alert alert-info"><b>Módulo en preparación (standby).</b> '
            "El conteo se habilitará cuando el repo del modelo publique el artefacto "
            "en Hugging Face Hub.</div>"
        )

    @reactive.effect
    @reactive.event(input.run_count)
    def _run_count() -> None:
        """Envía el ortomosaico al backend si el conteo está habilitado."""
        if not backend_status.get().get("counting_enabled"):
            ui.notification_show("El módulo de conteo está en standby.", type="warning")
            return
        uploaded = input.orthomosaic()
        if not uploaded:
            ui.notification_show("Sube un ortomosaico primero.", type="warning")
            return
        with open(uploaded[0]["datapath"], "rb") as handle:
            response = httpx.post(
                f"{API_BASE_URL}/api/count",
                files={"file": handle},
                data={"area_ha": input.area_ha()},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        if response.status_code == httpx.codes.OK:
            count_result.set(response.json())
        else:
            ui.notification_show(f"Error del backend: {response.status_code}.", type="error")

    @render.ui
    def count_metrics():
        """Renderiza las métricas del último conteo, si existe."""
        result = count_result.get()
        if not result:
            return ui.p("Sin resultados aún.")
        return ui.TagList(
            ui.h3(f"Plantas detectadas: {result['count']}"),
            ui.p(
                f"Densidad: {result['density']} pl/Ha · Malezas: {result['weeds']} · "
                f"Fallas: {result['failures']}% · Confianza: {result['confidence']}"
            ),
        )

    @render.image
    def count_overlay():
        """Renderiza el overlay con las cajas detectadas, si existe."""
        result = count_result.get()
        if not result:
            return None
        overlay_path = "/tmp/agrovision_overlay.png"  # noqa: S108 - archivo temporal de sesión
        with open(overlay_path, "wb") as handle:
            handle.write(base64.b64decode(result["overlay_b64"]))
        return {"src": overlay_path, "width": "100%"}

    @reactive.effect
    @reactive.event(input.save_credentials)
    def _save_credentials() -> None:
        """Guarda las credenciales en memoria de sesión (nunca en disco)."""
        credentials.set({"groq": input.groq_key(), "copernicus": input.copernicus_secret()})
        ui.notification_show("Credenciales activas solo en esta sesión.", type="message")

    @render.text
    def credentials_state() -> str:
        """Indica cuántas credenciales están activas en la sesión (sin revelarlas)."""
        active = sum(1 for value in credentials.get().values() if value)
        return f"Credenciales activas en esta sesión: {active} (se borran al refrescar)."


app = App(app_ui, server)
