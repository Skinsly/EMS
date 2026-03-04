from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import (
    Attachment,
    ConstructionLog,
    Inventory,
    MachineLedger,
    Material,
    ProgressPlanItem,
    Project,
    StockInItem,
    StockInOrder,
    StockMovement,
    StockOutItem,
    StockOutOrder,
)
from .attachments import safe_remove_uploaded_file


def delete_project_cascade(
    project_id: int,
    db: Session,
    password_ok: bool,
    confirm_ok: bool,
) -> dict:
    project = db.get(Project, project_id)
    if not project or not project.is_active:
        raise HTTPException(status_code=404, detail="工程不存在")
    if not password_ok:
        raise HTTPException(status_code=400, detail="登录密码错误")
    if not confirm_ok:
        raise HTTPException(status_code=400, detail="确认短语不正确")

    stock_in_ids = db.scalars(select(StockInOrder.id).where(StockInOrder.project_id == project.id)).all()
    stock_out_ids = db.scalars(select(StockOutOrder.id).where(StockOutOrder.project_id == project.id)).all()
    log_ids = db.scalars(select(ConstructionLog.id).where(ConstructionLog.project_id == project.id)).all()
    machine_ledger_ids = db.scalars(select(MachineLedger.id).where(MachineLedger.project_id == project.id)).all()
    material_ids = db.scalars(select(Material.id).where(Material.project_id == project.id)).all()

    attachment_paths: list[str] = []

    if log_ids:
        log_attachments = db.scalars(
            select(Attachment).where(Attachment.order_type == "construction_log", Attachment.order_id.in_(log_ids))
        ).all()
        attachment_paths.extend([row.path for row in log_attachments if row.path])
        db.execute(delete(Attachment).where(Attachment.order_type == "construction_log", Attachment.order_id.in_(log_ids)))

    if stock_in_ids:
        stock_in_attachments = db.scalars(
            select(Attachment).where(Attachment.order_type == "stock_in", Attachment.order_id.in_(stock_in_ids))
        ).all()
        attachment_paths.extend([row.path for row in stock_in_attachments if row.path])
        db.execute(delete(Attachment).where(Attachment.order_type == "stock_in", Attachment.order_id.in_(stock_in_ids)))
        db.execute(delete(StockInItem).where(StockInItem.order_id.in_(stock_in_ids)))

    if stock_out_ids:
        stock_out_attachments = db.scalars(
            select(Attachment).where(Attachment.order_type == "stock_out", Attachment.order_id.in_(stock_out_ids))
        ).all()
        attachment_paths.extend([row.path for row in stock_out_attachments if row.path])
        db.execute(delete(Attachment).where(Attachment.order_type == "stock_out", Attachment.order_id.in_(stock_out_ids)))
        db.execute(delete(StockOutItem).where(StockOutItem.order_id.in_(stock_out_ids)))

    if machine_ledger_ids:
        machine_attachments = db.scalars(
            select(Attachment).where(Attachment.order_type == "machine_ledger", Attachment.order_id.in_(machine_ledger_ids))
        ).all()
        attachment_paths.extend([row.path for row in machine_attachments if row.path])
        db.execute(
            delete(Attachment).where(
                Attachment.order_type == "machine_ledger",
                Attachment.order_id.in_(machine_ledger_ids),
            )
        )

    db.execute(delete(StockMovement).where(StockMovement.project_id == project.id))
    db.execute(delete(StockInOrder).where(StockInOrder.project_id == project.id))
    db.execute(delete(StockOutOrder).where(StockOutOrder.project_id == project.id))
    db.execute(delete(ProgressPlanItem).where(ProgressPlanItem.project_id == project.id))
    db.execute(delete(ConstructionLog).where(ConstructionLog.project_id == project.id))
    db.execute(delete(MachineLedger).where(MachineLedger.project_id == project.id))

    if material_ids:
        db.execute(delete(Inventory).where(Inventory.material_id.in_(material_ids)))

    db.execute(delete(Material).where(Material.project_id == project.id))

    project.is_active = False
    db.commit()

    for file_path in set(attachment_paths):
        safe_remove_uploaded_file(file_path)

    return {"ok": True}
