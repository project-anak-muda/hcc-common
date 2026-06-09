# hcc-common

Shared Python library for the **HCC detection platform**. One installable source
of truth that every service repo (`hcc-detector`, `hcc-reviewer`, `hcc-trainer`,
`hcc-janitor`) depends on — so config, the DB schema, storage layout, and the
Redis contracts are defined **once**.

> Folder is `hcc-common` (dashes aren't legal in import names); the importable
> package is **`hcc_common`** (underscore).

## Modules

| Import | Purpose |
|---|---|
| `hcc_common.config` | pydantic-settings — all env-driven settings (`get_settings()`). |
| `hcc_common.db` | SQLAlchemy 2.0 models + `session_scope()`; the Timescale schema lives here. |
| `hcc_common.storage` | S3/MinIO client (`get_object_store()`): buckets, hourly raw-frame keys, lifecycle. |
| `hcc_common.bus` | Redis (`get_bus()`): work queues, cooldown locks, camera-lease sharding. |
| `hcc_common.schemas` | pydantic DTOs that cross service boundaries (queue payloads). |

```python
from hcc_common.config import get_settings
from hcc_common.db import Base, session_scope, Detection
from hcc_common.storage import get_object_store
from hcc_common.bus import get_bus
```

## Versioning

This package is the **contract** between services, so it is **semver-tagged**.
A breaking change (renamed column, changed queue payload, new required setting)
is a **minor/major bump**, and services pin a version. The DB schema is owned
here too — migrations live in the `migrations/` repo and import these models.

## How service repos consume it

Each service is its **own git repo** and pulls `hcc-common` as a dependency.

**Production / CI — pin a tagged version (git URL dependency):**
```
# in a service's requirements.txt
hcc-common @ git+https://github.com/<org>/hcc-common.git@v0.1.0
```
```dockerfile
# in a service Dockerfile (build context = the service repo)
RUN pip install --no-cache-dir -r requirements.txt   # pulls hcc-common from git
```

**Local dev — editable, live edits:** check `hcc-common` out next to the service
repos and install it editable so changes apply with no rebuild:
```bash
pip install -e ../hcc-common
```
The dev `docker-compose` bind-mounts `../hcc-common` into each container for the
same effect.

## Develop / test this library

```bash
pip install -e .            # editable install into the current venv
python -c "import hcc_common; from hcc_common.db import Base; print(sorted(Base.metadata.tables))"
```

## Release checklist

1. Update models/settings/schemas; if the DB changed, add an Alembic migration.
2. Bump `version` in `pyproject.toml` (semver).
3. Tag: `git tag v0.x.y && git push --tags`.
4. Bump the pin in each service repo that needs the change.
