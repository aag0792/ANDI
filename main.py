"""ANDI Gateway v0.1 - servidor MCP de solo lectura.

Herramientas expuestas:
  - buscar_cliente(termino)  -> andi.sp_buscar_cliente
  - cliente_360(codigo_cliente) -> andi.sp_cliente_360

Endpoints:
  - GET  /health   (sin autenticación, no revela datos)
  - POST /mcp      (protocolo MCP, requiere Bearer token)
"""
import asyncio
import contextlib
import hmac
from datetime import datetime
from pathlib import Path

import requests
import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

try:
    from . import config, db
except ImportError:  # Ejecutado como `python main.py`
    import config
    import db

try:
    from .andi_agent import (
        build_client_selection_message,
        build_email_for_quote,
        build_project_schedule,
        estimate_project,
        generate_pdf_proposal,
        generate_quote,
        list_quote_history,
        parse_user_request,
        save_quote_history,
        summarize_meeting,
    )
except ImportError:  # Ejecutado como `python main.py`
    from andi_agent import (
        build_client_selection_message,
        build_email_for_quote,
        build_project_schedule,
        estimate_project,
        generate_pdf_proposal,
        generate_quote,
        list_quote_history,
        parse_user_request,
        save_quote_history,
        summarize_meeting,
    )

VERSION = "0.1.0"

mcp = FastMCP("ANDI Gateway", stateless_http=True, json_response=True)


@mcp.tool()
async def buscar_cliente(termino: str) -> dict:
    """Busca clientes en Softland por código o nombre (máximo 10 resultados).

    Solo lectura. Devuelve código, nombre, contacto, teléfono, correo y saldo.
    """
    termino = (termino or "").strip()
    if not 2 <= len(termino) <= 60:
        db.audit("buscar_cliente", {"termino": termino[:60]}, None, False, "termino_invalido")
        return {"error": "El término debe tener entre 2 y 60 caracteres."}

    try:
        # pyodbc es bloqueante: lo movemos a un hilo para no frenar el servidor
        rows = await asyncio.to_thread(db.call_procedure, "andi.sp_buscar_cliente", termino)
    except Exception as exc:  # no filtrar detalles internos al cliente
        db.audit("buscar_cliente", {"termino": termino}, None, False, type(exc).__name__)
        return {"error": "No se pudo consultar la base de datos. Revisa el log del Gateway."}

    db.audit("buscar_cliente", {"termino": termino}, len(rows), True)
    return {"total": len(rows), "clientes": rows}


@mcp.tool()
async def cliente_360(codigo_cliente: str) -> dict:
    """Devuelve una vista 360 del cliente desde Softland.

    Incluye ficha completa, cuentas por cobrar abiertas e historial detallado
    de facturación/artículos. La consulta es de solo lectura.
    """
    codigo = (codigo_cliente or "").strip()
    if not 1 <= len(codigo) <= 40:
        db.audit("cliente_360", {"codigo_cliente": codigo[:40]}, None, False, "codigo_invalido")
        return {"error": "El código de cliente es obligatorio y debe tener máximo 40 caracteres."}

    try:
        sets = await asyncio.to_thread(db.call_procedure_sets, "andi.sp_cliente_360", codigo)
    except Exception as exc:
        db.audit("cliente_360", {"codigo_cliente": codigo}, None, False, type(exc).__name__)
        return {"error": "No se pudo consultar Cliente 360. Revisa el log del Gateway."}

    perfil = sets[0][0] if len(sets) > 0 and sets[0] else None
    cuentas_por_cobrar = sets[1] if len(sets) > 1 else []
    historial = sets[2] if len(sets) > 2 else []

    if perfil is None:
        db.audit("cliente_360", {"codigo_cliente": codigo}, 0, True)
        return {"error": "No se encontró el cliente solicitado.", "codigo_cliente": codigo}

    saldo_dolar = round(sum(float(x.get("SALDO_DOLAR") or 0) for x in cuentas_por_cobrar), 2)
    saldo_local = round(sum(float(x.get("SALDO_LOCAL") or 0) for x in cuentas_por_cobrar), 2)
    total_facturado = round(sum(float(x.get("TOTAL_LINEA") or 0) for x in historial), 2)
    facturas = {str(x.get("FACTURA")) for x in historial if x.get("FACTURA") is not None}
    fechas = [x.get("FECHA") for x in historial if x.get("FECHA")]

    resumen = {
        "saldo_dolar": saldo_dolar,
        "saldo_local": saldo_local,
        "documentos_pendientes": len(cuentas_por_cobrar),
        "total_facturado_usd": total_facturado,
        "cantidad_facturas": len(facturas),
        "ultima_compra": max(fechas) if fechas else None,
    }

    total_rows = 1 + len(cuentas_por_cobrar) + len(historial)
    db.audit("cliente_360", {"codigo_cliente": codigo}, total_rows, True)
    return {
        "cliente": perfil,
        "resumen": resumen,
        "cuentas_por_cobrar": cuentas_por_cobrar,
        "historial_compras": historial,
    }


@mcp.tool()
async def buscar_clientes_para_cotizacion(termino: str, limite: int = 10) -> dict:
    """Busca clientes y devuelve una lista útil para escoger antes de preparar la cotización."""
    termino = (termino or "").strip()
    if not 2 <= len(termino) <= 60:
        return {"error": "El término debe tener entre 2 y 60 caracteres."}
    try:
        rows = await asyncio.to_thread(db.call_procedure, "andi.sp_buscar_cliente", termino)
    except Exception as exc:
        return {"error": f"No se pudo consultar la base de datos: {type(exc).__name__}"}

    matches = rows[: max(1, min(int(limite), 10))]
    return {
        "termino": termino,
        "total": len(matches),
        "clientes": matches,
        "message": build_client_selection_message(termino, matches),
    }


@mcp.tool()
async def seleccionar_cliente_cotizacion(termino: str, codigo_cliente: str) -> dict:
    """Valida si un cliente de la búsqueda es el que se quiere usar para la cotización."""
    termino = (termino or "").strip()
    codigo = (codigo_cliente or "").strip()
    if not termino or not codigo:
        return {"error": "Se requieren termino y codigo_cliente."}

    matches = (await buscar_clientes_para_cotizacion(termino, limite=10)).get("clientes", [])
    for client in matches:
        if str(client.get("codigo") or "").lower() == codigo.lower():
            return {"seleccionado": True, "cliente": client}
    return {"seleccionado": False, "error": "No se encontró el cliente seleccionado."}


@mcp.tool()
async def crear_estimacion_proyecto(
    project_name: str,
    client_name: str,
    description: str,
    complexity: str = "medium",
    modules: list[str] | None = None,
    integrations: int = 0,
    users: int = 10,
    localization: bool = False,
) -> dict:
    """Genera una estimación inicial para un proyecto de software o digital."""
    if not project_name or not client_name or not description:
        return {"error": "project_name, client_name y description son obligatorios."}
    return estimate_project(
        project_name=project_name,
        client_name=client_name,
        description=description,
        complexity=complexity,
        modules=modules,
        integrations=integrations,
        users=users,
        localization=localization,
    )


@mcp.tool()
async def crear_cronograma_proyecto(
    project_name: str,
    client_name: str,
    description: str,
    complexity: str = "medium",
    modules: list[str] | None = None,
    integrations: int = 0,
    users: int = 10,
    localization: bool = False,
    start_date: str | None = None,
) -> dict:
    """Genera un cronograma de trabajo basado en la estimación del proyecto."""
    estimate = estimate_project(
        project_name=project_name,
        client_name=client_name,
        description=description,
        complexity=complexity,
        modules=modules,
        integrations=integrations,
        users=users,
        localization=localization,
    )
    return build_project_schedule(estimate, start_date=start_date)


@mcp.tool()
async def generar_cotizacion(
    project_name: str,
    client_name: str,
    description: str,
    complexity: str = "medium",
    modules: list[str] | None = None,
    integrations: int = 0,
    users: int = 10,
    localization: bool = False,
    discount_percent: float = 0.0,
    margin_percent: float = 0.2,
    output_path: str = "exports/propuesta.pdf",
) -> dict:
    """Genera la estimación, cronograma y PDF de la propuesta con costo final."""
    estimate = estimate_project(
        project_name=project_name,
        client_name=client_name,
        description=description,
        complexity=complexity,
        modules=modules,
        integrations=integrations,
        users=users,
        localization=localization,
    )
    quote = generate_quote(
        project_name=project_name,
        client_name=client_name,
        estimate=estimate,
        discount_percent=discount_percent,
        margin_percent=margin_percent,
    )
    pdf = generate_pdf_proposal(estimate, output_path=output_path)
    quote["pdf"] = pdf
    schedule = build_project_schedule(estimate)
    quote["schedule"] = schedule
    record = save_quote_history({
        "id": f"QT-{int(datetime.utcnow().timestamp())}",
        "project_name": project_name,
        "client_name": client_name,
        "final_cost": quote.get("final_cost"),
        "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "pdf_path": output_path,
    })
    quote["quote_id"] = record["id"]
    quote["pdf_path"] = output_path
    return quote


@mcp.tool()
async def resumir_reunion(notes: str) -> dict:
    """Resume una reunión o sesión con decisiones, pendientes y tareas."""
    if not notes or not notes.strip():
        return {"error": "Se requieren notas o transcripción de la reunión."}
    return summarize_meeting(notes)


@mcp.tool()
async def listar_cotizaciones(limit: int = 10) -> dict:
    """Devuelve el historial de cotizaciones generadas por ANDI."""
    data = list_quote_history(limit=limit)
    return {"total": len(data), "cotizaciones": data}


@mcp.tool()
async def obtener_cotizacion(cotizacion_id: str) -> dict:
    """Recupera una cotización por su identificador."""
    if not cotizacion_id:
        return {"error": "cotizacion_id es obligatorio."}
    history = list_quote_history(limit=100)
    for item in history:
        if item.get("id") == cotizacion_id:
            return {"cotizacion": item}
    return {"error": "No se encontró la cotización solicitada."}


@mcp.tool()
async def generar_email_cotizacion(
    project_name: str,
    client_email: str,
    proposal_pdf_path: str,
) -> dict:
    """Prepara el contenido de correo para enviar la propuesta en PDF."""
    if not project_name or not client_email or not proposal_pdf_path:
        return {"error": "project_name, client_email y proposal_pdf_path son obligatorios."}
    return build_email_for_quote(project_name, client_email, proposal_pdf_path)


class BearerAuth(BaseHTTPMiddleware):
    """Exige `Authorization: Bearer <GATEWAY_TOKEN>` en todo menos /health."""

    async def dispatch(self, request, call_next):
        path = request.url.path
        public_paths = {"/health", "/", "/condiciones-generales", "/terms"}
        if path in public_paths or path.startswith("/assets"):
            return await call_next(request)
        header = request.headers.get("authorization", "")
        token = header[7:] if header.lower().startswith("bearer ") else ""
        if not hmac.compare_digest(token, config.GATEWAY_TOKEN):
            return JSONResponse({"error": "no autorizado"}, status_code=401)
        return await call_next(request)


async def health(_request):
    return JSONResponse({"status": "ok", "service": "ANDI Gateway", "version": VERSION})


async def terms_page(_request):
    term_html = """
    <!doctype html>
    <html lang="es">
      <head>
        <meta charset="utf-8" />
        <title>Condiciones Generales - ANDI</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <style>
          body { font-family: Arial, sans-serif; margin: 32px auto; max-width: 860px; line-height: 1.6; color: #1f2937; padding: 0 20px; }
          h1 { margin-bottom: 12px; }
          .box { background: #fff; border: 1px solid #e5e7eb; border-radius: 12px; padding: 24px; }
          ol { padding-left: 20px; }
          a { color: #f36b00; text-decoration: none; }
        </style>
      </head>
      <body>
        <div class="box">
          <h1>Condiciones generales</h1>
          <ol>
            <li>El alcance del proyecto, costos y tiempos serán confirmados por escrito antes de iniciar la ejecución.</li>
            <li>Los entregables, cronogramas, estimaciones y propuestas podrán ajustarse si se modifica el alcance o existen dependencias externas.</li>
            <li>La validación del cliente es necesaria para avanzar en cada fase del proyecto.</li>
            <li>Los pagos y plazos se acordarán conforme a la propuesta emitida y la política comercial vigente.</li>
            <li>ANDI podrá modificar la propuesta si se agregan requisitos, servicios o tiempos no contemplados al momento de la emisión.</li>
            <li>La propuesta tiene vigencia de 15 días naturales desde su emisión.</li>
          </ol>
          <p><a href="/">Volver a ANDI</a></p>
        </div>
      </body>
    </html>
    """
    return HTMLResponse(term_html)


CHAT_HTML = """
<!doctype html>
<html lang="es">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>ANDI Assistant</title>
    <style>
      :root {
        --bg: #f3f3f3;
        --panel: #ffffff;
        --ink: #1f2937;
        --muted: #8a939d;
        --primary: #f36b00;
        --gray: #a9afb6;
        --shadow: rgba(15, 23, 42, 0.10);
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        background: var(--bg);
        color: var(--ink);
        font-family: Arial, Helvetica, sans-serif;
      }
      .shell {
        max-width: 1200px;
        margin: 0 auto;
        padding: 18px 18px 24px;
      }
      .hero {
        display: flex;
        align-items: center;
        justify-content: center;
        min-height: 180px;
        padding: 0;
      }
      .hero-robot {
        display: flex;
        justify-content: center;
        align-items: center;
      }
      .hero-robot img {
        width: min(360px, 72vw);
        height: auto;
        display: block;
        filter: drop-shadow(0 10px 18px rgba(0, 0, 0, 0.08));
      }
      .card {
        max-width: 900px;
        margin: 0 auto;
        background: rgba(255,255,255,0.55);
        border: 1px solid rgba(15,23,42,0.06);
        border-radius: 14px;
        padding: 14px;
      }
      .meta {
        display: none;
      }
      .chat {
        min-height: 54px;
        max-height: 140px;
        overflow: auto;
        background: rgba(255,255,255,0.25);
        border: 1px solid rgba(148,163,184,0.18);
        border-radius: 10px;
        padding: 10px 12px;
        margin-bottom: 10px;
        white-space: pre-wrap;
        font-size: 13px;
        line-height: 1.45;
      }
      textarea {
        width: 100%;
        min-height: 52px;
        border-radius: 10px;
        border: 1px solid rgba(148,163,184,0.25);
        background: rgba(255,255,255,0.7);
        color: var(--ink);
        padding: 10px 12px;
        font-size: 14px;
        resize: vertical;
      }
      .actions {
        margin-top: 8px;
        display: flex;
        justify-content: flex-end;
      }
      button {
        background: var(--primary);
        color: #fff;
        border: none;
        border-radius: 8px;
        padding: 9px 14px;
        font-weight: bold;
        cursor: pointer;
        box-shadow: none;
      }
      @media (max-width: 760px) {
        .shell { padding: 12px 12px 20px; }
        .hero { min-height: 140px; }
        .card { padding: 12px; }
      }
    </style>
  </head>
  <body>
    <div class="shell">
      <div class="hero">
        <div class="hero-robot">
          <img src="/assets/Andi blanco.jpeg" alt="Logo ANDI" />
        </div>
      </div>

      <div class="card">
        <div class="meta">Cotizaciones, cronogramas, estimaciones y resúmenes</div>
        <div id="chat" class="chat">ANDI: Hola, puedo ayudarte a estimar proyectos, crear cronogramas, preparar cotizaciones y resumir reuniones.</div>
        <textarea id="message" placeholder="Ejemplo: Necesito una cotización para Agribio para un portal de clientes con login, dashboard y cotizaciones"></textarea>
        <div class="actions">
          <button id="sendBtn" type="button">Enviar</button>
        </div>
        <div style="margin-top: 10px; font-size: 12px;"><a href="/condiciones-generales" target="_blank" style="color: #f36b00; text-decoration: none;">Ver condiciones generales</a></div>
      </div>
    </div>

    <script>
      document.addEventListener('DOMContentLoaded', () => {
        const chat = document.getElementById('chat');
        const input = document.getElementById('message');
        const sendBtn = document.getElementById('sendBtn');

        if (!chat || !input || !sendBtn) {
          return;
        }

        function append(text) {
          chat.insertAdjacentHTML('beforeend', '<br><br>' + text);
          chat.scrollTop = chat.scrollHeight;
        }

        async function sendMessage() {
          const message = input.value.trim();
          if (!message) return;
          append('Tú: ' + message);
          input.value = '';
          try {
            const response = await fetch('/assistant/chat', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ message })
            });
            const data = await response.json();
            if (!response.ok) {
              append('ANDI: ' + (data.detail || data.error || 'No pude procesar tu solicitud.'));
              return;
            }
            append('ANDI: ' + (data.message || JSON.stringify(data, null, 2)));
          } catch (error) {
            append('ANDI: Error de comunicación con el servicio.');
          }
        }

        sendBtn.addEventListener('click', sendMessage);
        input.addEventListener('keydown', (event) => {
          if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            sendMessage();
          }
        });
      });
    </script>
  </body>
</html>
"""


def call_openai_for_response(message: str, context: dict | None = None) -> str | None:
    """Optional: reescribe la respuesta final con OpenAI si hay API key configurada."""
    if not config.OPENAI_API_KEY:
        return None
    try:
        payload = {
            "model": config.OPENAI_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Eres ANDI, un asistente comercial para cotizaciones, cronogramas y propuestas. "
                        "Responde de manera amigable, clara y profesional en español. "
                        "Mantén la información real del contexto y no inventes datos."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Usuario: {message}\n\n"
                        f"Contexto interno: {context or {}}\n\n"
                        "Quiero que la respuesta final sea natural, breve y útil para un cliente o vendedor."
                    ),
                },
            ],
            "temperature": 0.32,
            "max_tokens": 300,
        }
        response = requests.post(
            f"{config.OPENAI_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {config.OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        return (data.get("choices") or [{}])[0].get("message", {}).get("content", "").strip() or None
    except Exception:
        return None


def format_assistant_message(payload: dict) -> str:
    intent = (payload.get("intent") or "general").lower()
    if intent == "general":
        return payload.get("message") or "Puedo ayudarte con cotizaciones, estimaciones, cronogramas y resúmenes."

    if intent == "proposal":
        proposal = payload.get("proposal") or {}
        estimate = payload.get("estimate") or {}
        project = proposal.get("project_name") or estimate.get("project_name") or "tu proyecto"
        client = proposal.get("client_name") or estimate.get("client_name") or "Cliente"
        final_cost = proposal.get("final_cost") or proposal.get("adjusted_cost") or 0
        schedule = payload.get("schedule") or payload.get("proposal", {}).get("schedule") or {}
        total_days = schedule.get("total_days") or 0
        return (
            f"He preparado una propuesta para {client} en {project}. "
            f"El costo estimado final es ${final_cost:.2f} CRC y el cronograma total tiene {total_days} días."
        )

    if intent == "schedule":
        schedule = payload.get("schedule") or {}
        project = schedule.get("project_name") or "tu proyecto"
        total_weeks = schedule.get("total_weeks") or 0
        tasks = schedule.get("tasks") or []
        first_task = tasks[0].get("phase") if tasks else "inicio"
        return (
            f"Te preparé el cronograma de {project}. "
            f"Incluye {total_weeks} semanas de trabajo y comienza con {first_task}."
        )

    if intent == "summary":
        summary = payload.get("summary") or {}
        title = summary.get("title") or "Resumen de la reunión"
        decision_count = len(summary.get("decisions") or [])
        task_count = len(summary.get("pending_tasks") or [])
        return f"{title}. Tengo {decision_count} decisiones clave y {task_count} pendientes por cerrar."

    return payload.get("message") or "He revisado tu solicitud y estoy listo para ayudarte."


async def chat_home(_request):
    return HTMLResponse(CHAT_HTML)


async def assistant_chat(request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    message = (payload.get("message") or payload.get("text") or "").strip()
    if not message:
        return JSONResponse({"error": "Se requiere un mensaje."}, status_code=400)

    parsed = parse_user_request(message)
    intent = parsed["intent"]

    if intent == "general":
        response = {
            "intent": "general",
            "message": "Puedo ayudarte con cotizaciones, estimaciones, cronogramas, calendario, PDF y resúmenes de reuniones.",
            "parsed": parsed,
        }
        if config.OPENAI_API_KEY:
            polished = call_openai_for_response(message, response)
            if polished:
                response["message"] = polished
        return JSONResponse(response)

    if intent == "proposal":
        client_term = parsed.get("client_name") or "cliente"
        if client_term and client_term.lower() not in {"cliente", "nuevo"}:
            try:
                matches = await asyncio.to_thread(db.call_procedure, "andi.sp_buscar_cliente", client_term)
            except Exception:
                matches = []
            if len(matches) > 1:
                response = {
                    "intent": "client_selection",
                    "requires_client_selection": True,
                    "parsed": parsed,
                    "clientes": matches,
                    "message": build_client_selection_message(client_term, matches),
                }
                return JSONResponse(response)

    estimate = estimate_project(
        project_name=parsed["project_name"],
        client_name=parsed["client_name"],
        description=parsed["description"],
        complexity=parsed["complexity"],
        modules=parsed["modules"],
        integrations=parsed["integrations"],
        users=parsed["users"],
        localization=parsed["localization"],
    )

    if intent == "proposal":
        proposal = generate_quote(
            project_name=parsed["project_name"],
            client_name=parsed["client_name"],
            estimate=estimate,
            discount_percent=0.0,
            margin_percent=0.2,
        )
        pdf_path = f"exports/{parsed['project_name'].lower().replace(' ', '_')}.pdf"
        pdf = generate_pdf_proposal(estimate, output_path=pdf_path)
        proposal["pdf"] = pdf
        schedule = build_project_schedule(estimate)
        proposal["schedule"] = schedule
        record = save_quote_history({
            "id": f"QT-{int(__import__('time').time())}",
            "project_name": parsed["project_name"],
            "client_name": parsed["client_name"],
            "final_cost": proposal.get("final_cost"),
            "created_at": __import__('datetime').datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "pdf_path": pdf_path,
        })
        response = {"intent": "proposal", "parsed": parsed, "estimate": estimate, "proposal": proposal, "schedule": schedule, "quote_id": record["id"], "pdf_path": pdf_path}
        response["message"] = format_assistant_message(response)
        if config.OPENAI_API_KEY:
            polished = call_openai_for_response(message, response)
            if polished:
                response["message"] = polished
        return JSONResponse(response)

    if intent == "schedule":
        schedule = build_project_schedule(estimate)
        response = {"intent": "schedule", "parsed": parsed, "estimate": estimate, "schedule": schedule}
        response["message"] = format_assistant_message(response)
        if config.OPENAI_API_KEY:
            polished = call_openai_for_response(message, response)
            if polished:
                response["message"] = polished
        return JSONResponse(response)

    if intent == "summary":
        summary = summarize_meeting(message)
        response = {"intent": "summary", "parsed": parsed, "summary": summary}
        response["message"] = format_assistant_message(response)
        if config.OPENAI_API_KEY:
            polished = call_openai_for_response(message, response)
            if polished:
                response["message"] = polished
        return JSONResponse(response)

    response = {"intent": intent, "parsed": parsed, "estimate": estimate}
    response["message"] = format_assistant_message(response)
    return JSONResponse(response)


mcp_app = mcp.streamable_http_app()  # debe crearse antes de usar mcp.session_manager
ROOT_DIR = Path(__file__).resolve().parent


@contextlib.asynccontextmanager
async def lifespan(_app):
    async with mcp.session_manager.run():
        yield


app = Starlette(
    routes=[
        Route("/health", health, methods=["GET"]),
        Route("/", chat_home, methods=["GET"]),
        Route("/chat", chat_home, methods=["GET"]),
        Route("/assistant/chat", assistant_chat, methods=["GET", "POST"]),
        Route("/api/chat", assistant_chat, methods=["GET", "POST"]),
        Route("/condiciones-generales", terms_page, methods=["GET"]),
        Route("/terms", terms_page, methods=["GET"]),
        Mount("/assets", app=StaticFiles(directory=str(ROOT_DIR)), name="assets"),
        Mount("/mcp", app=mcp_app),
    ],
    lifespan=lifespan,
)
app.add_middleware(BearerAuth)


if __name__ == "__main__":
    uvicorn.run(app, host=config.HOST, port=config.PORT)
