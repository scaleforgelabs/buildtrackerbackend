import os
import django
import sys

# Setup Django
sys.path.append('c:\\Users\\USER\\OneDrive\\Desktop\\coding\\buildtracker_project\\buildtracker_backend\\buildtracker__backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'buildtracker__backend.settings')
django.setup()

from tasks.models import TaskComment  # noqa: E402
from tasks.tasks import send_task_comment_notification  # noqa: E402

comment = TaskComment.objects.last()
if not comment:
    print("No comments found in DB.")
    sys.exit(0)

task = comment.task
print(f"Testing comment notification for Task: {task.id}, Comment: {comment.id}")

result = send_task_comment_notification(task.id, comment.id)
print(f"Celery task result: {result}")
