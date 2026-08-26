"""
Capa de datos real (Google Sheets).

Mismo contrato que utils/mock_data.py: mismas funciones, mismos nombres de
columnas en los DataFrames devueltos. Para migrar una página de mock a real,
basta con cambiar el import:

    from utils.mock_data import get_clientes, get_tareas   # antes
    from utils.sheets import get_clientes, get_tareas       # después

Lee y escribe directamente sobre el Google Sheet que sigue la estructura de
Plantilla_Despacho_Contable.xlsx (pestañas: Clientes, Tareas, Equipo,
Calendario_DIAN, Checklist_Plantillas, Checklist_Progreso, Historial_Tareas,
Responsables_Obligacion).

Requiere en .streamlit/secrets.toml (ver guía paso a paso):

    GOOGLE_SHEET_ID = "..."

    [gcp_service_account]
    type = "service_account"
    ...  (todo el contenido del JSON de la cuenta de servicio)

Y que la hoja esté compartida (como Editor) con el "client_email" de esa
cuenta de servicio.
"""

import re
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


def _normalizar_nit(nit) -> str:
    """Quita puntos y espacios para poder cruzar NITs aunque estén escritos
    con formato distinto en Clientes vs. Calendario_DIAN (ej. '902.063.943-2'
    vs '902063943-2')."""
    return re.sub(r"[.\s]", "", str(nit or "")).strip()


# ---------------------------------------------------------------------------
# CALENDARIO DIAN
# ---------------------------------------------------------------------------
@st.cache_data(ttl=300)
def get_calendario_dian() -> pd.DataFrame:
    """Una fila por (NIT, fecha, tipo de obligación), leída de la pestaña
    Calendario_DIAN. Es la fuente real de los vencimientos de cada cliente.
    Si la pestaña todavía no existe, devuelve un DataFrame vacío en vez de
    tumbar la app."""
    try:
        df = _leer("Calendario_DIAN")
    except gspread.exceptions.WorksheetNotFound:
        return pd.DataFrame()
    if df.empty:
        return df
    df = df.rename(columns={"NIT": "nit", "Fecha": "fecha_raw", "Tipo_Obligacion": "tipo"})
    df["fecha"] = df["fecha_raw"].apply(_parse_fecha)
    return df.drop(columns=["fecha_raw"])


def _proxima_obligacion_nit(nit, calendario: pd.DataFrame):
    """(fecha, tipos) de la próxima obligación de un NIT según Calendario_DIAN.
    `tipos` es una lista porque varias obligaciones distintas pueden vencer el
    mismo día (ej. IVA + Retención en la fuente + Retención ICA). Si ya
    pasaron todas las fechas registradas, devuelve la más reciente en vez de
    dejarlo en blanco. Si el NIT no aparece ahí, devuelve (None, [])."""
    if calendario.empty:
        return None, []
    clave = _normalizar_nit(nit)
    sub = calendario[calendario["nit"].apply(_normalizar_nit) == clave].dropna(subset=["fecha"])
    if sub.empty:
        return None, []
    futuras = sub[sub["fecha"] >= HOY]
    origen = futuras if not futuras.empty else sub
    fecha_obj = origen["fecha"].min() if not futuras.empty else origen["fecha"].max()
    tipos = origen[origen["fecha"] == fecha_obj]["tipo"].tolist()
    return fecha_obj, tipos


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
    })
    # Si el Sheet todavía no tiene esta columna (migración en curso), se
    # crea vacía en vez de tumbar toda la app con un KeyError.
    if "responsabilidades" not in df.columns:
        df["responsabilidades"] = ""

    # Fecha/tipo escritos a mano en Clientes (si existen) solo se usan como
    # respaldo cuando el NIT no aparece todavía en Calendario_DIAN.
    fecha_manual = df["Fecha_Vencimiento"].apply(_parse_fecha) if "Fecha_Vencimiento" in df.columns else None
    if "Fecha_Vencimiento" in df.columns:
        df = df.drop(columns=["Fecha_Vencimiento"])
    if "proximo_vencimiento" not in df.columns:
        df["proximo_vencimiento"] = ""

    # La fuente real de la fecha y el tipo de obligación es Calendario_DIAN,
    # cruzado por NIT — así se calculan solas y no hay que escribirlas cliente
    # por cliente cada mes.
    calendario = get_calendario_dian()
    fechas, tipos_por_cliente = [], []
    for i, nit in enumerate(df["nit"]):
        fecha, tipos = _proxima_obligacion_nit(nit, calendario)
        if fecha is None:
            fecha = fecha_manual.iloc[i] if fecha_manual is not None else None
            manual = str(df["proximo_vencimiento"].iloc[i] or "").strip()
            tipos = [manual] if manual else []
        fechas.append(fecha)
        tipos_por_cliente.append(tipos)
    df["fecha_vencimiento"] = fechas
    # Cuando varias obligaciones vencen el mismo día se muestran juntas,
    # separadas por coma (ej. "IVA, Retención en la fuente, Retención ICA").
    df["proximo_vencimiento"] = [", ".join(t) for t in tipos_por_cliente]

    # El responsable de cada obligación se busca en Checklist_Plantillas según
    # el Tipo (columna Responsable), así un solo cambio ahí actualiza a todos
    # los clientes que tengan ese tipo entre sus próximas obligaciones. Si las
    # obligaciones del mismo día tienen responsables distintos, se listan
    # todos (sin repetir).
    mapa = _mapa_responsables_por_tipo()

    def _responsables(tipos):
        vistos = []
        for t in tipos:
            r = mapa.get(t, "")
            if r and r not in vistos:
                vistos.append(r)
        return ", ".join(vistos)

    df["responsable_obligacion"] = [_responsables(t) for t in tipos_por_cliente]
    return df


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
def _mapa_responsables_por_tipo() -> dict:
    """{Tipo: Responsable} leído de la pestaña Responsables_Obligacion.

    Ojo: esto es distinto del Responsable que puede haber en cada fila de
    Checklist_Plantillas — ese es quién hace CADA PASO del checklist (varias
    personas por tipo, ej. quien ingresa la info no es quien la presenta).
    Responsables_Obligacion en cambio tiene una sola fila por tipo, con la
    persona "dueña"/responsable final de esa obligación (normalmente quien la
    revisa o presenta) — es la que se muestra en Clientes/Equipo como
    "Responsable de esa obligación".

    Esta pestaña es opcional: si todavía no existe en el Sheet, se devuelve
    un mapa vacío en vez de tumbar la app (así el resto de la página sigue
    funcionando mientras se termina de migrar)."""
    try:
        df = _leer("Responsables_Obligacion")
    except gspread.exceptions.WorksheetNotFound:
        return {}
    if df.empty or "Responsable" not in df.columns:
        return {}
    mapa = {}
    for _, r in df.iterrows():
        tipo = str(r.get("Tipo", "")).strip()
        resp = str(r.get("Responsable", "")).strip()
        if tipo and resp and tipo not in mapa:
            mapa[tipo] = resp
    return mapa


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
