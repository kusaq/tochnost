from infra.timescale_db.models import Error
from infra.timescale_db.storage.base_storage import PostgresStorage


class ErrorStorage(PostgresStorage[Error]):
    model_cls = Error
