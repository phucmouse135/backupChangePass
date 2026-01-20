# FILE: gmx_core.py
import time
import os
import tempfile
import threading
import contextlib
import inspect
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from fake_useragent import UserAgent

# --- CẤU HÌNH ---
TIMEOUT_MAX = 15  # Max seconds wait for element
SLEEP_INTERVAL = 1 
PROXY_HOST = "127.0.0.1"
_DRIVER_LOCK = threading.Lock()
_DRIVER_PATH = None
_LOCK_FILE_PATH = os.path.join(tempfile.gettempdir(), "uc_chromedriver.lock")

try:
    import msvcrt
except Exception:
    msvcrt = None


@contextlib.contextmanager
def _global_install_lock():
    if not msvcrt:
        yield
        return
    lock_file = open(_LOCK_FILE_PATH, "w")
    try:
        msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
        yield
    finally:
        try:
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        finally:
            lock_file.close()


def _supports_param(fn, name):
    try:
        return name in inspect.signature(fn).parameters
    except Exception:
        return False


def _resolve_driver_path():
    global _DRIVER_PATH
    if _DRIVER_PATH:
        return _DRIVER_PATH
    install_fn = getattr(uc, "install", None)
    if not install_fn:
        return None
    _DRIVER_PATH = install_fn()
    return _DRIVER_PATH


def _create_driver(options, retries=3, delay=1.5):
    last_exc = None
    for _ in range(retries):
        try:
            driver_path = _resolve_driver_path()
            kwargs = {"options": options}
            if driver_path and _supports_param(uc.Chrome, "driver_executable_path"):
                kwargs["driver_executable_path"] = driver_path
            return uc.Chrome(**kwargs)
        except OSError as exc:
            last_exc = exc
            if "WinError 183" in str(exc) or isinstance(exc, FileExistsError):
                time.sleep(delay)
                continue
            raise
    if last_exc:
        raise last_exc

def get_driver(headless=False, proxy_port=None):
    """Initialize browser with config + Proxy + Fake UA"""
    options = uc.ChromeOptions()
    
    # 1. Fake IP (9Proxy)
    if proxy_port:
        proxy_server = f"http://{PROXY_HOST}:{proxy_port}"
        options.add_argument(f'--proxy-server={proxy_server}')
        print(f"[CORE] Proxy set to: {proxy_server}")
    else:
        # Default fallback or no proxy
        pass 
    
    # 2. Static User Agent (no network call)
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    print(f"[CORE] UserAgent: {user_agent}")
    options.add_argument(f'--user-agent={user_agent}')

    # 3. Chống detect cơ bản
    if headless:
        options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-popup-blocking")
    
    # Tắt load ảnh để chạy nhanh
    prefs = {"profile.managed_default_content_settings.images": 2}
    options.add_experimental_option("prefs", prefs)
    
    print(f"[CORE] Opening Browser (Headless: {headless})...")
    with _DRIVER_LOCK:
        with _global_install_lock():
            driver = _create_driver(options)
    
    # 4. Bypass detection script thêm sau khi init
    # Overwrite property navigator.webdriver = undefined
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    return driver

def find_element_safe(driver, by, value, timeout=TIMEOUT_MAX, click=False, send_keys=None):
    """
    Hàm tìm kiếm an toàn (Polling Loop).
    - Tự động retry nếu không thấy.
    - Trả về Element nếu thành công.
    - Trả về None nếu timeout.
    """
    end_time = time.time() + timeout
    while time.time() < end_time:
        if reload_if_ad_popup(driver):
            return None
        try:
            element = driver.find_element(by, value)
            
            # Scroll nhẹ để element vào view (tránh bị che)
            # driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            
            if click:
                element.click()
                return True
            
            if send_keys:
                element.clear()
                element.send_keys(send_keys)
                return True
            
            return element # Trả về element để xử lý tiếp
        except Exception:
            time.sleep(SLEEP_INTERVAL)
            continue
    
    print(f"[ERROR] Không tìm thấy hoặc không thao tác được: {value}")
    return None

def reload_if_ad_popup(driver, url="https://www.gmx.net/"):
    """Reload to GMX home if ad-consent popup is shown."""
    try:
        try:
            current_url = driver.current_url
        except Exception:
            current_url = ""

        if current_url.startswith("https://suche.gmx.net/web"):
            driver.get(url)
            time.sleep(2)
            return True

        for element in driver.find_elements(By.CSS_SELECTOR, "span.title"):
            try:
                text = element.text.strip()
            except Exception:
                text = ""
            if "Wir finanzieren uns" in text:
                driver.get(url)
                time.sleep(2)
                return True

        for button in driver.find_elements(By.TAG_NAME, "button"):
            try:
                text = button.text.strip()
            except Exception:
                text = ""
            if text in ("Akzeptieren und weiter", "Zum Abo ohne Fremdwerbung"):
                driver.get(url)
                time.sleep(2)
                return True

        try:
            page_source = driver.page_source
        except Exception:
            page_source = ""

        page_lower = page_source.lower()
        if "wir finanzieren uns" in page_lower:
            popup_hints = [
                "werbung",
                "akzeptieren und weiter",
                "zum abo ohne fremdwerbung",
                "postfach ohne fremdwerbebanner",
                "abfrage nochmals anzeigen",
            ]
            if any(hint in page_lower for hint in popup_hints):
                driver.get(url)
                time.sleep(2)
                return True
        elif "wir finanzieren uns" in page_source and "Werbung" in page_source:
            driver.get(url)
            time.sleep(2)
            return True
    except Exception:
        pass
    return False
