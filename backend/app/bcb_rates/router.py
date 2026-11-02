from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Path, Request
from pydantic import ValidationError
from ..auth import authenticate
from .schemas import Period, RateHistory, RateError
from .service import RateService

router = APIRouter(prefix="/api/fixed-income/rates", tags=["bcb-rates"], dependencies=[Depends(authenticate)])


def rates_service(request: Request):
    service = getattr(request.app.state, "bcb_rates_service", None)
    if service is None:
        raise HTTPException(503, detail={"code": "rates_service_unavailable"})
    return service


@router.get("/{series_code}", response_model=RateHistory)
async def historical_rates(start_date: date, end_date: date, series_code: int = Path(ge=11, le=12),
                           service: RateService = Depends(rates_service)):
    try:
        period = Period(start_date=start_date, end_date=end_date)
    except ValidationError:
        raise HTTPException(422, detail={"code": "invalid_period", "message": "Use datas não futuras, em ordem, com até 366 dias inclusivos."}) from None
    try:
        return await service.get(series_code, period)
    except RateError as error:
        raise HTTPException(error.status, detail={"code": error.code}, headers={"Retry-After": str(error.retry_after)}) from None
