import asyncio
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

from app.core.config import settings
from app.core.enums import Role
from app.services.legal_attachments import (
    attachment_path,
    can_delete_attachment,
    save_legal_attachment,
    validate_attachment_relation,
)
from app.services.legal_permissions import LegalAccessContext, LegalCapability


class LegalAttachmentSecurityTest(unittest.TestCase):
    def _context(self, *capabilities: LegalCapability) -> LegalAccessContext:
        return LegalAccessContext(
            user_id=7,
            role=Role.RISK_AUDITOR,
            is_superuser=False,
            capabilities=frozenset(capabilities),
        )

    def test_attachment_path_stays_inside_legal_upload_root(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            settings, "UPLOAD_DIR", temp_dir
        ):
            target = attachment_path("../../outside.pdf")

            self.assertEqual(target.name, "outside.pdf")
            self.assertEqual(target.parent, (Path(temp_dir) / "legal-risk").resolve())

    def test_upload_rejects_disallowed_extension_without_writing_file(self):
        upload = UploadFile(filename="payload.exe", file=BytesIO(b"unsafe"))

        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            settings, "UPLOAD_DIR", temp_dir
        ):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(save_legal_attachment(
                    Mock(), upload,
                    case=SimpleNamespace(id=11), related_type="case", related_id=None,
                    category="evidence", actor=SimpleNamespace(id=7),
                ))

            self.assertEqual(raised.exception.status_code, 400)
            self.assertFalse((Path(temp_dir) / "legal-risk").exists())

    def test_upload_uses_generated_storage_name_and_records_digest(self):
        content = b"%PDF-1.7\nlegal evidence"
        upload = UploadFile(
            filename="../evidence.pdf",
            file=BytesIO(content),
            headers=Headers({"content-type": "text/html"}),
        )
        db = Mock()

        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            settings, "UPLOAD_DIR", temp_dir
        ):
            row, target = asyncio.run(save_legal_attachment(
                db, upload,
                case=SimpleNamespace(id=11), related_type="case", related_id=None,
                category="evidence", actor=SimpleNamespace(id=7),
            ))

            self.assertEqual(row.original_name, "evidence.pdf")
            self.assertNotEqual(row.storage_name, row.original_name)
            self.assertEqual(row.extension, ".pdf")
            self.assertEqual(row.mime_type, "application/pdf")
            self.assertEqual(row.size_bytes, len(content))
            self.assertEqual(len(row.sha256), 64)
            self.assertEqual(target.read_bytes(), content)
            db.add.assert_called_once_with(row)
            db.flush.assert_called_once_with()

    def test_upload_rejects_extension_spoofing_and_removes_partial_file(self):
        upload = UploadFile(
            filename="payload.jpg",
            file=BytesIO(b"<script>alert('xss')</script>"),
            headers=Headers({"content-type": "image/jpeg"}),
        )

        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            settings, "UPLOAD_DIR", temp_dir
        ):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(save_legal_attachment(
                    Mock(), upload,
                    case=SimpleNamespace(id=11), related_type="case", related_id=None,
                    category="evidence", actor=SimpleNamespace(id=7),
                ))

            self.assertEqual(raised.exception.status_code, 400)
            self.assertEqual(list((Path(temp_dir) / "legal-risk").iterdir()), [])

    def test_delete_requires_writable_case_and_owner_or_manager(self):
        owner_attachment = SimpleNamespace(uploaded_by=7)
        other_attachment = SimpleNamespace(uploaded_by=8)
        writable_case = SimpleNamespace(archived_at=None)
        archived_case = SimpleNamespace(archived_at=object())
        owner_context = self._context(LegalCapability.DELETE_ATTACHMENT)
        manager_context = self._context(LegalCapability.MANAGE_DETAIL)

        self.assertTrue(can_delete_attachment(owner_context, owner_attachment, writable_case))
        self.assertFalse(can_delete_attachment(owner_context, other_attachment, writable_case))
        self.assertTrue(can_delete_attachment(manager_context, other_attachment, writable_case))
        self.assertFalse(can_delete_attachment(manager_context, owner_attachment, archived_case))

    def test_attachment_relation_must_belong_to_the_same_case(self):
        db = Mock()
        db.scalar.return_value = None

        with self.assertRaises(HTTPException) as raised:
            validate_attachment_relation(
                db,
                case_id=11,
                related_type="progress",
                related_id=99,
            )

        self.assertEqual(raised.exception.status_code, 422)
        self.assertIn("不属于当前案件", raised.exception.detail)


if __name__ == "__main__":
    unittest.main()
