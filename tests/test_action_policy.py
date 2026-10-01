from action_policy import can_execute, classify_tool, decision


def test_read_and_prepare_actions_are_allowed():
    assert can_execute("buscar_cliente") is True
    assert can_execute("generar_cotizacion") is True
    assert classify_tool("generar_cotizacion") == "prepare"


def test_unknown_action_is_forbidden():
    result = decision("ejecutar_sql")
    assert result["allowed"] is False
    assert result["classification"] == "forbidden"
