from django.contrib import admin

from .models import Task, TaskAttachment, TaskComment

admin.site.register(Task)
admin.site.register(TaskAttachment)
admin.site.register(TaskComment)