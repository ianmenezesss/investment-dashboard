from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo
from pydantic import BaseModel, ConfigDict, Field, model_validator

SERIES = {11: "SELIC", 12: "CDI"}


def today():
    return datetime.now(ZoneInfo("America/Sao_Paulo")).date()


class Period(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def valid_period(self):
        if self.start_date > self.end_date or self.end_date > today():
            raise ValueError("Datas invertidas ou futuras")
        if (self.end_date - self.start_date).days >= 366:
            raise ValueError("Intervalo máximo de 366 dias, incluindo as duas datas")
        return self


class Observation(BaseModel):
    model_config = ConfigDict(frozen=True)
    date: date
    value: Decimal = Field(max_digits=20, decimal_places=12, allow_inf_nan=False)
    series_code: Literal[11, 12]
    unit: Literal["% ao dia"] = "% ao dia"


class RateHistory(BaseModel):
    model_config = ConfigDict(frozen=True)
    series_code: Literal[11, 12]
    name: Literal["CDI", "SELIC"]
    unit: Literal["% ao dia"] = "% ao dia"
    source: Literal["BCB/SGS"] = "BCB/SGS"
    start_date: date
    end_date: date
    status: Literal["ok", "empty"]
    observations: tuple[Observation, ...]
    duplicates_removed: int
    last_observation_date: date | None
    fetched_at: datetime
    expires_at: datetime
    from_cache: bool = False


class RateError(Exception):
    def __init__(self, code: str, status: int = 503, retry_after: int = 30):
        self.code, self.status, self.retry_after = code, status, retry_after
        super().__init__(code)
