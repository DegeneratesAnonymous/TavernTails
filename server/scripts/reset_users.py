"""Reset users DB for development: remove all users and create one test account.

Usage: python -m server.scripts.reset_users
"""
from sqlmodel import Session, select
from server import db


def reset_users():
    db.create_db_and_tables()
    with Session(db.engine) as session:
        users = session.exec(select(db.User)).all()
        for u in users:
            session.delete(u)
        session.commit()

        # Create a single test user
        email = 'test@example.com'
        password = 'secret'
        username = 'TestUser'
        profile = {'name': username, 'email': email, 'preferences': {}}
        user = db.create_user(email=email, password=password, username=username, profile=profile)

        # Mark verified
        stmt = select(db.User).where(db.User.id == user.id)
        dbu = session.exec(stmt).first()
        dbu.verified = True
        dbu.verification_token = None
        session.add(dbu)
        session.commit()

    print(f"Reset complete. Test user: {email} / {password}")


if __name__ == '__main__':
    reset_users()
