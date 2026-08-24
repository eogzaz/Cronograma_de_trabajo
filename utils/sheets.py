"""
Capa de datos real (Google Sheets).

Mismo contrato que utils/mock_data.py: mismas funciones, mismos nombres de
columnas en los DataFrames devueltos. Para migrar una página de mock a real,
basta con cambiar el import:

    from utils.mock_data import get_clientes, get_tareas   # antes
    from utils.sheets import get_clientes, get_tareas       # después

Lee y escribe directamente sobre el Google Sheet que sigue la estructura de
Plantilla_Despacho_Contable.xlsx (pestañas: Clientes, Tareas, Equipo,
Checklist_Plantillas, Checklist_Progreso, Historial_Tareas).

Requiere en .streamlit/secrets.toml (ver guía paso a paso):

    GOOGLE_SHEET_ID = "..."

    [gcp_service_account]
    type = "service_account"
    ...  (todo el contenido del JSON de la cuenta de servicio)

Y que la hoja esté compartida (como Editor) con el "client_email" de esa
cuenta de servicio.
"""

from datetime import date, datetime

import gspread
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

HOY = date.today()


# ---------------------------------------------------------------------------
# CONEXIÓN
# ---------------------------------------------------------------------------
@st.cache_resource
def _client() -> gspread.Client:
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], scopes=SCOPES
    )
    return gspread.authorize(creds)


@st.cache_resource
def _sheet():
    return _client().open_by_key(st.secrets["GOOGLE_SHEET_ID"])


def _ws(nombre: str):
    return _sheet().worksheet(nombre)


def _leer(nombre: str) -> pd.DataFrame:
    """Lee una pestaña completa como DataFrame, usando la fila 1 como encabezados."""
    registros = _ws(nombre).get_all_records()
    return pd.DataFrame(registros)


def _parse_fecha(valor) -> date | None:
    if not valor:
        return None
    if isinstance(valor, date):
        return valor
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(valor), fmt).date()
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# CLIENTES
# ---------------------------------------------------------------------------
@st.cache_data(ttl=30)
def get_clientes() -> pd.DataFrame:
    df = _leer("Clientes")
    if df.empty:
        return df
    df = df.rename(columns={
        "ID": "id", "Nombre": "nombre", "NIT": "nit",
        "Responsabilidades": "responsabilidades", "Estado": "estado",
        "Proxima_Obligacion": "proximo_vencimiento",
        "Responsable_Obligacion": "responsable_obligacion",
    })
    # Si el Sheet todavía no tiene estas columnas (migración en curso), se
    # crean vacías en vez de tumbar toda la app con un KeyError.
    for col in ("responsabilidades", "responsable_obligacion"):
        if col not in df.columns:
            df[col] = ""
    df["fecha_vencimiento"] = df["Fecha_Vencimiento"].apply(_parse_fecha)
    return df.drop(columns=["Fecha_Vencimiento"])


# ---------------------------------------------------------------------------
# TAREAS
# ---------------------------------------------------------------------------
@st.cache_data(ttl=30)
def get_tareas() -> pd.DataFrame:
    df = _leer("Tareas")
    if df.empty:
        return df
    df = df.rename(columns={
        "ID": "id", "Titulo": "titulo", "Cliente": "cliente", "Responsable": "responsable",
        "Estado": "estado", "Prioridad": "prioridad",
    })
    df["fecha_limite"] = df["Fecha_Limite"].apply(_parse_fecha)
    return df.drop(columns=["Fecha_Limite"])


def crear_tarea(titulo: str, cliente: str, responsable: str, fecha_limite: date,
                 prioridad: str = "Media", estado: str = "Pendiente") -> None:
    ws = _ws("Tareas")
    ids_existentes = [int(v) for v in ws.col_values(1)[1:] if str(v).strip().isdigit()]
    nuevo_id = max(ids_existentes, default=0) + 1
    ws.append_row([
        nuevo_id, titulo, cliente, responsable, estado, prioridad,
        fecha_limite.strftime("%d/%m/%Y"),
    ])
    get_tareas.clear()


def actualizar_estado_tarea(tarea_id: int, nuevo_estado: str) -> None:
    """Cambia la columna Estado de una tarea puntual, ubicándola por su ID."""
    ws = _ws("Tareas")
    ids = ws.col_values(1)[1:]  # columna A, sin encabezado
    for i, v in enumerate(ids, start=2):  # fila 2 en adelante
        if str(v).strip() == str(tarea_id):
            ws.update_cell(i, 5, nuevo_estado)  # columna E = Estado
            get_tareas.clear()
            try:
                _ws("Historial_Tareas").append_row(
                    [tarea_id, HOY.strftime("%d/%m/%Y"), f"Estado actualizado a '{nuevo_estado}'"]
                )
            except gspread.exceptions.WorksheetNotFound:
                pass  # la pestaña Historial_Tareas es opcional
            return


def get_historial_tarea(tarea_id: int) -> list[dict]:
    df = _leer("Historial_Tareas")
    if df.empty or "Tarea_ID" not in df.columns:
        return [{"fecha": HOY, "evento": "Tarea creada"}]
    sub = df[df["Tarea_ID"] == tarea_id]
    if sub.empty:
        return [{"fecha": HOY, "evento": "Tarea creada"}]
    return [
        {"fecha": _parse_fecha(r["Fecha"]), "evento": r["Evento"]}
        for _, r in sub.iterrows()
    ]


# ---------------------------------------------------------------------------
# CHECKLISTS
# ---------------------------------------------------------------------------
@st.cache_data(ttl=300)
def get_checklist_template(tipo: str) -> list[str]:
    df = _leer("Checklist_Plantillas")
    if df.empty:
        return []
    sub = df[df["Tipo"] == tipo].sort_values("Orden")
    return sub["Paso"].tolist()


def get_checklist_progreso(cliente: str, tipo: str) -> dict[str, bool]:
    """Devuelve {paso: completado} para pintar los checkboxes ya marcados."""
    df = _leer("Checklist_Progreso")
    if df.empty:
        return {}
    sub = df[(df["Cliente"] == cliente) & (df["Tipo"] == tipo)]
    return {
        r["Paso"]: str(r["Completado"]).strip().upper() == "TRUE"
        for _, r in sub.iterrows()
    }


def set_checklist_item(cliente: str, tipo: str, paso: str, completado: bool) -> None:
    ws = _ws("Checklist_Progreso")
    registros = ws.get_all_records()
    valor = "TRUE" if completado else "FALSE"
    fecha = HOY.strftime("%d/%m/%Y")

    for i, r in enumerate(registros, start=2):  # fila 1 = encabezados
        if r["Cliente"] == cliente and r["Tipo"] == tipo and r["Paso"] == paso:
            ws.update(f"D{i}:E{i}", [[valor, fecha]])
            return

    ws.append_row([cliente, tipo, paso, valor, fecha])


# ---------------------------------------------------------------------------
# EQUIPO
# ---------------------------------------------------------------------------
@st.cache_data(ttl=30)
def get_equipo() -> pd.DataFrame:
    equipo = _leer("Equipo")
    if equipo.empty:
        return equipo
    equipo = equipo.rename(columns={"Nombre": "nombre", "Rol": "rol"})

    tareas = get_tareas()
    clientes = get_clientes()

    equipo["clientes_asignados"] = equipo["nombre"].apply(
        lambda n: (clientes["responsable_obligacion"] == n).sum() if not clientes.empty else 0
    )
    equipo["tareas_activas"] = equipo["nombre"].apply(
        lambda n: ((tareas["responsable"] == n) & tareas["estado"].isin(["Pendiente", "En proceso"])).sum()
        if not tareas.empty else 0
    )
    equipo["tareas_vencidas"] = equipo["nombre"].apply(
        lambda n: ((tareas["responsable"] == n) & (tareas["estado"] == "Vencida")).sum()
        if not tareas.empty else 0
    )
    return equipo


# ---------------------------------------------------------------------------
# HELPERS DE ESTADO / COLOR (sin cambios frente a mock_data.py — no golpean la hoja)
# ---------------------------------------------------------------------------
def estado_semaforo(fecha_vencimiento: date) -> str:
    dias = (fecha_vencimiento - HOY).days
    if dias < 0:
        return "🔴"
    elif dias <= 5:
        return "🟡"
    return "🟢"
