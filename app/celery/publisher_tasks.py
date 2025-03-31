from app.celery.shared_tasks import notify_external_service, send_screenshot_request
from app.database.postgres import get_postgres
from loguru import logger
from app.database.postgres.crud import update_publication_status
from shared.celery_app import celery_app
import httpx

async def send_to_publisher(result_data: dict, priority: int = 1, callback_url: str = None) -> str:
    """
    Відправляє результати парсингу на публікацію
    
    Args:
        result_data: Дані для публікації (результати парсингу)
        priority: Пріоритет завдання (1-10)
        callback_url: URL для колбеку після публікації
        
    Returns:
        ID завдання Celery
    """
    try:
        task = celery_app.send_task(
            "publisher.publish_result",
            args=[result_data],
            kwargs={"callback_url": callback_url},
            queue="publishing_queue",
            priority=priority
        )
        logger.info(f"Sent data to publisher (task_id: {task.id})")
        return task.id
    except Exception as e:
        logger.error(f"Failed to send to publisher: {e}")
        raise


async def handle_publisher_callback(task_id: str, result: dict):
    """
    Обробляє результати публікації
    
    Args:
        task_id: ID завершеної задачі
        result: Результати публікації
    """
    try:
        logger.info(f"Handling publisher callback for task {task_id}")
        
        # 1. Оновлюємо запис в БД
        await update_publication_status(
            result_id=result['result_id'],
            published_url=result['published_url']
        )
        
        # 2. Якщо потрібен скріншот
        if result.get('need_screenshot'):
            screenshot_task_id = await send_screenshot_request(
                url=result['published_url'],
                result_id=result['result_id']
            )
            logger.info(f"Screenshot task started: {screenshot_task_id}")
        
        # 3. Колбек зовнішньому сервісу
        if result.get('callback_url'):
            await notify_external_service(
                url=result['callback_url'],
                data={
                    "status": "published",
                    "task_id": task_id,
                    "published_url": result['published_url']
                }
            )
            
    except Exception as e:
        logger.error(f"Failed to handle publisher callback: {e}")
        raise