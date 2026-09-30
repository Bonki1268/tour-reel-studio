"""資料庫版 repository（spec 0005）。ORM 與領域物件的轉換集中在這裡。"""

from sqlalchemy.ext.asyncio import AsyncEngine

from app.domain.ports import Repositories


def sql_repositories(engine: AsyncEngine) -> Repositories:
    raise NotImplementedError
