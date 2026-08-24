"""
Dashboard - Sistema de Gestión para Despacho Contable
Punto de entrada de la app (Streamlit multipágina).

Las demás secciones viven en la carpeta pages/. Streamlit las detecta
automáticamente y arma el menú lateral con el nombre e ícono de cada archivo.
"""

import streamlit as st
import pandas as pd
from utils.sheets import get_clientes, get_tareas, get_equipo, estado_semaforo, HOY

st.set_page_config(
    page_title="Despacho Contable",
    page_icon="🏠",
    layout="wide",
)

st.title("🏠 Dashboard")
st.caption(f"Hoy es {HOY.strftime('%d de %B de %Y')}")

clientes = get_clientes()
tareas = get_tareas()
equipo = get_equipo()

# ---------------------------------------------------------------------------
# INDICADORES PRINCIPALES
# ---------------------------------------------------------------------------
pendientes = (tareas["estado"] == "Pendiente").sum()
en_proceso = (tareas["estado"] == "En proceso").sum()
vencidas = (tareas["estado"] == "Vencida").sum()
clientes_activos = (clientes["estado"] == "Activo").sum()

col1, col2, col3, col4 = st.columns(4)
col1.metric("Tareas pendientes", pendientes)
col2.metric("En proceso", en_proceso)
col3.metric("Tareas vencidas", vencidas, delta=f"{vencidas} urgentes" if vencidas else None, delta_color="inverse")
col4.metric("Clientes activos", clientes_activos)

st.divider()

# ---------------------------------------------------------------------------
# PRÓXIMOS VENCIMIENTOS
# ---------------------------------------------------------------------------
col_izq, col_der = st.columns([1.3, 1])

with col_izq:
    st.subheader("📅 Próximos vencimientos")
    prox = clientes.sort_values("fecha_vencimiento").copy()
    prox["🔔"] = prox["fecha_vencimiento"].apply(estado_semaforo)
    st.dataframe(
        prox[["🔔", "nombre", "proximo_vencimiento", "responsable_obligacion", "fecha_vencimiento"]],
        column_config={
            "nombre": "Cliente",
            "proximo_vencimiento": "Obligación",
            "responsable_obligacion": "Responsable",
            "fecha_vencimiento": st.column_config.DateColumn("Vence", format="DD/MM/YYYY"),
        },
        hide_index=True,
        use_container_width=True,
    )

with col_der:
    st.subheader("👥 Indicadores por contador")
    resumen = equipo[["nombre", "tareas_activas", "tareas_vencidas"]].set_index("nombre")
    st.bar_chart(resumen)

st.divider()

# ---------------------------------------------------------------------------
# TAREAS QUE REQUIEREN ATENCIÓN
# ---------------------------------------------------------------------------
st.subheader("⚠️ Tareas que requieren atención")
criticas = tareas[tareas["estado"].isin(["Vencida", "Pendiente"])].sort_values("fecha_limite")
st.dataframe(
    criticas[["titulo", "cliente", "responsable", "estado", "prioridad", "fecha_limite"]],
    column_config={
        "titulo": "Tarea",
        "cliente": "Cliente",
        "responsable": "Responsable",
        "estado": "Estado",
        "prioridad": "Prioridad",
        "fecha_limite": st.column_config.DateColumn("Fecha límite", format="DD/MM/YYYY"),
    },
    hide_index=True,
    use_container_width=True,
)

st.info("💡 Este dashboard usa datos de ejemplo. El siguiente paso es conectar Supabase para que todo sea real y persistente.")
