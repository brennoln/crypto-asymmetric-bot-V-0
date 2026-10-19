import pytest

from data.database import db_manager


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Redireciona o singleton ``db_manager`` para um banco temporário isolado.

    O ``db_manager`` é importado por nome em ``src.execution.paper_client``, então
    alterar o atributo da instância redireciona todas as gravações dos testes.
    """
    db_path = tmp_path / "trading_history_test.db"
    monkeypatch.setattr(db_manager, "db_path", str(db_path))
    return db_path
