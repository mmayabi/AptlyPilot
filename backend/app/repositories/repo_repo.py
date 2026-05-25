from sqlmodel import Session, select

from app.models.repo import Repo


def list_repos(session: Session) -> list[Repo]:
    statement = select(Repo).order_by(Repo.provider, Repo.release, Repo.name)
    return list(session.exec(statement).all())


def list_repos_by_provider(session: Session, provider: str) -> list[Repo]:
    statement = (
        select(Repo)
        .where(Repo.provider == provider)
        .order_by(Repo.release, Repo.name)
    )
    return list(session.exec(statement).all())


def list_repos_by_provider_release(session: Session, provider: str, release: str) -> list[Repo]:
    statement = (
        select(Repo)
        .where(Repo.provider == provider, Repo.release == release)
        .order_by(Repo.name)
    )
    return list(session.exec(statement).all())


def get_repo_by_name(session: Session, repo_name: str) -> Repo | None:
    statement = select(Repo).where(Repo.name == repo_name)
    return session.exec(statement).first()


def create_repo(session: Session, repo: Repo) -> Repo:
    session.add(repo)
    session.commit()
    session.refresh(repo)
    return repo


def save_repo(session: Session, repo: Repo) -> Repo:
    session.add(repo)
    session.commit()
    session.refresh(repo)
    return repo