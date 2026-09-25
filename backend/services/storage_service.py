"""
Supabase Storage Service for Dataset Files & Metadata.
Manages raw uploads, processed datasets, and metadata artifacts in Supabase Storage and PostgreSQL.
"""

import uuid
import logging
import psycopg2
from typing import Optional, Dict, Any, List
from psycopg2.extras import RealDictCursor, Json

from core.supabase import get_supabase_connection

logger = logging.getLogger(__name__)

DEFAULT_BUCKET = "datasets"


class SupabaseStorageService:
    """
    Centralized service for managing dataset files, raw uploads, processed CSVs/Parquet,
    and metadata sidecars in Supabase Storage and PostgreSQL.
    """

    def __init__(self, default_bucket: str = DEFAULT_BUCKET):
        self.default_bucket = default_bucket

    def build_storage_path(
        self,
        chat_id: str,
        dataset_id: str,
        file_role: str,
        filename: str,
        user_id: Optional[str] = None
    ) -> str:
        owner = user_id or "guest"
        role_clean = file_role.strip().lower()
        fname_clean = filename.strip()
        return f"{owner}/{chat_id}/{dataset_id}/{role_clean}/{fname_clean}"

    def upload_file(
        self,
        storage_path: str,
        content: bytes,
        file_type: str,
        file_role: str,
        dataset_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        user_id: Optional[str] = None,
        bucket: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Stores file content in Supabase Storage and records metadata in dataset_files & storage.objects.
        """
        bucket_name = bucket or self.default_bucket
        file_size = len(content)

        with get_supabase_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # 1. Upsert binary storage content in dataset_file_contents
                cur.execute(
                    """
                    INSERT INTO public.dataset_file_contents (storage_bucket, storage_path, content, content_type)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (storage_bucket, storage_path)
                    DO UPDATE SET content = EXCLUDED.content, created_at = CURRENT_TIMESTAMP;
                    """,
                    (bucket_name, storage_path, psycopg2.Binary(content), f"application/{file_type}")
                )

                # 2. Upsert storage.objects metadata entry
                cur.execute(
                    """
                    INSERT INTO storage.objects (id, bucket_id, name, metadata)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT DO NOTHING;
                    """,
                    (
                        str(uuid.uuid4()),
                        bucket_name,
                        storage_path,
                        Json({"size": file_size, "mimetype": f"application/{file_type}"})
                    )
                )

                # 3. Insert or update dataset_files record if dataset_id provided
                file_record_id = str(uuid.uuid4())
                if dataset_id:
                    cur.execute(
                        """
                        INSERT INTO public.dataset_files (id, dataset_id, chat_id, user_id, storage_bucket, storage_path, file_type, file_role, file_size)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
                        """,
                        (
                            file_record_id,
                            dataset_id,
                            chat_id,
                            user_id,
                            bucket_name,
                            storage_path,
                            file_type,
                            file_role,
                            file_size
                        )
                    )

        logger.info(f"Uploaded file to Supabase Storage: {bucket_name}/{storage_path} ({file_size} bytes)")
        return {
            "id": file_record_id,
            "dataset_id": dataset_id,
            "chat_id": chat_id,
            "storage_bucket": bucket_name,
            "storage_path": storage_path,
            "file_type": file_type,
            "file_role": file_role,
            "file_size": file_size
        }

    def download_file(self, storage_path: str, bucket: Optional[str] = None) -> Optional[bytes]:
        """
        Retrieves raw binary file content from Supabase Storage.
        """
        bucket_name = bucket or self.default_bucket
        with get_supabase_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT content FROM public.dataset_file_contents
                    WHERE storage_bucket = %s AND storage_path = %s;
                    """,
                    (bucket_name, storage_path)
                )
                row = cur.fetchone()
                if not row:
                    logger.warning(f"File not found in Supabase Storage: {bucket_name}/{storage_path}")
                    return None
                return bytes(row["content"])

    def delete_file(self, storage_path: str, bucket: Optional[str] = None) -> bool:
        """
        Deletes a single file from Supabase Storage and PostgreSQL.
        """
        bucket_name = bucket or self.default_bucket
        with get_supabase_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM public.dataset_file_contents WHERE storage_bucket = %s AND storage_path = %s;",
                    (bucket_name, storage_path)
                )
                cur.execute(
                    "DELETE FROM storage.objects WHERE bucket_id = %s AND name = %s;",
                    (bucket_name, storage_path)
                )
                cur.execute(
                    "DELETE FROM public.dataset_files WHERE storage_bucket = %s AND storage_path = %s;",
                    (bucket_name, storage_path)
                )
                return True

    def delete_dataset_files(self, dataset_id: str) -> bool:
        """
        Deletes all storage files associated with a dataset.
        """
        with get_supabase_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT storage_bucket, storage_path FROM public.dataset_files WHERE dataset_id = %s;",
                    (dataset_id,)
                )
                rows = cur.fetchall()
                for row in rows:
                    cur.execute(
                        "DELETE FROM public.dataset_file_contents WHERE storage_bucket = %s AND storage_path = %s;",
                        (row["storage_bucket"], row["storage_path"])
                    )
                    cur.execute(
                        "DELETE FROM storage.objects WHERE bucket_id = %s AND name = %s;",
                        (row["storage_bucket"], row["storage_path"])
                    )
                cur.execute("DELETE FROM public.dataset_files WHERE dataset_id = %s;", (dataset_id,))
                return True

    def list_dataset_files(self, dataset_id: str) -> List[Dict[str, Any]]:
        """
        Lists all storage files for a specific dataset.
        """
        with get_supabase_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, dataset_id, chat_id, user_id, storage_bucket, storage_path, file_type, file_role, file_size, created_at
                    FROM public.dataset_files
                    WHERE dataset_id = %s
                    ORDER BY created_at ASC;
                    """,
                    (dataset_id,)
                )
                rows = cur.fetchall()
                return [dict(r) for r in rows]
