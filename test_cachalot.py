import os
import django
import asyncio
from asgiref.sync import sync_to_async

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'buildtracker__backend.settings')
django.setup()

from wiki.models import WikiDocument  # noqa: E402
from workspaces.models import Workspace  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402

User = get_user_model()

async def test_cachalot():
    @sync_to_async
    def _read():
        workspace = Workspace.objects.first()
        # This will be cached by cachalot
        docs = list(WikiDocument.objects.filter(workspace=workspace))
        return len(docs), workspace

    @sync_to_async
    def _write(workspace):
        user = User.objects.first()
        return WikiDocument.objects.create(
            workspace=workspace,
            document_title="Test Cachalot Async 1",
            author=user,
            visibility="private"
        )
        
    print("Reading initial docs...")
    count1, workspace = await _read()
    print(f"Initial count: {count1}")
    
    print("Writing new doc in async...")
    doc = await _write(workspace)
    print(f"Created doc id: {doc.id}")
    
    print("Reading docs again...")
    count2, _ = await _read()
    print(f"Count after create: {count2}")
    
    if count1 == count2:
        print("FAIL: Cachalot did not invalidate the cache!")
    else:
        print("SUCCESS: Cachalot invalidated correctly.")
        
if __name__ == '__main__':
    asyncio.run(test_cachalot())
    
