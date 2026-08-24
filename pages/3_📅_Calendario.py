import streamlit as st
from datetime import timedelta
from utils.sheets import get_clientes, estado_semaforo, HOY

st.set_page_config(page_title="Calendario", page_icon="📅", layout="wide")
st.title("📅 Calendario de vencimientos DIAN")

clientes = get_clientes()

vista = st.radio("Ver", ["Hoy", "Esta semana", "Este mes"], horizontal=True)

if vista == "Hoy":
    limite = HOY
elif vista == "Esta semana":
    limite = HOY + timedelta(days=7)
else:
    limite = HOY + timedelta(days=30)

en_rango = clientes[clientes["fecha_vencimiento"] <= limite].sort_values("fecha_vencimiento")

st.caption("🟢 Al día · 🟡 Próximo a vencer (≤5 días) · 🔴 Vencido")

if en_rango.empty:
    st.success("No hay vencimientos en este rango.")
else:
    for _, row in en_rango.iterrows():
        icono = estado_semaforo(row["fecha_vencimiento"])
        dias = (row["fecha_vencimiento"] - HOY).days
        texto_dias = f"vence en {dias} días" if dias >= 0 else f"vencido hace {-dias} días"
        with st.container(border=True):
            c1, c2, c3 = st.columns([0.5, 3, 2])
            c1.markdown(f"### {icono}")
            c2.markdown(f"**{row['nombre']}** — {row['proximo_vencimiento']}")
            c2.caption(f"Responsable: {row['responsable_obligacion']}")
            c3.markdown(f"{row['fecha_vencimiento'].strftime('%d/%m/%Y')}")
            c3.caption(texto_dias)

st.divider()
st.subheader("🔔 Recordatorios")
st.caption("En la versión conectada, esta sección enviará recordatorios automáticos por correo o WhatsApp "
           "unos días antes de cada vencimiento.")
