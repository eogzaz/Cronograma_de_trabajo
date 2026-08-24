import streamlit as st
from utils.sheets import (
    get_tareas, get_clientes, get_equipo, get_historial_tarea,
    crear_tarea, actualizar_estado_tarea,
)

st.set_page_config(page_title="Tareas", page_icon="📋", layout="wide")
st.title("📋 Tareas")

tareas = get_tareas()
clientes = get_clientes()
equipo = get_equipo()

ESTADOS = ["Pendiente", "En proceso", "Finalizada", "Vencida"]

tab_tablero, tab_nueva, tab_historial = st.tabs(["Tablero", "➕ Nueva tarea", "🕒 Historial"])


def _tarjeta_tarea(t):
    """Tarjeta de una tarea con selector para cambiar su estado in situ."""
    prioridad_icono = {"Alta": "🔴", "Media": "🟡", "Baja": "🟢"}.get(t["prioridad"], "⚪")
    with st.container(border=True):
        st.markdown(f"**{t['titulo']}**")
        st.caption(f"{t['cliente']} · {t['responsable']}")
        st.caption(f"{prioridad_icono} Prioridad {t['prioridad']} · vence {t['fecha_limite'].strftime('%d/%m')}")
        try:
            indice_actual = ESTADOS.index(t["estado"])
        except ValueError:
            indice_actual = 0
        nuevo_estado = st.selectbox(
            "Estado", ESTADOS, index=indice_actual,
            key=f"estado_tarea_{t['id']}", label_visibility="collapsed",
        )
        if nuevo_estado != t["estado"]:
            actualizar_estado_tarea(int(t["id"]), nuevo_estado)
            st.toast(f"🔄 '{t['titulo']}' ahora está en «{nuevo_estado}».", icon="🔄")
            st.rerun()


# ---------------------------------------------------------------------------
# TABLERO POR ESTADO
# ---------------------------------------------------------------------------
with tab_tablero:
    col_pend, col_proc, col_fin = st.columns(3)
    columnas = {
        "Pendiente": col_pend,
        "En proceso": col_proc,
        "Finalizada": col_fin,
    }

    for estado, col in columnas.items():
        with col:
            st.markdown(f"**{estado}** ({(tareas['estado'] == estado).sum()})")
            subset = tareas[tareas["estado"] == estado]
            for _, t in subset.iterrows():
                _tarjeta_tarea(t)

    vencidas = tareas[tareas["estado"] == "Vencida"]
    if not vencidas.empty:
        st.divider()
        st.markdown("**🔴 Vencidas**")
        for _, t in vencidas.iterrows():
            _tarjeta_tarea(t)

# ---------------------------------------------------------------------------
# NUEVA TAREA
# ---------------------------------------------------------------------------
with tab_nueva:
    st.markdown("Asigna una nueva tarea a un miembro del equipo.")
    with st.form("form_nueva_tarea", clear_on_submit=True):
        titulo = st.text_input("✓ Descripción de la tarea", placeholder="Ej. Elaborar IVA julio")
        c1, c2 = st.columns(2)
        with c1:
            responsable = st.selectbox("Responsable", equipo["nombre"])
            cliente = st.selectbox("Cliente", clientes["nombre"])
        with c2:
            fecha_limite = st.date_input("Fecha límite")
            prioridad = st.select_slider("Prioridad", options=["Baja", "Media", "Alta"], value="Media")
        estado = st.selectbox("Estado inicial", ["Pendiente", "En proceso"])

        enviado = st.form_submit_button("Crear tarea", type="primary")
        if enviado:
            if titulo:
                crear_tarea(
                    titulo=titulo,
                    cliente=cliente,
                    responsable=responsable,
                    fecha_limite=fecha_limite,
                    prioridad=prioridad,
                    estado=estado,
                )
                st.toast(f"✅ Tarea '{titulo}' asignada a {responsable} para {cliente} y guardada en el Sheet.", icon="✅")
                st.rerun()
            else:
                st.error("Escribe una descripción para la tarea.")

# ---------------------------------------------------------------------------
# HISTORIAL DE UNA TAREA
# ---------------------------------------------------------------------------
with tab_historial:
    tarea_sel = st.selectbox("Selecciona una tarea", tareas["titulo"])
    tarea_id = tareas[tareas["titulo"] == tarea_sel]["id"].iloc[0]
    historial = get_historial_tarea(tarea_id)

    for evento in historial:
        st.markdown(f"**{evento['fecha']}**")
        st.caption(evento["evento"])
