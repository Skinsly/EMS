from decimal import Decimal

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class PasswordChangeRequest(BaseModel):
    old_password: str
    new_username: str = ""
    new_password: str = ""


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    must_change_password: bool


class BootstrapInitRequest(BaseModel):
    username: str
    password: str


class MaterialCreate(BaseModel):
    name: str
    spec: str = ""
    unit: str = ""


class MaterialUpdate(BaseModel):
    name: str
    spec: str = ""
    unit: str = ""


class StockOrderItemInput(BaseModel):
    material_id: int
    qty: Decimal = Field(gt=0)
    remark: str = ""


class StockInCreate(BaseModel):
    warehouse_id: int | None = None
    note: str = ""
    items: list[StockOrderItemInput]


class StockOutCreate(BaseModel):
    warehouse_id: int | None = None
    receiver_name: str = ""
    usage: str = ""
    work_area: str = ""
    note: str = ""
    items: list[StockOrderItemInput]


class ProjectCreate(BaseModel):
    name: str
    start_date: str = ""


class ProjectDeleteRequest(BaseModel):
    password: str
    confirm_text: str


class ConstructionLogCreate(BaseModel):
    log_date: str = ""
    title: str
    weather: str = ""
    content: str = ""


class ConstructionLogUpdate(BaseModel):
    title: str = ""
    log_date: str = ""
    weather: str = ""
    content: str = ""


class ProgressPlanItemCreate(BaseModel):
    task_name: str
    owner: str = ""
    start_date: str = ""
    end_date: str = ""
    progress: int = Field(default=0, ge=0, le=100)
    status: str = "未开始"
    predecessor: str = ""
    note: str = ""
    sort_order: int = 0


class ProgressPlanItemUpdate(BaseModel):
    task_name: str
    owner: str = ""
    start_date: str = ""
    end_date: str = ""
    progress: int = Field(default=0, ge=0, le=100)
    status: str = "未开始"
    predecessor: str = ""
    note: str = ""
    sort_order: int = 0


class InventoryDeleteRequest(BaseModel):
    inventory_ids: list[int]
    password: str


class MaterialDeleteRequest(BaseModel):
    material_ids: list[int]


class FileCategoryCreate(BaseModel):
    name: str


class FileCategoryRename(BaseModel):
    name: str


class FileCategoryDeleteRequest(BaseModel):
    password: str
    delete_files_confirmed: bool = False
