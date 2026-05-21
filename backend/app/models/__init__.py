"""
全モデルをここで import することで Alembic autogenerate が全テーブルを検出できる。
新しいモデルを追加したら必ずここに追記する。
"""
from app.models.admin_user import AdminUser, AdminRole
from app.models.approval_log import ApprovalLog, ApprovalAction
from app.models.company import Company
from app.models.entry import WorkerSiteEntry, EntryStatus
from app.models.feedback import UxFeedback
from app.models.qr_code import SiteQrCode
from app.models.site import Site
from app.models.worker import Worker, WorkerType, BloodType, Gender

__all__ = [
    "AdminUser",
    "AdminRole",
    "ApprovalLog",
    "ApprovalAction",
    "Company",
    "WorkerSiteEntry",
    "EntryStatus",
    "UxFeedback",
    "SiteQrCode",
    "Site",
    "Worker",
    "WorkerType",
    "BloodType",
    "Gender",
]
