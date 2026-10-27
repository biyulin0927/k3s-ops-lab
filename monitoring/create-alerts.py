"""通过 Grafana HTTP API 创建 钉钉联系人 + 告警规则 + 通知策略。

用法（在 master 上）：
    export GRAFANA_URL=http://127.0.0.1:30300
    export GRAFANA_USER=admin
    export GRAFANA_PASS=admin123
    python3 create-alerts.py

只依赖标准库。可重复执行（已存在会更新）。
"""

import base64
import json
import os
import urllib.error
import urllib.request

URL = os.environ.get("GRAFANA_URL", "http://127.0.0.1:30300").rstrip("/")
USER = os.environ.get("GRAFANA_USER", "admin")
PASS = os.environ.get("GRAFANA_PASS", "admin123")
AUTH = base64.b64encode(f"{USER}:{PASS}".encode()).decode()
WEBHOOK = "http://feishu-relay.default.svc.cluster.local:8080/alert"
FOLDER = "k3s-alerts"
GROUP = "k3s-alerts"


def call(method: str, path: str, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        f"{URL}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Basic {AUTH}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode()
            try:
                return resp.status, (json.loads(body) if body else {})
            except json.JSONDecodeError:
                return resp.status, body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        return exc.code, body


def _find_folder() -> dict | None:
    code, folders = call("GET", "/api/folders?limit=1000")
    if code == 200 and isinstance(folders, list):
        for f in folders:
            if f.get("title") == FOLDER:
                return f
    return None


def ensure_folder() -> str:
    found = _find_folder()
    if found:
        print(f"[folder] 已存在 uid={found['uid']}")
        return found["uid"]

    code, res = call("POST", "/api/folders", {"title": FOLDER})
    if code in (200, 201) and isinstance(res, dict) and "uid" in res:
        print(f"[folder] 已创建 uid={res['uid']}")
        return res["uid"]

    found = _find_folder()
    if found:
        print(f"[folder] 已存在 uid={found['uid']}")
        return found["uid"]
    raise SystemExit(f"[folder] 创建失败 {code} {res}")


def ensure_contact_point() -> None:
    payload = {
        "name": "dingtalk",
        "type": "webhook",
        "disableResolveMessage": False,
        "settings": {"url": WEBHOOK, "httpMethod": "POST"},
    }
    code, res = call("POST", "/api/v1/provisioning/contact-points", payload)
    if code == 409:
        # 已存在则先查 uid 再 PUT 更新
        code2, cps = call("GET", "/api/v1/provisioning/contact-points")
        for cp in cps if isinstance(cps, list) else []:
            if cp.get("name") == "dingtalk":
                payload["uid"] = cp["uid"]
                code, res = call("PUT", f"/api/v1/provisioning/contact-points/{cp['uid']}", payload)
                break
    print(f"[contact] dingtalk -> {code}")


def rule(title, expr, threshold, dur, severity, summary, ref_range=600) -> dict:
    return {
        "title": title,
        "ruleGroup": GROUP,
        "condition": "C",
        "noDataState": "OK",
        "execErrState": "Error",
        "for": dur,
        "orgID": 1,
        "labels": {"severity": severity},
        "annotations": {"summary": summary},
        "data": [
            {
                "refId": "A",
                "relativeTimeRange": {"from": ref_range, "to": 0},
                "datasourceUid": "prometheus",
                "model": {
                    "editorMode": "code",
                    "expr": expr,
                    "instant": True,
                    "range": False,
                    "intervalMs": 1000,
                    "maxDataPoints": 43200,
                    "refId": "A",
                },
            },
            {
                "refId": "C",
                "datasourceUid": "__expr__",
                "model": {
                    "conditions": [
                        {
                            "evaluator": {"params": [threshold], "type": "gt"},
                            "operator": {"type": "and"},
                            "query": {"params": ["A"]},
                            "reducer": {"params": [], "type": "last"},
                            "type": "query",
                        }
                    ],
                    "datasource": {"type": "__expr__", "uid": "__expr__"},
                    "expression": "A",
                    "refId": "C",
                    "type": "threshold",
                },
            },
        ],
    }


RULES = [
    rule(
        "节点内存使用率过高",
        '(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100',
        85, "2m", "warning",
        "节点 {{ $labels.instance }} 内存使用率超过 85%",
    ),
    rule(
        "节点磁盘使用率过高",
        '(1 - node_filesystem_avail_bytes{mountpoint="/",fstype!="tmpfs"} '
        '/ node_filesystem_size_bytes{mountpoint="/",fstype!="tmpfs"}) * 100',
        85, "5m", "warning",
        "节点 {{ $labels.instance }} 根分区使用率超过 85%",
    ),
    rule(
        "Pod 频繁重启",
        'increase(kube_pod_container_status_restarts_total{namespace="demo"}[10m])',
        3, "1m", "critical",
        "Pod {{ $labels.namespace }}/{{ $labels.pod }} 10 分钟内重启超过 3 次",
    ),
    rule(
        "应用 5xx 比例过高",
        'sum(rate(http_requests_total{status="500"}[5m])) / sum(rate(http_requests_total[5m])) * 100',
        20, "1m", "critical",
        "应用 5xx 请求占比超过 20%",
        300,
    ),
]


def main() -> None:
    print(f"[grafana] {URL}")
    uid = ensure_folder()
    ensure_contact_point()

    code, existing = call("GET", "/api/v1/provisioning/alert-rules")
    by_title = {
        r["title"]: r["uid"] for r in existing
    } if isinstance(existing, list) else {}

    for r in RULES:
        r["folderUID"] = uid
        if r["title"] in by_title:
            code, res = call(
                "PUT", f"/api/v1/provisioning/alert-rules/{by_title[r['title']]}", r
            )
            print(f"[rule] 更新 {r['title']} -> {code}")
        else:
            code, res = call("POST", "/api/v1/provisioning/alert-rules", r)
            print(f"[rule] 创建 {r['title']} -> {code}")
            if code not in (200, 201):
                print(f"       {res}")

    policy = {
        "route": {
            "receiver": "dingtalk",
            "group_by": ["alertname"],
            "group_wait": "30s",
            "group_interval": "1m",
            "repeat_interval": "4h",
        }
    }
    code, res = call("PUT", "/api/v1/provisioning/policies", policy)
    print(f"[policy] 通知策略 -> dingtalk : {code}")

    code, cps = call("GET", "/api/v1/provisioning/contact-points")
    print(f"[check] 联系人数 {len(cps) if isinstance(cps, list) else '?'}")
    code, rules = call("GET", "/api/v1/provisioning/alert-rules")
    print(f"[check] 规则数 {len(rules) if isinstance(rules, list) else '?'}")


if __name__ == "__main__":
    main()
