# ABOUTME: SQLAlchemy declarative base class for ORM models
# ABOUTME: Provides the foundation for all database models in the application

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models.

    This class serves as the foundation for all database models,
    providing common functionality and ensuring consistent table
    naming and behavior across the application.
    """

    pass


# NOTE: Model imports have been moved to avoid circular dependencies.
# Models are registered when they are imported in other modules.
