"""
Capa de datos real (Google Sheets).

Mismo contrato "de cara a las páginas" que utils/mock_data.py: las funciones
devuelven DataFrames con columnas legibles (nombre, cliente, responsable...),
aunque por dentro el Sheet ya funciona como una base de datos relacional real:
cada tabla tiene una llave primaria (ID_*) y las relaciones entre tablas se
hacen por esa llave, no por texto repetido. Para migrar una página de mock a
real, basta con cambiar el import:

    from utils.mock_data import get_clientes, get_tareas   # antes
    from utils.sheets import get_clientes, get_tareas       # después

Esquema del Google Sheet (llave primaria en negrita):

    Clientes             **ID_Cliente**, Nombre, NIT, Responsabilidades,
                         Software_Contable, Estado
    Equipo               **ID_Equipo**, Nombre, Rol, Email
    Tipos_Obligacion     **ID_Tipo**, Nombre
    Tareas               **ID**, Titulo, ID_Cliente→Clientes,
                         ID_Responsable→Equipo, Estado, Prioridad, Fecha_Limite,
                         ID_Tipo→Tipos_Obligacion (vacío si la tarea se creó a
                         mano en vez de generarse desde un checklist)
    Checklist_Plantillas ID_Tipo→Tipos_Obligacion, Orden, Paso,
                         ID_Responsable→Equipo   (llave compuesta ID_Tipo+Orden)
    Responsables_Obligacion  ID_Tipo→Tipos_Obligacion (una fila por tipo),
                         ID_Responsable→Equipo
    Checklist_Progreso   ID_Cliente→Clientes, ID_Tipo→Tipos_Obligacion, Paso,
                         Completado, Fecha_Actualizacion
    Historial_Tareas     Tarea_ID→Tareas.ID, Fecha, Evento
    Calendario_DIAN      NIT→Clientes.NIT (llave natural: así llega el
                         calendario oficial de la DIAN), Fecha,
                         ID_Tipo→Tipos_Obligacion

Todas las funciones get_* resuelven esas llaves internamente y devuelven
nombres legibles (cliente, responsable, tipo) — las páginas nunca ven un ID
suelto, salvo donde se expone a propósito (ej. clientes["id"]).

Requiere en .streamlit/secrets.toml (ver guía paso a paso):

    GOOGLE_SHEET_ID = "..."

    [gcp_service_account]
    type = "service_account"
    ...  (todo el contenido del JSON de la cuenta de servicio)

Y que la hoja esté compartida (como Editor) con el "client_email" de esa
cuenta de servicio.
"""

import re
from datetime import date, datetime, timedelta

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


@st.cache_resource
def _ws(nombre: str):
    """Se cachea como recurso (no solo los datos) porque .worksheet() hace
    una llamada de METADATA a la API de Sheets cada vez que se invoca — sin
    cachear, cada _leer()/escritura dispara esa llamada de más, y con varias
    en un mismo rerun (ej. al generar tareas del calendario) se llega rápido
    al límite de peticiones por minuto de Google y la app truena con un
    gspread.exceptions.APIError. Cachear el objeto Worksheet no cachea sus
    datos: cada .get_all_records()/.append_row()/etc. sobre él sigue yendo
    a la API en el momento, solo se evita repetir la búsqueda de la pestaña."""
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


def _id(valor) -> int | None:
    """Convierte el valor de una celda ID_* a entero comparable. Google
    Sheets puede devolver un mismo ID como int, float (1.0) o texto ("1")
    según cómo esté formateada la celda — esto normaliza los tres casos.
    Si la celda está vacía o no es un número, devuelve None."""
    try:
        return int(float(valor))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# MAPAS DE LLAVES (id <-> nombre) — leen la pestaña "cruda", sin pasar por
# get_equipo()/get_clientes(), para no crear referencias circulares (esas dos
# funciones a su vez usan estos mapas indirectamente a través de otras).
# ---------------------------------------------------------------------------
@st.cache_data(ttl=30)
def _mapa_equipo_id_a_nombre() -> dict:
    df = _leer("Equipo")
    if df.empty or "ID_Equipo" not in df.columns:
        return {}
    return {_id(r["ID_Equipo"]): str(r["Nombre"]).strip() for _, r in df.iterrows() if _id(r["ID_Equipo"]) is not None}


@st.cache_data(ttl=30)
def _mapa_equipo_nombre_a_id() -> dict:
    return {v: k for k, v in _mapa_equipo_id_a_nombre().items()}


@st.cache_data(ttl=30)
def _mapa_clientes_id_a_nombre() -> dict:
    df = _leer("Clientes")
    if df.empty or "ID_Cliente" not in df.columns:
        return {}
    return {_id(r["ID_Cliente"]): str(r["Nombre"]).strip() for _, r in df.iterrows() if _id(r["ID_Cliente"]) is not None}


@st.cache_data(ttl=30)
def _mapa_clientes_nombre_a_id() -> dict:
    return {v: k for k, v in _mapa_clientes_id_a_nombre().items()}


@st.cache_data(ttl=30)
def _mapa_clientes_por_nit() -> dict:
    """{NIT normalizado: (id_cliente, nombre)} — para poder generar tareas a
    partir de una fila de Calendario_DIAN, que solo trae el NIT."""
    df = _leer("Clientes")
    if df.empty or "ID_Cliente" not in df.columns:
        return {}
    mapa = {}
    for _, r in df.iterrows():
        id_cliente = _id(r.get("ID_Cliente"))
        nit_norm = _normalizar_nit(r.get("NIT"))
        if id_cliente is not None and nit_norm:
            mapa[nit_norm] = (id_cliente, str(r.get("Nombre", "")).strip())
    return mapa


@st.cache_data(ttl=300)
def get_tipos_obligacion() -> pd.DataFrame:
    """Catálogo de tipos de obligación (IVA, Retención en la fuente, ...).
    Es la tabla "padre" que Checklist_Plantillas, Responsables_Obligacion,
    Calendario_DIAN y Checklist_Progreso referencian por ID_Tipo en vez de
    repetir el nombre como texto en cada una."""
    try:
        df = _leer("Tipos_Obligacion")
    except gspread.exceptions.WorksheetNotFound:
        return pd.DataFrame(columns=["id", "nombre"])
    if df.empty:
        return pd.DataFrame(columns=["id", "nombre"])
    return df.rename(columns={"ID_Tipo": "id", "Nombre": "nombre"})


@st.cache_data(ttl=300)
def _tipos_id_a_nombre() -> dict:
    df = get_tipos_obligacion()
    return {_id(r["id"]): str(r["nombre"]).strip() for _, r in df.iterrows() if _id(r["id"]) is not None}


@st.cache_data(ttl=300)
def _tipos_nombre_a_id() -> dict:
    return {v: k for k, v in _tipos_id_a_nombre().items()}


# ---------------------------------------------------------------------------
# CALENDARIO DIAN
# ---------------------------------------------------------------------------
@st.cache_data(ttl=300)
def get_calendario_dian() -> pd.DataFrame:
    """Una fila por (NIT, fecha, tipo de obligación), leída de la pestaña
    Calendario_DIAN. Es la fuente real de los vencimientos de cada cliente.
    El cruce con Clientes se hace por NIT (llave natural — así llega el
    calendario oficial de la DIAN), y el tipo de obligación se resuelve desde
    Tipos_Obligacion a partir de ID_Tipo. Si la pestaña todavía no existe,
    devuelve un DataFrame vacío en vez de tumbar la app."""
    try:
        df = _leer("Calendario_DIAN")
    except gspread.exceptions.WorksheetNotFound:
        return pd.DataFrame()
    if df.empty:
        return df
    df = df.rename(columns={"NIT": "nit", "Fecha": "fecha_raw", "ID_Tipo": "id_tipo"})
    df["fecha"] = df["fecha_raw"].apply(_parse_fecha)
    tipos = _tipos_id_a_nombre()
    df["tipo"] = df["id_tipo"].apply(lambda v: tipos.get(_id(v), ""))
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
COLUMNAS_CLIENTES = [
    "id", "nombre", "nit", "responsabilidades", "software_contable", "estado",
    "proximo_vencimiento", "responsable_obligacion", "fecha_vencimiento",
]


@st.cache_data(ttl=30)
def get_clientes() -> pd.DataFrame:
    df = _leer("Clientes")
    if df.empty:
        # Sin filas todavía (pestaña recién creada o vacía) — se devuelve con
        # las columnas esperadas para que el resto de la app no truene con un
        # KeyError al intentar leer clientes["nombre"], etc.
        return pd.DataFrame(columns=COLUMNAS_CLIENTES)
    df = df.rename(columns={
        "ID_Cliente": "id", "Nombre": "nombre", "NIT": "nit",
        "Responsabilidades": "responsabilidades", "Software_Contable": "software_contable",
        "Estado": "estado", "Proxima_Obligacion": "proximo_vencimiento",
    })
    # Si el Sheet todavía no tiene estas columnas (migración en curso), se
    # crean vacías en vez de tumbar toda la app con un KeyError.
    for col in ("responsabilidades", "software_contable"):
        if col not in df.columns:
            df[col] = ""

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

    # El responsable de cada obligación se busca en Responsables_Obligacion
    # (por ID_Tipo), así un solo cambio ahí actualiza a todos los clientes que
    # tengan ese tipo entre sus próximas obligaciones. Si las obligaciones del
    # mismo día tienen responsables distintos, se listan todos (sin repetir).
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
COLUMNAS_TAREAS = ["id", "titulo", "cliente", "tipo", "responsable", "estado", "prioridad", "fecha_limite"]


@st.cache_data(ttl=30)
def get_tareas() -> pd.DataFrame:
    df = _leer("Tareas")
    if df.empty:
        # Sin tareas todavía — devolver con las columnas esperadas en vez de
        # un DataFrame totalmente vacío, para que tareas["estado"] no truene.
        return pd.DataFrame(columns=COLUMNAS_TAREAS)
    df = df.rename(columns={
        "ID": "id", "Titulo": "titulo", "ID_Cliente": "id_cliente",
        "ID_Responsable": "id_responsable", "Estado": "estado", "Prioridad": "prioridad",
        "ID_Tipo": "id_tipo",
    })
    # Columna nueva (Tareas generadas desde el calendario) — si el Sheet
    # todavía no la tiene, se crea vacía en vez de tumbar la app.
    if "id_tipo" not in df.columns:
        df["id_tipo"] = None

    clientes_map = _mapa_clientes_id_a_nombre()
    equipo_map = _mapa_equipo_id_a_nombre()
    tipos_map = _tipos_id_a_nombre()
    df["cliente"] = df["id_cliente"].apply(lambda v: clientes_map.get(_id(v), "(cliente no encontrado)"))
    df["responsable"] = df["id_responsable"].apply(lambda v: equipo_map.get(_id(v), "(responsable no encontrado)"))
    # Las tareas creadas a mano (no generadas desde un checklist) no tienen
    # tipo — queda como cadena vacía en vez de "None".
    df["tipo"] = df["id_tipo"].apply(lambda v: tipos_map.get(_id(v), ""))
    df["fecha_limite"] = df["Fecha_Limite"].apply(_parse_fecha)
    return df.drop(columns=["Fecha_Limite"])


def crear_tarea(titulo: str, cliente: str, responsable: str, fecha_limite: date,
                 prioridad: str = "Media", estado: str = "Pendiente") -> None:
    """Recibe cliente/responsable por NOMBRE (así los eligen en el
    selectbox) y los guarda como ID_Cliente/ID_Responsable en la hoja —
    la página no necesita saber que por dentro todo es relacional. Esta
    función es para tareas sueltas creadas a mano, por eso no lleva tipo de
    obligación (queda en blanco en la columna ID_Tipo)."""
    ws = _ws("Tareas")
    ids_existentes = [int(v) for v in ws.col_values(1)[1:] if str(v).strip().isdigit()]
    nuevo_id = max(ids_existentes, default=0) + 1
    id_cliente = _mapa_clientes_nombre_a_id().get(cliente)
    id_responsable = _mapa_equipo_nombre_a_id().get(responsable)
    ws.append_row([
        nuevo_id, titulo, id_cliente, id_responsable, estado, prioridad,
        fecha_limite.strftime("%d/%m/%Y"), "",
    ])
    get_tareas.clear()


def generar_tareas_desde_calendario(horizonte_dias: int = 30) -> dict:
    """Convierte cada obligación próxima de Calendario_DIAN (cliente + tipo +
    fecha) en tareas reales: una por cada paso del checklist de ese tipo
    (Checklist_Plantillas), asignada al responsable de ese paso, con
    Fecha_Limite = la fecha de la obligación.

    Es la manera de que "las tareas sean los pasos del checklist, generadas
    según el calendario" en vez de crearse una por una a mano. Se puede
    correr las veces que sea: si una obligación (mismo cliente + tipo +
    fecha) ya tiene tareas generadas, se omite — no duplica.

    Devuelve un resumen: {"tareas_creadas", "obligaciones_generadas",
    "obligaciones_omitidas", "clientes"}."""
    resumen = {"tareas_creadas": 0, "obligaciones_generadas": 0, "obligaciones_omitidas": 0, "clientes": 0}

    calendario = get_calendario_dian()
    if calendario.empty:
        return resumen

    limite = HOY + timedelta(days=horizonte_dias)
    proximas = calendario.dropna(subset=["fecha"])
    proximas = proximas[(proximas["fecha"] >= HOY) & (proximas["fecha"] <= limite)]
    if proximas.empty:
        return resumen

    clientes_por_nit = _mapa_clientes_por_nit()
    equipo_nombre_a_id = _mapa_equipo_nombre_a_id()
    tareas_existentes = _leer("Tareas")
    tiene_columnas_ids = (
        not tareas_existentes.empty
        and "ID_Cliente" in tareas_existentes.columns
        and "ID_Tipo" in tareas_existentes.columns
        and "Fecha_Limite" in tareas_existentes.columns
    )

    def _ya_generada(id_cliente, id_tipo, fecha_str) -> bool:
        if not tiene_columnas_ids:
            return False
        coincide = (
            (tareas_existentes["ID_Cliente"].apply(_id) == id_cliente)
            & (tareas_existentes["ID_Tipo"].apply(_id) == id_tipo)
            & (tareas_existentes["Fecha_Limite"].astype(str).str.strip() == fecha_str)
        )
        return bool(coincide.any())

    ws = _ws("Tareas")
    ids_existentes = [int(v) for v in ws.col_values(1)[1:] if str(v).strip().isdigit()]
    siguiente_id = max(ids_existentes, default=0) + 1

    # Se trae el checklist de cada tipo UNA sola vez (no una vez por fila del
    # calendario) — con 636 filas y varias decenas dentro del horizonte, sin
    # esto se dispararían igual de llamadas repetidas a la API de Sheets.
    tipos_en_rango = {t for t in proximas["tipo"] if t}
    plantillas_por_tipo = {t: get_checklist_template_detallado(t) for t in tipos_en_rango}

    filas_nuevas = []
    clientes_tocados = set()

    for _, fila in proximas.iterrows():
        info_cliente = clientes_por_nit.get(_normalizar_nit(fila["nit"]))
        if not info_cliente:
            continue  # NIT del calendario que todavía no tiene cliente registrado
        id_cliente, _nombre_cliente = info_cliente
        id_tipo = _id(fila.get("id_tipo"))
        tipo_nombre = fila.get("tipo", "")
        fecha_obj = fila["fecha"]
        fecha_str = fecha_obj.strftime("%d/%m/%Y")

        if _ya_generada(id_cliente, id_tipo, fecha_str):
            resumen["obligaciones_omitidas"] += 1
            continue

        pasos = plantillas_por_tipo.get(tipo_nombre, [])
        if not pasos:
            continue  # todavía no hay checklist definido para este tipo

        dias_para_vencer = (fecha_obj - HOY).days
        prioridad = "Alta" if dias_para_vencer <= 5 else "Media" if dias_para_vencer <= 15 else "Baja"

        for paso in pasos:
            id_responsable = equipo_nombre_a_id.get(paso["responsable"])
            filas_nuevas.append([
                siguiente_id, paso["paso"], id_cliente, id_responsable,
                "Pendiente", prioridad, fecha_str, id_tipo,
            ])
            siguiente_id += 1

        resumen["obligaciones_generadas"] += 1
        clientes_tocados.add(id_cliente)

    if filas_nuevas:
        ws.append_rows(filas_nuevas)
        get_tareas.clear()

    resumen["tareas_creadas"] = len(filas_nuevas)
    resumen["clientes"] = len(clientes_tocados)
    return resumen


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
    """{nombre del tipo: nombre del responsable}, resuelto desde
    Responsables_Obligacion (que guarda ID_Tipo + ID_Responsable) contra los
    catálogos Tipos_Obligacion y Equipo.

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
    if df.empty:
        return {}
    tipos = _tipos_id_a_nombre()
    equipo = _mapa_equipo_id_a_nombre()
    mapa = {}
    for _, r in df.iterrows():
        tipo_nombre = tipos.get(_id(r.get("ID_Tipo")))
        resp_nombre = equipo.get(_id(r.get("ID_Responsable")))
        if tipo_nombre and resp_nombre and tipo_nombre not in mapa:
            mapa[tipo_nombre] = resp_nombre
    return mapa


@st.cache_data(ttl=300)
def get_checklist_template(tipo: str) -> list[str]:
    """Recibe el NOMBRE del tipo (el que se ve en el selectbox) y lo resuelve
    a ID_Tipo para filtrar Checklist_Plantillas."""
    df = _leer("Checklist_Plantillas")
    if df.empty:
        return []
    id_tipo = _tipos_nombre_a_id().get(tipo)
    sub = df[df["ID_Tipo"].apply(_id) == id_tipo].sort_values("Orden")
    return sub["Paso"].tolist()


@st.cache_data(ttl=300)
def get_checklist_template_detallado(tipo: str) -> list[dict]:
    """Igual que get_checklist_template, pero además trae el responsable de
    CADA paso — lo usa generar_tareas_desde_calendario() para saber a quién
    asignarle cada tarea."""
    df = _leer("Checklist_Plantillas")
    if df.empty:
        return []
    id_tipo = _tipos_nombre_a_id().get(tipo)
    sub = df[df["ID_Tipo"].apply(_id) == id_tipo].sort_values("Orden")
    equipo = _mapa_equipo_id_a_nombre()
    return [
        {"paso": r["Paso"], "responsable": equipo.get(_id(r.get("ID_Responsable")), "")}
        for _, r in sub.iterrows()
    ]


def get_checklist_progreso(cliente: str, tipo: str) -> dict[str, bool]:
    """Devuelve {paso: completado} para pintar los checkboxes ya marcados.
    cliente/tipo llegan por nombre y se resuelven a ID_Cliente/ID_Tipo."""
    df = _leer("Checklist_Progreso")
    if df.empty:
        return {}
    id_cliente = _mapa_clientes_nombre_a_id().get(cliente)
    id_tipo = _tipos_nombre_a_id().get(tipo)
    sub = df[(df["ID_Cliente"].apply(_id) == id_cliente) & (df["ID_Tipo"].apply(_id) == id_tipo)]
    return {
        r["Paso"]: str(r["Completado"]).strip().upper() == "TRUE"
        for _, r in sub.iterrows()
    }


def set_checklist_item(cliente: str, tipo: str, paso: str, completado: bool) -> None:
    ws = _ws("Checklist_Progreso")
    registros = ws.get_all_records()
    id_cliente = _mapa_clientes_nombre_a_id().get(cliente)
    id_tipo = _tipos_nombre_a_id().get(tipo)
    valor = "TRUE" if completado else "FALSE"
    fecha = HOY.strftime("%d/%m/%Y")

    for i, r in enumerate(registros, start=2):  # fila 1 = encabezados
        if _id(r.get("ID_Cliente")) == id_cliente and _id(r.get("ID_Tipo")) == id_tipo and r.get("Paso") == paso:
            ws.update(f"D{i}:E{i}", [[valor, fecha]])
            return

    ws.append_row([id_cliente, id_tipo, paso, valor, fecha])


# ---------------------------------------------------------------------------
# EQUIPO
# ---------------------------------------------------------------------------
COLUMNAS_EQUIPO = ["id", "nombre", "rol", "clientes_asignados", "tareas_activas", "tareas_vencidas"]


@st.cache_data(ttl=30)
def get_equipo() -> pd.DataFrame:
    equipo = _leer("Equipo")
    if equipo.empty:
        return pd.DataFrame(columns=COLUMNAS_EQUIPO)
    equipo = equipo.rename(columns={"ID_Equipo": "id", "Nombre": "nombre", "Rol": "rol"})

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
def estado_semaforo(fecha_vencimiento: date | None) -> str:
    # Clientes sin ninguna fecha registrada en Calendario_DIAN (todavía no
    # están ahí, o no tienen próxima obligación) no deben tumbar la app.
    if not fecha_vencimiento:
        return "⚪"
    dias = (fecha_vencimiento - HOY).days
    if dias < 0:
        return "🔴"
    elif dias <= 5:
        return "🟡"
    return "🟢"
