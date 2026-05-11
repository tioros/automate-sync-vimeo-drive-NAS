"""
Script to create initial Admin and Auditor users.
Run: python -m scripts.create_users
"""

from app.database import get_sync_db
from app.models.user import User, UserRole
from app.auth import hash_password


def create_initial_users():
    db = get_sync_db()
    try:
        # Check if users already exist
        existing = db.query(User).count()
        if existing > 0:
            print(f"⚠️  {existing} usuário(s) já existem. Pulando criação.")
            return

        # Create Admin
        admin = User(
            email="admin@drivevimeo.local",
            password_hash=hash_password("admin123"),
            role=UserRole.admin,
        )
        db.add(admin)

        # Create Auditor
        auditor = User(
            email="auditor@drivevimeo.local",
            password_hash=hash_password("auditor123"),
            role=UserRole.auditor,
        )
        db.add(auditor)

        db.commit()
        print("✅ Usuários criados com sucesso:")
        print("   Admin:   admin@drivevimeo.local / admin123")
        print("   Auditor: auditor@drivevimeo.local / auditor123")
        print("⚠️  Altere as senhas em produção!")

    except Exception as e:
        db.rollback()
        print(f"❌ Erro ao criar usuários: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    create_initial_users()
