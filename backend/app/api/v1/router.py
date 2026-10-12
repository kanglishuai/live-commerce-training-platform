"""API v1 路由汇总。"""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    aftersales,
    agents,
    auth,
    classes,
    commerce,
    competitions,
    files,
    live,
    orders,
    products,
    reviews,
    sessions,
    tasks,
    users,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(classes.router)
api_router.include_router(tasks.router)
api_router.include_router(sessions.router)
api_router.include_router(products.router)
api_router.include_router(commerce.router)
api_router.include_router(live.router)
api_router.include_router(orders.router)
api_router.include_router(aftersales.router)
api_router.include_router(reviews.router)
api_router.include_router(competitions.router)
api_router.include_router(agents.router)
api_router.include_router(files.router)
