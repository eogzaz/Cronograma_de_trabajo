import streamlit as st
from utils.sheets import get_checklist_template, get_clientes, get_checklist_progreso, set_checklist_item

st.set_page_config(page_title="Checklists", page_icon="✅", layout="wide")
st.title("✅ Checklists")

clientes = get_clientes()

col1, col2 = st.columns(2)
with col1:
    tipo = st.selectbox(
        "Tipo de obligación",
        ["IVA", "IVA Bimestral", "Retención en la fuente", "Retención ICA", "Renta", "Nómina"],
    )
with col2:
    cliente = st.selectbox("Cliente", clientes["nombre"])

pasos = get_checklist_template(tipo)
progreso_guardado = get_checklist_progreso(cliente, tipo)

# Cada checkbox tiene una llave única por combinación cliente + tipo + paso,
# para que Streamlit no mezcle el estado entre distintas combinaciones.
key_prefix = f"chk_{cliente}_{tipo}"

st.subheader(f"{tipo} — {cliente}")

completados = 0
for i, paso in enumerate(pasos):
    valor_guardado = progreso_guardado.get(paso, False)
    marcado = st.checkbox(paso, value=valor_guardado, key=f"{key_prefix}_{i}")
    if marcado != valor_guardado:
        set_checklist_item(cliente, tipo, paso, marcado)
    if marcado:
        completados += 1

if pasos:
    progreso = completados / len(pasos)
    st.progress(progreso, text=f"{completados} de {len(pasos)} pasos completados")

    if progreso == 1:
        st.success("✅ Checklist completado.")

st.divider()
st.caption("💡 El progreso se guarda por cliente y tipo de obligación directamente en el Google Sheet "
           "(pestaña Checklist_Progreso), así que no se reinicia entre sesiones ni entre usuarios.")
