import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict
from urllib.parse import parse_qs, quote_plus, urlparse


def build_enterprise_console_html(
    screen_text: str = "Готов. Пиши запрос.",
    prompt_value: str = "",
    auto_refresh_seconds: int = 0,
) -> str:
    refresh_meta = ""
    if auto_refresh_seconds > 0:
        refresh_meta = f'<meta http-equiv="refresh" content="{int(auto_refresh_seconds)}">'
    escaped_screen = html.escape(screen_text)
    escaped_prompt = html.escape(prompt_value)
    return """<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  __REFRESH_META__
  <title>Enterprise</title>
  <style>
    :root { --bg:#0b1015; --panel:#121922; --line:#263241; --text:#e6edf3; --muted:#8ea0b5; --acc:#3a8bff; --chip:#0f141b; --app-height:100dvh; --kb-offset:0px; }
    * { box-sizing:border-box; }
    html, body { height:100%; }
    body {
      margin:0;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      background:
        radial-gradient(circle at top, rgba(58,139,255,0.12), transparent 34%),
        linear-gradient(180deg,#0b1015,#0d131b);
      color:var(--text);
      min-height:var(--app-height);
      height:var(--app-height);
      overflow:hidden;
    }
    .wrap {
      width:100%;
      padding:calc(8px + env(safe-area-inset-top)) 10px calc(8px + env(safe-area-inset-bottom));
      height:var(--app-height);
      display:flex;
      flex-direction:column;
      gap:8px;
    }
    .screen {
      background:var(--panel);
      border:1px solid var(--line);
      border-radius:20px;
      padding:16px 16px 22px;
      min-height:0;
      white-space:pre-wrap;
      overflow:auto;
      font-size:14px;
      line-height:1.5;
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.03);
    }
    .screen.live { flex:1 1 auto; width:100%; }
    .composer {
      flex:0 0 auto;
      position:sticky;
      bottom:0;
      padding-bottom:max(4px, calc(env(safe-area-inset-bottom) + var(--kb-offset)));
      background:linear-gradient(180deg, rgba(11,16,21,0), rgba(11,16,21,0.92) 24%, rgba(11,16,21,1));
    }
    .composer-form {
      display:flex;
      align-items:center;
      background:rgba(12,17,24,0.96);
      border:1px solid var(--line);
      border-radius:20px;
      padding:6px 10px;
      box-shadow: 0 10px 30px rgba(0,0,0,0.24);
    }
    .composer-input {
      width:100%;
      min-width:0;
      background:transparent;
      border:none;
      outline:none;
      color:var(--text);
      font:inherit;
      font-size:15px;
      line-height:1.3;
      padding:10px 8px;
    }
    .composer-input::placeholder { color:var(--muted); }
    .composer-send {
      flex:0 0 auto;
      width:34px;
      height:34px;
      border:none;
      border-radius:10px;
      background:transparent;
      color:var(--muted);
      font:inherit;
      font-size:16px;
    }
    @media (max-width: 720px) {
      .wrap { padding:calc(6px + env(safe-area-inset-top)) 8px calc(6px + env(safe-area-inset-bottom)); gap:8px; }
      .screen { border-radius:18px; padding:14px 14px 18px; font-size:13px; }
      .composer-form { border-radius:18px; padding:4px 8px; }
      .composer-input { padding:10px; font-size:15px; }
      .composer-send { width:32px; height:32px; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div id="screen" class="screen live">__SCREEN_TEXT__</div>
    <div class="composer">
      <form id="composer" class="composer-form" method="post" action="/enterprise-console/submit">
        <input id="cmd" name="cmd" value="__PROMPT_VALUE__" class="composer-input" type="text" enterkeyhint="send" autocomplete="off" autocorrect="off" autocapitalize="sentences" spellcheck="false" placeholder="Сообщение Enterprise">
        <button id="send" class="composer-send" type="submit" aria-label="Отправить">&#10148;</button>
      </form>
    </div>
  </div>
  <script>
    const root = document.documentElement;
    const params = new URLSearchParams(window.location.search);
    const jobId = params.get("job_id") || "";
    const screen = document.getElementById("screen");
    const input = document.getElementById("cmd");
    let pollTimer = null;
    let pollFailures = 0;
    let wasAtBottom = true;
    function updateScreen(text, forceBottom = false) {
      const nearBottom = screen.scrollHeight - screen.scrollTop - screen.clientHeight < 48;
      screen.textContent = text;
      if (forceBottom || nearBottom || wasAtBottom) {
        screen.scrollTop = screen.scrollHeight;
      }
      wasAtBottom = screen.scrollHeight - screen.scrollTop - screen.clientHeight < 48;
    }
    function syncViewport() {
      const vv = window.visualViewport;
      const height = vv ? vv.height : window.innerHeight;
      const offsetTop = vv ? vv.offsetTop : 0;
      const keyboardOffset = Math.max(0, window.innerHeight - height - offsetTop);
      root.style.setProperty("--app-height", `${Math.max(320, Math.round(height + offsetTop))}px`);
      root.style.setProperty("--kb-offset", `${Math.round(keyboardOffset)}px`);
    }
    function pollJob() {
      if (!jobId) return;
      const xhr = new XMLHttpRequest();
      xhr.open("GET", `/enterprise-console/api/jobs/${encodeURIComponent(jobId)}`, true);
      xhr.setRequestHeader("Cache-Control", "no-store");
      xhr.onreadystatechange = function () {
        if (xhr.readyState !== 4) return;
        if (xhr.status < 200 || xhr.status >= 300) {
          pollFailures += 1;
          if (pollFailures >= 4 && document.activeElement !== input) {
            window.location.replace(window.location.href);
          }
          return;
        }
        try {
          const data = JSON.parse(xhr.responseText || "{}");
          if (!data.ok) return;
          pollFailures = 0;
          const header = `[codex live]\\n> ${data.command || ""}\\n[status] ${data.done ? "done" : "running"}${data.exit_code !== null && data.exit_code !== undefined ? ` | exit=${data.exit_code}` : ""}\\n\\n`;
          let text = header + ((data.events || []).join("\\n") || "[ожидание событий]");
          if (data.answer) text += `\\n\\n[final]\\n${data.answer}`;
          if (data.stderr) text += `\\n\\nSTDERR:\\n${data.stderr}`;
          updateScreen(text);
          if (data.done && pollTimer) {
            clearInterval(pollTimer);
            pollTimer = null;
          }
        } catch (_) {
          pollFailures += 1;
        }
      };
      try {
        xhr.send(null);
      } catch (_) {
        pollFailures += 1;
      }
    }
    if (window.visualViewport) {
      window.visualViewport.addEventListener("resize", syncViewport);
      window.visualViewport.addEventListener("scroll", syncViewport);
    }
    window.addEventListener("resize", syncViewport);
    screen.addEventListener("scroll", () => {
      wasAtBottom = screen.scrollHeight - screen.scrollTop - screen.clientHeight < 48;
    });
    setTimeout(() => {
      syncViewport();
      if (jobId) {
        pollJob();
        pollTimer = setInterval(pollJob, 900);
      }
    }, 0);
  </script>
</body>
</html>""".replace("__REFRESH_META__", refresh_meta).replace("__SCREEN_TEXT__", escaped_screen).replace("__PROMPT_VALUE__", escaped_prompt)


def run_enterprise_console_server(
    *,
    bridge: "TelegramBridge",
    secret: str,
    bind_host: str,
    port: int,
) -> None:
    class EnterpriseConsoleHandler(BaseHTTPRequestHandler):
        def _write_json(self, payload: Dict[str, object], status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _write_html(self, html_text: str, status: int = 200, *, set_auth_cookie: bool = False) -> None:
            body = html_text.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            if set_auth_cookie:
                self.send_header("Set-Cookie", f"enterprise_console_auth={secret}; Path=/; HttpOnly; SameSite=Lax")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _redirect(self, location: str, status: int = 303) -> None:
            self.send_response(status)
            self.send_header("Location", location)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()

        def _cookie_token(self) -> str:
            raw_cookie = self.headers.get("Cookie", "") or ""
            for part in raw_cookie.split(";"):
                name, _, value = part.strip().partition("=")
                if name == "enterprise_console_auth":
                    return value.strip()
            return ""

        def _is_local_request(self) -> bool:
            host = (self.headers.get("Host", "") or "").strip().lower()
            if host.startswith("127.0.0.1:") or host == "127.0.0.1":
                return True
            if host.startswith("localhost:") or host == "localhost":
                return True
            client_ip = (self.client_address[0] or "").strip()
            return client_ip in {"127.0.0.1", "::1"}

        def _authorized(self) -> bool:
            if self._is_local_request():
                return True
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query or "")
            query_token = query.get("token", [""])[0].strip()
            return query_token == secret or self._cookie_token() == secret

        def log_message(self, format: str, *args) -> None:
            return

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if not self._authorized():
                self._write_json({"ok": False, "error": "forbidden"}, status=403)
                return
            if parsed.path == "/enterprise-console":
                query = parse_qs(parsed.query or "")
                prompt = (query.get("prompt", [""])[0] or "").strip()
                job_id = (query.get("job_id", [""])[0] or "").strip()
                screen_text = "Готов. Пиши запрос."
                auto_refresh_seconds = 0
                if job_id:
                    snapshot = bridge.get_console_job_snapshot(job_id)
                    if snapshot is None:
                        screen_text = "Job не найден."
                    else:
                        live_lines = snapshot.get("events") or []
                        stderr = str(snapshot.get("stderr") or "")
                        answer = str(snapshot.get("answer") or "")
                        exit_code = snapshot.get("exit_code")
                        header = (
                            "[codex live]\n"
                            f"> {prompt or snapshot.get('command') or ''}\n"
                            f"[status] {'done' if snapshot.get('done') else 'running'}"
                            f"{f' | exit={exit_code}' if exit_code is not None else ''}\n\n"
                        )
                        screen_text = header + ("\n".join(str(line) for line in live_lines) or "[ожидание событий]")
                        if answer:
                            screen_text += f"\n\n[final]\n{answer}"
                        if stderr:
                            screen_text += f"\n\nSTDERR:\n{stderr}"
                self._write_html(
                    bridge.build_webapp_html(
                        screen_text=screen_text,
                        prompt_value="",
                        auto_refresh_seconds=auto_refresh_seconds,
                    ),
                    set_auth_cookie=True,
                )
                return
            if parsed.path.startswith("/enterprise-console/api/jobs/"):
                job_id = parsed.path.rsplit("/", 1)[-1]
                snapshot = bridge.get_console_job_snapshot(job_id)
                if snapshot is None:
                    self._write_json({"ok": False, "error": "not found"}, status=404)
                    return
                snapshot["ok"] = True
                self._write_json(snapshot)
                return
            self._write_json({"ok": False, "error": "not found"}, status=404)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if not self._authorized():
                self._write_json({"ok": False, "error": "forbidden"}, status=403)
                return
            content_length = int(self.headers.get("Content-Length", "0") or "0")
            raw = self.rfile.read(content_length) if content_length > 0 else b"{}"
            try:
                if "application/x-www-form-urlencoded" in (self.headers.get("Content-Type", "") or ""):
                    payload = {key: values[0] for key, values in parse_qs(raw.decode("utf-8") or "").items()}
                else:
                    payload = json.loads(raw.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                payload = {}
            if parsed.path == "/enterprise-console/submit":
                command = str(payload.get("command") or payload.get("cmd") or "").strip()
                if not command:
                    self._redirect("/enterprise-console")
                    return
                job_id = bridge.start_console_job(command)
                self._redirect(f"/enterprise-console?job_id={job_id}&prompt={quote_plus(command)}")
                return
            if parsed.path == "/enterprise-console/api/exec":
                command = str(payload.get("command") or "").strip()
                if not command:
                    self._write_json({"ok": False, "error": "empty prompt"}, status=400)
                    return
                self._write_json({"ok": True, "job_id": bridge.start_console_job(command)})
                return
            self._write_json({"ok": False, "error": "not found"}, status=404)

    server = ThreadingHTTPServer((bind_host, port), EnterpriseConsoleHandler)
    server.serve_forever()


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tg_codex_bridge import TelegramBridge
