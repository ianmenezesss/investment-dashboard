from datetime import date, datetime, timezone
from contextlib import asynccontextmanager
import httpx
from decimal import Decimal
from typing import Literal
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import exists, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from .database import ensure_production_role, get_db, settings
from .finance import summarize
from .models import Operation
from .auth import authenticate
from .access import private_db
from .market_data.brapi import BrapiProvider
from .market_data.equity_history import BrapiEquityHistoryProvider, EquityHistoryService
from .market_data.service import QuoteService
from .valuation import PortfolioValuation, value_portfolio
from .price_basis import purchase_price_basis
from .fixed_income.router import router as fixed_income_router
from .fixed_income.revisions import router as revision_router
from .bcb_rates.provider import SGSProvider
from .bcb_rates.service import RateService
from .bcb_rates.router import router as bcb_rates_router
from .fixed_income.returns_router import router as fixed_income_returns_router
from .fixed_income.observation_routes import router as observation_router
from .fixed_income.history import router as observed_history_router
from .portfolio import router as portfolio_router
from .portfolio import aggregate_capital_flows, aggregate_composition, local_today
from .performance import FinancialPerformance, build_financial_performance
from .equity_history import router as equity_history_router
from .individual_equity_history import EquityPriceHistoryService, router as individual_equity_history_router
from .equity_comparison import router as equity_comparison_router
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler


@asynccontextmanager
async def lifespan(app):
    # Constructing the client makes no external request. No polling or startup fetch.
    async with httpx.AsyncClient(trust_env=False, limits=httpx.Limits(max_connections=1)) as market_client, \
            httpx.AsyncClient(trust_env=False, limits=httpx.Limits(max_connections=1)) as history_client, \
            httpx.AsyncClient(trust_env=False, limits=httpx.Limits(max_connections=1)) as rates_client:
        token = settings.brapi_token.get_secret_value().strip()
        app.state.quote_service = QuoteService(BrapiProvider(market_client, token),
            enabled=settings.market_data_enabled, configured=bool(token))
        app.state.equity_history_service = EquityHistoryService(
            BrapiEquityHistoryProvider(history_client, token),
            enabled=settings.market_data_enabled and settings.equity_history_enabled, configured=bool(token))
        # Nenhum provedor individual é configurado sem validação de dados/licença.
        app.state.individual_equity_price_history_service = EquityPriceHistoryService(
            provider=None, enabled=settings.individual_equity_history_enabled)
        app.state.bcb_rates_service = RateService(SGSProvider(rates_client))
        try:
            yield
        finally:
            app.state.quote_service = None
            app.state.equity_history_service = None
            app.state.individual_equity_price_history_service = None
            app.state.bcb_rates_service = None


app = FastAPI(title="Investment Dashboard", version="0.1.5", lifespan=lifespan, docs_url=None if settings.environment == "production" else "/docs", redoc_url=None, openapi_url=None if settings.environment == "production" else "/openapi.json")
app.include_router(fixed_income_router)
app.include_router(revision_router)
app.include_router(bcb_rates_router)
app.include_router(fixed_income_returns_router)
app.include_router(observation_router)
app.include_router(observed_history_router)
app.include_router(portfolio_router)
app.include_router(equity_history_router)
app.include_router(individual_equity_history_router)
app.include_router(equity_comparison_router)


@app.exception_handler(RequestValidationError)
async def safe_observation_validation(request, exc):
    if request.url.path.endswith(("/opening-balance", "/observations")):
        return JSONResponse(status_code=422, content={"detail": [{"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]} for error in exc.errors()]})
    return await request_validation_exception_handler(request, exc)
app.add_middleware(CORSMiddleware, allow_origins=[settings.cors_origin], allow_methods=["GET", "POST", "DELETE"], allow_headers=["Authorization", "Content-Type", "Idempotency-Key"])
@app.middleware("http")
async def privacy_headers(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    if settings.environment == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    return response


@app.exception_handler(SQLAlchemyError)
async def database_error(request, exc):
    # Não devolver SQL, parâmetros, credenciais ou stack traces ao cliente.
    return JSONResponse(status_code=503, content={"detail": "Banco de dados temporariamente indisponível"})


@app.exception_handler(Exception)
async def unexpected_error(request, exc):
    return JSONResponse(status_code=500, content={"detail": "Erro interno ao processar a solicitação"}, headers={"Cache-Control": "no-store"})


class OperationInput(BaseModel):
    ticker: str = Field(pattern=r"^[A-Z0-9]{4,20}$")
    kind: Literal["BUY", "SELL"]
    date: date
    quantity: Decimal = Field(gt=0, max_digits=20, decimal_places=8)
    price: Decimal = Field(gt=0, max_digits=20, decimal_places=8)
    fees: Decimal = Field(default=Decimal(0), ge=0, max_digits=20, decimal_places=8)

    @field_validator("date")
    @classmethod
    def historical(cls, value):
        if value > date.today():
            raise ValueError("A operação não pode ter data futura")
        return value


def records(db):
    return list(db.scalars(select(Operation).where(Operation.owner_id == db.info.get("owner_id")).order_by(Operation.date, Operation.id)))


def held_tickers(db: Session = Depends(private_db)):
    tickers = [h["ticker"] for h in summarize(records(db))["holdings"]]
    # Read-only snapshot: return the pooled connection before waiting on external HTTP.
    db.rollback()
    return tickers


def quote_service(request: Request):
    service = getattr(request.app.state, "quote_service", None)
    if service is None:
        raise HTTPException(503, "Serviço de cotações não inicializado")
    return service


@app.get("/api/quotes")
async def quotes(tickers: list[str] = Depends(held_tickers), service: QuoteService = Depends(quote_service)):
    return {"quotes": await service.get_many(tickers)}


def portfolio_snapshot(db: Session = Depends(private_db)):
    operations = records(db)
    summary = summarize(operations)
    basis = purchase_price_basis(operations)
    captured_at = datetime.now(timezone.utc)
    db.rollback()  # Release the read transaction before external HTTP; no ledger writes.
    return summary, captured_at, basis


@app.get("/api/dashboard/valuation", response_model=PortfolioValuation)
async def portfolio_valuation(snapshot=Depends(portfolio_snapshot), service: QuoteService = Depends(quote_service)):
    summary, captured_at, basis = snapshot
    quotes = await service.get_many([h["ticker"] for h in summary["holdings"]])
    return value_portfolio(summary, quotes, ledger_as_of=captured_at, price_basis=basis)


@app.get("/api/dashboard/performance", response_model=FinancialPerformance, dependencies=[Depends(authenticate)])
async def dashboard_performance(db: Session = Depends(private_db), service: QuoteService = Depends(quote_service)):
    """Private current snapshot that composes existing ledger and valuation rules."""
    from .fixed_income.models import Investment, InvestmentArchive, Lot
    from .fixed_income.observations import PositionObservation
    from .fixed_income.projection import effective_movements

    today, owner = local_today(), db.info.get("owner_id")
    operations = list(db.scalars(select(Operation).where(
        Operation.owner_id == owner, Operation.date <= today
    ).order_by(Operation.date, Operation.id)))
    projected = effective_movements(db)
    movements = list(db.execute(select(projected).where(
        projected.c.owner_id == owner, projected.c.date <= today
    ).order_by(projected.c.date, projected.c.id)).mappings())
    investments = list(db.scalars(select(Investment).where(
        Investment.owner_id == owner,
        ~exists(select(InvestmentArchive.id).where(InvestmentArchive.investment_id == Investment.id)),
    )))
    lots = list(db.scalars(select(Lot).where(Lot.owner_id == owner)))
    observations = list(db.scalars(select(PositionObservation).where(
        PositionObservation.owner_id == owner, PositionObservation.as_of <= today
    )))

    summary = summarize(operations)
    basis = purchase_price_basis(operations)
    ledger_as_of = datetime.now(timezone.utc)
    flows = aggregate_capital_flows(operations, movements, start=date.min, end=today)
    composition = aggregate_composition(operations, movements, investments, lots, observations, as_of=today)
    tickers = [holding["ticker"] for holding in summary["holdings"]]
    db.rollback()  # Keep the DB snapshot consistent and release it before quote HTTP.

    quotes = await service.get_many(tickers)
    valuation = value_portfolio(summary, quotes, ledger_as_of=ledger_as_of, price_basis=basis)
    return build_financial_performance(as_of=today, ledger_as_of=ledger_as_of,
        flows=flows, valuation=valuation, composition=composition)


def serialize(op):
    return {key: str(getattr(op, key)) if isinstance(getattr(op, key), Decimal) else getattr(op, key) for key in ("id", "ticker", "kind", "date", "quantity", "price", "fees")}


@app.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    ensure_production_role(db)
    return {"status": "ok"}


@app.get("/api/dashboard", dependencies=[Depends(authenticate)])
def dashboard(db: Session = Depends(private_db)):
    def decimal_strings(value):
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, dict):
            return {key: decimal_strings(item) for key, item in value.items()}
        if isinstance(value, list):
            return [decimal_strings(item) for item in value]
        return value
    return decimal_strings(summarize(records(db)))


@app.get("/api/operations", dependencies=[Depends(authenticate)])
def operations(db: Session = Depends(private_db)):
    return [serialize(op) for op in records(db)]


@app.post("/api/operations", status_code=201, dependencies=[Depends(authenticate)])
def create(data: OperationInput, db: Session = Depends(private_db)):
    # Serializa mutações inclusive quando a tabela ainda está vazia.
    db.execute(text("LOCK TABLE operations IN EXCLUSIVE MODE"))
    op = Operation(**data.model_dump(), owner_id=db.info.get("owner_id"))
    db.add(op)
    db.flush()
    try:
        summarize(records(db))
    except ValueError as error:
        db.rollback()
        raise HTTPException(422, str(error))
    payload = serialize(op)
    db.commit()
    return payload


@app.delete("/api/operations/{operation_id}", status_code=204, dependencies=[Depends(authenticate)])
def delete(operation_id: int, db: Session = Depends(private_db)):
    db.execute(text("LOCK TABLE operations IN EXCLUSIVE MODE"))
    op = db.scalar(select(Operation).where(Operation.id == operation_id, Operation.owner_id == db.info.get("owner_id")))
    if not op:
        raise HTTPException(404, "Operação não encontrada")
    db.delete(op)
    db.flush()
    try:
        summarize(records(db))
    except ValueError as error:
        db.rollback()
        raise HTTPException(422, str(error))
    db.commit()


@app.get("/api/export", dependencies=[Depends(authenticate)])
def export(db: Session = Depends(private_db)):
    return {"schema_version": 1, "operations": [serialize(op) for op in records(db)]}
