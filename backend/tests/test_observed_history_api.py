from datetime import date
from app.auth import authenticate, Principal
from app.main import app
from app.fixed_income.observations import PositionObservation
from app.fixed_income.models import InvestmentArchive
from test_fixed_income import A, B, PATH, client, create

def payload(day, value):
    return {"as_of":day,"gross_value":value,"net_value":value,"source":"Extrato fictício"}

def expect_status(response, status):
    assert response.status_code == status, response.text

def test_observed_history_is_private_excludes_archives_and_filters_dates(client):
    investment=create(client, application_date="2024-12-01")
    expect_status(client.post(f"{PATH}/{investment}/opening-balance",json=payload("2025-01-01","100.00")),201)
    for day,value in [("2025-02-01","120.00"),("2025-03-01","125.00")]:
        expect_status(client.post(f"{PATH}/{investment}/observations",json=payload(day,value)),201)
    url=f"{PATH}/{investment}/observed-history?start=2025-02-01&end=2025-03-01"
    data=client.get(url)
    assert data.status_code==200 and [p["as_of"] for p in data.json()["points"]]==["2025-02-01","2025-03-01"]
    assert data.json()["coverage"]=="observed_points_only"
    app.dependency_overrides[authenticate]=lambda: Principal(B)
    assert client.get(url).status_code==404
    app.dependency_overrides[authenticate]=lambda: Principal(A)
    empty=create(client)
    result=client.get(f"{PATH}/{empty}/observed-history?start=2025-01-01&end=2025-03-01")
    assert result.status_code==200 and result.json()["coverage"]=="unavailable" and result.json()["points"]==[]
    # Tombstone represents an already archived owned contract.
    from app.database import get_db
    session=next(app.dependency_overrides[get_db]())
    session.add(InvestmentArchive(investment_id=empty,owner_id=A));session.commit();session.close()
    assert client.get(f"{PATH}/{empty}/observed-history?start=2025-01-01&end=2025-03-01").status_code==404
    assert client.get(f"{PATH}/{investment}/observed-history?start=2025-03-01&end=2025-01-01").status_code==422
