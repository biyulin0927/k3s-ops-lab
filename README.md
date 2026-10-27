# k3s 涓€浣撳寲杩愮淮骞冲彴

鍦?2 鍙?2C2G 闃块噷浜?ECS 涓婃惌寤虹殑杞婚噺绾т笟鍔¤繍缁村钩鍙帮細k3s 闆嗙兢鎵胯浇 Flask + MySQL 涓氬姟锛岄厤濂?Ingress銆佺洃鎺у憡璀︺€佹棩蹇椾笌鏁呴殰婕旂粌銆?
> 杩欐槸涓€涓?*瀛︿範 + 绠€鍘?*椤圭洰锛岀洰鏍囨槸瀹屾暣璧颁竴閬嶃€岄儴缃?鈫?瑙傛祴 鈫?鏁呴殰 鈫?澶嶇洏銆嶇殑杩愮淮闂幆銆?
## 鏋舵瀯

```
寮€鍙戣€?push 鈹€鈹€鈻?GitHub Actions 鈹€鈹€鈻?闀滃儚浠撳簱(ghcr.io / ACR)
                                      鈹?kubectl set image
                                      鈻?鈹屸攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?鈹?k3s 闆嗙兢锛? 鑺傜偣锛?72.16.0.0/12锛?                         鈹?鈹?                                                         鈹?鈹? ns: demo                      ns: monitoring            鈹?鈹? 鈹屸攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹? 鈹屸攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?    鈹屸攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?           鈹?鈹? 鈹?web 脳2  鈹傗攢鈻垛攤 mysql    鈹?    鈹?Prometheus 鈹?           鈹?鈹? 鈹?Flask   鈹? 鈹?Stateful 鈹?    鈹?Alertmgr   鈹傗攢鈹€鈻?椋炰功    鈹?鈹? 鈹斺攢鈹€鈹€鈹€鈹攢鈹€鈹€鈹€鈹? 鈹斺攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?    鈹?Loki       鈹?           鈹?鈹?      鈹?                       鈹?Grafana    鈹?           鈹?鈹?      鈻?                       鈹斺攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?           鈹?鈹?  Traefik Ingress锛?0/443锛?                              鈹?鈹斺攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?```

## 鎶€鏈爤

| 绫诲埆 | 缁勪欢 |
|---|---|
| 瀹瑰櫒缂栨帓 | k3s v1.36.5锛圞ubernetes 杞婚噺鍙戣鐗堬級 |
| 鍏ュ彛 | Traefik Ingress Controller |
| 涓氬姟 | Python Flask + PyMySQL |
| 鏁版嵁搴?| MySQL 8.0锛圫tatefulSet + local-path 瀛樺偍锛?|
| 鐩戞帶 | Prometheus + Grafana + Alertmanager |
| 鏃ュ織 | Loki + Promtail |
| 閰嶇疆绠＄悊 | Ansible |
| 鑷姩鍖?| GitHub Actions |

## 鐜淇℃伅

| 瑙掕壊 | 涓绘満鍚?| 绉佺綉 IP | 鍏綉 IP |
|---|---|---|---|
| master | iz2vcih52kdnj152u1buo0z | 172.26.13.50 | 8.156.73.132 |
| worker | k3s-node1 | 172.26.13.51 | 8.156.68.82 |

- 鍦板煙锛氬崕涓?瑗垮崡锛坈n-chengdu锛?- 瑙勬牸锛? vCPU / 2 GiB锛孶buntu 22.04
- 闀滃儚鍔犻€燂細`/etc/rancher/k3s/registries.yaml`锛坉ocker.m.daocloud.io 绛夛級

## 杩涘害

- [x] 鍙岃妭鐐?k3s 闆嗙兢锛岃妭鐐?Ready
- [x] 閰嶇疆闀滃儚鍔犻€燂紝瑙ｅ喅 docker.io 瓒呮椂
- [x] Traefik Ingress 璐€氾紙nginx 楠岃瘉锛屾祻瑙堝櫒 200锛?- [x] Flask + MySQL 涓氬姟閮ㄧ讲锛坵eb:v1 闀滃儚锛? 鍓湰璺ㄨ妭鐐癸紝/api/time 杩斿洖鏁版嵁搴撴椂闂达級
- [x] GitHub Actions 鑷姩鍙戝竷锛坧ush 鈫?鏋勫缓 ghcr 闀滃儚 鈫?kubectl set image 婊氬姩鏇存柊 鈫?澶辫触鑷姩鍥炴粴锛?- [x] Prometheus + Grafana 鐩戞帶鐪嬫澘锛? 涓潰鏉匡細CPU / 鍐呭瓨 / 纾佺洏 / 缃戠粶 / QPS / P95 / Pod 閲嶅惎锛?- [x] 鍛婅閾捐矾锛圙rafana 鍛婅瑙勫垯 鈫?Webhook 鈫?Relay 鈫?閽夐拤锛? 鏉¤鍒欏凡瀹炴祴瑙﹀彂锛?- [ ] Loki 鏃ュ織鏌ヨ
- [ ] 6 绫绘晠闅滄紨缁冿紙瑙?`drills/`锛?
## 褰撳墠鐘舵€侊紙2026-10-26 鏀跺伐锛?
**宸插畬鎴?*

| 椤?| 璇存槑 |
|---|---|
| 闆嗙兢 | 2 鑺傜偣 k3s v1.36.5锛寃orker 2C4G |
| 涓氬姟 | Flask + MySQL锛? 鍓湰璺ㄨ妭鐐癸紝`/api/time` 姝ｅ父 |
| 鍏ュ彛 | Traefik Ingress锛宍pathType: Prefix` |
| 闀滃儚 | ghcr.io 鑷姩鏋勫缓锛宬3s 閰嶇疆浜?docker.io / registry.k8s.io 鍔犻€?|
| CI/CD | GitHub Actions 鍏ㄩ摼璺獙璇侀€氳繃锛坘ubeconfig 鐢?base64 瀛?Secret锛?|
| 鐩戞帶 | Prometheus + 鐙珛 Grafana锛圢odePort 30300锛夈€? 闈㈡澘鐪嬫澘 |
| 鍛婅 | Grafana 瑙勫垯 鈫?Webhook Relay 鈫?閽夐拤锛? 鏉¤鍒欏疄娴嬭Е鍙?鎭㈠ |
| 澶嶇洏 | `drills/00` Ingress 404銆乣drills/07` 鑺傜偣鍋滄満绾ц仈鏁呴殰 |

**杩涜涓?/ 寰呭鐞?*

1. **Loki 鏃ュ織**锛氭湭閮ㄧ讲锛孏rafana 閲岃繕娌℃湁鏃ュ織鏌ヨ鑳藉姏
2. **鏁呴殰婕旂粌**锛氳繕宸?5 涓紙纾佺洏鎵撴弧銆丳od OOM銆佽妭鐐瑰畷鏈恒€丮ySQL 涓嶅彲鐢ㄣ€侀暅鍍忔媺鍙栧け璐ワ級
3. **master 浠嶆槸 2C2G**锛氭殏涓嶇己鍐呭瓨锛屼絾婕旂粌鏃惰窇澶ч噺 Pod 鍙兘涓嶅
4. **6443 瀹夊叏缁?*锛欳I 楠岃瘉鍚庡簲鏀瑰洖 `118.113.89.85/32`
5. **GitHub Actions 閮ㄧ讲 job 浼氬け璐?*锛?443 鏈澶栧紑鏀撅紝灞為鏈燂紱瑕侀暱鏈熻嚜鍔ㄩ儴缃查渶鑷墭绠?Runner

**涓嬫寮€宸ラ『搴?*

1. 纭鐜锛歚kubectl get nodes`銆乣kubectl -n monitoring get pods`銆乣curl http://127.0.0.1/api/time`
2. 鍋氭晠闅滄紨缁冿紙姣忎釜璁颁笁涓椂闂寸偣锛氭敞鍏?/ 鍛婅 / 鎭㈠锛夛紝鍐欒繘 `drills/` 骞舵洿鏂?`婕旂粌璁板綍琛?md`
3. 瑁?Loki + Promtail锛孏rafana 鍔犳棩蹇楁暟鎹簮
4. 琛?README 鎴浘涓庢紨缁冩眹鎬伙紙骞冲潎鍙戠幇鏃堕棿銆丮TTR锛?
## 鐩綍缁撴瀯

```
k3s-ops-lab/
鈹溾攢鈹€ README.md
鈹溾攢鈹€ ansible/                  # 鑺傜偣鍒濆鍖?playbook
鈹溾攢鈹€ app/                      # 涓氬姟搴旂敤
鈹?  鈹溾攢鈹€ app.py                # Flask 鏈嶅姟锛?api/time 鏌?MySQL锛?鈹?  鈹溾攢鈹€ requirements.txt
鈹?  鈹溾攢鈹€ Dockerfile
鈹?  鈹斺攢鈹€ k8s/                  # K8s 娓呭崟
鈹溾攢鈹€ .github/workflows/        # CI/CD 娴佹按绾?鈹溾攢鈹€ monitoring/               # 鐩戞帶閰嶇疆
鈹?  鈹溾攢鈹€ values-prometheus.yaml
鈹?  鈹溾攢鈹€ alert-rules.yaml
鈹?  鈹溾攢鈹€ grafana-dashboard.json
鈹?  鈹斺攢鈹€ feishu-relay/         # 鍛婅杞彂鍒伴涔?鈹斺攢鈹€ drills/                   # 鏁呴殰婕旂粌涓庡鐩樿褰?```

## 鐩戞帶涓庡憡璀︽晥鏋?
Grafana 鐪嬫澘锛? 涓潰鏉匡紝鏁版嵁鏉ヨ嚜 Prometheus锛夛細

![Grafana 鐩戞帶鐪嬫澘](docs/grafana-dashboard.png)

鍛婅缁?Grafana 瑙勫垯 鈫?Webhook Relay 鈫?閽夐拤缇ゆ帹閫侊紝瑙﹀彂涓庢仮澶嶅悇鏈変竴娆￠€氱煡锛?
![閽夐拤鍛婅](docs/dingtalk-alert.png)

![閽夐拤鍛婅鎭㈠](docs/dingtalk-alert-resolved.png)

## 蹇€熷紑濮?
```bash
# 1. 閮ㄧ讲涓氬姟
kubectl apply -f app/k8s/

# 2. 楠岃瘉
curl http://<node-ip>/api/time

# 3. 瀹夎鐩戞帶锛堝緟瀹屾垚锛?helm install kube-prom prometheus-community/kube-prometheus-stack \
  -n monitoring --create-namespace -f monitoring/values-prometheus.yaml
```

## 鏁呴殰婕旂粌璁板綍

| 缂栧彿 | 涓婚 | 鐘舵€?|
|---|---|---|
| 00 | Ingress 404锛坧athType 涓嶅尮閰嶏級 | 鉁?|
| 01 | 鑺傜偣纾佺洏鎵撴弧 | 猬?|
| 02 | Pod OOM | 猬?|
| 03 | 鑺傜偣瀹曟満 | 猬?|
| 04 | MySQL 涓嶅彲鐢?| 猬?|
| 05 | 璇垹閰嶇疆 | 猬?|
| 06 | 闀滃儚鎷夊彇澶辫触 | 猬?|

## 澶囨敞

- 鏈」鐩负涓汉瀛︿範鐢ㄩ€旓紝鑺傜偣涓哄崟鐐?master锛屼笉鍏峰鐢熶骇楂樺彲鐢ㄨ兘鍔?- 瀛樺偍浣跨敤 local-path锛堟湰鍦扮洏锛夛紝鏁版嵁闅忚妭鐐逛涪澶憋紝鐢熶骇鐜搴斾娇鐢ㄤ簯鐩樻垨鍒嗗竷寮忓瓨鍌?