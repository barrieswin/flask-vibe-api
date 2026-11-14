"""入帳分類相關 API 路由。"""

from datetime import datetime, timezone

from flask import Blueprint, request

from extensions import db
from models import IncomeCategory
from utils import api_response

income_categories_bp = Blueprint(
    "income_categories", __name__, url_prefix="/api/income-categories"
)


@income_categories_bp.get("")
def list_income_categories():
    """取得入帳分類清單。若無資料回傳 200 與空清單。"""
    categories = db.session.scalars(
        db.select(IncomeCategory).order_by(IncomeCategory.id.asc())
    ).all()
    return api_response(
        200, "取得入帳分類清單成功", [cat.to_dict() for cat in categories]
    )


@income_categories_bp.post("")
def create_income_category():
    """新增入帳分類。必填 name。成功回傳 201。"""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return api_response(400, "請提供合法的 JSON 物件格式", None)

    # 1. 必填 name
    name_raw = payload.get("name")
    if not isinstance(name_raw, str) or not name_raw.strip():
        return api_response(400, "分類名稱為必填項目且不可為空", None)
    name = name_raw.strip()

    # 檢查名稱重複
    existing = db.session.scalar(db.select(IncomeCategory).filter_by(name=name))
    if existing:
        return api_response(400, "分類名稱已存在，不可重複", None)

    # 2. 可空 description
    description_raw = payload.get("description")
    description = None
    if description_raw is not None:
        if isinstance(description_raw, str):
            description = description_raw.strip() or None
        else:
            return api_response(400, "分類描述必須為文字格式", None)

    # 客戶端不送主鍵與 created_at，送了也不採用
    category = IncomeCategory(name=name, description=description)
    db.session.add(category)
    db.session.commit()

    return api_response(201, "入帳分類新增成功", category.to_dict())


@income_categories_bp.get("/<int:category_id>")
def get_income_category(category_id: int):
    """取得單一入帳分類。若無該列回傳 404。"""
    category = db.session.get(IncomeCategory, category_id)
    if not category:
        return api_response(404, "找不到指定的入帳分類", None)
    return api_response(200, "取得入帳分類成功", category.to_dict())


@income_categories_bp.patch("/<int:category_id>")
def update_income_category(category_id: int):
    """修改入帳分類資訊。可改名稱、描述。改 updated_at。不可改主鍵。"""
    category = db.session.get(IncomeCategory, category_id)
    if not category:
        return api_response(404, "找不到指定的入帳分類", None)

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return api_response(400, "請提供合法的 JSON 物件格式", None)

    if "id" in payload and payload["id"] != category.id:
        return api_response(400, "不可修改主鍵", None)

    # 修改名稱
    if "name" in payload:
        name_raw = payload.get("name")
        if not isinstance(name_raw, str) or not name_raw.strip():
            return api_response(400, "分類名稱不可為空", None)
        name = name_raw.strip()
        if name != category.name:
            existing = db.session.scalar(
                db.select(IncomeCategory).filter(
                    IncomeCategory.name == name, IncomeCategory.id != category.id
                )
            )
            if existing:
                return api_response(400, "分類名稱已存在，不可重複", None)
            category.name = name

    # 修改描述（送 null 代表清除）
    if "description" in payload:
        description_raw = payload.get("description")
        if description_raw is None:
            category.description = None
        elif isinstance(description_raw, str):
            category.description = description_raw.strip() or None
        else:
            return api_response(400, "分類描述必須為文字格式", None)

    category.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    return api_response(200, "入帳分類更新成功", category.to_dict())
