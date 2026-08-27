from datetime import date

import streamlit as st
from utils.sheets import (
    get_tareas, get_clientes, get_equipo, get_historial_tarea,
    crear_tarea, actualizar_estado_tarea, generar_tareas_desde_calendario,
)

st.set_page_config(page_title="Tareas", page_icon="📋", layout="wide")
st.title("📋 Tareas")

tareas = get_tareas()
clientes = get_clientes()
equipo = get_equipo()

ESTADOS = ["Pendiente", "En proceso", "Finalizada", "Vencida"]

tab_tablero, tab_generar, tab_nueva, tab_historial = st.tabs(
    ["Tablero", "🔄 Generar del calendario", "➕ Nueva tarea", "🕒 Historial"]
)


def _tarjeta_tarea(t):
    """Tarjeta de una tarea con selector para cambiar su estado in situ."""
    prioridad_icono = {"Alta": "🔴", "Media": "🟡", "Baja": "🟢"}.get(t["prioridad"], "⚪")
    with st.container(border=True):
        st.markdown(f"**{t['titulo']}**")
        subtitulo = t["cliente"] + (f" · {t['tipo']}" if t["tipo"] else "") + f" · {t['responsable']}"
        st.caption(subtitulo)
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
# GENERAR TAREAS DESDE EL CALENDARIO
# ---------------------------------------------------------------------------
with tab_generar:
    st.markdown(
        "Convierte cada obligación próxima de **Calendario_DIAN** en tareas reales: "
        "una por cada paso del checklist de ese tipo (Checklist_Plantillas), asignada "
        "a quien le corresponde ese paso, con la fecha de la obligación como fecha límite."
    )
    horizonte = st.selectbox(
        "Generar para las obligaciones que vencen en los próximos...",
        [15, 30, 45, 60], index=1, format_func=lambda d: f"{d} días",
    )
    if st.button("🔄 Generar tareas pendientes", type="primary"):
        resumen = generar_tareas_desde_calendario(horizonte_dias=horizonte)
        if resumen["tareas_creadas"] == 0 and resumen["obligaciones_omitidas"] == 0:
            st.info("No hay obligaciones en ese rango de fechas todavía (o falta el checklist de ese tipo).")
        else:
            st.success(
                f"✅ Se crearon {resumen['tareas_creadas']} tareas para "
                f"{resumen['obligaciones_generadas']} obligación(es) de {resumen['clientes']} cliente(s)."
                + (f" {resumen['obligaciones_omitidas']} obligación(es) ya tenían tareas generadas y se omitieron."
                   if resumen["obligaciones_omitidas"] else "")
            )
            st.rerun()
    st.caption(
        "💡 Se puede correr las veces que sea: si una obligación (mismo cliente + tipo + fecha) "
        "ya tiene tareas generadas, se omite — no se duplica."
    )

# ---------------------------------------------------------------------------
# NUEVA TAREA
# ---------------------------------------------------------------------------
with tab_nueva:
    st.markdown("Asigna una nueva tarea a un miembro del equipo.")

    # Fuera del formulario para que reaccione al instante al cambiar de cliente.
    cliente = st.selectbox("Cliente", clientes["nombre"], key="nueva_tarea_cliente")
    info_cliente = clientes[clientes["nombre"] == cliente].iloc[0]
    fecha_sugerida = info_cliente["fecha_vencimiento"]
    if fecha_sugerida:
        st.caption(
            f"📅 Próxima obligación de este cliente ({info_cliente['proximo_vencimiento']}): "
            f"{fecha_sugerida.strftime('%d/%m/%Y')} — se usa como fecha límite sugerida abajo, "
            f"la puedes cambiar si esta tarea es distinta."
        )

    with st.form("form_nueva_tarea", clear_on_submit=True):
        titulo = st.text_input("✓ Descripción de la tarea", placeholder="Ej. Elaborar IVA julio")
        c1, c2 = st.columns(2)
        with c1:
            responsable = st.selectbox("Responsable", equipo["nombre"])
            prioridad = st.select_slider("Prioridad", options=["Baja", "Media", "Alta"], value="Media")
        with c2:
            fecha_limite = st.date_input("Fecha límite", value=fecha_sugerida or date.today())
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
    if tareas.empty:
        st.caption("Todavía no hay tareas creadas.")
        st.stop()
    # Se identifica por ID (no por título): con tareas generadas desde
    # checklists es normal que varias compartan el mismo título (ej.
    # "Presentar") para clientes distintos.
    tarea_id = st.selectbox(
        "Selecciona una tarea", tareas["id"],
        format_func=lambda i: (lambda t: f"{t['titulo']} — {t['cliente']} ({t['fecha_limite'].strftime('%d/%m/%Y')})")(
            tareas[tareas["id"] == i].iloc[0]
        ),
    )
    historial = get_historial_tarea(tarea_id)

    for evento in historial:
        st.markdown(f"**{evento['fecha']}**")
        st.caption(evento["evento"])
