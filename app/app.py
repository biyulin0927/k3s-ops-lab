"""演示业务：Flask + MySQL，提供 /api/time 与 /metrics。

部署到 k3s 的 demo 命名空间，供监控与故障演练使用。
"""

import os
import time

import pymysql
from flask import Flask, jsonify
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

app = Flask(__name__)

REQ = Counter("http_requests_total", "Total requests", ["path", "status"])
LAT = Histogram("http_request_duration_seconds", "Request latency", ["path"])

DB = dict(
    host=os.getenv("DB_HOST", "mysql"),
    user=os.getenv("DB_USER", "app"),
    password=os.getenv("DB_PASSWORD", "app123456"),
    database=os.getenv("DB_NAME", "demo"),
    connect_timeout=2,
)


def query():
    conn = pymysql.connect(**DB)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT NOW()")
            return cur.fetchone()[0]
    finally:
        conn.close()


@app.route("/healthz")
def healthz():
    """存活探针：只证明进程还在，不查依赖。"""
    return "ok"


@app.route("/readyz")
def readyz():
    """就绪探针：真查一次数据库。

    04 号演练暴露的问题：MySQL 挂了，web 仍然是 Ready，
    k8s 和 Ingress 都不知道后端已经废了，用户拿到的是 500。
    改成查库之后，DB 不可用时 Pod 会变 NotReady，Ingress 摘掉后端，
    调用方看到的是 503（明确"暂时不可用"），而不是应用层 500。
    """
    try:
        query()
        return "ok"
    except Exception as exc:  # noqa: BLE001
        return f"db unavailable: {exc}", 503


@app.route("/metrics")
def metrics():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


@app.route("/api/time")
def api_time():
    start = time.time()
    try:
        now = query()
        REQ.labels("/api/time", "200").inc()
        return jsonify({"db_time": str(now), "host": os.uname().nodename})
    except Exception as exc:  # noqa: BLE001
        REQ.labels("/api/time", "500").inc()
        return jsonify({"error": str(exc)}), 500
    finally:
        LAT.labels("/api/time").observe(time.time() - start)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
