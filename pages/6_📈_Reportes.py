import streamlit as st
import pandas as pd
from utils.sheets import get_tareas, get_equipo

st.set_page_config(page_title="Reportes", page_icon="📈", layout="wide")
st.title("📈 Reportes")

tareas = get_tareas()
equipo = get_equipo()

tab_productividad, tab_vencidas = st.tabs(["Productividad", "Tareas vencidas"])

with tab_productividad:
    st.subheader("Tareas por estado y responsable")
    resumen = pd.crosstab(tareas["responsable"], tareas["estado"])
    st.dataframe(resumen, use_container_width=True)
    st.bar_chart(resumen)

    st.subheader("Distribución general")
    conteo_estado = tareas["estado"].value_counts()
    st.bar_chart(conteo_estado)

with tab_vencidas:
    st.subheader("Tareas vencidas")
    vencidas = tareas[tareas["estado"] == "Vencida"]
    if vencidas.empty:
        st.success("No hay tareas vencidas actualmente. 🎉")
    else:
        st.dataframe(
            vencidas[["titulo", "cliente", "responsable", "prioridad", "fecha_limite"]],
            column_config={
                "titulo": "Tarea", "cliente": "Cliente", "responsable": "Responsable", "prioridad": "Prioridad",
                "fecha_limite": st.column_config.DateColumn("Fecha límite", format="DD/MM/YYYY"),
            },
            hide_index=True, use_container_width=True,
        )

    st.caption("💡 Con Supabase conectado, estos reportes se calcularán en tiempo real sobre datos históricos, "
               "y podrás exportarlos o programarlos por correo.")
