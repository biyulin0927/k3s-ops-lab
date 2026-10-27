"""Alertmanager → 飞书（或钉钉）告警转发。

只用标准库，容器启动即用，不需要 pip install。
环境变量 FEISHU_WEBHOOK 必填，形如：
    https://open.feishu.cn/open-apis/bot/v2/hook/xxxx
如果用的是钉钉机器人，改 DINGTALK=1，payload 会自动换成钉钉格式。
"""

import json
import os
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

WEBHOOK = os.environ["FEISHU_WEBHOOK"]
IS_DINGTALK = os.environ.get("DINGTALK") == "1"
LEVEL_ICON = {"critical": "🔴", "warning": "🟠", "info": "🔵"}


def render(alert: dict) -> str:
    status = alert.get("status", "firing")
    icon = "✅" if status == "resolved" else LEVEL_ICON.get(
        alert.get("labels", {}).get("severity", ""), "🔵"
    )
    labels = alert.get("labels", {})
    annotations = alert.get("annotations", {})
    target = labels.get("pod") or labels.get("instance") or labels.get("node") or "-"
    return (
        f"【运维告警】{icon} {labels.get('alertname', '未知告警')}\n"
        f"状态：{'已恢复' if status == 'resolved' else '触发中'}\n"
        f"对象：{target}\n"
        f"命名空间：{labels.get('namespace', '-')}\n"
        f"详情：{annotations.get('summary', '-')}\n"
        f"时间：{alert.get('startsAt', '')[:19]}"
    )


def send(text: str) -> None:
    if IS_DINGTALK:
        payload = {"msgtype": "text", "text": {"content": text}}
    else:
        payload = {"msg_type": "text", "content": {"text": text}}
    req = urllib.request.Request(
        WEBHOOK,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        print(f"[relay] sent, status={resp.status}", flush=True)


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            data = json.loads(body or b"{}")
            alerts = data.get("alerts", [])
            print(f"[relay] received {len(alerts)} alert(s)", flush=True)
            for alert in alerts:
                send(render(alert))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
        except Exception as exc:  # noqa: BLE001
            print(f"[relay] ERROR {exc}", flush=True)
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(exc).encode())

    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"relay ok")

    def log_message(self, *args):  # 静音默认访问日志
        pass


if __name__ == "__main__":
    print("[relay] listening on 0.0.0.0:8080", flush=True)
    HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
