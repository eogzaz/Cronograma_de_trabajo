import streamlit as st
from utils.sheets import get_equipo, get_tareas, get_clientes

st.set_page_config(page_title="Equipo", page_icon="👤", layout="wide")
st.title("👤 Equipo")

equipo = get_equipo()
tareas = get_tareas()
clientes = get_clientes()

st.subheader("Carga laboral")
st.dataframe(
    equipo,
    column_config={
        "nombre": "Nombre", "rol": "Rol",
        "clientes_asignados": "Clientes asignados",
        "tareas_activas": "Tareas activas",
        "tareas_vencidas": "Tareas vencidas",
    },
    hide_index=True, use_container_width=True,
)

st.bar_chart(equipo.set_index("nombre")[["tareas_activas", "tareas_vencidas"]])

st.divider()
st.subheader("🔍 Detalle por persona")
persona = st.selectbox("Selecciona una persona", equipo["nombre"])

c1, c2 = st.columns(2)
with c1:
    st.markdown("**Clientes asignados**")
    st.dataframe(
        clientes[clientes["responsable"] == persona][["nombre", "estado", "proximo_vencimiento"]],
        column_config={"nombre": "Cliente", "estado": "Estado", "proximo_vencimiento": "Próxima obligación"},
        hide_index=True, use_container_width=True,
    )

with c2:
    st.markdown("**Tareas asignadas**")
    st.dataframe(
        tareas[tareas["responsable"] == persona][["titulo", "cliente", "estado", "prioridad", "fecha_limite"]],
        column_config={
            "titulo": "Tarea", "cliente": "Cliente", "estado": "Estado", "prioridad": "Prioridad",
            "fecha_limite": st.column_config.DateColumn("Fecha límite", format="DD/MM/YYYY"),
        },
        hide_index=True, use_container_width=True,
    )
