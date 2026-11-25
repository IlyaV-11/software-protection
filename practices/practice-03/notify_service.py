"""Notification Service из методички: имитация отправки, без реальной почты."""
from datetime import datetime, timezone
import logging

from fastapi import FastAPI
from pydantic import BaseModel, EmailStr

app_notify = FastAPI(title="Notification Service")
logger = logging.getLogger("uvicorn.error")
notifications: list[dict] = []


class Notification(BaseModel):
    user_id: int
    email: EmailStr
    message: str


@app_notify.post("/notify/")
async def send_notification(notification: Notification):
    data = notification.model_dump()
    notifications.append({**data, "received_at": datetime.now(timezone.utc).isoformat()})
    logger.info("Sending notification to %s: %s", notification.email, notification.message)
    return {"status": "sent", "notification": data}


@app_notify.get("/notifications/")
async def get_notifications():
    """Просмотр полученных уведомлений для проверки HTTP-интеграции."""
    return notifications


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app_notify, host="127.0.0.1", port=8011)
