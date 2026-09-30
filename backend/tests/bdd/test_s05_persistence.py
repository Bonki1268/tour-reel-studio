import asyncio
from collections.abc import Coroutine, Iterator
from typing import Any, TypeVar

import pytest
from pytest_bdd import given, parsers, scenarios, then, when
from sqlalchemy import Connection, Engine, inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from app.domain.ports import Repositories
from app.storage.sql_repos import sql_repositories
from tests.conftest import alembic_config, database_url
from tests.persistence_data import (
    SECTION7_TABLES,
    assert_same_json,
    make_job,
    sample_project,
    sample_timeline,
    seed_shot,
    seed_take,
    seed_video,
)

pytestmark = pytest.mark.S05

scenarios("api/s05_persistence.feature")

T = TypeVar("T")
MIGRATE_SCHEMA = "s05_from_scratch"


class Db:
    """在同一個事件迴圈中執行 async repository（pytest-bdd 的步驟是同步函式）。"""

    def __init__(self) -> None:
        self.runner = asyncio.Runner()
        self.engine = create_async_engine(database_url())
        self.repos: Repositories = sql_repositories(self.engine)

    def run(self, coro: Coroutine[Any, Any, T]) -> T:
        return self.runner.run(coro)

    def close(self) -> None:
        self.runner.run(self.engine.dispose())
        self.runner.close()


@pytest.fixture
def db(clean_db: None) -> Iterator[Db]:
    d = Db()
    yield d
    d.close()


@pytest.fixture
def ctx() -> dict[str, Any]:
    return {}


# S05-01


@pytest.fixture
def scratch_conn(sync_engine: Engine) -> Iterator[Connection]:
    """獨立 schema 的連線：從零遷移，不影響其他測試使用的 public schema。"""
    with sync_engine.connect() as conn:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {MIGRATE_SCHEMA} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {MIGRATE_SCHEMA}"))
        conn.execute(text(f"SET search_path TO {MIGRATE_SCHEMA}"))
        conn.commit()
        yield conn
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {MIGRATE_SCHEMA} CASCADE"))
        conn.execute(text("RESET search_path"))  # 連線會回到連線池，不可殘留 search_path
        conn.commit()


@given("一個空的資料庫")
def empty_database(ctx: dict[str, Any], scratch_conn: Connection) -> None:
    assert inspect(scratch_conn).get_table_names(schema=MIGRATE_SCHEMA) == []
    ctx["conn"] = scratch_conn


@when("執行所有 Alembic 遷移")
def run_all_migrations(ctx: dict[str, Any]) -> None:
    conn: Connection = ctx["conn"]
    command.upgrade(alembic_config(conn), "head")
    conn.commit()


@then("架構書 §7 列出的資料表全部存在")
def section7_tables_exist(ctx: dict[str, Any]) -> None:
    tables = set(inspect(ctx["conn"]).get_table_names(schema=MIGRATE_SCHEMA))
    assert SECTION7_TABLES - tables == set()


# S05-02


@given("一個已遷移的空資料庫")
def migrated_empty_database(ctx: dict[str, Any], db: Db) -> None:
    ctx["db"] = db


@when(parsers.parse('建立專案 "{name}" 並寫入品牌檔案'))
def create_project_with_brand(ctx: dict[str, Any], name: str) -> None:
    db: Db = ctx["db"]
    project, brand = sample_project(name)
    db.run(db.repos.projects.add(project, brand))
    ctx["written"] = (project, brand)


@then("可以讀回相同的專案與品牌檔案內容")
def project_and_brand_read_back(ctx: dict[str, Any]) -> None:
    db: Db = ctx["db"]
    project, brand = ctx["written"]
    loaded = db.run(db.repos.projects.get(project.id))
    assert loaded == (project, brand)
    assert loaded[0].name == "梅子農場"
    assert_same_json(loaded[1].visual, brand.visual)
    assert_same_json(loaded[1].info, brand.info)


# S05-03


@given(parsers.parse("一支影片的第 {shot_no:d} 鏡已有 1 個版本"))
def shot_with_one_take(ctx: dict[str, Any], db: Db, shot_no: int) -> None:
    shot = db.run(seed_shot(db.repos, shot_no=shot_no))
    first = db.run(db.repos.shots.add_take(shot.id, keyframe_key="take1/keyframe.png", status="done"))
    ctx.update(db=db, shot=shot, first=first)


@when(parsers.parse("第 {shot_no:d} 鏡重生"))
def regenerate_shot(ctx: dict[str, Any], shot_no: int) -> None:
    db: Db = ctx["db"]
    assert ctx["shot"].shot_no == shot_no
    ctx["second"] = db.run(db.repos.shots.add_take(ctx["shot"].id))


@then(parsers.parse("第 {shot_no:d} 鏡有 {count:d} 個版本"))
def shot_has_takes(ctx: dict[str, Any], shot_no: int, count: int) -> None:
    db: Db = ctx["db"]
    takes = db.run(db.repos.shots.takes(ctx["shot"].id))
    assert [t.attempt for t in takes] == list(range(1, count + 1))
    ctx["takes"] = takes


@then(parsers.parse("目前版本指向第 {attempt:d} 個版本"))
def current_take_is(ctx: dict[str, Any], attempt: int) -> None:
    db: Db = ctx["db"]
    shot = db.run(db.repos.shots.get_shot(ctx["shot"].id))
    assert shot is not None
    current = next(t for t in ctx["takes"] if t.id == shot.current_take_id)
    assert current.attempt == attempt


@then(parsers.parse("第 {attempt:d} 個版本仍可讀取"))
def earlier_take_readable(ctx: dict[str, Any], attempt: int) -> None:
    take = next(t for t in ctx["takes"] if t.attempt == attempt)
    assert take == ctx["first"]


# S05-04


@given(parsers.parse('已存在冪等鍵為 "{key}" 的生成工作'))
def existing_job(ctx: dict[str, Any], db: Db, key: str) -> None:
    take = db.run(seed_take(db.repos))
    job, created = db.run(db.repos.jobs.create_or_get(make_job(take.id, key)))
    assert created
    ctx.update(db=db, take=take, key=key, original=job)


@when("再次建立相同冪等鍵的生成工作")
def create_same_key_again(ctx: dict[str, Any]) -> None:
    db: Db = ctx["db"]
    dup = make_job(ctx["take"].id, ctx["key"], model="img-model-b", status="running")
    ctx["result"] = db.run(db.repos.jobs.create_or_get(dup))


@then("回傳既有的生成工作而非建立新的")
def returns_existing_job(ctx: dict[str, Any]) -> None:
    db: Db = ctx["db"]
    job, created = ctx["result"]
    assert created is False
    assert job == ctx["original"]
    assert db.run(db.repos.jobs.count_by_key(ctx["key"])) == 1


# S05-05


@given("一支影片有一份時間軸 JSON")
def video_with_timeline(ctx: dict[str, Any], db: Db) -> None:
    ctx.update(db=db, video=db.run(seed_video(db.repos)))
    ctx["video"].timeline = sample_timeline()


@when("儲存後重新讀取")
def save_and_reload(ctx: dict[str, Any]) -> None:
    db: Db = ctx["db"]
    db.run(db.repos.videos.save(ctx["video"]))
    ctx["loaded"] = db.run(db.repos.videos.get(ctx["video"].id))


@then("時間軸 JSON 與原本內容相同")
def timeline_unchanged(ctx: dict[str, Any]) -> None:
    assert ctx["loaded"] is not None
    assert_same_json(ctx["loaded"].timeline, sample_timeline())
