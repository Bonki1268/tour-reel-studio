"""SSE 測試：以 uvicorn 在背景執行緒啟動真的伺服器，並以另一個執行緒串流讀取事件（spec 0008 待決事項 7）。"""

import json
import queue
import socket
import threading
import time
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class LiveServer:
    def __init__(self, app: FastAPI) -> None:
        self.port = _free_port()
        config = uvicorn.Config(
            app, host="127.0.0.1", port=self.port, log_level="warning", lifespan="off",
            timeout_graceful_shutdown=1,
        )
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> None:
        self.thread.start()
        deadline = time.monotonic() + 5
        while not self.server.started:
            if time.monotonic() > deadline:
                raise TimeoutError("uvicorn 沒有在 5 秒內啟動")
            time.sleep(0.02)

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=5)


class SseReader:
    """讀取 SSE，解析出 (event, data) 放入佇列；stop() 後在下一行（含 keep-alive）結束連線。"""

    def __init__(self, url: str) -> None:
        self.url = url
        self.events: queue.Queue[tuple[str, dict[str, Any]]] = queue.Queue()
        self.raw: list[str] = []
        self._stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def _run(self) -> None:
        with httpx.Client(timeout=httpx.Timeout(5, read=5)) as client, client.stream("GET", self.url) as r:
            event, data = "", ""
            for line in r.iter_lines():
                self.raw.append(line)
                if self._stop.is_set():
                    return
                if line.startswith("event: "):
                    event = line[len("event: "):]
                elif line.startswith("data: "):
                    data = line[len("data: "):]
                elif line == "" and event:
                    self.events.put((event, json.loads(data)))
                    event, data = "", ""

    def wait_for(self, event_type: str, timeout: float = 5) -> dict[str, Any]:
        """等到指定類型的事件；回傳其 data。先前收到的其他事件會被略過。"""
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"{timeout} 秒內沒有收到 {event_type} 事件；原始內容：{self.raw}")
            try:
                event, data = self.events.get(timeout=remaining)
            except queue.Empty:
                continue
            if event == event_type:
                return data

    def stop(self) -> None:
        self._stop.set()
        self.thread.join(timeout=5)
