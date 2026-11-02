"""Explicit administrative loader for the fictitious v2 demo scenario.

This script is intentionally not exposed as an HTTP route. It validates the target
Supabase project and Auth identity before writing one atomic, owner-scoped transaction.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from pathlib import Path
import sys
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.engine import make_url

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
DEFAULT_FIXTURE = REPO_ROOT / "docs" / "fixtures" / "v2-demo-scenario.json"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.accounts import AccountFixtureLoad, AccountMember
from app.database import SessionLocal, settings
from app.financial_events import FinancialEvent, FinancialEventRevision
from app.fixed_income.models import ApplicationRevision, Investment, InvestmentArchive, Lot, Movement
from app.fixed_income.observations import PositionObservation
from app.models import Operation
from app.wealth_observations import PortfolioValuationObservation


MAX_AMOUNT = Decimal("999999999999.99")
TICKER_RE = re.compile(r"^[A-Z][A-Z0-9]{3,19}$")
FICTITIOUS_LABEL = "FICTÍCIO — cenário v2-demo-scenario"
FINANCIAL_MODELS = (
    Operation, Investment, Lot, Movement, PositionObservation, InvestmentArchive,
    ApplicationRevision, FinancialEvent, FinancialEventRevision, PortfolioValuationObservation,
)


class FixtureError(ValueError):
    pass


def _date(value, label: str, *, today: date) -> date:
    if not isinstance(value, str):
        raise FixtureError(f"Data inválida em {label}")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise FixtureError(f"Data inválida em {label}") from None
    if parsed.isoformat() != value or parsed > today:
        raise FixtureError(f"Data futura ou inválida em {label}")
    return parsed


def _money(
    value,
    label: str,
    *,
    positive: bool = False,
    max_amount: Decimal = MAX_AMOUNT,
    max_scale: int = 8,
) -> Decimal:
    if not isinstance(value, str):
        raise FixtureError(f"Valor monetário deve ser texto decimal em {label}")
    try:
        amount = Decimal(value)
    except InvalidOperation:
        raise FixtureError(f"Valor monetário inválido em {label}") from None
    if not amount.is_finite() or amount < 0 or amount > max_amount or positive and amount == 0:
        raise FixtureError(f"Valor fora do intervalo em {label}")
    normalized = amount.normalize()
    if max(0, -normalized.as_tuple().exponent) > max_scale:
        raise FixtureError(f"Precisão superior à suportada em {label}")
    return amount


def validate_fixture(payload: dict, *, today: date | None = None) -> dict:
    today = today or date.today()
    if not isinstance(payload, dict) or "fict" not in str(payload.get("notice", "")).casefold():
        raise FixtureError("O cenário precisa estar identificado como fictício")
    as_of = _date(payload.get("as_of"), "as_of", today=today)
    operations = payload.get("operations")
    if not isinstance(operations, list) or not operations:
        raise FixtureError("O cenário precisa conter operações de ações")

    holdings: dict[str, dict[str, Decimal]] = {}
    realized = Decimal(0)
    validated_operations = []
    known_tickers = set()
    last_operation_date: dict[str, date] = {}
    for index, item in enumerate(operations):
        label = f"operations[{index}]"
        if not isinstance(item, dict):
            raise FixtureError(f"Operação inválida em {label}")
        ticker = item.get("ticker")
        kind = item.get("kind")
        if not isinstance(ticker, str) or not TICKER_RE.fullmatch(ticker) or kind not in ("BUY", "SELL"):
            raise FixtureError(f"Ativo ou tipo de operação inválido em {label}")
        day = _date(item.get("date"), label, today=today)
        if day > as_of:
            raise FixtureError(f"Operação posterior à data-base em {label}")
        if ticker in last_operation_date and day < last_operation_date[ticker]:
            raise FixtureError(f"Operações devem estar em ordem cronológica por ativo em {label}")
        last_operation_date[ticker] = day
        quantity = _money(item.get("quantity"), f"{label}.quantity", positive=True)
        price = _money(item.get("price"), f"{label}.price", positive=True)
        fees = _money(item.get("fees"), f"{label}.fees")
        position = holdings.setdefault(ticker, {"quantity": Decimal(0), "cost": Decimal(0)})
        gross = quantity * price
        if kind == "BUY":
            position["quantity"] += quantity
            position["cost"] += gross + fees
        else:
            if quantity > position["quantity"]:
                raise FixtureError(f"Venda superior à posição em {label}")
            basis = position["cost"] * quantity / position["quantity"]
            realized += gross - fees - basis
            position["quantity"] -= quantity
            position["cost"] -= basis
        known_tickers.add(ticker)
        validated_operations.append({"ticker": ticker, "kind": kind, "date": day,
                                     "quantity": quantity, "price": price, "fees": fees})

    open_cost = sum((position["cost"] for position in holdings.values()), Decimal(0))
    contract = payload.get("fixed_income_contract")
    if not isinstance(contract, dict) or contract.get("product_type") != "CDB":
        raise FixtureError("O cenário precisa conter um contrato CDB")
    if not all(isinstance(contract.get(field), str) and contract[field].strip()
               for field in ("issuer", "product_name")):
        raise FixtureError("Emissor e nome do CDB são obrigatórios")
    remuneration, indexer = contract.get("remuneration"), contract.get("indexer")
    if (remuneration, indexer) not in (("FIXED", "NONE"), ("CDI", "CDI")):
        raise FixtureError("Remuneração e indexador do CDB são incompatíveis")
    rate = _money(contract.get("contracted_rate"), "contracted_rate", positive=True,
                  max_amount=Decimal("9999.99999999"))
    application_date = _date(contract.get("application_date"), "application_date", today=today)
    maturity_date = _date(contract.get("maturity_date"), "maturity_date", today=date.max)
    if maturity_date <= application_date:
        raise FixtureError("Vencimento do CDB deve ser posterior à aplicação inicial")
    opening = contract.get("opening_observation")
    application = contract.get("application")
    cdb_position = contract.get("position_observation")
    if not all(isinstance(item, dict) for item in (opening, application, cdb_position)):
        raise FixtureError("Abertura, movimentação e posição observada do CDB são obrigatórias")
    opening_day = _date(opening.get("as_of"), "opening_observation.as_of", today=today)
    movement_day = _date(application.get("date"), "application.date", today=today)
    cdb_day = _date(cdb_position.get("as_of"), "position_observation.as_of", today=today)
    if opening_day != application_date or movement_day <= opening_day or cdb_day < movement_day or cdb_day > as_of:
        raise FixtureError("A cronologia do CDB está inconsistente")
    opening_gross = _money(opening.get("gross_value"), "opening gross_value", max_scale=2)
    opening_net = _money(opening.get("net_value"), "opening net_value", max_scale=2)
    app_amount = _money(application.get("principal_amount"), "application principal", positive=True)
    cdb_gross = _money(cdb_position.get("gross_value"), "CDB gross_value", max_scale=2)
    cdb_net = _money(cdb_position.get("net_value"), "CDB net_value", max_scale=2)
    if opening_net > opening_gross or cdb_net > cdb_gross:
        raise FixtureError("Posição líquida do CDB não pode superar a bruta")
    for entry, label in ((opening, "opening_observation"), (cdb_position, "position_observation")):
        if not isinstance(entry.get("source"), str) or "fict" not in entry["source"].casefold():
            raise FixtureError(f"Fonte de {label} deve identificar os dados como fictícios")

    events = payload.get("financial_events")
    if not isinstance(events, list):
        raise FixtureError("A lista de eventos financeiros é inválida")
    validated_events = []
    for index, event in enumerate(events):
        label = f"financial_events[{index}]"
        if not isinstance(event, dict):
            raise FixtureError(f"Evento inválido em {label}")
        kind = event.get("kind")
        day = _date(event.get("event_date"), f"{label}.event_date", today=today)
        if day > as_of or kind not in ("CONTRIBUTION", "WITHDRAWAL", "DIVIDEND", "JCP"):
            raise FixtureError(f"Tipo ou data inválida em {label}")
        cash = _money(event.get("cash_amount"), f"{label}.cash_amount", positive=True)
        ticker = event.get("ticker")
        if kind in ("DIVIDEND", "JCP"):
            if not isinstance(ticker, str) or ticker not in known_tickers:
                raise FixtureError(f"Provento sem ativo correspondente em {label}")
        elif ticker is not None:
            raise FixtureError(f"Fluxo externo não deve apontar para um ativo em {label}")
        gross = None if event.get("gross_amount") is None else _money(event["gross_amount"], f"{label}.gross_amount", positive=True)
        tax = None if event.get("tax_withheld") is None else _money(event["tax_withheld"], f"{label}.tax_withheld")
        if kind == "JCP" and gross is not None and tax is not None and gross - tax != cash:
            raise FixtureError(f"Bruto, tributos e líquido inconsistentes em {label}")
        if kind in ("CONTRIBUTION", "WITHDRAWAL") and (gross is not None or tax is not None):
            raise FixtureError(f"Fluxo externo não deve declarar bruto ou tributo em {label}")
        source = event.get("source")
        if not isinstance(source, str) or "fict" not in source.casefold():
            raise FixtureError(f"Fonte deve identificar o evento como fictício em {label}")
        validated_events.append({"kind": kind, "event_date": day, "ticker": ticker,
                                 "cash_amount": cash, "gross_amount": gross, "tax_withheld": tax,
                                 "source": f"{FICTITIOUS_LABEL} — {source}"})

    wealth = payload.get("wealth_observations")
    if not isinstance(wealth, list) or len(wealth) < 3:
        raise FixtureError("São necessárias ao menos três observações patrimoniais para os gráficos")
    validated_wealth = []
    previous_day = None
    for index, point in enumerate(wealth):
        label = f"wealth_observations[{index}]"
        if not isinstance(point, dict):
            raise FixtureError(f"Observação patrimonial inválida em {label}")
        day = _date(point.get("as_of"), f"{label}.as_of", today=today)
        if day > as_of or previous_day is not None and day <= previous_day:
            raise FixtureError("Observações patrimoniais devem estar ordenadas e dentro do cenário")
        previous_day = day
        equity_value = _money(point.get("equities_market_value"), f"{label}.equities_market_value", max_scale=2)
        source = point.get("equities_source")
        if not isinstance(source, str) or "fict" not in source.casefold():
            raise FixtureError(f"Fonte patrimonial deve identificar dados fictícios em {label}")
        coverage = point.get("fixed_income_coverage")
        gross_raw, net_raw = point.get("fixed_income_gross_value"), point.get("fixed_income_net_value")
        if coverage == "empty":
            if gross_raw is not None or net_raw is not None:
                raise FixtureError("Cobertura vazia não pode conter valor de renda fixa")
            gross_value = net_value = None
        elif coverage == "complete":
            if gross_raw is None or net_raw is None:
                raise FixtureError("Cobertura completa exige valores bruto e líquido")
            gross_value = _money(gross_raw, f"{label}.fixed_income_gross_value", max_scale=2)
            net_value = _money(net_raw, f"{label}.fixed_income_net_value", max_scale=2)
            if net_value > gross_value:
                raise FixtureError("Valor líquido da renda fixa não pode superar o bruto")
        else:
            raise FixtureError(f"Cobertura fictícia inválida em {label}")
        validated_wealth.append({"as_of": day, "equities_market_value": equity_value,
                                 "equities_source": f"{FICTITIOUS_LABEL} — {source}",
                                 "fixed_income_coverage": coverage,
                                 "fixed_income_gross_value": gross_value,
                                 "fixed_income_net_value": net_value})
    expected = payload.get("expected_checks")
    if not isinstance(expected, dict) or expected.get("wealth_observation_count") != len(validated_wealth):
        raise FixtureError("Quantidade de observações não corresponde às verificações do cenário")
    if validated_wealth[-1]["as_of"] != as_of or as_of != cdb_day:
        raise FixtureError("A última observação patrimonial deve coincidir com a data-base do cenário e do CDB")
    last = validated_wealth[-1]
    if (last["fixed_income_coverage"] != "complete"
            or last["fixed_income_gross_value"] != cdb_gross
            or last["fixed_income_net_value"] != cdb_net):
        raise FixtureError("A posição consolidada final diverge da posição observada do CDB")

    check_values = {
        "bbas3_realized_gain_before_tax": realized,
        "open_equity_acquisition_cost": open_cost,
        "fixed_income_gross_observation": cdb_gross,
        "fixed_income_net_observation": cdb_net,
        "consolidated_net_observation": last["equities_market_value"] + cdb_net,
        "external_contributions": sum((e["cash_amount"] for e in validated_events if e["kind"] == "CONTRIBUTION"), Decimal(0)),
        "external_withdrawals": sum((e["cash_amount"] for e in validated_events if e["kind"] == "WITHDRAWAL"), Decimal(0)),
        "dividends_received": sum((e["cash_amount"] for e in validated_events if e["kind"] == "DIVIDEND"), Decimal(0)),
        "jcp_received_net": sum((e["cash_amount"] for e in validated_events if e["kind"] == "JCP"), Decimal(0)),
        "cdb_application_principal": app_amount,
    }
    required_checks = set(check_values) | {"wealth_observation_count"}
    if not isinstance(expected, dict) or set(expected) != required_checks:
        raise FixtureError("O conjunto de verificações financeiras da fixture está incompleto ou inesperado")
    for key, actual in check_values.items():
        if _money(expected[key], f"expected_checks.{key}") != actual:
            raise FixtureError(f"Verificação financeira inconsistente: {key}")
    if expected.get("wealth_observation_count") != len(validated_wealth):
        raise FixtureError("Quantidade de observações não corresponde às verificações do cenário")

    goal = payload.get("goal_input")
    if not isinstance(goal, dict):
        raise FixtureError("Meta fictícia do cenário está ausente")
    target = _money(goal.get("targetAmount"), "goal.targetAmount", positive=True)
    initial = _money(goal.get("initialReferenceAmount"), "goal.initialReferenceAmount")
    progress = _money(goal.get("manualProgressAmount"), "goal.manualProgressAmount")
    _date(goal.get("targetDate"), "goal.targetDate", today=date.max)
    if initial > target or progress > target or not isinstance(goal.get("name"), str) or "fict" not in goal["name"].casefold():
        raise FixtureError("Meta fictícia possui valores ou identificação inconsistentes")

    return {"as_of": as_of, "operations": validated_operations, "events": validated_events,
            "contract": contract, "opening": {"as_of": opening_day, "gross_value": opening_gross,
                "net_value": opening_net, "source": f"{FICTITIOUS_LABEL} — {opening['source']}"},
            "application": {"date": movement_day, "principal_amount": app_amount},
            "cdb_observation": {"as_of": cdb_day, "gross_value": cdb_gross, "net_value": cdb_net,
                "source": f"{FICTITIOUS_LABEL} — {cdb_position['source']}"},
            "wealth": validated_wealth, "fixture_id": "v2-demo-scenario"}


def load_fictional_fixture(
    db: Session,
    *,
    user_id: UUID,
    admin_id: UUID,
    payload: dict,
    project_verified: bool,
    today: date | None = None,
) -> dict[str, int | str]:
    """Load the fixture only into a proven, active, empty owner account."""
    if not isinstance(user_id, UUID) or not isinstance(admin_id, UUID):
        raise FixtureError("UUID explícitos de destino e administrador são obrigatórios")
    if admin_id not in settings.invitation_admin_ids:
        raise FixtureError("Administrador não autorizado")
    if project_verified is not True:
        raise FixtureError("Projeto Supabase e banco de destino não foram confirmados")
    clean = validate_fixture(payload, today=today)
    try:
        if db.bind.dialect.name == "postgresql":
            db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                       {"key": f"dashboard-fixture:{user_id}"})
            db.execute(text("SELECT set_config('app.user_id',:user_id,true),set_config('app.admin_id',:admin_id,true)"),
                       {"user_id": str(user_id), "admin_id": str(admin_id)})
        member = db.get(AccountMember, user_id)
        if member is None or member.status != "active":
            raise FixtureError("A conta de destino precisa ter membership ativo neste projeto")
        if db.get(AccountFixtureLoad, user_id) is not None:
            raise FixtureError("Esta fixture já foi carregada; nenhum registro foi alterado")
        for model in FINANCIAL_MODELS:
            count = db.scalar(select(func.count()).select_from(model).where(model.owner_id == user_id)) or 0
            if count:
                raise FixtureError("A carteira de destino não está vazia; nenhum registro foi alterado")

        for item in clean["operations"]:
            db.add(Operation(owner_id=user_id, ticker=item["ticker"], kind=item["kind"], date=item["date"],
                             quantity=item["quantity"], price=item["price"], fees=item["fees"]))

        contract = clean["contract"]
        investment = Investment(owner_id=user_id, issuer=contract["issuer"], product_name=contract["product_name"],
            product_type="CDB", remuneration=contract["remuneration"], indexer=contract["indexer"],
            contracted_rate=Decimal(contract["contracted_rate"]), application_date=date.fromisoformat(contract["application_date"]),
            maturity_date=date.fromisoformat(contract["maturity_date"]))
        db.add(investment)
        db.flush()
        db.add(PositionObservation(investment_id=investment.id, owner_id=user_id, kind="OPENING", reason="POSITION",
            as_of=clean["opening"]["as_of"], gross_value=clean["opening"]["gross_value"], net_value=clean["opening"]["net_value"],
            source=clean["opening"]["source"], notes=FICTITIOUS_LABEL))
        db.flush()
        observed_points = [point for point in clean["wealth"] if point["fixed_income_coverage"] == "complete"]

        def add_cdb_observation(point):
            source = (clean["cdb_observation"]["source"]
                     if point["as_of"] == clean["cdb_observation"]["as_of"]
                     else FICTITIOUS_LABEL + " — posição do cenário")
            db.add(PositionObservation(investment_id=investment.id, owner_id=user_id, kind="OBSERVATION", reason="POSITION",
                as_of=point["as_of"], gross_value=point["fixed_income_gross_value"],
                net_value=point["fixed_income_net_value"], source=source, notes=FICTITIOUS_LABEL))

        # The database tracking trigger forbids observations before a later movement;
        # persist the pre-application point first, then the movement, then later points.
        for point in observed_points:
            if point["as_of"] < clean["application"]["date"]:
                add_cdb_observation(point)
        db.flush()
        lot = Lot(investment_id=investment.id, owner_id=user_id, application_date=clean["application"]["date"])
        db.add(lot)
        db.flush()
        db.add(Movement(investment_id=investment.id, lot_id=lot.id, owner_id=user_id, kind="APPLICATION",
            date=clean["application"]["date"], principal_amount=clean["application"]["principal_amount"]))
        db.flush()
        for point in observed_points:
            if point["as_of"] >= clean["application"]["date"]:
                add_cdb_observation(point)

        for item in clean["events"]:
            db.add(FinancialEvent(owner_id=user_id, request_id=uuid4(), kind=item["kind"], event_date=item["event_date"],
                ticker=item["ticker"], cash_amount=item["cash_amount"], gross_amount=item["gross_amount"],
                tax_withheld=item["tax_withheld"], source=item["source"], description=None))
        for item in clean["wealth"]:
            db.add(PortfolioValuationObservation(owner_id=user_id, request_id=uuid4(), as_of=item["as_of"],
                equities_market_value=item["equities_market_value"], equities_source=item["equities_source"],
                fixed_income_gross_value=item["fixed_income_gross_value"], fixed_income_net_value=item["fixed_income_net_value"],
                fixed_income_coverage=item["fixed_income_coverage"],
                fixed_income_sources=([{"asset": contract["product_name"], "source": FICTITIOUS_LABEL}]
                                      if item["fixed_income_coverage"] == "complete" else []),
                missing_fixed_income=[]))
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                           separators=(",", ":")).encode("utf-8")).hexdigest()
        db.add(AccountFixtureLoad(user_id=user_id, fixture_id=clean["fixture_id"], fixture_sha256=digest,
                                  loaded_by=admin_id, loaded_at=datetime.now(timezone.utc)))
        db.flush()
        db.commit()
        return {"status": "loaded", "operations": len(clean["operations"]), "events": len(clean["events"]),
                "wealth_observations": len(clean["wealth"]), "cdb_contracts": 1}
    except Exception:
        db.rollback()
        raise


def _project_ref_from_supabase(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    match = re.fullmatch(r"([a-z0-9-]+)\.supabase\.co", host)
    if not match:
        raise FixtureError("SUPABASE_URL não identifica um projeto Supabase válido")
    return match.group(1)


def _project_ref_from_database(database_url: str) -> str:
    parsed = make_url(database_url)
    host = (parsed.host or "").lower()
    direct = re.fullmatch(r"db\.([a-z0-9-]+)\.supabase\.co", host)
    if direct:
        return direct.group(1)
    if host.endswith(".pooler.supabase.com") and parsed.username and "." in parsed.username:
        return parsed.username.rsplit(".", 1)[1].lower()
    raise FixtureError("DATABASE_URL não identifica com segurança o projeto Supabase de destino")


def verify_target_project(expected_ref: str) -> None:
    if not re.fullmatch(r"[a-z0-9-]{1,64}", expected_ref):
        raise FixtureError("Informe um project ref explícito e válido")
    supabase_ref = _project_ref_from_supabase(settings.supabase_url)
    database_ref = _project_ref_from_database(settings.database_url.get_secret_value())
    if supabase_ref != expected_ref or database_ref != expected_ref:
        raise FixtureError("SUPABASE_URL, DATABASE_URL e project ref não correspondem")


def verify_supabase_target(user_id: UUID) -> None:
    key = settings.supabase_service_role_key.get_secret_value().strip()
    if not key:
        raise FixtureError("SUPABASE_SERVICE_ROLE_KEY não está configurada no backend")
    try:
        with httpx.Client(trust_env=False, timeout=httpx.Timeout(8, connect=3)) as client:
            response = client.get(f"{settings.supabase_url}/auth/v1/admin/users/{user_id}",
                headers={"apikey": key, "Authorization": f"Bearer {key}"})
        if response.status_code != 200:
            raise FixtureError("O UUID de destino não foi encontrado no projeto Supabase confirmado")
        body = response.json()
        user = body.get("user", body) if isinstance(body, dict) else None
        if not isinstance(user, dict) or str(user.get("id", "")) != str(user_id) or not user.get("email_confirmed_at"):
            raise FixtureError("A conta de destino não é uma identidade confirmada deste projeto")
    except (httpx.HTTPError, ValueError, TypeError):
        raise FixtureError("Não foi possível validar a conta no projeto Supabase") from None


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise FixtureError("Não foi possível ler o arquivo da fixture") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", required=True, help="UUID explícito da conta de destino")
    parser.add_argument("--confirm-user-id", required=True, help="Repita o UUID da conta de destino")
    parser.add_argument("--admin-id", required=True, help="UUID do administrador autorizado")
    parser.add_argument("--confirm-admin-id", required=True, help="Repita o UUID do administrador")
    parser.add_argument("--project-ref", required=True, help="Project ref Supabase que será conferido")
    parser.add_argument("--confirm", required=True, help="Digite: LOAD FICTIONAL FIXTURE INTO <UUID>")
    args = parser.parse_args(argv)
    try:
        user_id = UUID(args.user_id)
        admin_id = UUID(args.admin_id)
        if args.confirm_user_id != str(user_id) or args.confirm_admin_id != str(admin_id):
            raise FixtureError("UUIDs de confirmação não correspondem")
        if args.confirm != f"LOAD FICTIONAL FIXTURE INTO {user_id}":
            raise FixtureError("Confirmação explícita não corresponde ao destino")
        if admin_id not in settings.invitation_admin_ids:
            raise FixtureError("Administrador não autorizado pela allowlist do backend")
        if settings.auth_mode != "supabase":
            raise FixtureError("O loader exige AUTH_MODE=supabase")
        verify_target_project(args.project_ref)
        verify_supabase_target(admin_id)
        verify_supabase_target(user_id)
        payload = _load_json(DEFAULT_FIXTURE)
        clean = validate_fixture(payload)
        with SessionLocal() as db:
            result = load_fictional_fixture(db, user_id=user_id, admin_id=admin_id, payload=payload,
                project_verified=True)
        print("Fixture fictícia carregada em uma única transação.")
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (FixtureError, ValueError, SQLAlchemyError):
        print("Loader interrompido sem confirmar alterações. Confira a conta, o projeto e a conexão.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
