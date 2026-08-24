"""
Capa de datos real (Supabase).

Mismo contrato que utils/mock_data.py: mismas funciones, mismos nombres de
columnas en los DataFrames devueltos. Para migrar una página de mock a real,
basta con cambiar el import:

    from utils.mock_data import get_clientes, get_tareas   # antes
    from utils.db import get_clientes, get_tareas           # después

Requiere en .streamlit/secrets.toml (o en Streamlit Community Cloud, en la
sección Secrets de la app):

    SUPABASE_URL = "https://xxxx.supabase.co"
    SUPABASE_KEY = "..."   # anon key (con RLS activo) o service_role si corre solo en backend

Y el esquema de supabase/schema.sql ya ejecutado en el proyecto de Supabase.
"""

from datetime import date

import pandas as pd
import streamlit as st
from supabase import create_client, Client


@st.cache_resource
def _client() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])


HOY = date.today()


# ---------------------------------------------------------------------------
# CLIENTES
# ---------------------------------------------------------------------------
@st.cache_data(ttl=60)
def get_clientes() -> pd.DataFrame:
    res = (
        _client()
        .table("clientes")
        .select("id, nombre, nit, estado, proximo_vencimiento, fecha_vencimiento, equipo(nombre)")
        .execute()
    )
    df = pd.DataFrame(res.data)
    if df.empty:
        return df
    df["responsable"] = df["equipo"].apply(lambda e: e["nombre"] if e else None)
    df["fecha_vencimiento"] = pd.to_datetime(df["fecha_vencimiento"]).dt.date
    return df.drop(columns=["equipo"])


# ---------------------------------------------------------------------------
# TAREAS
# ---------------------------------------------------------------------------
@st.cache_data(ttl=60)
def get_tareas() -> pd.DataFrame:
    res = (
        _client()
        .table("tareas")
        .select("id, titulo, estado, prioridad, fecha_limite, clientes(nombre), equipo(nombre)")
        .execute()
    )
    df = pd.DataFrame(res.data)
    if df.empty:
        return df
    df["cliente"] = df["clientes"].apply(lambda c: c["nombre"] if c else None)
    df["responsable"] = df["equipo"].apply(lambda e: e["nombre"] if e else None)
    df["fecha_limite"] = pd.to_datetime(df["fecha_limite"]).dt.date
    return df.drop(columns=["clientes", "equipo"])


def crear_tarea(titulo: str, cliente_id: int, responsable_id: int, fecha_limite: date,
                 prioridad: str = "Media", estado: str = "Pendiente") -> None:
    _client().table("tareas").insert({
        "titulo": titulo,
        "cliente_id": cliente_id,
        "responsable_id": responsable_id,
        "fecha_limite": fecha_limite.isoformat(),
        "prioridad": prioridad,
        "estado": estado,
    }).execute()
    get_tareas.clear()


def get_historial_tarea(tarea_id: int) -> list[dict]:
    res = (
        _client()
        .table("tarea_historial")
        .select("creado_en, evento")
        .eq("tarea_id", tarea_id)
        .order("creado_en")
        .execute()
    )
    if not res.data:
        return [{"fecha": HOY, "evento": "Tarea creada"}]
    return [{"fecha": pd.to_datetime(r["creado_en"]).date(), "evento": r["evento"]} for r in res.data]


# ---------------------------------------------------------------------------
# CHECKLISTS
# ---------------------------------------------------------------------------
@st.cache_data(ttl=300)
def get_checklist_template(tipo: str) -> list[str]:
    res = (
        _client()
        .table("checklist_template_items")
        .select("paso")
        .eq("tipo", tipo)
        .order("orden")
        .execute()
    )
    return [r["paso"] for r in res.data]


def get_checklist_progreso(cliente_id: int, tipo: str) -> dict[str, bool]:
    """Devuelve {paso: completado} para pintar los checkboxes ya marcados."""
    res = (
        _client()
        .table("checklist_items")
        .select("completado, checklist_template_items(paso)")
        .eq("cliente_id", cliente_id)
        .eq("tipo", tipo)
        .execute()
    )
    return {r["checklist_template_items"]["paso"]: r["completado"] for r in res.data}


def set_checklist_item(cliente_id: int, tipo: str, template_item_id: int, completado: bool) -> None:
    _client().table("checklist_items").upsert({
        "cliente_id": cliente_id,
        "tipo": tipo,
        "template_item_id": template_item_id,
        "completado": completado,
    }, on_conflict="cliente_id,template_item_id").execute()


# ---------------------------------------------------------------------------
# EQUIPO
# ---------------------------------------------------------------------------
@st.cache_data(ttl=60)
def get_equipo() -> pd.DataFrame:
    equipo = pd.DataFrame(_client().table("equipo").select("id, nombre, rol").execute().data)
    if equipo.empty:
        return equipo

    tareas = get_tareas()
    clientes = get_clientes()

    equipo["clientes_asignados"] = equipo["nombre"].apply(lambda n: (clientes["responsable"] == n).sum())
    equipo["tareas_activas"] = equipo["nombre"].apply(
        lambda n: ((tareas["responsable"] == n) & tareas["estado"].isin(["Pendiente", "En proceso"])).sum()
    )
    equipo["tareas_vencidas"] = equipo["nombre"].apply(
        lambda n: ((tareas["responsable"] == n) & (tareas["estado"] == "Vencida")).sum()
    )
    return equipo.drop(columns=["id"])


# ---------------------------------------------------------------------------
# HELPERS DE ESTADO / COLOR (sin cambios frente a mock_data.py — no golpean la BD)
# ---------------------------------------------------------------------------
def estado_semaforo(fecha_vencimiento: date) -> str:
    dias = (fecha_vencimiento - HOY).days
    if dias < 0:
        return "🔴"
    elif dias <= 5:
        return "🟡"
    return "🟢"
