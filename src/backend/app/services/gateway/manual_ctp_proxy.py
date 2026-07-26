import logging
import os
import subprocess
import sys
from collections.abc import Callable
from typing import Any

from app.services.gateway import net_probe

_logger = logging.getLogger(__name__)


def count_utun_interfaces(
    *,
    run_command: Callable[..., Any] = subprocess.run,
    logger: logging.Logger = _logger,
) -> int | None:
    """Count active utun interfaces, preferring psutil over ifconfig."""
    try:
        import psutil

        return sum(1 for name in psutil.net_if_addrs() if name.startswith("utun"))
    except ImportError:
        pass
    except Exception:
        logger.debug("psutil-based utun interface count failed", exc_info=True)

    try:
        ifconfig = run_command(
            ["ifconfig"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return ifconfig.stdout.count("utun")
    except Exception:
        logger.debug("ifconfig-based utun interface count failed", exc_info=True)
        return None


def is_macos_tun_proxy_active(
    *,
    platform: str | None = None,
    count_interfaces: Callable[[], int | None] = count_utun_interfaces,
    run_command: Callable[..., Any] = subprocess.run,
) -> bool:
    """Detect if macOS has an active TUN transparent proxy."""
    if (platform or sys.platform) != "darwin":
        return False
    try:
        utun_count = count_interfaces()
        if utun_count is None or utun_count < 5:
            return False
        scutil = run_command(
            ["scutil", "--proxy"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return "HTTPEnable : 1" in scutil.stdout or "SOCKSEnable : 1" in scutil.stdout
    except Exception:
        return False


def get_macos_default_gateway(
    *,
    run_command: Callable[..., Any] = subprocess.run,
) -> tuple[str, str] | tuple[None, None]:
    """Return (gateway_ip, interface) for the default route on macOS."""
    try:
        result = run_command(
            ["route", "-n", "get", "default"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        gateway = interface = None
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if stripped.startswith("gateway:"):
                gateway = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("interface:"):
                interface = stripped.split(":", 1)[1].strip()
        if gateway is not None and interface is not None:
            return gateway, interface
        return None, None
    except Exception:
        return None, None


def check_route_goes_through_tun(
    ip: str,
    *,
    run_command: Callable[..., Any] = subprocess.run,
    logger: logging.Logger = _logger,
) -> bool:
    """Check if a specific IP is routed through a TUN interface."""
    try:
        result = run_command(
            ["route", "-n", "get", ip],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if stripped.startswith("interface:"):
                iface = stripped.split(":", 1)[1].strip()
                return iface.startswith("utun")
    except Exception:
        logger.debug("Route lookup for %s failed; assuming no TUN route", ip, exc_info=True)
    return False


def has_host_route(
    ip: str,
    expected_iface: str,
    *,
    run_command: Callable[..., Any] = subprocess.run,
) -> bool:
    """Check if a host-specific route exists for *ip* through *expected_iface*."""
    try:
        result = run_command(
            ["route", "-n", "get", ip],
            capture_output=True,
            text=True,
            timeout=5,
        )
        iface = None
        is_host = False
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if stripped.startswith("interface:"):
                iface = stripped.split(":", 1)[1].strip()
            if stripped.startswith("destination:") and ip in stripped:
                is_host = True
        return is_host and iface == expected_iface
    except Exception:
        return False


def add_direct_route_for_ip(
    ip: str,
    gateway: str,
    interface: str,
    logger: Any,
    *,
    has_route: Callable[[str, str], bool] = has_host_route,
    run_command: Callable[..., Any] = subprocess.run,
) -> bool:
    """Add a host route so *ip* bypasses TUN and uses the physical gateway."""
    if has_route(ip, interface):
        logger.debug("Host route for %s via %s already exists", ip, interface)
        return True

    strategies = [
        ["sudo", "-n", "route", "-n", "add", "-host", ip, gateway],
        [
            "osascript",
            "-e",
            f'do shell script "route -n add -host {ip} {gateway}" with administrator privileges',
        ],
        ["route", "-n", "add", "-host", ip, gateway],
    ]
    for cmd in strategies:
        try:
            result = run_command(cmd, capture_output=True, text=True, timeout=30)
            output = (result.stdout or "") + (result.stderr or "")
            if result.returncode == 0 or "already in table" in output.lower():
                logger.info("Added direct route for %s via %s", ip, gateway)
                return True
        except Exception:
            continue
    return False


def extract_ips_from_fronts(*fronts: str) -> list[str]:
    """Extract unique IP addresses from CTP front address strings."""
    return net_probe.extract_ips_from_fronts(*fronts)


def add_ips_to_proxy_bypass_file(ips: list[str], logger: Any) -> bool:
    """Add IPs to a proxy app user-defined direct/local bypass list."""
    home = os.path.expanduser("~")
    bypass_files = [
        os.path.join(home, "Library", "Application Support", "ViewTurbo", "user_local.txt"),
        os.path.join(home, "Library", "Application Support", "Clash Verge", "user_local.txt"),
    ]

    for fpath in bypass_files:
        if not os.path.isfile(fpath):
            continue
        try:
            existing = set()
            with open(fpath, encoding="utf-8") as fh:
                for line in fh:
                    stripped = line.strip()
                    if stripped:
                        existing.add(stripped)

            to_add = [ip for ip in ips if ip not in existing]
            if not to_add:
                logger.debug("CTP IPs already in %s", fpath)
                return True

            with open(fpath, "a", encoding="utf-8") as fh:
                for ip in to_add:
                    fh.write(f"{ip}\n")
            logger.info("Added CTP server IPs to proxy direct list %s: %s", fpath, to_add)
            return True
        except Exception as exc:
            logger.debug("Failed to update %s: %s", fpath, exc)
    return False


def find_clash_external_controller() -> tuple[str, str] | tuple[None, None]:
    """Find Clash external controller (host:port) and secret from config files."""
    home = os.path.expanduser("~")
    config_dirs = [
        os.path.join(home, ".config", "clash"),
        os.path.join(home, ".config", "mihomo"),
    ]
    app_support = os.path.join(home, "Library", "Application Support")
    try:
        for entry in os.listdir(app_support):
            if "clash" in entry.lower() or "mihomo" in entry.lower():
                config_dirs.append(os.path.join(app_support, entry))
    except OSError:
        pass

    for dirname in config_dirs:
        for fname in ("config.yaml", "verge.yaml", "clash.yaml"):
            fpath = os.path.join(dirname, fname)
            if not os.path.isfile(fpath):
                continue
            try:
                with open(fpath, encoding="utf-8") as fh:
                    content = fh.read(16384)
                port = secret = None
                for line in content.splitlines():
                    stripped = line.strip()
                    if stripped.startswith("external-controller:"):
                        port = stripped.split(":", 2)[-1].strip().strip("'\"")
                    elif stripped.startswith("secret:"):
                        secret = stripped.split(":", 1)[1].strip().strip("'\"")
                if port:
                    host_port = port if ":" in port else f"127.0.0.1:{port}"
                    return f"http://{host_port}", secret or ""
            except Exception:
                continue

    for probe_port in (9090, 9097, 19090):
        try:
            import urllib.request

            req = urllib.request.Request(
                f"http://127.0.0.1:{probe_port}/version",
                headers={"User-Agent": "ai-for-investor"},
            )
            resp = urllib.request.urlopen(req, timeout=2)
            if resp.status == 200:
                return f"http://127.0.0.1:{probe_port}", ""
        except Exception:
            continue
    return None, None


def clash_api_add_direct_rules(
    ips: list[str],
    logger: Any,
    *,
    find_controller: Callable[
        [], tuple[str, str] | tuple[None, None]
    ] = find_clash_external_controller,
) -> bool:
    """Try to add DIRECT rules for IPs via Clash external controller API."""
    base_url, secret = find_controller()
    if not base_url:
        return False

    import json as _json
    import urllib.request

    headers = {"Content-Type": "application/json", "User-Agent": "ai-for-investor"}
    if secret:
        headers["Authorization"] = f"Bearer {secret}"

    for ip in ips:
        payload = _json.dumps({"payload": f"IP-CIDR,{ip}/32,DIRECT,no-resolve"}).encode()
        try:
            req = urllib.request.Request(
                f"{base_url}/rules/prepend",
                data=payload,
                headers=headers,
                method="POST",
            )
            urllib.request.urlopen(req, timeout=3)
            logger.info("Clash API: added DIRECT rule for %s", ip)
        except Exception:
            try:
                req = urllib.request.Request(
                    f"{base_url}/rules",
                    data=_json.dumps(
                        {
                            "prepend": [f"IP-CIDR,{ip}/32,DIRECT,no-resolve"],
                        }
                    ).encode(),
                    headers=headers,
                    method="PATCH",
                )
                urllib.request.urlopen(req, timeout=3)
                logger.info("Clash API (PATCH): added DIRECT rule for %s", ip)
            except Exception as exc:
                logger.debug("Clash API rule add failed for %s: %s", ip, exc)
                return False
    return True


def ensure_ctp_direct_routes(
    td_front: str,
    md_front: str,
    logger: Any,
    *,
    is_tun_proxy_active: Callable[[], bool] = is_macos_tun_proxy_active,
    extract_ips: Callable[..., list[str]] = extract_ips_from_fronts,
    add_bypass_file: Callable[[list[str], Any], bool] = add_ips_to_proxy_bypass_file,
    add_clash_rules: Callable[[list[str], Any], bool] = clash_api_add_direct_rules,
    get_default_gateway: Callable[
        [], tuple[str, str] | tuple[None, None]
    ] = get_macos_default_gateway,
    add_direct_route: Callable[[str, str, str, Any], bool] = add_direct_route_for_ip,
) -> None:
    """Bypass active TUN proxy routes for CTP server IPs."""
    if not is_tun_proxy_active():
        return

    ips = extract_ips(td_front, md_front)
    if not ips:
        return

    logger.info("检测到TUN代理(Clash/Surge/ViewTurbo等)，尝试为CTP服务器IP绕过代理: %s", ips)

    if add_bypass_file(ips, logger):
        logger.info("已将CTP IP写入代理直连列表（可能需要重启代理软件生效）")

    if add_clash_rules(ips, logger):
        logger.info("已通过Clash API为CTP添加DIRECT规则")
        return

    gateway, interface = get_default_gateway()
    if not gateway:
        logger.warning(
            "检测到TUN代理拦截CTP流量，但无法获取默认网关。请手动运行: %s",
            " && ".join(f"sudo route add -host {ip} <网关IP>" for ip in ips),
        )
        return

    logger.info("Clash API不可用，尝试添加直连路由: %s -> %s (%s)", ips, gateway, interface)
    failed_ips: list[str] = []
    for ip in ips:
        if not add_direct_route(ip, gateway, interface or "en0", logger):
            failed_ips.append(ip)

    if failed_ips:
        cmds = " && ".join(f"sudo route add -host {ip} {gateway}" for ip in failed_ips)
        logger.warning(
            "无法自动添加CTP直连路由(需要sudo权限)。请手动执行: %s",
            cmds,
        )


def maybe_tunnel_ctp_fronts(
    td_front: str,
    md_front: str,
    logger: Any,
    *,
    parse_front: Callable[[str], tuple[str, int] | tuple[None, None]],
    ensure_tunnel: Callable[[str, int], int],
    is_proxy_tunnel_needed: Callable[[], bool],
) -> tuple[str, str]:
    """Create HTTP CONNECT tunnels for CTP fronts when a system proxy is active."""
    if not is_proxy_tunnel_needed():
        return td_front, md_front

    logger.info("检测到系统HTTP代理，创建HTTP CONNECT隧道以绕过CTP流量拦截")

    def _rewrite(front: str) -> str:
        host, port = parse_front(front)
        if not host or not port:
            return front
        try:
            local_port = ensure_tunnel(host, port)
            rewritten = f"tcp://127.0.0.1:{local_port}"
            logger.info(
                "CTP隧道: %s -> CONNECT %s:%d via proxy -> %s",
                rewritten,
                host,
                port,
                front,
            )
            return rewritten
        except Exception as exc:
            logger.warning("创建CTP隧道失败(%s:%d): %s, 使用原始地址", host, port, exc)
            return front

    return _rewrite(td_front), _rewrite(md_front)


def detect_system_tun_proxy(
    *,
    is_tun_proxy_active: Callable[[], bool] = is_macos_tun_proxy_active,
) -> str | None:
    """Return a user-facing hint if TUN proxy is active, else None."""
    if is_tun_proxy_active():
        return (
            "检测到系统代理(Clash/Surge/ViewTurbo等)可能拦截了CTP的TCP流量。"
            "CTP使用原生TCP连接，透明代理无法解析其二进制协议。"
            "系统已自动通过HTTP CONNECT隧道转发CTP流量。"
            "如仍无法连接，请检查代理软件是否允许CONNECT方法。"
        )
    return None
