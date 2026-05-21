import argparse

from sqlmodel import Session

from app.db.init_db import init_db
from app.db.session import engine
from app.services.auth_service import create_initial_admin


def main() -> None:
    parser = argparse.ArgumentParser(description="Create initial AptlyPilot admin user")

    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--email", required=False, default=None)
    parser.add_argument("--full-name", required=False, default=None)

    args = parser.parse_args()

    init_db()

    with Session(engine) as session:
        user = create_initial_admin(
            session=session,
            username=args.username,
            password=args.password,
            email=args.email,
            full_name=args.full_name,
        )

    print(f"Admin user is ready: username={user.username}, id={user.id}")


if __name__ == "__main__":
    main()