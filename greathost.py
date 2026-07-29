##### greathost.py api后台协议抓取，指定名续期 ######

import os, re, time, json, requests
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from selenium import webdriver as std_webdriver
from seleniumwire import webdriver as wire_webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

EMAIL = os.getenv("GREATHOST_EMAIL", "")
PASSWORD = os.getenv("GREATHOST_PASSWORD", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
PROXY_URL = None
IS_PROXY = os.environ.get("IS_PROXY", "false").lower() == "true"
PROXY_SERVER = os.getenv('S5_PROXY') or os.getenv('PROXY_SERVER') or "socks://127.0.0.1:1080"
if IS_PROXY:
    PROXY_URL = PROXY_SERVER
    print(f"🔗 挂载代理: {PROXY_SERVER}")
else:
    print("🍭 未使用代理，直连访问")

TARGET_NAME = os.getenv("TARGET_NAME", "nowx") #=====目标服务器名=====

STATUS_MAP = {
    "running": ["🟢", "Running"],
    "starting": ["🟡", "Starting"],
    "stopped": ["🔴", "Stopped"],
    "offline": ["⚪", "Offline"],
    "suspended": ["🚫", "Suspended"]
}

def get_current_ip(proxy_server: str = "") -> str:
    proxies = None
    if proxy_server:
        proxies = {"http": proxy_server, "https": proxy_server}
    response = requests.get("https://api.ip.sb/ip", proxies=proxies, timeout=15)
    response.raise_for_status()
    return response.text.strip()

def now_shanghai():
    try:
        return datetime.now(ZoneInfo("Asia/Shanghai")).strftime('%Y/%m/%d %H:%M:%S')
    except:
        # Windows 本地可能缺少 tzdata
        return datetime.now().strftime('%Y/%m/%d %H:%M:%S')

def calculate_hours(date_str):
    try:
        if not date_str: return 0
        clean = re.sub(r'\.\d+Z$', 'Z', date_str)
        expiry = datetime.fromisoformat(clean.replace('Z', '+00:00'))
        diff = (expiry - datetime.now(timezone.utc)).total_seconds() / 3600
        return max(0, int(diff))
    except Exception as e:
        print(f"⚠️ 时间解析失败: {e}")
        return 0

def send_notice(kind, fields):
    titles = {
        "renew_success": "🎉 <b>GreatHost 续期成功</b>",
        "maxed_out": "🈵 <b>GreatHost 已达上限</b>",
        "cooldown": "⏳ <b>GreatHost 还在冷却中</b>",
        "renew_failed": "⚠️ <b>GreatHost 续期未生效</b>",
        "error": "🚨 <b>GreatHost 脚本报错</b>"
    }
    body = "\n".join([f"{e} {k}: {v}" for e, k, v in fields])
    msg = f"{titles.get(kind, '📢 通知')}\n\n{body}\n📅 时间: {now_shanghai()}"
    
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                data={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"},
                proxies={"http": None, "https": None},
                timeout=10
            )
            print(f"📡 Telegram 接口响应状态码: {resp.status_code}")
            if resp.status_code != 200:
                print(f"📡 Telegram 接口返回错误: {resp.text}")
        except Exception as e:
            print(f"❌ Telegram 通知发送失败: {e}")
    else:
        print(f"⚠️ Telegram 配置缺失: TOKEN={'已设置' if TELEGRAM_BOT_TOKEN else '未设置'}, ID={'已设置' if TELEGRAM_CHAT_ID else '未设置'}")

    try:
        md = msg.replace("<b>", "**").replace("</b>", "**").replace("<code>", "`").replace("</code>", "`")
        with open("README.md", "w", encoding="utf-8") as f:
            f.write(f"# GreatHost 自动续期状态\n\n{md}\n\n> 最近更新: {now_shanghai()}")
    except: pass

class GH:
    def __init__(self):
        opts = Options()
        # 如果在 GitHub Actions 运行，强制开启无头模式
        # 如果在本地运行，默认开启无头，但你可以通过修改下面这行来观察浏览器
        if os.getenv("GITHUB_ACTIONS") or os.getenv("HEADLESS") == "true":
            opts.add_argument("--headless=new")
        
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--window-size=1920,1080")
        # 禁用自动化控制特征
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
        
        # 深度隐藏特征
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option('useAutomationExtension', False)
        
        proxy = {'proxy': {'http': PROXY_URL, 'https': PROXY_URL}} if PROXY_URL else None
        
        if proxy:
            print("🌐 使用 selenium-wire 代理模式")
            self.d = wire_webdriver.Chrome(options=opts, seleniumwire_options=proxy)
        else:
            print("🚀 使用标准 Selenium 直连模式")
            self.d = std_webdriver.Chrome(options=opts)
            
        # 移除 webdriver 特征
        self.d.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        })
            
        self.w = WebDriverWait(self.d, 40)

    def api(self, url, method="GET"):
        print(f"📡 API 调用 [{method}] {url}")
        script = f"return fetch('{url}',{{method:'{method}'}}).then(r=>r.json()).catch(e=>({{success:false,message:e.toString()}}))"
        return self.d.execute_script(script)

    def get_ip(self):
        try:
            self.d.get("https://api.ipify.org?format=json")
            ip = json.loads(self.d.find_element(By.TAG_NAME, "body").text).get("ip", "Unknown")
            print(f"🌐 落地 IP: {ip}")
            return ip
        except:
            print("🌐 落地 IP: 无法获取")
            return "Unknown"

    def login(self):
        print(f"🔑 正在登录: {EMAIL[:3]}***...")
        self.d.get("https://greathost.es/login")
        time.sleep(5) # 给 Cloudflare 验证和页面加载留出缓冲时间
        self.w.until(EC.presence_of_element_located((By.NAME, "email"))).send_keys(EMAIL)
        self.d.find_element(By.NAME, "password").send_keys(PASSWORD)
        self.d.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        self.w.until(EC.url_contains("/dashboard"))

    def get_server(self):
        servers = self.api("/api/servers").get("servers", [])
        return next((s for s in servers if s.get("name") == TARGET_NAME), None)

    def get_status(self, sid):
        info = self.api(f"/api/servers/{sid}/information")
        st = info.get("status", "unknown").lower()
        icon, name = STATUS_MAP.get(st, ["❓", st])
        print(f"📋 状态核对: {TARGET_NAME} | {icon} {name}")
        return icon, name

    def get_renew_info(self, sid):
        data = self.api(f"/api/renewal/contracts/{sid}")
        print(f"DEBUG: 原始合同数据 -> {str(data)[:100]}...")
        # 注意：data.get("contract", {}) 在 contract 键存在但值为 None 时仍会返回 None，
        # 直接 .get 会抛 AttributeError，因此先显式兜底为空 dict。
        contract = data.get("contract") or {}
        return contract.get("renewalInfo") or data.get("renewalInfo") or {}

    def dump_page_diagnostics(self, tag="diag"):
        """超时/异常时把页面关键信息打到日志，不依赖 artifact 也能排查。"""
        try:
            url = self.d.current_url
            title = self.d.title
            src = self.d.page_source or ""
            body_text = ""
            try:
                body_text = self.d.find_element(By.TAG_NAME, "body").text or ""
            except Exception:
                body_text = ""
            has_btn = "renew-free-server-btn" in src
            cf_hit = any(k in src.lower() for k in (
                "cf-browser-verification", "just a moment", "cloudflare",
                "attention required", "challenge-platform",
            ))
            print(f"🩺 [{tag}] URL: {url}")
            print(f"🩺 [{tag}] title: {title!r}")
            print(f"🩺 [{tag}] has #renew-free-server-btn in source: {has_btn}")
            print(f"🩺 [{tag}] cloudflare/challenge 迹象: {cf_hit}")
            print(f"🩺 [{tag}] body 文本前 500 字: {body_text[:500]!r}")
            # 源码片段：按钮附近或整体前 800 字，便于对照 DOM 是否挂载
            idx = src.find("renew-free-server-btn")
            if idx >= 0:
                print(f"🩺 [{tag}] 按钮附近 HTML: {src[max(0, idx-120):idx+200]!r}")
            else:
                print(f"🩺 [{tag}] page_source 前 800 字: {src[:800]!r}")
        except Exception as e:
            print(f"⚠️ 诊断信息采集失败: {type(e).__name__}: {e}")

    def get_btn(self, sid):
        """读取续期按钮文案（仅用于判断是否冷却 Wait）。

        根因（已用 Actions 诊断验证）：按钮 #renew-free-server-btn 可在 DOM 中存在，
        但 .text 长期为空（JS 未填充或不可见文本），原先对非空 text 干等 40s 会 TimeoutException。
        策略：等 presence；文案短超时 + textContent 兜底；仍空则返回 ""，由上层走 renew API。
        """
        target = f"https://greathost.es/contracts/{sid}"
        print(f"🧭 打开合同页: {target}")
        self.d.get(target)
        try:
            btn = self.w.until(EC.presence_of_element_located((By.ID, "renew-free-server-btn")))
        except TimeoutException:
            print("⏱️ get_btn：按钮元素未出现，采集诊断后抛出")
            self.dump_page_diagnostics(tag="get_btn_no_element")
            raise

        def _btn_label(el):
            # .text 只含「可见」文本；textContent 可拿到隐藏/尚未 layout 的文案
            return (el.text or el.get_attribute("textContent") or "").strip()

        try:
            # 文案由前端异步填充，不应占用与 presence 同级的 40s
            WebDriverWait(self.d, 10).until(lambda d: _btn_label(btn) != "")
        except TimeoutException:
            print("⚠️ get_btn：按钮已在 DOM 但 10s 内文案仍空，跳过冷却文案探测，交由 renew API 判断")
            self.dump_page_diagnostics(tag="get_btn_empty_text")

        btn_text = _btn_label(btn)
        print(f"🔘 按钮状态: '{btn_text}'" + (" (空，将尝试 API 续期)" if not btn_text else ""))
        return btn_text

    def renew(self, sid):
        print(f"🚀 正在执行续期 POST...")
        return self.api(f"/api/renewal/contracts/{sid}/renew-free", "POST")

    def close(self):
        self.d.quit()

def run():
    # 启动浏览器前先校验凭据，避免空值喂给登录表单后干等 40s 超时才报错
    if not EMAIL or not PASSWORD:
        raise SystemExit("❌ 缺少 GREATHOST_EMAIL / GREATHOST_PASSWORD 环境变量")
    gh = GH()
    try:
        ip = gh.get_ip()
        gh.login()
        srv = gh.get_server()
        if not srv: raise Exception(f"未找到服务器 {TARGET_NAME}")
        sid = srv["id"]
        print(f"✅ 已锁定目标服务器: {TARGET_NAME} (ID: {sid})")

        icon, stname = gh.get_status(sid)
        status_disp = f"{icon} {stname}"

        info = gh.get_renew_info(sid)
        before = calculate_hours(info.get("nextRenewalDate"))

        btn = gh.get_btn(sid)
        print(f"🔘 按钮状态: '{btn}' | 剩余: {before}h")

        if "Wait" in btn:
            m = re.search(r"Wait\s+(\d+\s+\w+)", btn)
            send_notice("cooldown", [
                ("📛","服务器名称",TARGET_NAME),
                ("🆔","ID",f"<code>{sid}</code>"),
                ("⏳","冷却时间",m.group(1) if m else btn),
                ("📊","当前累计",f"{before}h"),
                ("🚀","服务器状态",status_disp)
            ])
            return

        res = gh.renew(sid)
        ok = res.get("success", False)
        msg = res.get("message", "无返回消息")
        # details 可能为 None，先兜底再取 nextRenewalDate，避免 (None).get 抛错
        details = res.get("details") or {}
        after = calculate_hours(details.get("nextRenewalDate")) if ok else before
        print(f"📡 续期响应结果: {ok} | Date='{details.get('nextRenewalDate')}' | Message='{msg}'")

        if ok and after > before:
            send_notice("renew_success", [
                ("📛","服务器名称",TARGET_NAME),
                ("🆔","ID",f"<code>{sid}</code>"),
                ("⏰","增加时间",f"{before} ➔ {after}h"),
                ("🚀","服务器状态",status_disp),
                ("💡","提示",msg),
                ("🌐","落地 IP",f"<code>{ip}</code>")
            ])
        elif "5 d" in msg or before > 108:
            send_notice("maxed_out", [
                ("📛","服务器名称",TARGET_NAME),
                ("🆔","ID",f"<code>{sid}</code>"),
                ("⏰","剩余时间",f"{after}h"),
                ("🚀","服务器状态",status_disp),
                ("💡","提示",msg),
                ("🌐","落地 IP",f"<code>{ip}</code>")
            ])
        else:
            send_notice("renew_failed", [
                ("📛","服务器名称",TARGET_NAME),
                ("🆔","ID",f"<code>{sid}</code>"),
                ("🚀","服务器状态",status_disp),
                ("⏰","剩余时间",f"{before}h"),
                ("💡","提示",msg),
                ("🌐","落地 IP",f"<code>{ip}</code>")
            ])
    except Exception as e:
        print(f"🚨 运行异常: {type(e).__name__}: {e}")
        # 保存页面源码和截图用于排查是否触发了验证码或加载失败
        if 'gh' in locals():
            try:
                # 再打一遍诊断，覆盖非 get_btn 路径的超时/异常
                gh.dump_page_diagnostics(tag="run_except")
                gh.d.save_screenshot("error_screenshot.png")
                with open("error_page.html", "w", encoding="utf-8") as f:
                    f.write(gh.d.page_source)
                print("📋 已保存错误页面源码 (error_page.html) 和截图 (error_screenshot.png)")
            except Exception as se:
                print(f"⚠️ 保存调试信息失败: {se}")

        error_msg = str(e).replace("<", "&lt;").replace(">", "&gt;")
        send_notice("error", [
            ("📛", "服务器名称", TARGET_NAME),
            ("❌", "故障", f"<code>{type(e).__name__}: {error_msg[:100]}</code>"),
            ("🌐", "代理状态", "已尝试直连/Stealth")
        ])
        # 以非 0 退出，让 Actions 判定 failure，从而上传 debug-artifacts
        # （此前 except 吞异常后正常退出，Upload Error Page 被 if: failure() 跳过）
        raise SystemExit(1) from e

    finally:
        # 增加一个判断，防止 gh 没初始化成功导致报错
        if 'gh' in locals():
            try: gh.close()
            except: pass

if __name__ == "__main__":
    run()