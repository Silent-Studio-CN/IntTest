#!/usr/bin/env python3
"""网络测试工作线程 — 多流并发、跨平台、接口感知"""

import time
import os
import re
import threading
import subprocess
import platform
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Optional

import requests
import psutil
import logging
from PySide6.QtCore import QThread, Signal
from app.core.config import get_headers

log = logging.getLogger("IntTest")

# ── 常量 ───────────────────────────────────────────────────────
DOWNLOAD_URLS = [
    # 海外线路
    ("Tele2 (欧洲)", "http://speedtest.tele2.net/100MB.zip"),
    ("OVH (欧洲)", "https://proof.ovh.net/files/100Mb.dat"),
    ("ThinkBroadband (英国)", "http://ipv4.download.thinkbroadband.com/100MB.zip"),
    # 国内线路
    ("腾讯云 (国内)", "https://dldir1.qq.com/qqfile/qq/PCQQ9.7.17/QQ9.7.17.29225.exe"),
    ("浙江大学 (教育网)", "http://speedtest.zju.edu.cn/1000M"),
    ("Cloudflare (全球)", "https://speed.cloudflare.com/__down?during=download&bytes=104857600"),
]
UPLOAD_URL = "http://speedtest.tele2.net/upload.php"
PING_TARGETS = [
    ("百度", "www.baidu.com"),
    ("腾讯", "www.qq.com"),
    ("阿里", "www.aliyun.com"),
    ("GitHub", "github.com"),
    ("谷歌", "www.google.com"),
]

# IP 信息查询 API（多路备用）
IP_APIS = [
    ("https://api.ip.sb/geoip", "ip.sb"),
    ("https://ip-api.com/json/?fields=query,city,country,countryCode,isp,org,as,asname", "ip-api"),
    ("https://ipinfo.io/json", "ipinfo"),
]
IPV4_APIS = ["https://api-ipv4.ip.sb/ip", "https://api4.ipify.org"]
IPV6_APIS = ["https://api-ipv6.ip.sb/ip", "https://api6.ipify.org"]
IP_ISP_API = "https://whois.pconline.com.cn/ipJson.jsp?json=true"

# 下载/上传并发流数
NUM_STREAMS = 6
CHUNK_SIZE = 64 * 1024  # 64 KB
UPLOAD_CHUNK = 512 * 1024  # 512 KB 每 POST


# ================================================================
#  网络接口工具函数
# ================================================================
@dataclass
class InterfaceInfo:
    name: str
    type: str               # "有线" / "无线" / "未知"
    is_up: bool
    speed_mbps: int         # 链路速度 (可能为 0)
    ip: str = ""
    mac: str = ""
    bytes_sent: int = 0
    bytes_recv: int = 0


def get_active_interfaces() -> list[InterfaceInfo]:
    """返回当前活动的网络接口列表"""
    stats = psutil.net_if_stats()
    addrs = psutil.net_if_addrs()
    io = psutil.net_io_counters(pernic=True)
    result = []

    # 无线关键词（不区分大小写）
    wireless_kw = {"wi-fi", "wlan", "无线", "802.11", "wireless", "wlp"}

    for name, stat in stats.items():
        if not stat.isup:
            continue
        # 跳过 loopback
        if name.lower() in ("lo", "loopback", "localhost"):
            continue
        if name not in io:
            continue

        ip = ""
        mac = ""
        if name in addrs:
            for a in addrs[name]:
                if a.family.name == "AF_INET" and not ip:
                    ip = a.address
                if a.family.name == "AF_PACKET" or (a.family.name == "AF_LINK" and not mac):
                    mac = a.address

        # 判断有线/无线
        lower = name.lower()
        if any(kw in lower for kw in wireless_kw):
            iface_type = "无线"
        else:
            # 有线通常为 eth/en/以太网
            iface_type = "有线"

        # 只有有流量才视为活动
        cnt = io[name]
        if cnt.bytes_sent == 0 and cnt.bytes_recv == 0:
            continue

        result.append(InterfaceInfo(
            name=name,
            type=iface_type,
            is_up=True,
            speed_mbps=getattr(stat, "speed", 0),
            ip=ip,
            mac=mac,
            bytes_sent=cnt.bytes_sent,
            bytes_recv=cnt.bytes_recv,
        ))
    return result


def get_primary_interface() -> Optional[InterfaceInfo]:
    """返回流量最大的接口（主接口）"""
    ifaces = get_active_interfaces()
    if not ifaces:
        return None
    return max(ifaces, key=lambda i: i.bytes_sent + i.bytes_recv)


def get_platform() -> str:
    """返回人类可读的平台名称"""
    sys_ = platform.system()
    if sys_ == "Windows":
        return f"Windows {platform.release()} ({platform.machine()})"
    elif sys_ == "Darwin":
        import subprocess
        try:
            ver = subprocess.run(
                ["sw_vers", "-productVersion"], capture_output=True, text=True, timeout=3
            ).stdout.strip()
            arch = platform.machine()
            return f"macOS {ver} ({arch})"
        except Exception:
            return f"macOS ({platform.machine()})"
    elif sys_ == "Linux":
        return f"Linux ({platform.machine()})"
    return sys_


# ================================================================
#  Ping 工具函数
# ================================================================
def _ping(host: str, timeout: float = 3.0):
    """ping 一个主机，返回 (ping_ok: bool, latency_ms: float)"""
    try:
        param = "-n" if platform.system().lower() == "windows" else "-c"
        cmd = ["ping", param, "1", "-w", str(int(timeout * 1000)), host]
        start = time.perf_counter()
        ret = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout + 0.5,
            creationflags=subprocess.CREATE_NO_WINDOW
            if platform.system() == "Windows" else 0,
        )
        elapsed = (time.perf_counter() - start) * 1000
        if ret.returncode == 0:
            # 正则匹配任何 "time=XXms" 或 "时间=XXms" 模式
            m = re.search(r'(?:time|时间)[=<]\s*([\d.]+)\s*ms', ret.stdout, re.IGNORECASE)
            if m:
                return True, float(m.group(1))
            return True, round(elapsed, 1)
        return False, 0.0
    except Exception:
        return False, 0.0


# ================================================================
#  DownloadWorker – 多流并发下载速度测试
# ================================================================
class DownloadWorker(QThread):
    progress = Signal(int)
    speed = Signal(float)            # Mbps
    finished = Signal(float, float)  # avg_mbps, total_mb
    error = Signal(str)
    status_msg = Signal(str)

    def __init__(self, url: str = "", duration: int = 15, streams: int = NUM_STREAMS,
                 parent=None):
        super().__init__(parent)
        self.url = url or DOWNLOAD_URLS[0][1]
        self.duration = duration
        self.streams = streams
        self._stop_event = threading.Event()
        self._total = 0
        self._lock = threading.Lock()

    def stop(self):
        self._stop_event.set()

    def run(self):
        self.status_msg.emit("正在探测文件大小…")
        try:
            head = requests.head(self.url, timeout=10, headers=get_headers())
            file_size = int(head.headers.get("Content-Length", 0))
        except Exception as e:
            log.warning(f"下载连接失败: {e}")
            self.error.emit(f"无法连接服务器: {e}")
            return

        supports_range = file_size > 0
        if supports_range:
            part = file_size // self.streams
            ranges = [(i * part, (i + 1) * part - 1) for i in range(self.streams)]
            ranges[-1] = (ranges[-1][0], file_size - 1)
            self.status_msg.emit(f"多流下载 ({self.streams} 路并发)…")
            self._run_range_download(ranges)
        else:
            self.status_msg.emit("单流下载 (服务器不支持分段)…")
            self._run_single_download()

    def _run_range_download(self, ranges):
        start_time = time.perf_counter()
        last_t = start_time
        last_bytes = 0

        def stream_worker(s, e):
            hdrs = get_headers()
            hdrs["Range"] = f"bytes={s}-{e}"
            try:
                resp = requests.get(self.url, headers=hdrs, stream=True, timeout=30)
                if resp.status_code not in (206, 200):
                    return
                for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                    if self._stop_event.is_set():
                        break
                    if chunk:
                        with self._lock:
                            self._total += len(chunk)
            except Exception as e:
                log.debug(f"下载流异常: {e}")

        with ThreadPoolExecutor(max_workers=self.streams) as pool:
            futures = [pool.submit(stream_worker, s, e) for s, e in ranges]

            while not self._stop_event.is_set():
                time.sleep(0.3)
                now = time.perf_counter()
                elapsed = now - start_time
                if elapsed >= self.duration and self._total > 1024 * 1024:
                    break
                interval = now - last_t
                if interval > 0:
                    cur = self._total
                    inst_mbps = (cur - last_bytes) / interval * 8 / 1_000_000
                    self.speed.emit(inst_mbps)
                    self.progress.emit(min(int(elapsed / self.duration * 100), 99))
                    self.status_msg.emit(
                        f"下载中… {cur / 1_000_000:.1f} MB / {elapsed:.1f}s "
                        f"({inst_mbps:.1f} Mbps)"
                    )
                    last_bytes = cur
                    last_t = now

            self._stop_event.set()

        total_t = time.perf_counter() - start_time
        if total_t > 0 and self._total > 0:
            avg = self._total / total_t * 8 / 1_000_000
            self.progress.emit(100)
            self.finished.emit(avg, self._total / 1_000_000)
            self.status_msg.emit(
                f"下载完成: {self._total/1_000_000:.1f} MB, "
                f"平均 {avg:.2f} Mbps ({self.streams} 路)"
            )
        else:
            self.error.emit("未下载到数据")

    def _run_single_download(self):
        start_time = time.perf_counter()
        last_t = start_time
        last_bytes = 0

        try:
            resp = requests.get(self.url, stream=True, timeout=30, headers=get_headers())
            resp.raise_for_status()
            for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                if self._stop_event.is_set():
                    return
                if chunk:
                    self._total += len(chunk)
                    now = time.perf_counter()
                    elapsed = now - start_time
                    if elapsed >= self.duration and self._total > 1024 * 1024:
                        break
                    if now - last_t >= 0.3:
                        interval = now - last_t
                        inst = (self._total - last_bytes) / interval * 8 / 1_000_000
                        self.speed.emit(inst)
                        self.progress.emit(min(int(elapsed / self.duration * 100), 99))
                        last_t = now
                        last_bytes = self._total
            total_t = time.perf_counter() - start_time
            if total_t > 0 and self._total > 0:
                avg = self._total / total_t * 8 / 1_000_000
                self.progress.emit(100)
                self.finished.emit(avg, self._total / 1_000_000)
        except Exception as e:
            if not self._stop_event.is_set():
                self.error.emit(f"下载异常: {e}")


# ================================================================
#  UploadWorker – 多流并发上传速度测试
# ================================================================
class UploadWorker(QThread):
    progress = Signal(int)
    speed = Signal(float)
    finished = Signal(float, float)
    error = Signal(str)
    status_msg = Signal(str)

    def __init__(self, url: str = "", duration: int = 15, streams: int = 4,
                 parent=None):
        super().__init__(parent)
        self.url = url or UPLOAD_URL
        self.duration = duration
        self.streams = streams
        self._stop_event = threading.Event()
        self._total = 0
        self._lock = threading.Lock()
        # 预生成 1MB 随机数据 (os.urandom 比 random.randint 快数十倍)
        self._data = os.urandom(1024 * 1024)

    def stop(self):
        self._stop_event.set()

    def run(self):
        self.status_msg.emit(f"多流上传 ({self.streams} 路并发)…")
        start_time = time.perf_counter()
        last_t = start_time
        last_bytes = 0

        def upload_worker():
            while not self._stop_event.is_set():
                try:
                    files = {"file": ("test.bin", self._data)}
                    hdrs = get_headers()
                    resp = requests.post(self.url, files=files, timeout=15, headers=hdrs)
                    if resp.status_code in (200, 201, 204):
                        with self._lock:
                            self._total += len(self._data)
                except Exception:
                    pass
                time.sleep(0.05)

        threads = []
        for _ in range(self.streams):
            t = threading.Thread(target=upload_worker, daemon=True)
            t.start()
            threads.append(t)

        while not self._stop_event.is_set():
            time.sleep(0.3)
            now = time.perf_counter()
            elapsed = now - start_time
            if elapsed >= self.duration and self._total > 512 * 1024:
                self._stop_event.set()
                break
            interval = now - last_t
            if interval > 0:
                cur = self._total
                inst = (cur - last_bytes) / interval * 8 / 1_000_000
                self.speed.emit(inst)
                self.progress.emit(min(int(elapsed / self.duration * 100), 99))
                self.status_msg.emit(
                    f"上传中… {cur/1_000_000:.1f} MB / {elapsed:.1f}s"
                )
                last_bytes = cur
                last_t = now

        self._stop_event.set()
        total_t = time.perf_counter() - start_time
        if total_t > 0 and self._total > 0:
            avg = self._total / total_t * 8 / 1_000_000
            self.progress.emit(100)
            self.finished.emit(avg, self._total / 1_000_000)
            self.status_msg.emit(
                f"上传完成: {self._total/1_000_000:.1f} MB, "
                f"平均 {avg:.2f} Mbps ({self.streams} 路)"
            )
        elif self._total == 0:
            self.error.emit("上传测试失败：无数据上传")


# ================================================================
#  PingWorker – 并发连通性测试
# ================================================================
class PingWorker(QThread):
    result = Signal(str, str, bool, float)
    finished = Signal()

    def __init__(self, targets=None, parent=None):
        super().__init__(parent)
        self.targets = targets or PING_TARGETS

    def run(self):
        with ThreadPoolExecutor(max_workers=5) as pool:
            futs = {pool.submit(_ping, addr): (n, addr) for n, addr in self.targets}
            for f in as_completed(futs):
                n, addr = futs[f]
                ok, lat = f.result()
                self.result.emit(n, addr, ok, lat)
        self.finished.emit()


# ================================================================
#  MonitorWorker – 实时网速监控 (psutil)
# ================================================================
class MonitorWorker(QThread):
    data = Signal(float, float, float, float)  # dl_kbps, ul_kbps, total_dl_mb, total_ul_mb
    interface_changed = Signal(str, str, int)   # name, type, speed_mbps

    def __init__(self, interval: float = 1.0, parent=None):
        super().__init__(parent)
        self.interval = interval
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        old = psutil.net_io_counters()
        last_iface_check = 0.0
        while not self._stop_event.is_set():
            # 使用 Event.wait 替代 time.sleep，可被 stop() 立即中断
            if self._stop_event.wait(self.interval):
                break
            new = psutil.net_io_counters()
            dl_kbps = (new.bytes_recv - old.bytes_recv) / self.interval / 1024
            ul_kbps = (new.bytes_sent - old.bytes_sent) / self.interval / 1024
            self.data.emit(
                dl_kbps, ul_kbps,
                new.bytes_recv / (1024 * 1024),
                new.bytes_sent / (1024 * 1024),
            )
            old = new

            now = time.time()
            if now - last_iface_check >= 10:
                last_iface_check = now
                primary = get_primary_interface()
                if primary:
                    self.interface_changed.emit(
                        primary.name, primary.type, primary.speed_mbps
                    )


# ================================================================
#  IPInfoWorker – 公网 IP、ISP、地理位置检测
# ================================================================
class IPInfoWorker(QThread):
    result = Signal(dict)
    error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        data = {"ipv4": "", "ipv6": "", "isp": "", "country": "", "city": "", "org": ""}
        if not self._running:
            return

        # 多路备用 IP API
        for api_url, name in IP_APIS:
            if not self._running:
                return
            try:
                resp = requests.get(api_url, timeout=5, headers=get_headers())
                if resp.status_code == 200:
                    j = resp.json()
                    if name == "ip-api":
                        data["ipv4"] = j.get("query", "")
                        data["country"] = j.get("country", "")
                        data["city"] = j.get("city", "")
                        data["org"] = j.get("org", "") or j.get("isp", "")
                        data["asn"] = j.get("as", "").replace("AS", "") if j.get("as") else ""
                        data["asn_org"] = j.get("asname", "") or j.get("org", "")
                        data["country_code"] = j.get("countryCode", "")
                    elif name == "ipinfo":
                        data["ipv4"] = j.get("ip", "")
                        data["country"] = j.get("country", "")
                        data["city"] = j.get("city", "")
                        data["org"] = j.get("org", "")
                        asn_raw = j.get("org", "")
                        if "AS" in asn_raw:
                            parts = asn_raw.split(" ", 1)
                            data["asn"] = parts[0].replace("AS", "")
                            data["asn_org"] = parts[1] if len(parts) > 1 else ""
                        data["country_code"] = ""
                    else:  # ip.sb
                        data["ipv4"] = j.get("ip", "")
                        data["country"] = j.get("country", "")
                        data["city"] = j.get("city", "")
                        data["org"] = j.get("org", "")
                        data["asn"] = j.get("asn", "")
                        data["asn_org"] = j.get("asn_org", "")
                        data["country_code"] = j.get("country_code", "")
                    if data.get("ipv4"):
                        break  # 拿到 IP 就跳出
            except Exception as e:
                log.debug(f"IP API {name} 失败: {e}")

        # IPv6
        if self._running:
            for api in IPV6_APIS:
                try:
                    r6 = requests.get(api, timeout=3, headers=get_headers())
                    if r6.status_code == 200:
                        ip6 = r6.text.strip()
                        if ip6:
                            data["ipv6"] = ip6
                            break
                except Exception:
                    continue
            if not data.get("ipv6"):
                data["ipv6"] = "不支持"

        # 中文 ISP（仅国内可用，失败不阻塞）
        if self._running:
            try:
                r_cn = requests.get(IP_ISP_API, timeout=3)
                if r_cn.status_code == 200:
                    # pconline 返回 GBK 编码
                    r_cn.encoding = "gbk"
                    try:
                        j = r_cn.json()
                        addr = j.get("addr", "")
                        if addr:
                            data["isp"] = addr
                    except Exception:
                        pass
            except Exception:
                pass

        if self._running:
            self.result.emit(data)


# ================================================================
#  NetCheckWorker – IPv4 / IPv6 连通性检测
# ================================================================
class NetCheckWorker(QThread):
    result = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        if not self._running:
            return
        checks = {
            "ipv4_dns": False, "ipv6_dns": False,
            "ipv4_http": False, "ipv6_http": False,
            "ipv4_latency": 0.0, "ipv6_latency": 0.0,
        }
        import socket as _socket
        try:
            _socket.getaddrinfo("www.baidu.com", 80, family=_socket.AF_INET)
            checks["ipv4_dns"] = True
        except Exception:
            pass
        try:
            _socket.getaddrinfo("www.baidu.com", 80, family=_socket.AF_INET6)
            checks["ipv6_dns"] = True
        except Exception:
            pass

        if not self._running:
            return
        for key, urls, lat_key in [
            ("ipv4_http", IPV4_APIS, "ipv4_latency"),
            ("ipv6_http", IPV6_APIS, "ipv6_latency"),
        ]:
            if not self._running:
                return
            for url in urls:
                try:
                    start = time.perf_counter()
                    r = requests.get(url, timeout=5, headers=get_headers())
                    elapsed = (time.perf_counter() - start) * 1000
                    if r.status_code == 200:
                        checks[key] = True
                        checks[lat_key] = round(elapsed, 1)
                        break
                except Exception:
                    continue

        if self._running:
            self.result.emit(checks)


# ================================================================
#  JitterWorker – 网络波动/抖动检测
# ================================================================
class JitterWorker(QThread):
    result = Signal(dict)   # {min_ms, avg_ms, max_ms, jitter_ms, loss_rate, samples}

    def __init__(self, target: str = "www.baidu.com", count: int = 20, parent=None):
        super().__init__(parent)
        self.target = target
        self.count = count
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        latencies = []
        for i in range(self.count):
            if not self._running:
                break
            ok, lat = _ping(self.target, timeout=2)
            if ok:
                latencies.append(lat)

        if not latencies:
            self.result.emit({
                "min": 0, "avg": 0, "max": 0,
                "jitter": 0, "loss": 100, "samples": [],
            })
            return

        loss = (1 - len(latencies) / self.count) * 100
        avg = sum(latencies) / len(latencies)
        variance = sum((x - avg) ** 2 for x in latencies) / len(latencies)
        jitter = variance ** 0.5  # 标准差作为抖动值

        self.result.emit({
            "min": round(min(latencies), 1),
            "avg": round(avg, 1),
            "max": round(max(latencies), 1),
            "jitter": round(jitter, 1),
            "loss": round(loss, 1),
            "samples": [round(x, 1) for x in latencies],
        })
