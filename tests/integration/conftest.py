import pytest

# Neutralise le fixture autouse du conftest parent qui initialise Peewee.
# Les tests d'intégration tapent directement sur l'app via HTTP — pas besoin de BD locale.
@pytest.fixture(autouse=True)
def setup_test_db():
    yield
