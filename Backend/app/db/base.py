from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for future ORM models."""


# Import model modules here once they exist, for Alembic autogeneration.
