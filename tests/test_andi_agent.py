from pathlib import Path

from andi_agent import (
    build_client_selection_message,
    build_project_schedule,
    estimate_project,
    generate_pdf_proposal,
    parse_user_request,
)
from main import format_assistant_message


def test_parse_user_request_detects_proposal_intent():
    request = parse_user_request(
        "Necesito una cotización para Agribio para un portal de clientes con login, dashboard y cotizaciones"
    )

    assert request["intent"] == "proposal"
    assert request["client_name"] == "Agribio"
    assert request["project_name"]
    assert "portal" in request["description"].lower()


def test_parse_user_request_detects_final_client_name():
    request = parse_user_request("Preparate una cotización para Datasys")

    assert request["intent"] == "proposal"
    assert request["client_name"] == "Datasys"
    assert request["project_name"]


def test_parse_user_request_detects_client_before_follow_up_clause():
    request = parse_user_request(
        "Preparame una cotizacion para DAtasys y el me busque los clientes con nombre o alias"
    )

    assert request["intent"] == "proposal"
    assert request["client_name"] == "DAtasys"
    assert request["project_name"]


def test_estimate_project_returns_structured_data():
    estimate = estimate_project(
        project_name="Portal de clientes",
        client_name="Agribio",
        description="Portal con login, catálogo, cotizaciones y dashboard",
        complexity="medium",
        modules=["autenticación", "dashboard", "cotizaciones"],
        integrations=2,
        users=50,
        localization=True,
    )

    assert estimate["project_name"] == "Portal de clientes"
    assert estimate["total_hours"] > 0
    assert estimate["total_cost"] > 0
    assert len(estimate["phases"]) >= 3


def test_build_project_schedule_returns_tasks():
    estimate = estimate_project(
        project_name="CRM interno",
        client_name="Cliente demo",
        description="CRM sencillo con gestión de leads y seguimiento",
        complexity="low",
        modules=["leads", "seguimiento", "reportes"],
        integrations=1,
        users=15,
        localization=False,
    )
    schedule = build_project_schedule(estimate, start_date="2026-10-06")

    assert schedule["project_name"] == "CRM interno"
    assert len(schedule["tasks"]) >= 4
    assert schedule["total_weeks"] > 0


def test_generate_pdf_proposal_creates_file(tmp_path):
    estimate = estimate_project(
        project_name="App móvil",
        client_name="Cliente demo",
        description="App móvil para gestión de inventario",
        complexity="high",
        modules=["inventario", "pedidos", "reportes"],
        integrations=3,
        users=80,
        localization=True,
    )
    output = tmp_path / "proposal.pdf"

    result = generate_pdf_proposal(estimate, output_path=str(output))

    assert result["created"] is True
    assert output.exists()


def test_format_assistant_message_returns_natural_language():
    payload = {
        "intent": "proposal",
        "proposal": {"project_name": "Portal de clientes", "client_name": "Agribio", "final_cost": 1224.72},
        "schedule": {"total_days": 25},
    }

    message = format_assistant_message(payload)

    assert "Agribio" in message
    assert "1224.72" in message
    assert "cronograma" in message.lower()


def test_build_client_selection_message_lists_matches():
    clients = [
        {"codigo": "DTS-001", "nombre": "Datasys Chile"},
        {"codigo": "DTS-002", "nombre": "DataSys México"},
    ]

    message = build_client_selection_message("Datasys", clients)

    assert "Datasys" in message
    assert "DTS-001" in message
    assert "DTS-002" in message
    assert "elige" in message.lower()
