"""账号详情接口返回 cookie；列表接口继续隐藏。"""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile

SOURCE = Path(__file__).resolve().parent.parent / "app.py"


class Response:
    def __init__(self, status, body):
        self.status_code, self.body = status, body

    def json(self):
        return json.loads(self.body)


class Client:
    def __init__(self, app, headers):
        self.app, self.headers = app, headers

    async def request(self, method, path):
        hdr = dict(self.headers)
        hdr["content-length"] = "0"
        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                 "method": method, "scheme": "http", "path": path,
                 "raw_path": path.encode(), "query_string": b"", "root_path": "",
                 "headers": [(k.lower().encode(), v.encode()) for k, v in hdr.items()],
                 "server": ("test", 80), "client": ("test", 1)}
        messages = []
        sent = False

        async def receive():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": b"", "more_body": False}
            await asyncio.Event().wait()

        async def send(message):
            messages.append(message)

        await self.app(scope, receive, send)
        status = next(m["status"] for m in messages if m["type"] == "http.response.start")
        return Response(status, b"".join(m.get("body", b"") for m in messages))

    async def get(self, path):
        return await self.request("GET", path)


def main():
    home = tempfile.mkdtemp(prefix="muse2api-detail-")
    os.environ.update(MUSE2API_HOME=home, MUSE2API_PROFILE_ROOT=home, MUSE2API_KEY="test-only")
    sys.path.insert(0, str(SOURCE.parent))
    for name in ("config", "store", "engine", "cdp"):
        sys.modules.pop(name, None)
    spec = importlib.util.spec_from_file_location("account_detail_test_target", SOURCE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    acc = module.store.add_account(
        {"hatch_sess": "sess-secret", "hatch_gw": "gw", "hatch_vml": "vml",
         "hatch_native_auth_device": "dev"},
        label="查看用",
    )

    async def run():
        client = Client(module.app, {"Authorization": "Bearer test-only"})
        listed = await client.get("/admin/accounts")
        assert listed.status_code == 200, listed.status_code
        body = listed.body.decode()
        assert "sess-secret" not in body, "列表接口不应返回 cookie 值"
        row = next(a for a in listed.json()["accounts"] if a["id"] == acc["id"])
        assert "cookies" not in row

        detail = await client.get("/admin/accounts/" + acc["id"])
        assert detail.status_code == 200, detail.body
        data = detail.json()
        assert data["label"] == "查看用"
        assert data["cookies"]["hatch_sess"] == "sess-secret"
        assert "hatch_sess=sess-secret" in data["cookie_header"]
        assert data["essential_ok"] is True

        missing = await client.get("/admin/accounts/missing-account")
        assert missing.status_code == 404

        anon = Client(module.app, {})
        denied = await anon.get("/admin/accounts/" + acc["id"])
        assert denied.status_code == 401
        assert b"sess-secret" not in denied.body

    asyncio.run(run())
    html = (SOURCE.parent / "admin.html").read_text(encoding="utf-8")
    assert "function openModal(" in html
    assert "function viewAcc(" in html
    assert "prompt(" not in html
    assert "查看</button>" in html
    print("ok")


if __name__ == "__main__":
    main()
