from storages.backends.s3boto3 import S3Boto3Storage
import os
import uuid

class UniqueS3Boto3Storage(S3Boto3Storage):
    """
    A custom S3 storage backend that generates naturally unique filenames using UUIDs 
    to completely bypass the internal `.exists()` (HeadObject) permission check.
    This resolves the 403 Forbidden S3 errors when uploading files where the IAM 
    user does not have ListBucket/GetObject properties on the entire bucket.
    """
    def get_available_name(self, name, max_length=None):
        # Split the path and the filename
        dir_name, file_name = os.path.split(name)
        file_root, file_ext = os.path.splitext(file_name)
        
        # Inject an 8-character UUID into the filename to guarantee uniqueness
        unique_name = f"{file_root}_{uuid.uuid4().hex[:8]}{file_ext}"
        
        # Rejoin with the original directory
        return os.path.join(dir_name, unique_name)
