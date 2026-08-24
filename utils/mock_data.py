"""
Capa de datos de ejemplo (mock).

Esta capa simula lo que más adelante será una conexión real a Supabase.
Cada función aquí representa una consulta que, en el futuro, se reemplazará
por un `supabase.table(...).select(...)` real. Mantener esta separación
facilita la migración: las páginas de la app solo llaman a estas funciones,
nunca acceden a los datos "crudos" directamente.
"""

import pandas as pd
from datetime import date, timedelta

HOY = date.today()


def _fecha(dias_desde_hoy: int) -> date:
    return HOY + timedelta(days=dias_desde_hoy)


# ---------------------------------------------------------------------------
# CLIENTES
# ---------------------------------------------------------------------------
def get_clientes() -> pd.DataFrame:
    data = [
        {"id": 1, "nombre": "Empresa A S.A.S.", "nit": "900123456-1", "responsable": "Juan", "estado": "Activo", "proximo_vencimiento": "IVA julio", "fecha_vencimiento": _fecha(3)},
        {"id": 2, "nombre": "Empresa B Ltda.", "nit": "800987654-2", "responsable": "María", "estado": "Activo", "proximo_vencimiento": "Renta", "fecha_vencimiento": _fecha(15)},
        {"id": 3, "nombre": "Empresa C S.A.", "nit": "901222333-3", "responsable": "Carlos", "estado": "Activo", "proximo_vencimiento": "Nómina", "fecha_vencimiento": _fecha(-2)},
        {"id": 4, "nombre": "Comercial D S.A.S.", "nit": "900555111-4", "responsable": "Juan", "estado": "Activo", "proximo_vencimiento": "Retención", "fecha_vencimiento": _fecha(7)},
        {"id": 5, "nombre": "Distribuciones E", "nit": "800444222-5", "responsable": "María", "estado": "Inactivo", "proximo_vencimiento": "Exógena", "fecha_vencimiento": _fecha(30)},
    ]
    return pd.DataFrame(data)


# ---------------------------------------------------------------------------
# TAREAS
# ---------------------------------------------------------------------------
def get_tareas() -> pd.DataFrame:
    data = [
        {"id": 1, "titulo": "Elaborar IVA julio", "cliente": "Empresa A S.A.S.", "responsable": "Juan", "estado": "En proceso", "prioridad": "Alta", "fecha_limite": _fecha(3)},
        {"id": 2, "titulo": "Conciliar bancos junio", "cliente": "Empresa B Ltda.", "responsable": "María", "estado": "Pendiente", "prioridad": "Media", "fecha_limite": _fecha(5)},
        {"id": 3, "titulo": "Elaborar nómina", "cliente": "Empresa C S.A.", "responsable": "Carlos", "estado": "Vencida", "prioridad": "Alta", "fecha_limite": _fecha(-2)},
        {"id": 4, "titulo": "Revisar retención en la fuente", "cliente": "Comercial D S.A.S.", "responsable": "Juan", "estado": "Pendiente", "prioridad": "Alta", "fecha_limite": _fecha(7)},
        {"id": 5, "titulo": "Solicitar documentos exógena", "cliente": "Distribuciones E", "responsable": "María", "estado": "Finalizada", "prioridad": "Baja", "fecha_limite": _fecha(-10)},
        {"id": 6, "titulo": "Presentar declaración renta", "cliente": "Empresa B Ltda.", "responsable": "María", "estado": "Pendiente", "prioridad": "Alta", "fecha_limite": _fecha(15)},
    ]
    return pd.DataFrame(data)


def get_historial_tarea(tarea_id: int) -> list[dict]:
    historiales = {
        1: [
            {"fecha": _fecha(-3), "evento": "Juan creó la tarea"},
            {"fecha": _fecha(-2), "evento": "María revisó los soportes"},
            {"fecha": _fecha(-1), "evento": "Se enviaron documentos al cliente"},
        ],
    }
    return historiales.get(tarea_id, [{"fecha": HOY, "evento": "Tarea creada"}])


# ---------------------------------------------------------------------------
# CHECKLISTS
# ---------------------------------------------------------------------------
def get_checklist_template(tipo: str) -> list[str]:
    templates = {
        "IVA": ["Solicitar documentos", "Revisar compras", "Revisar ventas", "Conciliar", "Elaborar declaración", "Revisar", "Presentar", "Enviar soporte"],
        "Retención": ["Solicitar certificados", "Revisar bases", "Calcular retenciones", "Elaborar declaración", "Presentar", "Enviar soporte"],
        "Renta": ["Solicitar estados financieros", "Conciliar patrimonio", "Depurar renta", "Elaborar declaración", "Revisar", "Presentar", "Enviar soporte"],
        "Nómina": ["Recibir novedades", "Calcular nómina", "Calcular seguridad social", "Generar comprobantes", "Pagar seguridad social", "Enviar soportes"],
    }
    return templates.get(tipo, [])


# ---------------------------------------------------------------------------
# EQUIPO
# ---------------------------------------------------------------------------
def get_equipo() -> pd.DataFrame:
    data = [
        {"nombre": "Juan", "rol": "Contador Senior", "clientes_asignados": 2, "tareas_activas": 2, "tareas_vencidas": 0},
        {"nombre": "María", "rol": "Contadora", "clientes_asignados": 2, "tareas_activas": 3, "tareas_vencidas": 0},
        {"nombre": "Carlos", "rol": "Auxiliar Contable", "clientes_asignados": 1, "tareas_activas": 1, "tareas_vencidas": 1},
    ]
    return pd.DataFrame(data)


# ---------------------------------------------------------------------------
# HELPERS DE ESTADO / COLOR
# ---------------------------------------------------------------------------
def estado_semaforo(fecha_vencimiento: date) -> str:
    dias = (fecha_vencimiento - HOY).days
    if dias < 0:
        return "🔴"
    elif dias <= 5:
        return "🟡"
    return "🟢"
