#!/bin/bash
# CTP代理绕过设置脚本
# 当macOS使用Clash/Surge等TUN模式代理时，CTP原生TCP连接会被拦截
# 此脚本为CTP服务器IP添加直连路由，绕过TUN代理
#
# 用法: sudo bash scripts/setup_ctp_proxy_bypass.sh

set -e

# 获取默认网关
GATEWAY=$(route -n get default 2>/dev/null | awk '/gateway:/{print $2}')
IFACE=$(route -n get default 2>/dev/null | awk '/interface:/{print $2}')

if [ -z "$GATEWAY" ]; then
    echo "错误: 无法获取默认网关"
    exit 1
fi

echo "默认网关: $GATEWAY ($IFACE)"
echo ""

# CTP SimNow 服务器IP列表
CTP_IPS=(
    "182.254.243.31"    # SimNow (包括7x24)
    "180.168.146.187"   # SimNow备用
    "218.202.237.33"    # SimNow备用
)

for IP in "${CTP_IPS[@]}"; do
    # 检查是否已有host路由
    EXISTING=$(route -n get "$IP" 2>/dev/null | awk '/interface:/{print $2}')
    if [ "$EXISTING" = "$IFACE" ]; then
        echo "✓ $IP 已通过 $IFACE 直连"
    else
        route -n add -host "$IP" "$GATEWAY" 2>/dev/null && \
            echo "✓ $IP -> $GATEWAY ($IFACE) 已添加" || \
            echo "⚠ $IP 路由添加失败 (可能已存在)"
    fi
done

echo ""
echo "完成! CTP服务器现在将绕过TUN代理直连。"
echo "注意: 此路由在系统重启后会丢失，需要重新运行。"
