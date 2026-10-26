# Ingress 404 排查记录

- **日期**：2026-10-24
- **环境**：k3s v1.36.5 双节点（master 172.26.13.50 / worker 172.26.13.51）
- **耗时**：约 40 分钟

## 现象

- `kubectl get pods` 中 web 的两个副本都是 `Running`，READY 1/1
- `kubectl get endpoints web` 有两个后端地址（10.42.1.154:80、10.42.2.30:80）
- `kubectl get ingress web` 的 CLASS 为 `traefik`，ADDRESS 已分配
- 但 `curl http://127.0.0.1` 返回 **404**

## 排查过程

1. `curl -i http://127.0.0.1 | head -12`
   确认 404 是 Traefik 返回的（不是后端应用返回的），说明请求已到达 Ingress 层。

2. `kubectl port-forward svc/web 8080:80` + `curl localhost:8080`
   返回 **200**，证明 Pod 与 Service 均正常 → 问题锁定在 Ingress/Traefik 路由层。

3. `kubectl get ingress web -o yaml`
   发现 `pathType: Exact`、`path: /*`（或 `/`）。

4. `kubectl -n kube-system logs deploy/traefik` 无路由匹配报错（默认 INFO 级别看不到匹配细节）。

## 根因

`kubectl create ingress` 自动生成的 `pathType` 为 **Exact**（路径含 `*` 时为 Prefix 但路径写成 `/*`），
导致对 `/` 及子路径的请求无法匹配 Traefik 生成的 router，返回默认 404。

## 解决

改为显式声明 `pathType: Prefix`、`path: /`：

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: web
  namespace: default
spec:
  ingressClassName: traefik
  rules:
    - http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: web
                port:
                  number: 80
```

`kubectl apply` 后 `curl` 返回 **200**，浏览器访问公网 IP 正常。

## 经验沉淀

- **排查顺序**：先判断 404 来源（Ingress 还是应用）→ 用 port-forward 绕过 Ingress 验证后端 → 再查 Ingress 配置
- `kubectl port-forward` 是把「Ingress 问题」与「应用问题」快速切割的关键手段
- `kubectl create ingress` 的默认 pathType 容易踩坑，生产环境应使用显式 YAML 而非命令行动态生成

## 同类问题速查

| 返回码 | 含义 | 排查方向 |
|---|---|---|
| 404 | Traefik 无匹配路由 | Ingress 的 host / path / pathType / class |
| 503 | 路由匹配但后端无可用 Pod | `kubectl get endpoints`、readiness 探针 |
| 502 | 后端连接被拒绝 | 容器端口与 Service targetPort 是否一致 |
| connection refused | 请求未到达 Traefik | svclb / Service / 安全组 |
