from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from .observations import ObservationOutput


def financial_today():
    return datetime.now(ZoneInfo("America/Sao_Paulo")).date()


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class InvestmentInput(Input):
    issuer: str = Field(min_length=1, max_length=160)
    product_name: str = Field(min_length=1, max_length=160)
    product_type: Literal["CDB"] = "CDB"
    remuneration: Literal["FIXED", "CDI"]
    indexer: Literal["NONE", "CDI"]
    contracted_rate: Decimal = Field(gt=0, lt=10000, max_digits=12, decimal_places=8)
    application_date: date
    maturity_date: date

    @model_validator(mode="after")
    def contract(self):
        if (self.remuneration, self.indexer) not in (("FIXED", "NONE"), ("CDI", "CDI")):
            raise ValueError("Modalidade e indexador incompatíveis")
        if self.application_date > financial_today() or self.maturity_date <= self.application_date:
            raise ValueError("Datas do contrato inválidas")
        return self


class ApplicationInput(Input):
    date: date
    principal_amount: Decimal = Field(gt=0, max_digits=20, decimal_places=8)

    @field_validator("date")
    @classmethod
    def historical(cls, value):
        if value > financial_today():
            raise ValueError("Movimentação não pode ter data futura")
        return value


class RedemptionInput(ApplicationInput):
    lot_id: int = Field(gt=0)
    cash_received: Decimal | None = Field(default=None, ge=0, max_digits=20, decimal_places=8)


class Output(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class InvestmentOutput(Output):
    id: int
    issuer: str
    product_name: str
    product_type: str
    remuneration: str
    indexer: str
    contracted_rate: Decimal
    application_date: date
    maturity_date: date
    created_at: datetime
    tracking_mode: Literal["LEDGER", "CONSOLIDATED"] = "LEDGER"
    latest_observation: ObservationOutput | None = None


class MovementOutput(Output):
    id: int
    investment_id: int
    lot_id: int
    kind: str
    date: date
    principal_amount: Decimal
    cash_received: Decimal | None
    created_at: datetime


class LotOutput(Output):
    id: int
    application_date: date
    principal_balance: Decimal


class InvestmentDetail(InvestmentOutput):
    principal_balance: Decimal
    lots: list[LotOutput]
    opening_balance: ObservationOutput | None = None
