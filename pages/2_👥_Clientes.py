import re

import streamlit as st
from utils.sheets import get_clientes, get_tareas, estado_semaforo

st.set_page_config(page_title="Clientes", page_icon="👥", layout="wide")
st.title("👥 Clientes")

clientes = get_clientes()
tareas = get_tareas()

col_filtro, _ = st.columns([1, 3])
with col_filtro:
    filtro_estado = st.selectbox("Filtrar por estado", ["Todos", "Activo", "Inactivo"])

vista = clientes if filtro_estado == "Todos" else clientes[clientes["estado"] == filtro_estado]

st.subheader("Listado general")
tabla = vista.copy()
tabla["🔔"] = tabla["fecha_vencimiento"].apply(estado_semaforo)
st.dataframe(
    tabla[["🔔", "nombre", "nit", "responsabilidades", "estado", "proximo_vencimiento", "responsable_obligacion", "fecha_vencimiento"]],
    column_config={
        "nombre": "Cliente", "nit": "NIT", "responsabilidades": "Responsabilidades", "estado": "Estado",
        "proximo_vencimiento": "Próxima obligación",
        "responsable_obligacion": "Responsable de esa obligación",
        "fecha_vencimiento": st.column_config.DateColumn("Vence", format="DD/MM/YYYY"),
    },
    hide_index=True, use_container_width=True,
)

st.divider()
st.subheader("🔍 Ficha del cliente")
cliente_sel = st.selectbox("Selecciona un cliente", vista["nombre"])
info = clientes[clientes["nombre"] == cliente_sel].iloc[0]

tab_info, tab_oblig, tab_docs = st.tabs(["Información", "Obligaciones", "Documentos"])

with tab_info:
    c1, c2 = st.columns(2)
    c1.markdown(f"**NIT:** {info['nit']}")

    c1.markdown("**Responsabilidades:**")
    # Acepta tanto "IVA, Retención, Nómina" (comas) como varias líneas
    # dentro de la misma celda (Alt+Enter en Sheets).
    partes = [p.strip() for p in re.split(r"[,\n]", str(info["responsabilidades"])) if p.strip()]
    if partes:
        for p in partes:
            c1.markdown(f"- {p}")
    else:
        c1.caption("Sin responsabilidades registradas.")

    c1.markdown(f"**Estado:** {info['estado']}")
    c2.markdown(f"**Próximo vencimiento:** {info['proximo_vencimiento']} ({info['fecha_vencimiento'].strftime('%d/%m/%Y')})")
    c2.markdown(f"**Responsable de esa obligación:** {info['responsable_obligacion']}")

with tab_oblig:
    tareas_cliente = tareas[tareas["cliente"] == cliente_sel]
    if tareas_cliente.empty:
        st.caption("Sin tareas registradas para este cliente.")
    else:
        st.dataframe(
            tareas_cliente[["titulo", "responsable", "estado", "prioridad", "fecha_limite"]],
            column_config={
                "titulo": "Tarea", "responsable": "Responsable", "estado": "Estado", "prioridad": "Prioridad",
                "fecha_limite": st.column_config.DateColumn("Fecha límite", format="DD/MM/YYYY"),
            },
            hide_index=True, use_container_width=True,
        )

with tab_docs:
    st.caption("En la versión conectada a Supabase Storage, aquí se listarán y subirán los documentos del cliente.")
    st.file_uploader(
        "Subir documento (RUT, Cámara de Comercio, certificados, estados financieros, facturas)",
        accept_multiple_files=True,
    )
    st.caption("Demo: los archivos no se guardan todavía — falta conectar Supabase Storage.")
