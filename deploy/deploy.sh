#!/bin/bash
# ============================================================
# 抖音本地推 Agent — 腾讯云 Lighthouse 一键部署脚本
# 运行环境: Ubuntu 22.04 (2C2G)
# 运行前请确保: 代码已上传到 /opt/douyin-local-ad-agent/
# ============================================================

set -e

PROJECT_DIR="/opt/douyin-local-ad-agent"
SERVICE_NAME="douyin-dashboard"
PORT=8888

echo "========================================"
echo "  抖音本地推 Agent 部署脚本"
echo "========================================"
echo ""

# ---------- 检查项目目录 ----------
if [ ! -d "$PROJECT_DIR" ]; then
    echo "❌ 错误: 项目目录 $PROJECT_DIR 不存在"
    echo "   请先用 scp 把项目上传到服务器:"
    echo "   scp -r ~/Desktop/douyin-local-ad-agent root@你的IP:/opt/"
    exit 1
fi

cd "$PROJECT_DIR"

# ---------- 检查 .env ----------
if [ ! -f ".env" ]; then
    echo "❌ 错误: .env 文件不存在！"
    echo "   1. 在 Mac 上确认: ls ~/Desktop/douyin-local-ad-agent/.env"
    echo "   2. 重新打包并上传（.env 会被包含在 tar.gz 中）"
    exit 1
else
    # Set restrictive permissions on .env (contains API secrets)
    chmod 600 .env
    echo "   ✅ .env 已设置权限 (600)"
fi

# ---------- 检查 Python ----------
echo "[1/6] 检查 Python 环境..."
if ! command -v python3 &> /dev/null; then
    echo "   安装 Python3..."
    apt-get update -qq
    apt-get install -y -qq python3 python3-pip
fi
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "   ✅ Python $PYTHON_VERSION"

# ---------- 安装依赖 ----------
echo "[2/6] 安装 Python 依赖..."
if [ -f "requirements.txt" ]; then
    pip3 install -q -r requirements.txt
else
    pip3 install -q flask requests apscheduler pandas
fi
echo "   ✅ 依赖安装完成"

# ---------- 检查数据库 ----------
echo "[3/6] 检查数据库..."
if [ -f "data/ad_data.db" ]; then
    DB_SIZE=$(du -sh data/ad_data.db | awk '{print $1}')
    echo "   ✅ 数据库存在 ($DB_SIZE)"
else
    echo "   ⚠️ 数据库不存在，首次运行会自动创建"
fi

# ---------- 创建 systemd 服务 ----------
echo "[4/6] 创建 systemd 守护进程..."

cat > /etc/systemd/system/${SERVICE_NAME}.service << 'EOF'
[Unit]
Description=Douyin Local Ad Dashboard
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/douyin-local-ad-agent
Environment=PYTHONUNBUFFERED=1
Environment=LANG=en_US.UTF-8
ExecStart=/usr/bin/python3 /opt/douyin-local-ad-agent/ad.py 看板
Restart=always
RestartSec=10
StartLimitInterval=60
StartLimitBurst=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable ${SERVICE_NAME}
echo "   ✅ systemd 服务已创建并启用开机自启"

# ---------- 启动服务 ----------
echo "[5/6] 启动看板服务..."
systemctl stop ${SERVICE_NAME} 2>/dev/null || true
sleep 1
systemctl start ${SERVICE_NAME}
sleep 3

# 检查服务状态
if systemctl is-active --quiet ${SERVICE_NAME}; then
    echo "   ✅ 服务运行中"
else
    echo "   ❌ 服务启动失败，查看日志:"
    journalctl -u ${SERVICE_NAME} --no-pager -n 20
    exit 1
fi

# Health check
echo "   健康检查..."
sleep 2
HEALTH=$(curl -sf http://localhost:${PORT}/api/health 2>/dev/null || echo '{"status":"error"}')
if echo "$HEALTH" | grep -q '"status":"ok"'; then
    echo "   ✅ 健康检查通过"
else
    echo "   ⚠️  健康检查返回: $HEALTH"
fi

# Configure journald log limits
mkdir -p /etc/systemd/journald.conf.d/
cat > /etc/systemd/journald.conf.d/50-douyin.conf << 'JOURNALDEOF'
[Journal]
SystemMaxUse=500M
MaxRetentionSec=30day
JOURNALDEOF
systemctl restart systemd-journald 2>/dev/null || true
echo "   ✅ journald 日志限制已配置 (500MB/30天)"

# ---------- 显示访问信息 ----------
echo ""
echo "[6/6] 部署完成！"
echo ""
PUBLIC_IP=$(curl -s http://metadata.tencentyun.com/latest/meta-data/public-ipv4 2>/dev/null || echo "请查看腾讯云控制台")
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  公网 IP: $PUBLIC_IP"
echo "  看板地址: http://$PUBLIC_IP:${PORT}"
echo "  服务状态: systemctl status ${SERVICE_NAME}"
echo "  查看日志: journalctl -u ${SERVICE_NAME} -f"
echo "  重启服务: systemctl restart ${SERVICE_NAME}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "⚠️  重要提醒："
echo "   1. 请在腾讯云控制台 → 防火墙 → 添加规则: TCP ${PORT}"
echo "   2. 如果 .env 未上传，看板可以查看历史数据但无法同步新数据"
echo "   3. auth_code 每 30 天需更新一次，SSH 到服务器修改 .env 后重启服务"
echo ""
