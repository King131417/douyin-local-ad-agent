"""
Douyin Local Ad Agent — CLI Entry Point

Usage:
  python main.py dashboard    Start the web dashboard
  python main.py auth         授权向导 (获取授权链接 + 换取Token)
  python main.py sync         Run daily data sync
  python main.py backfill 30  Backfill 30 days of data
  python main.py query "昨天的ROI怎么样？"
  python main.py report       Generate daily report
  python main.py alerts       Check and push alerts
"""

import argparse
import logging
import os
import sys
from datetime import date, timedelta
from pathlib import Path

# Load .env before importing config
def _load_dotenv():
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip("\"'")
            if key not in os.environ:
                os.environ[key] = val

_load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")


def cmd_auth(args):
    """Authorization wizard for Ocean Engine."""
    from config.settings import OCEAN_ENGINE_APP_ID, OCEAN_ENGINE_SECRET, OCEAN_ENGINE_AUTH_CODE

    if not OCEAN_ENGINE_APP_ID or not OCEAN_ENGINE_SECRET:
        print("[错误] 请先在 .env 中配置 OCEAN_ENGINE_APP_ID 和 OCEAN_ENGINE_SECRET")
        return

    from src.api.auth import AuthManager

    if args.code:
        # Exchange auth_code for token
        print(f"正在用授权码换取 Access Token...")
        os.environ["OCEAN_ENGINE_AUTH_CODE"] = args.code
        auth = AuthManager()
        try:
            token = auth.get_token()
            print(f"\n✅ 授权成功！")
            print(f"   Access Token: {token[:20]}...")
            print(f"   广告主ID: {auth.advertiser_ids}")
            print(f"\n请在 .env 中将 OCEAN_ENGINE_AUTH_CODE 填入，然后运行: python main.py sync")
        except Exception as e:
            print(f"\n❌ 授权失败: {e}")
        return

    if OCEAN_ENGINE_AUTH_CODE:
        # Try to exchange existing auth_code
        print("检测到 .env 中已有授权码，尝试换取 Token...")
        auth = AuthManager()
        try:
            token = auth.get_token()
            print(f"✅ Token 获取成功！")
            print(f"   广告主ID: {auth.advertiser_ids}")
        except Exception as e:
            print(f"❌ Token 换取失败: {e}")
            print("   授权码可能已过期，请重新获取。\n")
        return

    # No auth_code, show the authorization URL
    auth_url = AuthManager.get_auth_url()
    print("=" * 60)
    print("  巨量引擎 OAuth2 授权向导")
    print("=" * 60)
    print()
    print(f"  📋 App ID: {OCEAN_ENGINE_APP_ID}")
    print()
    print("  请按以下步骤操作：")
    print()
    print("  1️⃣  在浏览器中打开下方授权链接：")
    print()
    print(f"  {auth_url}")
    print()
    print("  2️⃣  登录巨量引擎账号，选择要授权的广告主账户")
    print("  3️⃣  授权后页面会跳转到回调地址")
    print("      从地址栏中复制 auth_code 参数的值")
    print()
    print("  4️⃣  运行以下命令完成授权：")
    print()
    print("       python main.py auth --code <auth_code>")
    print()
    print("=" * 60)
    print()
    print("  💡 也可以直接编辑 .env 文件：")
    print("     OCEAN_ENGINE_AUTH_CODE=<你的auth_code>")
    print("     然后运行 python main.py auth")


def cmd_dashboard(args):
    """Start the web dashboard."""
    from src.web.app import start_dashboard
    start_dashboard(port=args.port, debug=args.debug)


def cmd_sync(args):
    """Run daily data sync."""
    from src.pipeline.etl import ETLPipeline
    pipeline = ETLPipeline()

    if args.date:
        target = date.fromisoformat(args.date)
        count = pipeline.run_daily_sync(target)
    else:
        count = pipeline.run_daily_sync()

    print(f"Synced {count} rows")


def cmd_backfill(args):
    """Backfill historical data."""
    from src.pipeline.etl import ETLPipeline
    pipeline = ETLPipeline()
    count = pipeline.run_backfill(days=args.days)
    print(f"Backfilled {count} rows over {args.days} days")


def cmd_query(args):
    """Process a natural language query."""
    from src.agent.agent import AdAgent
    agent = AdAgent()
    response = agent.query(args.text)
    print(response)


def cmd_report(args):
    """Generate a report."""
    from src.agent.agent import AdAgent
    agent = AdAgent()

    if args.weekly:
        report = agent.generate_weekly_report()
        filename = f"周报_{date.today().strftime('%Y%m%d')}.md"
    else:
        report = agent.generate_daily_report()
        filename = f"日报_{date.today().strftime('%Y%m%d')}.md"

    from config.settings import OUTPUTS_DIR
    filepath = OUTPUTS_DIR / filename
    filepath.write_text(report, encoding="utf-8")
    print(f"Report saved to: {filepath}")
    print(report)


def cmd_alerts(args):
    """Check and push alerts."""
    from src.agent.agent import AdAgent
    agent = AdAgent()
    agent.push_alerts()
    print("Alert check complete")


# ── CLI ───────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="抖音来客本地推投流数据分析及优化Agent"
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # auth
    p_auth = subparsers.add_parser("auth", help="授权向导")
    p_auth.add_argument("--code", type=str, help="授权码 (auth_code)")
    p_auth.set_defaults(func=cmd_auth)

    # dashboard
    p_dash = subparsers.add_parser("dashboard", help="启动数据看板")
    p_dash.add_argument("--port", type=int, default=8888, help="端口号")
    p_dash.add_argument("--debug", action="store_true", help="调试模式")
    p_dash.set_defaults(func=cmd_dashboard)

    # sync
    p_sync = subparsers.add_parser("sync", help="同步每日数据")
    p_sync.add_argument("--date", type=str, help="指定日期 YYYY-MM-DD")
    p_sync.set_defaults(func=cmd_sync)

    # backfill
    p_back = subparsers.add_parser("backfill", help="回填历史数据")
    p_back.add_argument("days", type=int, nargs="?", default=30, help="回填天数")
    p_back.set_defaults(func=cmd_backfill)

    # query
    p_query = subparsers.add_parser("query", help="自然语言查询")
    p_query.add_argument("text", type=str, help="查询内容")
    p_query.set_defaults(func=cmd_query)

    # report
    p_report = subparsers.add_parser("report", help="生成日报/周报")
    p_report.add_argument("--weekly", action="store_true", help="生成周报")
    p_report.set_defaults(func=cmd_report)

    # alerts
    p_alerts = subparsers.add_parser("alerts", help="检查异常并推送告警")
    p_alerts.set_defaults(func=cmd_alerts)

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()
