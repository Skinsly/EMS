from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow_naive)


class Warehouse(Base):
    __tablename__ = "warehouses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow_naive)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    start_date: Mapped[str] = mapped_column(String(20), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow_naive)


class Material(Base):
    __tablename__ = "materials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, index=True, default=0)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    spec: Mapped[str] = mapped_column(String(200), default="")
    unit: Mapped[str] = mapped_column(String(32), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow_naive)


class Inventory(Base):
    __tablename__ = "inventory"
    __table_args__ = (UniqueConstraint("material_id", "warehouse_id", name="uq_inventory_material_warehouse"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"), index=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), index=True)
    qty: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=Decimal("0.000"))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow_naive, onupdate=_utcnow_naive)

    material = relationship("Material")
    warehouse = relationship("Warehouse")


class StockInOrder(Base):
    __tablename__ = "stock_in_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, index=True, default=0)
    order_no: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"))
    operator_name: Mapped[str] = mapped_column(String(64), default="技术员")
    note: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="normal")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow_naive)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    warehouse = relationship("Warehouse")
    items = relationship("StockInItem", cascade="all, delete-orphan")


class StockInItem(Base):
    __tablename__ = "stock_in_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("stock_in_orders.id"), index=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"), index=True)
    qty: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    remark: Mapped[str] = mapped_column(String(255), default="")

    material = relationship("Material")


class StockOutOrder(Base):
    __tablename__ = "stock_out_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, index=True, default=0)
    order_no: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"))
    operator_name: Mapped[str] = mapped_column(String(64), default="技术员")
    receiver_name: Mapped[str] = mapped_column(String(64), default="")
    usage: Mapped[str] = mapped_column(String(255), default="")
    work_area: Mapped[str] = mapped_column(String(255), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="normal")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow_naive)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    warehouse = relationship("Warehouse")
    items = relationship("StockOutItem", cascade="all, delete-orphan")


class StockOutItem(Base):
    __tablename__ = "stock_out_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("stock_out_orders.id"), index=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"), index=True)
    qty: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    remark: Mapped[str] = mapped_column(String(255), default="")

    material = relationship("Material")


class StockMovement(Base):
    __tablename__ = "stock_movements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, index=True, default=0)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"), index=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), index=True)
    movement_type: Mapped[str] = mapped_column(String(8))
    order_type: Mapped[str] = mapped_column(String(16))
    order_id: Mapped[int] = mapped_column(Integer, index=True)
    item_id: Mapped[int] = mapped_column(Integer)
    qty: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    balance_after: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    operator_name: Mapped[str] = mapped_column(String(64), default="技术员")
    note: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow_naive, index=True)

    material = relationship("Material")
    warehouse = relationship("Warehouse")


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_type: Mapped[str] = mapped_column(String(16), index=True)
    order_id: Mapped[int] = mapped_column(Integer, index=True)
    filename: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(255), unique=True)
    content_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(Integer)
    path: Mapped[str] = mapped_column(String(400))
    uploaded_by: Mapped[str] = mapped_column(String(64), default="skins")
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow_naive)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class FileCategory(Base):
    __tablename__ = "file_categories"
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_file_category_project_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(64), index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow_naive)


class ProjectFile(Base):
    __tablename__ = "project_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("file_categories.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(400), unique=True)
    path: Mapped[str] = mapped_column(String(400))
    content_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(Integer)
    remark: Mapped[str] = mapped_column(String(255), default="")
    uploaded_by: Mapped[str] = mapped_column(String(64), default="skins")
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow_naive)

    category = relationship("FileCategory")


class ConstructionLog(Base):
    __tablename__ = "construction_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, index=True)
    log_date: Mapped[str] = mapped_column(String(20), default="")
    title: Mapped[str] = mapped_column(String(200), default="")
    weather: Mapped[str] = mapped_column(String(50), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow_naive)


class ProgressPlanItem(Base):
    __tablename__ = "progress_plan_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, index=True)
    task_name: Mapped[str] = mapped_column(String(200))
    owner: Mapped[str] = mapped_column(String(64), default="")
    start_date: Mapped[str] = mapped_column(String(20), default="")
    end_date: Mapped[str] = mapped_column(String(20), default="")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="未开始")
    predecessor: Mapped[str] = mapped_column(String(100), default="")
    note: Mapped[str] = mapped_column(String(255), default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow_naive)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    response_json: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow_naive, index=True)


class StockDraft(Base):
    __tablename__ = "stock_drafts"
    __table_args__ = (UniqueConstraint("project_id", "user_id", "draft_type", name="uq_stock_draft_scope"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    draft_type: Mapped[str] = mapped_column(String(8), index=True)
    payload_json: Mapped[str] = mapped_column(Text, default="[]")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow_naive, onupdate=_utcnow_naive, index=True)


class MachineLedger(Base):
    __tablename__ = "machine_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    spec: Mapped[str] = mapped_column(String(200), default="")
    use_date: Mapped[str] = mapped_column(String(20), default="")
    shift_count: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=Decimal("0.000"))
    remark: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow_naive, index=True)


class UserProjectAccess(Base):
    __tablename__ = "user_project_access"
    __table_args__ = (UniqueConstraint("user_id", "project_id", name="uq_user_project_access"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    project_id: Mapped[int] = mapped_column(Integer, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow_naive)
