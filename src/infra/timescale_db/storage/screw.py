from infra.timescale_db.models import Screw
from infra.timescale_db.storage.base_storage import PostgresStorage


class ScrewStorage(PostgresStorage[Screw]):
    model_cls = Screw
