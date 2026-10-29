from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth import Principal, authenticate
from app.database import Base, get_db
from app.fixed_income.models import ApplicationRevision, Investment, Lot, Movement
from app.main import app
from app.models import Operation

A = UUID('11111111-1111-4111-8111-111111111111')
B = UUID('22222222-2222-4222-8222-222222222222')


def test_unified_movement_history_effective_order_and_owner_isolation():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        inv_a = Investment(owner_id=A, issuer='Banco A', product_name='CDB A', product_type='CDB', remuneration='FIXED', indexer='NONE', contracted_rate=Decimal('12'), application_date=date(2025, 1, 1), maturity_date=date(2026, 1, 1))
        inv_b = Investment(owner_id=B, issuer='Banco B', product_name='CDB B', product_type='CDB', remuneration='FIXED', indexer='NONE', contracted_rate=Decimal('12'), application_date=date(2025, 1, 1), maturity_date=date(2026, 1, 1))
        db.add_all([inv_a, inv_b]); db.flush()
        lots = [Lot(investment_id=inv_a.id, owner_id=A, application_date=date(2025,1,1)), Lot(investment_id=inv_a.id, owner_id=A, application_date=date(2025,1,2)), Lot(investment_id=inv_a.id, owner_id=A, application_date=date(2025,1,3)), Lot(investment_id=inv_b.id, owner_id=B, application_date=date(2025,1,1))]
        db.add_all(lots); db.flush()
        app_row = Movement(investment_id=inv_a.id, lot_id=lots[0].id, owner_id=A, kind='APPLICATION', date=date(2025,1,1), principal_amount=Decimal('100.12345678'))
        void_row = Movement(investment_id=inv_a.id, lot_id=lots[1].id, owner_id=A, kind='APPLICATION', date=date(2025,1,2), principal_amount=Decimal('50'))
        redeem = Movement(investment_id=inv_a.id, lot_id=lots[2].id, owner_id=A, kind='REDEMPTION', date=date(2025,1,4), principal_amount=Decimal('20'), cash_received=Decimal('20.75'))
        db.add_all([app_row, void_row, redeem, Movement(investment_id=inv_b.id, lot_id=lots[3].id, owner_id=B, kind='APPLICATION', date=date(2025,1,1), principal_amount=Decimal('999'))])
        db.flush()
        db.add_all([ApplicationRevision(application_id=app_row.id, owner_id=A, revision=1, kind='REPLACE', replacement_date=date(2025,1,3), replacement_amount=Decimal('125.25'), reason='Correção', request_id=uuid4()), ApplicationRevision(application_id=void_row.id, owner_id=A, revision=1, kind='VOID', reason='Anulada', request_id=uuid4())])
        db.add_all([Operation(owner_id=A, ticker='ITUB4', kind='BUY', date=date(2025,1,2), quantity=Decimal('2'), price=Decimal('10.25'), fees=Decimal('0.50')), Operation(owner_id=A, ticker='VALE3', kind='BUY', date=date(2025,1,3), quantity=Decimal('1'), price=Decimal('30'), fees=Decimal('0')), Operation(owner_id=A, ticker='ITUB4', kind='SELL', date=date(2025,1,5), quantity=Decimal('1'), price=Decimal('12'), fees=Decimal('0.25')), Operation(owner_id=B, ticker='PETR4', kind='BUY', date=date(2025,1,1), quantity=Decimal('9'), price=Decimal('9'), fees=Decimal('0'))])
        db.commit()

    def db_session():
        with Session(engine) as db:
            yield db
    app.dependency_overrides[get_db] = db_session
    app.dependency_overrides[authenticate] = lambda: Principal(A)
    try:
        with TestClient(app) as client:
            response = client.get('/api/dashboard/movements?owner_id=' + str(B))
            assert response.status_code == 200
            data = response.json()
            assert [row['id'].split(':', 1)[0] for row in data] == ['equity', 'cdb', 'equity', 'cdb', 'equity']
            assert [(row['date'], row['asset'], row['operation']) for row in data] == [('2025-01-02', 'ITUB4', 'BUY'), ('2025-01-03', 'CDB A', 'APPLICATION'), ('2025-01-03', 'VALE3', 'BUY'), ('2025-01-04', 'CDB A', 'REDEMPTION'), ('2025-01-05', 'ITUB4', 'SELL')]
            application = data[1]
            assert Decimal(application['financial_value']) == Decimal('125.25') and application['quantity'] is None and application['fees'] is None
            assert Decimal(data[3]['financial_value']) == Decimal('20') and Decimal(data[3]['cash_received']) == Decimal('20.75')
            assert Decimal(data[0]['financial_value']) == Decimal('20.50') and Decimal(data[0]['fees']) == Decimal('0.50')
            assert all('CDB B' != row['asset'] and 'PETR4' != row['asset'] for row in data)
            assert [row['id'] for row in client.get('/api/dashboard/movements').json()] == [row['id'] for row in data]
            app.dependency_overrides[authenticate] = lambda: Principal(B)
            other = client.get('/api/dashboard/movements').json()
            assert {(row['investment_class'], row['asset']) for row in other} == {('AÇÕES', 'PETR4'), ('CDB', 'CDB B')}
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
