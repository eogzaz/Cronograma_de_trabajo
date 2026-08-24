# Sistema de Gestión para Despacho Contable

Esqueleto de aplicación en Streamlit para gestionar clientes, tareas, vencimientos
DIAN, checklists por obligación y productividad del equipo.

Por ahora usa **datos de ejemplo** (`utils/mock_data.py`) para que puedas navegar
la app y validar el flujo antes de conectar la fuente de datos real: un Google
Sheet que el equipo del despacho ya edita y actualiza seguido.

## Estructura del proyecto

```
despacho_app/
├── app.py                     # Dashboard (página de inicio)
├── requirements.txt
├── supabase/
│   └── schema.sql             # Alternativa con base de datos real (no usada por ahora)
├── utils/
│   ├── mock_data.py           # Datos de ejemplo (usado por defecto)
│   ├── db.py                  # Alternativa vía Supabase (no usada por ahora)
│   └── sheets.py              # Datos reales vía Google Sheets (mismo contrato que mock_data.py)
└── pages/
    ├── 1_📋_Tareas.py
    ├── 2_👥_Clientes.py
    ├── 3_📅_Calendario.py
    ├── 4_✅_Checklists.py
    ├── 5_👤_Equipo.py
    └── 6_📈_Reportes.py
```

Streamlit detecta automáticamente los archivos dentro de `pages/` y arma el
menú lateral con ellos (el número al inicio del nombre define el orden, y el
emoji se usa como ícono).

## Ejecutar localmente

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Desplegar en Streamlit Community Cloud

1. Sube esta carpeta a un repositorio de GitHub.
2. Entra a https://share.streamlit.io y conecta el repositorio.
3. Selecciona `app.py` como archivo principal.
4. Listo — cada push a la rama principal actualiza la app automáticamente.

## Conectar Google Sheets (fuente de datos actual)

El despacho ya lleva su información en un Google Sheet que se edita seguido,
así que la app se conecta directamente ahí en vez de a una base de datos
aparte. La estructura de referencia está en `Plantilla_Despacho_Contable.xlsx`
(pestañas: `Clientes`, `Tareas`, `Equipo`, `Checklist_Plantillas`,
`Checklist_Progreso`, `Historial_Tareas`).

Ver la guía paso a paso completa (cuenta de servicio de Google, permisos,
`secrets.toml`) más abajo / en la conversación con Claude. Resumen rápido una
vez tengas las credenciales:

1. Agrega a `.streamlit/secrets.toml` (o a los Secrets de la app en Streamlit
   Community Cloud) el `GOOGLE_SHEET_ID` y el bloque `[gcp_service_account]`
   con el contenido del JSON de la cuenta de servicio.
2. Comparte el Google Sheet (como Editor) con el `client_email` de esa cuenta
   de servicio.
3. En cada página, cambia el import de `utils.mock_data` a `utils.sheets`.
   Como ambos módulos exponen las mismas funciones, no hace falta tocar nada
   más del código de las páginas.
4. Actualiza el formulario de "Nueva tarea" (`pages/1_📋_Tareas.py`) para
   llamar a `sheets.crear_tarea(...)` en vez de solo mostrar `st.success`.
5. Actualiza Checklists (`pages/4_✅_Checklists.py`) para leer/guardar con
   `sheets.get_checklist_progreso` / `sheets.set_checklist_item` en vez de
   `session_state`.

### Nota sobre la alternativa con Supabase

`supabase/schema.sql` y `utils/db.py` quedan en el repo como alternativa por
si más adelante el despacho decide migrar de Google Sheets a una base de
datos real (mejor para concurrencia alta, validaciones fuertes, Auth con
roles). No se usan mientras la fuente de verdad sea el Sheet.
