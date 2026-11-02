"""Admin-only recovery for a self-deletion whose financial purge already committed."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
from uuid import UUID
from fastapi import HTTPException

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.accounts import _delete_supabase_identity, _run_deletion_function
from app.auth import Principal
from app.database import SessionLocal, settings
try:
    from .load_demo_fixture import FixtureError, verify_supabase_target, verify_target_project
except ImportError:
    from load_demo_fixture import FixtureError, verify_supabase_target, verify_target_project


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", required=True, help="UUID da exclusão iniciada pelo próprio usuário")
    parser.add_argument("--confirm-user-id", required=True, help="Repita o UUID da exclusão em andamento")
    parser.add_argument("--admin-id", required=True, help="UUID administrativo permitido")
    parser.add_argument("--confirm-admin-id", required=True, help="Repita o UUID administrativo")
    parser.add_argument("--project-ref", required=True, help="Project ref Supabase para conferência")
    parser.add_argument("--confirm", required=True, help="Digite: RESUME ACCOUNT DELETION <UUID>")
    args = parser.parse_args(argv)
    try:
        user_id, admin_id = UUID(args.user_id), UUID(args.admin_id)
        if args.confirm_user_id != str(user_id) or args.confirm_admin_id != str(admin_id):
            raise FixtureError("UUIDs de confirmação não correspondem")
        if args.confirm != f"RESUME ACCOUNT DELETION {user_id}":
            raise FixtureError("Confirmação explícita não corresponde à exclusão pendente")
        if settings.auth_mode != "supabase" or admin_id not in settings.invitation_admin_ids:
            raise FixtureError("Administrador Supabase não autorizado")
        if not settings.supabase_service_role_key.get_secret_value().strip():
            raise FixtureError("Chave administrativa Supabase não configurada")
        verify_target_project(args.project_ref)
        verify_supabase_target(admin_id)

        principal = Principal(user_id)
        with SessionLocal() as db:
            state = _run_deletion_function(db, "dashboard_account_deletion_state", principal)
            if state not in ("financial_data_deleted", "auth_identity_deleted"):
                raise FixtureError("Só é permitido retomar após a exclusão financeira já confirmada")
            if state == "financial_data_deleted":
                _delete_supabase_identity(user_id)
                state = _run_deletion_function(db, "mark_dashboard_auth_identity_deleted", principal)
            if state != "auth_identity_deleted" or not _run_deletion_function(
                    db, "finish_dashboard_account_deletion", principal):
                raise FixtureError("A solicitação continua pendente; nenhum outro usuário foi alterado")
        print("Solicitação de exclusão pendente finalizada com segurança.")
        return 0
    except (FixtureError, ValueError, HTTPException):
        print("Retomada interrompida sem iniciar outra exclusão. Confira a solicitação, o projeto e as permissões.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
