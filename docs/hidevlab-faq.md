# HiDevLab 官方 QA 整理（2026-08-01，飞书群官方发布）

> 来源：面壁大赛群官方 QA 整理文档。全部问题 + 官方回答 + 排查建议。
> 影响我们准备的关键点：
> 1. 环境路径 /workspace/user_data（挂载目录，持久化；实测，旧文档 /home/ma-user/work/user_data/ 已废弃）
> 2. shared_assets/ 官方共享空间——重要数据建议双备份
> 3. CANN 可能预装 9.0.0，需自行升级 9.1.0-beta1（run 包 --upgrade）
> 4. SSH 直连存在（管理页面拿环境 IP，ssh user@<IP>）——scp/rsync 可能可用
> 5. 平台需外网/蓝区访问（内网工作站访问可能 403）

## 环境关键信息

- user_data 路径：/workspace/user_data（实测）
- shared_assets 路径：官方共享空间（重要数据备份推荐位置）
- CANN 版本确认：echo $ASCEND_TOOLKIT_HOME（实测 cann-9.1.0-beta.3）；或 cat $ASCEND_TOOLKIT_HOME/version.cfg
- 架构确认：uname -a（aarch64 / x86_64）
- 环境状态：管理页面查看（运行中/创建中/异常/已删除）
- 卡时：1NPU=100h、2NPU=50h、4NPU=25h（Q15 再次确认）

## CANN 9.0.0 → 9.1.0-beta1 升级（Q8 官方步骤）

1. uname -a 确认架构（aarch64/x86_64）
2. https://www.hiascend.com/developer/download/community/result?module=cann&cann=9.0.0 下载 run 包
3. chmod +x xxx.run
4. ./xxx.run --upgrade
5. 出现 [xxx upgrade success] 即成功（升/降版本均此法）
6. 验证：python -c "import acl; print('ACL OK')"

## 常见故障速查

| 症状 | 处理 |
|---|---|
| user_data 丢失/空 | df -h 查挂载；ls -la /workspace/user_data/；确认环境未被删除；dmesg 查存储错误；联系官方（记录环境名+公网IP） |
| GlusterFS 故障 | mount | grep gluster；docker ps -a；mount -a 重挂载；联系官方 |
| WebIDE 403 | 确认外网/蓝区访问；无痕模式；清缓存；关代理/VPN；换浏览器；提供公网IP+参赛信息 |
| 418 | 提供公网IP+环境名联系官方 |
| 502/白屏 | Ctrl+F5；等 1-2 分钟；查环境状态；持续则联系官方 |
| SSH 无法解析主机名 | 确认环境运行中；cat ~/.ssh/config；用 IP 直连（ssh user@<IP>）；nslookup；ssh -V；联系官方 |
| VSCode TLS 断连 | 换网络；更新 VSCode/Remote-SSH；ssh -v 看日志；关防火墙/代理；SSH 配置加 ServerAliveInterval 60 |
| 连接一直转圈 | 等 3-5 分钟；取消重连；换连接方式；查环境状态 |
| 4 卡环境创建慢 | 多卡调度慢正常，等 5-10 分钟；配额不足会失败；开发用 1 卡省卡时 |
| 驱动不识别 | npu-smi info；dmesg | grep -i ascend；查 CANN/驱动兼容；重创环境；工单 |
| 环境删不掉/卡异常 | 强刷页面；清缓存；ping 环境IP；换连接方式；联系官方删除 |

## 工单渠道

容器内问题（如驱动不识别）经排查无效且不想删容器 → 右侧【在线工单】由内部人员处理

## 预防建议（官方）

- 重要数据同步保存到 shared_assets/ 共享空间，避免仅依赖 user_data
- 开发阶段先用 1 卡环境，多卡测试再开 4 卡（省卡时）
- 关键权重和数据及时备份
