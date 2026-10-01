from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


COMPLEXITY_FACTOR = {
    "low": 1.0,
    "medium": 1.35,
    "high": 1.8,
}


def build_client_selection_message(client_term: str, matches: list[dict[str, Any]]) -> str:
    """Construye un mensaje amigable para seleccionar cliente cuando hay varias coincidencias."""
    query = (client_term or "cliente").strip()
    if not matches:
        return f"No encontré clientes con '{query}'. Prueba con un nombre, alias o código más específico."

    if len(matches) == 1:
        item = matches[0]
        code = item.get("codigo") or item.get("code") or "Sin código"
        name = item.get("nombre") or item.get("name") or "Cliente"
        return f"Encontré una coincidencia para '{query}': {name} ({code}). Si quieres, puedo continuar con este cliente y preparar la cotización."

    items = "; ".join(
        f"{(item.get('codigo') or 'Sin código')} - {(item.get('nombre') or item.get('name') or 'Sin nombre')}"
        for item in matches[:5]
    )
    return (
        f"He encontrado {len(matches)} clientes que coinciden con '{query}'. "
        f"Elige uno de estos: {items}. Cuando me indiques el código o nombre, preparo la cotización."
    )


def parse_user_request(message: str) -> dict[str, Any]:
    """Interpreta un mensaje del usuario para decidir la intención del agente."""
    raw = (message or "").strip()
    lower = raw.lower()

    if any(token in lower for token in ["cronograma", "schedule", "agenda", "planificacion", "planning"]):
        intent = "schedule"
    elif any(token in lower for token in ["resumen", "reunion", "reunión", "meeting", "sintesis"]):
        intent = "summary"
    elif any(token in lower for token in ["cotiz", "cotización", "cotizacion", "presupuesto", "estim", "propuesta"]):
        intent = "proposal"
    else:
        intent = "general"

    client_name = "Cliente"
    match = re.search(
        r"(?:para|cliente|para el cliente|de)\s+"
        r"([A-ZÁÉÍÓÚÜÑ][A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9& .'-]*?)(?=\s*(?:y\b|que\b|me\b|el\b|para\b|con\b|de\b|por\b|del\b|$))",
        raw,
        flags=re.IGNORECASE,
    )
    if match:
        client_name = match.group(1).strip(" .-")

    description = raw
    for token in [
        "necesito",
        "quiero",
        "solicito",
        "una",
        "un",
        "cotizacion",
        "cotización",
        "propuesta",
        "estimación",
        "estimacion",
        "presupuesto",
        "para",
        "cliente",
        "del",
        "de",
    ]:
        description = re.sub(rf"\b{re.escape(token)}\b", " ", description, flags=re.IGNORECASE)
    description = re.sub(r"\s+", " ", description).strip() or "Proyecto digital con alcance a definir."

    project_name = "Proyecto " + (client_name if client_name != "Cliente" else "nuevo")
    if re.search(r"\bportal\b|\bapp\b|\bcrm\b|\bweb\b|\bmobile\b", lower):
        project_name = "Proyecto digital"

    modules: list[str] = []
    for keyword, module in {
        "login": "login",
        "dashboard": "dashboard",
        "cotizacion": "cotizaciones",
        "cotización": "cotizaciones",
        "reportes": "reportes",
        "inventario": "inventario",
        "crm": "crm",
        "ventas": "ventas",
        "notificaciones": "notificaciones",
    }.items():
        if keyword in lower:
            modules.append(module)

    if not modules:
        modules = ["módulo base"]

    integrations = 0
    if re.search(r"(\d+)\s*(?:integraciones?|integracion)", lower):
        integrations = int(re.search(r"(\d+)\s*(?:integraciones?|integracion)", lower).group(1))
    elif "integracion" in lower or "integración" in lower:
        integrations = 1

    users = 10
    match_users = re.search(r"(\d+)\s*(?:usuarios?|users?)", lower)
    if match_users:
        users = int(match_users.group(1))

    complexity = "medium"
    if any(token in lower for token in ["alto", "complejo", "compleja", "avanzado"]):
        complexity = "high"
    elif any(token in lower for token in ["simple", "básico", "basico", "sencillo"]):
        complexity = "low"

    localization = any(token in lower for token in ["localizacion", "localización", "idioma", "español", "ingles"])

    return {
        "intent": intent,
        "client_name": client_name,
        "project_name": project_name,
        "description": description,
        "complexity": complexity,
        "modules": modules,
        "integrations": integrations,
        "users": users,
        "localization": localization,
    }


def _as_date(value: str | date | None) -> date:
    if value is None:
        return date.today()
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value), "%Y-%m-%d").date()


def estimate_project(
    project_name: str,
    client_name: str,
    description: str,
    complexity: str = "medium",
    modules: list[str] | None = None,
    integrations: int = 0,
    users: int = 10,
    localization: bool = False,
    hourly_rate: float = 18.0,
) -> dict[str, Any]:
    """Crea una estimación inicial de un proyecto para ANDI."""
    complexity_key = str(complexity).lower()
    if complexity_key not in COMPLEXITY_FACTOR:
        complexity_key = "medium"

    module_list = modules or ["módulo inicial"]
    module_count = len(module_list)
    complexity_factor = COMPLEXITY_FACTOR[complexity_key]
    base_hours = 24 + (module_count * 12) + (integrations * 8) + (users * 0.6)
    if localization:
        base_hours += 12
    total_hours = round(base_hours * complexity_factor, 1)
    total_cost = round(total_hours * hourly_rate, 2)

    phases = [
        {
            "name": "Diagnóstico y alcance",
            "hours": round(total_hours * 0.12, 1),
            "description": "Definición de objetivos, alcance, requisitos y validación inicial.",
        },
        {
            "name": "Diseño y arquitectura",
            "hours": round(total_hours * 0.18, 1),
            "description": "Arquitectura, flujo funcional, prototipo y componentes clave.",
        },
        {
            "name": "Desarrollo principal",
            "hours": round(total_hours * 0.38, 1),
            "description": "Implementación de módulos y lógica de negocio.",
        },
        {
            "name": "Integraciones y QA",
            "hours": round(total_hours * 0.18, 1),
            "description": "Integraciones, pruebas, ajustes de calidad y validación final.",
        },
        {
            "name": "Entrega y soporte inicial",
            "hours": round(total_hours * 0.14, 1),
            "description": "Despliegue, documentación, capacitación y soporte inicial.",
        },
    ]

    return {
        "project_name": project_name,
        "client_name": client_name,
        "description": description,
        "complexity": complexity_key,
        "modules": module_list,
        "integrations": integrations,
        "users": users,
        "localization": localization,
        "hourly_rate": hourly_rate,
        "total_hours": total_hours,
        "total_cost": total_cost,
        "phases": phases,
    }


def build_project_schedule(estimate: dict[str, Any], start_date: str | date | None = None) -> dict[str, Any]:
    """Genera un cronograma semanal a partir de una estimación."""
    start = _as_date(start_date)
    tasks: list[dict[str, Any]] = []
    current = start

    for index, phase in enumerate(estimate["phases"], start=1):
        duration_days = max(5, int(round(float(phase["hours"]) / 8)))
        due_date = current + timedelta(days=duration_days)
        tasks.append(
            {
                "id": index,
                "phase": phase["name"],
                "start_date": current.isoformat(),
                "end_date": due_date.isoformat(),
                "duration_days": duration_days,
                "owner": "ANDI",
                "deliverable": phase["description"],
                "hours": float(phase["hours"]),
            }
        )
        current = due_date + timedelta(days=2)

    total_days = sum(task["duration_days"] for task in tasks)
    total_weeks = max(1, (total_days + 6) // 7)

    return {
        "project_name": estimate["project_name"],
        "start_date": start.isoformat(),
        "total_weeks": total_weeks,
        "total_days": total_days,
        "tasks": tasks,
    }


def generate_quote(
    project_name: str,
    client_name: str,
    estimate: dict[str, Any],
    discount_percent: float = 0.0,
    margin_percent: float = 0.2,
) -> dict[str, Any]:
    """Genera un resumen comercial del proyecto con margen y descuento."""
    base_cost = float(estimate["total_cost"])
    discount = base_cost * max(0.0, min(discount_percent, 0.5))
    adjusted_cost = base_cost - discount
    with_margin = adjusted_cost * (1 + max(0.0, min(margin_percent, 0.8)))

    return {
        "project_name": project_name,
        "client_name": client_name,
        "currency": "CRC",
        "base_cost": round(base_cost, 2),
        "discount_percent": round(discount_percent, 2),
        "discount_amount": round(discount, 2),
        "adjusted_cost": round(adjusted_cost, 2),
        "margin_percent": round(margin_percent, 2),
        "final_cost": round(with_margin, 2),
        "total_hours": estimate["total_hours"],
        "phases": estimate["phases"],
    }


QUOTE_HISTORY_PATH = Path("exports/quote_history.json")


def save_quote_history(record: dict[str, Any]) -> dict[str, Any]:
    """Guarda un registro de cotización en disco para consulta posterior."""
    QUOTE_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    if QUOTE_HISTORY_PATH.exists():
        try:
            with QUOTE_HISTORY_PATH.open("r", encoding="utf-8") as f:
                history = json.loads(f.read())
            if not isinstance(history, list):
                history = []
        except Exception:
            history = []
    else:
        history = []

    entry = {
        "id": record.get("id") or f"QT-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        "project_name": record.get("project_name") or "Proyecto",
        "client_name": record.get("client_name") or "Cliente",
        "final_cost": float(record.get("final_cost") or record.get("adjusted_cost") or 0.0),
        "created_at": record.get("created_at") or datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "pdf_path": record.get("pdf_path") or "",
    }
    history.insert(0, entry)
    with QUOTE_HISTORY_PATH.open("w", encoding="utf-8") as f:
        json.dump(history[:25], f, ensure_ascii=False, indent=2)
    return entry


def list_quote_history(limit: int = 10) -> list[dict[str, Any]]:
    """Devuelve el historial de cotizaciones recientes."""
    if not QUOTE_HISTORY_PATH.exists():
        return []
    try:
        with QUOTE_HISTORY_PATH.open("r", encoding="utf-8") as f:
            data = json.loads(f.read())
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    return data[: max(1, int(limit))]


def generate_pdf_proposal(estimate: dict[str, Any], output_path: str = "exports/propuesta.pdf") -> dict[str, Any]:
    """Genera un PDF con propuesta y condiciones generales."""
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    pdf = canvas.Canvas(str(target), pagesize=letter)
    width, height = letter

    pdf.setTitle(f"Propuesta - {estimate['project_name']}")
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(30 * mm, height - 25 * mm, "ANDI - Propuesta de proyecto")

    pdf.setFont("Helvetica", 11)
    pdf.drawString(30 * mm, height - 38 * mm, f"Proyecto: {estimate['project_name']}")
    pdf.drawString(30 * mm, height - 46 * mm, f"Cliente: {estimate['client_name']}")
    pdf.drawString(30 * mm, height - 54 * mm, f"Complejidad: {estimate['complexity']}")
    pdf.drawString(30 * mm, height - 62 * mm, f"Horas estimadas: {estimate['total_hours']}")
    pdf.drawString(30 * mm, height - 70 * mm, f"Costo estimado: ₡{estimate['total_cost']:.2f}")

    y = height - 95 * mm
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(30 * mm, y, "Fases")
    y -= 8 * mm
    pdf.setFont("Helvetica", 10)

    for phase in estimate["phases"]:
        pdf.drawString(32 * mm, y, f"- {phase['name']}: {phase['hours']} hrs")
        y -= 7 * mm
        if y < 40 * mm:
            pdf.showPage()
            y = height - 20 * mm

    pdf.showPage()
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(30 * mm, height - 25 * mm, "Condiciones generales")
    pdf.setFont("Helvetica", 10)
    terms = [
        "1. El alcance, costo y fechas serán confirmados por escrito antes del inicio del proyecto.",
        "2. Los tiempos de entrega pueden ajustarse según cambios de alcance, dependencias o entregables adicionales.",
        "3. El pago se realizará en los plazos acordados por la propuesta y podrá requerir anticipo inicial.",
        "4. El cliente deberá proporcionar información, acceso y aprobaciones en tiempo para evitar retrasos.",
        "5. ANDI se reserva el derecho a ejecutar la entrega en función del alcance aprobado y la disponibilidad de recursos.",
        "6. Esta propuesta tiene vigencia de 15 días naturales a partir de su emisión.",
    ]
    y = height - 40 * mm
    for line in terms:
        pdf.drawString(30 * mm, y, line[:110])
        y -= 8 * mm
        if y < 32 * mm:
            pdf.showPage()
            y = height - 20 * mm
    pdf.save()

    return {"created": True, "path": str(target), "filename": target.name}


def summarize_meeting(notes: str) -> dict[str, Any]:
    """Genera un resumen de reunión desde texto libre."""
    raw = (notes or "").strip()
    if not raw:
        return {"summary": "No se recibieron notas de la reunión.", "action_items": [], "decisions": []}

    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    action_items = [line for line in lines if line.lower().startswith(("acción:", "tarea:", "pendiente:"))]
    decisions = [line for line in lines if line.lower().startswith(("decisión:", "acuerdo:", "resultado:"))]

    if not action_items:
        action_items = [line for line in lines if "?" not in line and len(line) > 25][:5]
    if not decisions:
        decisions = [line for line in lines if len(line) > 30][:3]

    summary = (
        "Reunión registrada. Se identificaron los puntos principales, tareas pendientes y acuerdos "
        "de la sesión para continuar con el seguimiento."
    )

    return {
        "summary": summary,
        "action_items": action_items,
        "decisions": decisions,
        "notes_count": len(lines),
    }


def build_email_for_quote(project_name: str, client_email: str, proposal_pdf_path: str) -> dict[str, Any]:
    return {
        "to": client_email,
        "subject": f"Propuesta de proyecto: {project_name}",
        "body": (
            "Hola,\n\n"
            "Adjuntamos la propuesta del proyecto solicitada.\n"
            "Quedamos atentos para cualquier ajuste o aclaración.\n\n"
            "Saludos,\nANDI"
        ),
        "attachment": proposal_pdf_path,
    }
