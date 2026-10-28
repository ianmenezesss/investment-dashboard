from copy import deepcopy
from decimal import Decimal as D
import pytest
from app.main import app
from app.auth import authenticate, Principal
from app.bcb_rates.router import rates_service
from test_fixed_income import client, create, apply, redeem, A, B, PATH

# All values/institution/dates below are fictional and required only as test fixtures.
POSITION = dict(as_of="2026-10-15", gross_value="5000.00", net_value="4950.00", taxes_combined="50.00",
    reported_gain="250.00", confirmed_principal=None, source="Extrato fictício", notes=None)


def contract(client):
    return create(client, issuer="Banco Exemplo", product_name="CDB Pós-Fixado Exemplo", remuneration="CDI", indexer="CDI",
        contracted_rate="100", application_date="2026-10-15", maturity_date="2028-10-15")


def test_opening_is_observation_never_deposit_and_unknown_principal_is_null(client):
    investment = contract(client)
    response = client.post(f"{PATH}/{investment}/opening-balance", json=POSITION)
    assert response.status_code == 201, response.text
    data = response.json()
    assert D(data["gross_value"]) - D(data["taxes_combined"]) == D(data["net_value"])
    assert data["reported_gain"] == "250.00" and data["confirmed_principal"] is None
    detail = client.get(f"{PATH}/{investment}").json()
    assert detail["tracking_mode"] == "CONSOLIDATED" and detail["lots"] == []
    assert detail["opening_balance"] == data and detail["latest_observation"] == data
    assert client.get(f"{PATH}/{investment}/movements").json() == []
    assert client.get(PATH).json()[0]["latest_observation"] == data
    assert client.post(f"{PATH}/{investment}/opening-balance", json=POSITION).status_code == 409


@pytest.mark.parametrize("patch", [
    {"gross_value":"-1"}, {"net_value":"5001"}, {"taxes_combined":"49"},
    {"taxes_combined":"50", "ir_estimate":"50"}, {"taxes_combined":None,"ir_estimate":"60"},
    {"taxes_combined":None,"ir_estimate":"20","iof_estimate":"10"}, {"confirmed_principal":"-1"},
    {"gross_value":"NaN"}, {"gross_value":"1.001"}, {"as_of":"2099-01-01"}, {"as_of":"2026-10-14"},
    {"source":" "}, {"cash_received":"10"}, {"owner_id":str(B)},
])
def test_invalid_observations_rejected_without_synthesizing_history(client, patch):
    investment = contract(client)
    assert client.post(f"{PATH}/{investment}/opening-balance", json=POSITION | patch).status_code == 422
    assert client.get(f"{PATH}/{investment}/observations").json() == []


@pytest.mark.parametrize("taxes", [dict(taxes_combined=None,ir_estimate="40",iof_estimate="10"),
    dict(taxes_combined=None,ir_estimate="20",iof_estimate=None), dict(taxes_combined=None)])
def test_discriminated_partial_or_unknown_taxes_and_confirmed_principal(client, taxes):
    investment = contract(client)
    result = client.post(f"{PATH}/{investment}/opening-balance", json=POSITION | taxes | {"confirmed_principal":"4750"})
    assert result.status_code == 201
    assert result.json()["confirmed_principal"] == "4750.00"  # never 5000 - 250 inferred


def test_followup_lots_and_manual_redemption_reconciliation_preserve_all_records(client):
    investment = contract(client)
    first = client.post(f"{PATH}/{investment}/opening-balance", json=POSITION).json()
    assert client.post(f"{PATH}/{investment}/applications", json={"date":"2026-10-15","principal_amount":"100"}).status_code == 422
    lot = apply(client, investment, "100", "2026-10-16")
    assert lot["kind"] == "APPLICATION" and lot["principal_amount"] != "5000"
    second = POSITION | {"as_of":"2026-10-17", "gross_value":"4800", "net_value":"4750", "reason":"AFTER_CONSOLIDATED_REDEMPTION", "cash_received":"300"}
    result = client.post(f"{PATH}/{investment}/observations", json=second)
    assert result.status_code == 201, result.text
    assert result.json()["confirmed_principal"] is None
    assert client.get(f"{PATH}/{investment}/observations").json()[0] == first
    assert len(client.get(f"{PATH}/{investment}/movements").json()) == 1
    assert redeem(client, investment, 99999, "100", "2026-10-17").status_code == 404
    assert redeem(client, investment, lot["lot_id"], "10", "2026-10-16").status_code == 422
    assert redeem(client, investment, lot["lot_id"], "10", "2026-10-18").status_code == 201
    assert client.post(f"{PATH}/{investment}/observations", json=POSITION | {"as_of":"2026-10-17"}).status_code == 422
    assert client.delete(f"{PATH}/{investment}/observations/{first['id']}").status_code == 404
    assert client.post(f"{PATH}/{investment}/opening-balance", json=POSITION).status_code == 409


def test_contract_with_existing_lots_cannot_be_reopened_or_silently_rebased(client):
    investment = contract(client)
    apply(client, investment, "100", "2026-10-15")
    before = client.get(f"{PATH}/{investment}/movements").json()
    assert client.post(f"{PATH}/{investment}/opening-balance", json=POSITION).status_code == 409
    assert client.get(f"{PATH}/{investment}/movements").json() == before
    assert client.post(f"{PATH}/{investment}/observations", json=POSITION).status_code == 409


def test_no_cdi_on_manual_wealth_and_returns_of_new_lots_have_explicit_scope(client):
    investment = contract(client)
    client.post(f"{PATH}/{investment}/opening-balance", json=POSITION)
    class Forbidden:
        async def get(self,*_): raise AssertionError("Manual balance must never be capitalized")
    app.dependency_overrides[rates_service] = Forbidden
    query = "as_of=2026-10-15&convention=daily_cdi_pro_rata_decimal_v1&calendar=anbima_2024_2026_v1&tax_profile=br_resident_individual"
    data = client.get(f"{PATH}/{investment}/returns?{query}").json()
    assert data["scope"] == "post_opening_lots_only" and data["principal_balance"] is None
    assert data["net_value_estimate"] is None and data["status"] == "incomplete"
    apply(client, investment, "100", "2026-10-16")
    data = client.get(f"{PATH}/{investment}/returns?{query.replace('2026-10-15','2026-10-16')}").json()
    assert data["scope"] == "post_opening_lots_only" and D(data["principal_balance"]) == 100
    assert D(data["net_value_estimate"]) == 100  # same-day new lot, no rate or consolidated wealth added
    assert client.get(f"{PATH}/{investment}").json()["opening_balance"]["confirmed_principal"] is None


def test_owner_isolation_auth_and_private_error_sanitization(client):
    investment = contract(client)
    client.post(f"{PATH}/{investment}/opening-balance", json=POSITION)
    app.dependency_overrides[authenticate] = lambda: Principal(B)
    for suffix in ("observations", "opening-balance"):
        assert client.post(f"{PATH}/{investment}/{suffix}", json=POSITION).status_code == 404
    assert client.get(f"{PATH}/{investment}/observations").status_code == 404
    assert client.get(PATH).json() == []
    app.dependency_overrides.pop(authenticate)
    assert client.get(f"{PATH}/{investment}/observations").status_code == 401
    assert client.post(f"{PATH}/{investment}/opening-balance", json=POSITION).status_code == 401
    app.dependency_overrides[authenticate] = lambda: Principal(A)
    marker = "FAKE-SENSITIVE-MARKER-DO-NOT-ECHO"
    response = client.post(f"{PATH}/{investment}/observations", json=POSITION | {"gross_value":marker})
    assert response.status_code == 422 and marker not in response.text and '"input"' not in response.text
