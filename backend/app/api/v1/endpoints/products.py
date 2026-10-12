"""商品库：检索/筛选/维护（教师、管理员），学生选品时读取。"""

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.core import errors
from app.core.deps import DbDep, TeacherDep
from app.models.commerce import Product
from app.schemas.commerce import ProductCreateIn, ProductOut, ProductPatchIn
from app.schemas.common import Page

router = APIRouter(tags=["商品库"])

SORTS = {
    "default": Product.id,
    "heat": Product.heat.desc(),
    "price_asc": Product.market_price_cents.asc(),
    "price_desc": Product.market_price_cents.desc(),
}


@router.get("/products", response_model=Page[ProductOut], summary="商品检索（学生选品用）")
def list_products(
    db: DbDep,
    keyword: str | None = None,
    category: str | None = None,
    status: str | None = "on",
    sort: str = "default",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> Page[ProductOut]:
    stmt, count_stmt = select(Product), select(func.count(Product.id))
    if keyword:
        like = f"%{keyword}%"
        cond = Product.name.like(like) | Product.brand.like(like)
        stmt, count_stmt = stmt.where(cond), count_stmt.where(cond)
    if category:
        stmt, count_stmt = stmt.where(Product.category == category), count_stmt.where(Product.category == category)
    if status:
        stmt, count_stmt = stmt.where(Product.status == status), count_stmt.where(Product.status == status)
    total = db.execute(count_stmt).scalar_one()
    order = SORTS.get(sort, Product.id)
    rows = db.execute(
        stmt.order_by(order).offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    return Page[ProductOut](
        items=[ProductOut.model_validate(p) for p in rows], total=total, page=page, page_size=page_size
    )


@router.get("/products/{product_id}", response_model=ProductOut, summary="商品详情")
def get_product(product_id: int, db: DbDep) -> ProductOut:
    product = db.get(Product, product_id)
    if product is None:
        raise errors.not_found("商品", product_id)
    return ProductOut.model_validate(product)


@router.post("/products", response_model=ProductOut, summary="新增商品（教师/管理员）")
def create_product(payload: ProductCreateIn, user: TeacherDep, db: DbDep) -> ProductOut:
    product = Product(**payload.model_dump(), source="builtin", created_by=user.id)
    db.add(product)
    db.commit()
    return ProductOut.model_validate(product)


@router.patch("/products/{product_id}", response_model=ProductOut, summary="维护商品（教师/管理员）")
def patch_product(
    product_id: int, payload: ProductPatchIn, user: TeacherDep, db: DbDep
) -> ProductOut:
    product = db.get(Product, product_id)
    if product is None:
        raise errors.not_found("商品", product_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, key, value)
    db.commit()
    return ProductOut.model_validate(product)
