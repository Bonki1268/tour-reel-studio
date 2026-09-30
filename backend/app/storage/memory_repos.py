"""記憶體版 repository（spec 0005 R-006）：供單元測試取代資料庫。"""

from app.domain.ports import Repositories


def memory_repositories() -> Repositories:
    raise NotImplementedError
