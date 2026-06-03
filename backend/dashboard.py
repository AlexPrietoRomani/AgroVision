"""
Archivo: dashboard.py
Fecha de modificación: 03/06/2026
Autor: Equipo AgroVisión

Descripción:
UI **Shiny for Python (LEGACY)** de AgroVisión. Desde la Fase 8 la UI principal es
**Astro + Tailwind** (servida por el gateway en `/`); este dashboard Shiny se conserva
como alternativa montable en `/shiny` y para desarrollo. Mantiene los 6 módulos: Resumen de Campo,
Creación de Parcelas (mapa + dibujo), Teledetección (NDVI 5 años + clima + heatmap),
Conteo por Dron (**en desarrollo**), Asistente Agéntico (RAG) y Credenciales (efímeras).
Consume el backend FastAPI por HTTP, adjuntando las credenciales BYOK como cabeceras
`X-User-*` que viven solo en memoria de sesión (se borran al refrescar).

Acciones Principales:
    - Renderiza la SPA de 6 nav_panel con estado reactivo por sesión.
    - Orquesta llamadas al gateway (parcelas, NDVI, clima, chat).

Estructura Interna:
    - `app_ui`: definición declarativa (navbar + 6 paneles).
    - `server`: lógica reactiva (parcelas, mapa, gráficos, chat, credenciales).

Entradas / Dependencias:
    - `shiny`, `shinywidgets`, `ipyleaflet`, `plotly`, `httpx`; env `API_BASE_URL`.

Salidas / Efectos:
    - Estado efímero por sesión; nada se persiste en el cliente.

Ejecución (legacy):
    uv run python -m uvicorn backend.dashboard:app --host 127.0.0.1 --port 8001 --reload
"""

from __future__ import annotations

import base64
import os
import uuid

import httpx
import plotly.graph_objects as go
from dotenv import load_dotenv
from ipyleaflet import DrawControl, Map
from shiny import App, reactive, render, ui
from shinywidgets import output_widget, render_widget

load_dotenv()

API_BASE_URL: str = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
TIMEOUT: float = 120.0
_DEFAULT_CENTER = (-12.05, -77.04)  # Lima/costa peruana (cultivo de arándano de Hortifrut)

_EPHEMERAL_NOTICE = (
    "⚠️ <b>Tus credenciales se usan solo en esta sesión. No se guardan ni almacenan. "
    "Si actualizas o cierras la página, todo se borrará.</b>"
)
_BUBBLE_STYLE = "border:1px solid #e7e5e4;border-radius:8px;padding:8px;margin-bottom:8px;"

app_ui = ui.page_navbar(
    # 1) Resumen de Campo
    ui.nav_panel(
        "Resumen de Campo",
        ui.input_select("resumen_parcela", "Parcela activa", choices={}),
        ui.output_ui("resumen_kpis"),
    ),
    # 2) Creación de Parcelas
    ui.nav_panel(
        "Creación de Parcelas",
        ui.markdown(
            "Dibuja el polígono de tu parcela sobre el mapa (EPSG:4326), nómbrala y "
            "guárdala. Al guardar se dispara el **backfill NDVI de 5 años**."
        ),
        ui.row(
            ui.column(7, output_widget("mapa_draw")),
            ui.column(
                5,
                ui.input_text("parcela_name", "Nombre de la parcela", placeholder="Lote Sur"),
                ui.input_action_button(
                    "guardar_parcela", "💾 Guardar y disparar backfill", class_="btn-success"
                ),
                ui.output_ui("parcelas_list"),
            ),
        ),
    ),
    # 3) Teledetección
    ui.nav_panel(
        "Teledetección",
        ui.input_select("teledet_parcela", "Parcela", choices={}),
        ui.markdown(
            "Serie **NDVI mensual de 5 años** (Sentinel-2) vs. clima (Open-Meteo). "
            "Solo lectura; el dibujo está en *Creación de Parcelas*."
        ),
        output_widget("ndvi_chart"),
        ui.input_action_button("ver_heatmap", "🗺️ Ver heatmap NDVI (~10 m/px)"),
        ui.output_ui("heatmap_box"),
    ),
    # 4) Conteo por Dron (en desarrollo)
    ui.nav_panel(
        "Conteo por Dron",
        ui.output_ui("counting_banner"),
    ),
    # 5) Asistente Agéntico
    ui.nav_panel(
        "Asistente",
        ui.output_ui("chat_history"),
        ui.input_text("chat_input", "", placeholder="¿Cómo evolucionó el NDVI de mi parcela?"),
        ui.input_action_button("chat_send", "Enviar", class_="btn-primary"),
    ),
    # 6) Credenciales & APIs (efímeras)
    ui.nav_panel(
        "Credenciales & APIs",
        ui.HTML(f'<div class="alert alert-warning">{_EPHEMERAL_NOTICE}</div>'),
        ui.input_password("groq_key", "Groq API Key (asistente RAG)"),
        ui.input_password("cop_id", "Copernicus Client ID (Sentinel-2)"),
        ui.input_password("cop_secret", "Copernicus Client Secret"),
        ui.input_text("sb_url", "Supabase URL"),
        ui.input_password("sb_key", "Supabase anon key"),
        ui.input_action_button("save_credentials", "Usar en esta sesión"),
        ui.output_text("credentials_state"),
    ),
    title="AgroVisión",
    id="nav",
)


def server(input, output, session) -> None:  # noqa: ANN001 - firma fijada por Shiny
    """Lógica reactiva de la plataforma (parcelas, teledetección, chat, credenciales)."""
    credentials = reactive.value({})  # EFÍMERO: vive solo en esta sesión
    parcels = reactive.value([])  # [{id, name, lon, lat}]
    drawn_geojson = reactive.value(None)
    chat_log = reactive.value([])  # [{role, content, tools}]
    chat_session_id = reactive.value(f"sess-{uuid.uuid4()}")
    backend_status = reactive.value({})
    heatmap_b64 = reactive.value(None)

    def auth_headers() -> dict:
        """Construye las cabeceras X-User-* desde las credenciales efímeras de la sesión."""
        creds = credentials.get()
        mapping = {
            "X-User-Groq-Key": creds.get("groq"),
            "X-User-Copernicus-Id": creds.get("cop_id"),
            "X-User-Copernicus-Secret": creds.get("cop_secret"),
            "X-User-Supabase-Url": creds.get("sb_url"),
            "X-User-Supabase-Key": creds.get("sb_key"),
        }
        return {key: value for key, value in mapping.items() if value}

    def _refresh_parcels() -> None:
        """Recarga la lista de parcelas desde el backend."""
        try:
            response = httpx.get(f"{API_BASE_URL}/api/fields", headers=auth_headers(), timeout=30)
            parcels.set(response.json() if response.status_code == httpx.codes.OK else [])
        except httpx.HTTPError:
            parcels.set([])

    @reactive.effect
    def _startup() -> None:
        """Consulta estado del backend y parcelas al iniciar la sesión."""
        try:
            backend_status.set(httpx.get(f"{API_BASE_URL}/api/status", timeout=30).json())
        except httpx.HTTPError:
            backend_status.set({"error": "backend no disponible"})
        _refresh_parcels()

    @reactive.effect
    def _sync_selectors() -> None:
        """Mantiene los selectores de parcela sincronizados con la lista."""
        choices = {p["id"]: p["name"] for p in parcels.get()}
        ui.update_select("resumen_parcela", choices=choices)
        ui.update_select("teledet_parcela", choices=choices)

    def _parcel_by_id(field_id: str) -> dict | None:
        return next((p for p in parcels.get() if p["id"] == field_id), None)

    # --- Módulo: Creación de Parcelas ---
    @render_widget
    def mapa_draw():
        """Mapa interactivo con control de dibujo de polígonos."""
        leaflet_map = Map(center=_DEFAULT_CENTER, zoom=6, scroll_wheel_zoom=True)
        draw = DrawControl(
            polygon={"shapeOptions": {"color": "#15803D", "fillOpacity": 0.3}},
            polyline={},
            circlemarker={},
            rectangle={},
            circle={},
            marker={},
        )

        def _on_draw(target, action, geo_json):  # noqa: ANN001 - firma de ipyleaflet
            if geo_json and geo_json.get("geometry"):
                drawn_geojson.set(geo_json["geometry"])

        draw.on_draw(_on_draw)
        leaflet_map.add(draw)
        return leaflet_map

    @reactive.effect
    @reactive.event(input.guardar_parcela)
    def _guardar_parcela() -> None:
        """Persiste la parcela dibujada y dispara el backfill NDVI."""
        geometry = drawn_geojson.get()
        name = (input.parcela_name() or "").strip()
        if not geometry:
            ui.notification_show("Dibuja un polígono primero.", type="warning")
            return
        if not name:
            ui.notification_show("Escribe un nombre para la parcela.", type="warning")
            return
        try:
            response = httpx.post(
                f"{API_BASE_URL}/api/fields",
                json={"name": name, "geojson": geometry},
                headers=auth_headers(),
                timeout=60,
            )
        except httpx.HTTPError as error:
            ui.notification_show(f"Error de red: {error}", type="error")
            return
        if response.status_code == httpx.codes.OK:
            ui.notification_show(
                f"Parcela '{name}' guardada. Backfill NDVI (5 años) en curso…", type="message"
            )
            _refresh_parcels()
        else:
            ui.notification_show(
                f"Error {response.status_code}: {response.text[:160]}", type="error"
            )

    @render.ui
    def parcelas_list():
        """Lista las parcelas registradas."""
        items = parcels.get()
        if not items:
            return ui.p("Sin parcelas aún. Dibuja y guarda la primera.")
        return ui.TagList(
            ui.h5("Parcelas registradas"),
            ui.tags.ul(*[ui.tags.li(p["name"]) for p in items]),
        )

    # --- Módulo: Teledetección ---
    @reactive.calc
    def teledet_data() -> dict:
        """Obtiene serie NDVI (persistida) y clima de la parcela seleccionada."""
        field_id = input.teledet_parcela()
        if not field_id:
            return {"ndvi": [], "weather": []}
        ndvi: list = []
        weather: list = []
        try:
            response = httpx.post(
                f"{API_BASE_URL}/api/ndvi",
                json={"field_id": field_id},
                headers=auth_headers(),
                timeout=60,
            )
            if response.status_code == httpx.codes.OK:
                ndvi = response.json().get("series", [])
        except httpx.HTTPError:
            pass
        parcel = _parcel_by_id(field_id)
        if parcel and parcel.get("lat") is not None:
            try:
                response = httpx.post(
                    f"{API_BASE_URL}/api/weather",
                    json={"lat": parcel["lat"], "lon": parcel["lon"]},
                    timeout=60,
                )
                if response.status_code == httpx.codes.OK:
                    weather = response.json().get("series", [])
            except httpx.HTTPError:
                pass
        return {"ndvi": ndvi, "weather": weather}

    @render_widget
    def ndvi_chart():
        """Gráfico de doble eje: NDVI mensual vs precipitación."""
        data = teledet_data()
        fig = go.FigureWidget()
        ndvi = data["ndvi"]
        weather = data["weather"]
        fig.add_scatter(
            x=[p["date"] for p in ndvi],
            y=[p["mean_ndvi"] for p in ndvi],
            name="NDVI",
            line={"color": "#15803D", "width": 3},
        )
        fig.add_bar(
            x=[p["date"] for p in weather],
            y=[p["precip_mm"] for p in weather],
            name="Precipitación (mm)",
            marker_color="rgba(59,130,246,0.7)",
            yaxis="y2",
        )
        fig.update_layout(
            margin={"l": 40, "r": 40, "t": 30, "b": 30},
            yaxis={"title": "NDVI", "range": [0, 1]},
            yaxis2={"title": "Precip (mm)", "overlaying": "y", "side": "right"},
            legend={"orientation": "h"},
        )
        return fig

    @reactive.effect
    @reactive.event(input.ver_heatmap)
    def _cargar_heatmap() -> None:
        """Solicita el heatmap NDVI (PNG) de la parcela seleccionada."""
        field_id = input.teledet_parcela()
        if not field_id:
            ui.notification_show("Selecciona una parcela.", type="warning")
            return
        try:
            response = httpx.post(
                f"{API_BASE_URL}/api/ndvi/raster",
                json={"field_id": field_id},
                headers=auth_headers(),
                timeout=120,
            )
        except httpx.HTTPError as error:
            ui.notification_show(f"Error de red: {error}", type="error")
            return
        if response.status_code == httpx.codes.OK:
            heatmap_b64.set(base64.b64encode(response.content).decode("ascii"))
        else:
            heatmap_b64.set(None)
            ui.notification_show(
                f"No se pudo generar el heatmap ({response.status_code}). "
                "¿Configuraste Copernicus en Credenciales?",
                type="error",
            )

    @render.ui
    def heatmap_box():
        """Muestra el heatmap NDVI si se generó."""
        encoded = heatmap_b64.get()
        if not encoded:
            return ui.p("Pulsa el botón para ver el mapa de calor NDVI de la parcela.")
        return ui.img(
            src=f"data:image/png;base64,{encoded}",
            style="max-width:100%;border:1px solid #e7e5e4;border-radius:8px;",
        )

    # --- Módulo: Resumen de Campo ---
    @render.ui
    def resumen_kpis():
        """KPIs de la parcela seleccionada (NDVI último/tendencia, área)."""
        field_id = input.resumen_parcela()
        parcel = _parcel_by_id(field_id) if field_id else None
        if not parcel:
            return ui.p("Selecciona una parcela (créala en 'Creación de Parcelas').")
        series: list = []
        try:
            response = httpx.post(
                f"{API_BASE_URL}/api/ndvi",
                json={"field_id": field_id},
                headers=auth_headers(),
                timeout=60,
            )
            if response.status_code == httpx.codes.OK:
                series = response.json().get("series", [])
        except httpx.HTTPError:
            pass
        if series:
            ultimo = series[-1]["mean_ndvi"]
            delta = ultimo - series[0]["mean_ndvi"]
            ndvi_txt = f"{ultimo:.2f} (Δ {delta:+.2f} en {len(series)} meses)"
        else:
            ndvi_txt = "sin datos NDVI aún (backfill en curso o sin Copernicus)"
        return ui.TagList(
            ui.h4(parcel["name"]),
            ui.tags.ul(
                ui.tags.li(f"NDVI: {ndvi_txt}"),
                ui.tags.li("Densidad de plantas: en desarrollo (módulo de conteo)"),
            ),
        )

    # --- Módulo: Conteo (en desarrollo) ---
    @render.ui
    def counting_banner():
        """Aviso de módulo en desarrollo (standby)."""
        return ui.HTML(
            '<div class="alert alert-info"><b>Módulo en desarrollo (standby).</b> '
            "El conteo de plantas por dron se habilitará cuando el repositorio del modelo "
            "publique el artefacto en Hugging Face Hub. La plataforma ya queda lista para "
            "consumirlo (cola, worker y tabla creados, inactivos).</div>"
        )

    # --- Módulo: Asistente ---
    @reactive.effect
    @reactive.event(input.chat_send)
    def _chat_send() -> None:
        """Envía el turno al agente y agrega la respuesta al historial."""
        message = (input.chat_input() or "").strip()
        if not message:
            return
        log = list(chat_log.get())
        log.append({"role": "user", "content": message, "tools": []})
        chat_log.set(log)
        try:
            response = httpx.post(
                f"{API_BASE_URL}/api/chat",
                json={"session_id": chat_session_id.get(), "message": message},
                headers=auth_headers(),
                timeout=TIMEOUT,
            )
        except httpx.HTTPError as error:
            log.append({"role": "assistant", "content": f"Error de red: {error}", "tools": []})
            chat_log.set(list(log))
            return
        if response.status_code == httpx.codes.OK:
            data = response.json()
            log.append(
                {
                    "role": "assistant",
                    "content": data.get("reply", ""),
                    "tools": [t["tool"] for t in data.get("tool_logs", [])],
                }
            )
        else:
            detail = response.json().get("detail", response.text[:160])
            log.append({"role": "assistant", "content": f"Error: {detail}", "tools": []})
        chat_log.set(list(log))
        ui.update_text("chat_input", value="")

    @render.ui
    def chat_history():
        """Renderiza el historial del chat con la traza de herramientas."""
        entries = chat_log.get()
        if not entries:
            return ui.p("Pregúntame sobre el NDVI, el clima o la densidad de tus parcelas.")
        bubbles = []
        for entry in entries:
            who = "🧑 Tú" if entry["role"] == "user" else "🤖 AgroVisión AI"
            tools = (
                ui.tags.small(f" · herramientas: {', '.join(entry['tools'])}")
                if entry.get("tools")
                else ""
            )
            bubbles.append(
                ui.div(
                    ui.tags.b(who),
                    tools,
                    ui.p(entry["content"]),
                    style=_BUBBLE_STYLE,
                )
            )
        return ui.TagList(*bubbles)

    # --- Módulo: Credenciales (efímeras) ---
    @reactive.effect
    @reactive.event(input.save_credentials)
    def _save_credentials() -> None:
        """Guarda las credenciales en memoria de sesión (nunca en disco)."""
        credentials.set(
            {
                "groq": input.groq_key(),
                "cop_id": input.cop_id(),
                "cop_secret": input.cop_secret(),
                "sb_url": input.sb_url(),
                "sb_key": input.sb_key(),
            }
        )
        ui.notification_show("Credenciales activas solo en esta sesión.", type="message")
        _refresh_parcels()

    @render.text
    def credentials_state() -> str:
        """Indica cuántas credenciales están activas (sin revelarlas)."""
        active = sum(1 for value in credentials.get().values() if value)
        return f"Credenciales activas en esta sesión: {active} (se borran al refrescar)."


app = App(app_ui, server)
