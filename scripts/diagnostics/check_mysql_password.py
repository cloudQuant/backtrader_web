"""尝试用不同密码连接本地 MySQL root 用户，找到可用密码。"""
import subprocess
import sys

CANDIDATES = [
    ("无密码", ""),
    ("19900404", "19900404"),
    ("759019", "759019"),
    ("199057", "199057"),
    ("19900507", "19900507"),
]

def try_password(label: str, pwd: str) -> bool:
    """用 mysql 客户端尝试连接，返回是否成功。"""
    cmd = ["mysql", "-u", "root", "-e", "SELECT 1;", "--connect-timeout=5"]
    if pwd:
        cmd.append(f"-p{pwd}")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except FileNotFoundError:
        print("❌ 本机未找到 mysql 客户端，请确认 MySQL 已安装并在 PATH 中。")
        sys.exit(1)
    except subprocess.TimeoutExpired:
        return False

def main():
    print("开始测试本地 MySQL root 密码...\n")
    found = False
    for label, pwd in CANDIDATES:
        ok = try_password(label, pwd)
        status = "✅ 成功" if ok else "❌ 失败"
        display = label if pwd else "(空密码)"
        print(f"  {display}: {status}")
        if ok:
            found = True
            print(f"\n🎉 可用密码: {label}")
            break
    if not found:
        print("\n⚠️ 所有候选密码均失败，请检查 MySQL 是否在运行或密码是否正确。")

if __name__ == "__main__":
    main()
