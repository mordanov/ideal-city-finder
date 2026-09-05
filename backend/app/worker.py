from arq.connections import RedisSettings

from app.config import settings
from app.services.search_orchestrator import run_search


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    functions = [run_search]
    max_jobs = 10
