"""额度查询必须按账号切换页面，不能复用当前标签页的 Usage。"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import engine as engine_mod


def main():
    engine = object.__new__(engine_mod.MuseEngine)
    closed = []

    class Page:
        def js(self, _code):
            return True

        def close(self):
            closed.append(True)

    engine.page = Page()
    engine.current_acc_id = "account-a"
    same = engine.ensure_page({"hatch_sess": "a"}, account_id="account-a")
    assert same is engine.page, "同一账号应复用已打开的页面"
    assert closed == [], "同一账号不应关闭页面"

    opened = {}

    def open_page():
        page = SimpleNamespace(js=lambda _code: False, send=lambda *a, **k: None, close=lambda: None)
        opened["page"] = page
        return page

    engine._open_page = open_page
    engine.renew_session_http = staticmethod(
        lambda cookies, expires=None, wake_vm=True: {"cookies": cookies, "cookies_exp": expires or {}})
    engine._apply_cookies = lambda page, cookies, expires=None: opened.__setitem__("cookies", cookies)
    engine.cfg = SimpleNamespace(login_wait=0)
    engine._wait_ws_ready = lambda page, timeout=15: True
    try:
        engine.ensure_page({"hatch_sess": "b"}, account_id="account-b")
    except engine_mod.MuseGenerationError:
        pass
    assert closed, "切换账号时必须先关掉上一个账号的页面"
    assert opened.get("cookies", {}).get("hatch_sess") == "b", "切换后必须注入目标账号的 cookie"
    assert engine.page is None, "新页面没打开成功时不能继续留着上一个账号"

    seen = {}

    def ensure_page(cookies, expires=None, account_id=None):
        seen["account_id"] = account_id
        return engine.page

    engine.ensure_page = ensure_page
    engine._click_point = lambda x, y: None
    panel = (
        "Usage\nFree plan\nWeekly limit resets on Oct 9\n10% used\n"
        "Additional tokens\nNever expires\n4% used (320M tokens left)\n"
    )

    def js(code):
        if "role=dialog" in code:
            return panel
        return json.dumps({"x": 1, "y": 1})

    engine.page = SimpleNamespace(js=js, send=lambda *a, **k: None)
    engine_mod.time.sleep = lambda _s: None
    parsed = engine.quota({"hatch_sess": "b"}, account_id="account-b")
    assert seen["account_id"] == "account-b", "quota 必须把账号 ID 传给页面切换"
    assert parsed["weekly_used_pct"] == 10, parsed
    assert parsed["extra_used_pct"] == 4, parsed
    assert parsed["extra_left"] == "320M tokens left", parsed
    print("ok")


if __name__ == "__main__":
    main()
