from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "fantasy_assistant",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.tasks.content_tasks",
        "app.tasks.data_tasks"
    ]
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_routes={
        'app.tasks.content_tasks.*': {'queue': 'content'},
        'app.tasks.data_tasks.*': {'queue': 'data'},
    }
)