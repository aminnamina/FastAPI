# Celery tasks
from .main import celery_app

@celery_app.task
def send_email_task(email: str):
    import time
    time.sleep(5)
    print(f"Email sent to {email}")
    return f"Email sent to {email}"
