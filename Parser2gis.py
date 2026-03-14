#!/usr/bin/env python3

from __future__ import annotations
import argparse
import base64
import codecs
import json
import queue
import re
import threading
import urllib.parse
import webbrowser
import logging
import random
from abc import ABC, abstractmethod
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union
import sys
import os
import textwrap
import socket
import tempfile
import shutil
import contextlib
import subprocess
import time
import csv
import requests
import pydantic
import pychrome
import psutil
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from tkinter.scrolledtext import ScrolledText
from pydantic import field_validator
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

# Версия программы
VERSION = "1.4.0"
GITHUB_REPO = "Inter1ark/Parser-2gis"

# Проверка платформы
running_linux = lambda: sys.platform.startswith('linux')
running_windows = lambda: sys.platform.startswith('win32')
running_mac = lambda: sys.platform.startswith('darwin')

# Пути
def data_path() -> Path:
    return Path(__file__).parent / 'data'

def user_path() -> Path:
    return Path.home() / '.config' / 'parser-2gis'

# Настройка логирования
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('pychrome').setLevel(logging.WARNING)
logger = logging.getLogger('parser-2gis')

# Подавление ошибок в потоках pychrome (Python 3.8+)
try:
    _original_excepthook = threading.excepthook
    def _silent_thread_excepthook(args):
        """Подавляет JSONDecodeError из pychrome._recv_loop"""
        if args.exc_type == json.decoder.JSONDecodeError:
            # Игнорируем JSONDecodeError из pychrome - это нормально при закрытии
            return
        # Остальные ошибки показываем
        _original_excepthook(args)
    threading.excepthook = _silent_thread_excepthook
except AttributeError:
    # Python < 3.8 не имеет threading.excepthook
    pass

# ----------------- SX.ORG helpers -----------------

# ----------------- Auto-update via GitHub tags -----------------
def check_for_updates() -> dict | None:
    """Проверяет наличие новой версии на GitHub.
    Возвращает {'version': '1.4.0', 'url': '...', 'notes': '...'} или None.
    """
    try:
        resp = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
            timeout=8,
            headers={"Accept": "application/vnd.github.v3+json"}
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        tag = data.get("tag_name", "").lstrip("vV")
        if not tag:
            return None
        # Сравниваем версии (tuple сравнение)
        def ver_tuple(v):
            return tuple(int(x) for x in v.split('.') if x.isdigit())
        if ver_tuple(tag) > ver_tuple(VERSION):
            return {
                'version': tag,
                'url': data.get('html_url', f'https://github.com/{GITHUB_REPO}/releases/latest'),
                'notes': data.get('body', '')[:300],
            }
    except Exception as e:
        logger.debug("Ошибка проверки обновлений: %s", e)
    return None


def get_sxorg_balance(api_key: str) -> str:
    """Получить баланс пользователя SX.ORG."""
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=Retry(total=3)))
    try:
        resp = session.get("https://api.sx.org/v2/user/balance",
                          params={"apiKey": api_key}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get('success'):
            return str(data.get('balance', 'неизвестно'))
        return "неизвестно"
    except Exception as e:
        logger.error("Ошибка получения баланса SX.ORG: %s", e)
        return "неизвестно"
    finally:
        session.close()


def create_sxorg_proxy(api_key: str) -> Dict[str, Any]:
    """Создать мобильную SHARED прокси через SX.ORG API.
    Возвращает dict с ключами: proxy_string, refresh_link, host, port, login, password.
    """
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=Retry(total=3)))
    try:
        resp = session.post(
            "https://api.sx.org/v2/proxy/create-port",
            params={"apiKey": api_key},
            json={
                "country_code": "RU",
                "type_id": 3,           # mobile
                "proxy_type_id": 3,     # mobile
                "name": "Parser2GIS",
                "server_port_type_id": 0  # SHARED — ключевой параметр!
            },
            timeout=30
        )
        resp.raise_for_status()
        data = resp.json()
        logger.info("SX.ORG create-port ответ: %s", data)

        if not data.get("success"):
            logger.error("SX.ORG create error: %s", data.get('message', 'неизвестно'))
            return {}

        p = data["data"][0] if isinstance(data["data"], list) else data["data"]
        proxy_string = f"{p['login']}:{p['password']}@{p['server']}:{p['port']}"
        refresh_link = p.get("refresh_link") or p.get("REFRESH_LINK", "")

        return {
            'proxy_string': proxy_string,
            'refresh_link': refresh_link,
            'host': p.get('server', ''),
            'port': str(p.get('port', '')),
            'login': p.get('login', ''),
            'password': p.get('password', ''),
        }
    except Exception as e:
        logger.error("Ошибка создания SX.ORG прокси: %s", e)
        return {}
    finally:
        session.close()


def refresh_sxorg_ip(refresh_link: str) -> bool:
    """Сменить внешний IP прокси через refresh_link."""
    if not refresh_link:
        logger.warning("refresh_link не задан")
        return False
    try:
        r = requests.get(refresh_link, timeout=15)
        data = r.json()
        if data.get('success'):
            logger.info("✅ IP прокси обновлён!")
            return True
        else:
            logger.warning("⚠️ Не удалось обновить IP: %s", data)
            return False
    except Exception as e:
        logger.error("Ошибка обновления IP: %s", e)
        return False

# ----------------- proxy file loader -----------------
def load_proxy_file(file_path: str, proxy_method: str, api_key: Optional[str] = None, proxy_string: Optional[str] = None, **kwargs) -> List[Dict[str, str]]:
    """Загрузка прокси. sxorg использует сохранённый proxy_string, file читает файл."""
    if proxy_method == 'sxorg':
        # SX.ORG: используем сохранённый proxy_string (login:pass@host:port)
        if not proxy_string:
            logger.warning("⚠️ Прокси SX.ORG не создана! Зайдите в Настройки → Прокси → Создать прокси.")
            return []
        logger.info("="*60)
        logger.info("🔄 ЗАГРУЗКА ПРОКСИ SX.ORG")
        logger.info("="*60)
        # Парсим login:pass@host:port
        try:
            auth_part, addr_part = proxy_string.rsplit('@', 1)
            login, password = auth_part.split(':', 1)
            host, port = addr_part.rsplit(':', 1)
            logger.info("🌐 Прокси: %s:%s", host, port)
            logger.info("👤 Логин: %s", login[:10] + "...")
            logger.info("✅ Прокси загружена!")
            logger.info("="*60)
            return [{'host': host, 'port': port, 'username': login, 'password': password}]
        except Exception as e:
            logger.error("❌ Ошибка парсинга proxy_string '%s': %s", proxy_string, e)
            return []
    elif proxy_method == 'file' and file_path:
        proxies = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    parts = line.split(':')
                    if len(parts) == 2:
                        proxies.append({'host': parts[0], 'port': parts[1]})
                    elif len(parts) == 4:
                        proxies.append({'host': parts[0], 'port': parts[1], 'username': parts[2], 'password': parts[3]})
                    else:
                        logger.warning("Некорректный формат прокси: %s", line)
        except Exception as e:
            logger.error("Ошибка чтения файла прокси %s: %s", file_path, e)
        return proxies
    return []

# ----------------- Models (kept) -----------------
class Point(pydantic.BaseModel):
    lat: float
    lon: float

class NameExModel(pydantic.BaseModel):
    primary: str
    extension: Optional[str] = None
    legal_name: Optional[str] = None
    description: Optional[str] = None
    short_name: Optional[str] = None
    addition: Optional[str] = None

class Contact(pydantic.BaseModel):
    type: str
    value: str
    text: Optional[str] = None
    url: Optional[str] = None
    print_text: Optional[str] = None
    comment: Optional[str] = None

# (Other models omitted for brevity in comments but defined earlier - kept in code)
class ContactGroup(pydantic.BaseModel):
    contacts: List[Contact]
    schedule: Optional[Any] = None
    comment: Optional[str] = None
    name: Optional[str] = None

class Address(pydantic.BaseModel):
    building_id: Optional[str] = None
    building_name: Optional[str] = None
    building_code: Optional[str] = None
    postcode: Optional[str] = None
    makani: Optional[str] = None

class Org(pydantic.BaseModel):
    id: str
    name: str
    branch_count: int

class Flags(pydantic.BaseModel):
    is_default: Optional[bool] = None
    is_district_area_center: Optional[bool] = None
    is_region_center: Optional[bool] = None
    temporary_closed: Optional[str] = None

class AdmDivItem(pydantic.BaseModel):
    id: Optional[str] = None
    name: str
    caption: Optional[str] = None
    type: str
    city_alias: Optional[str] = None
    flags: Optional[Flags] = None
    detailed_subtype: Optional[str] = None

class Reviews(pydantic.BaseModel):
    general_rating: Optional[float] = None
    general_review_count: Optional[int] = None

class Rubric(pydantic.BaseModel):
    id: Optional[str] = None
    kind: Optional[str] = None
    name: str
    short_id: Optional[int] = None
    alias: Optional[str] = None
    parent_id: Optional[str] = None

class CatalogItem(pydantic.BaseModel):
    id: str
    address: Optional[Address] = None
    address_comment: Optional[str] = None
    address_name: Optional[str] = None
    adm_div: List[AdmDivItem] = []
    city_alias: Optional[str] = None
    contact_groups: List[ContactGroup] = []
    locale: str = "ru"
    name: Optional[str] = None
    name_ex: Optional[NameExModel] = None
    reviews: Optional[Reviews] = None
    org: Optional[Org] = None
    point: Optional[Point] = None
    region_id: Optional[str] = None
    segment_id: Optional[str] = None
    rubrics: List[Rubric] = []
    schedule: Optional[Any] = None
    timezone_offset: Optional[int] = None
    type: str = "business"
    is_deleted: Optional[bool] = None

    @property
    def url(self) -> str:
        return 'https://2gis.ru/firm/%s' % self.id.split('_')[0]

# ----------------- Utilities -----------------
def floor_to_hundreds(n: int) -> int:
    return (n // 100) * 100

def wait_until_finished(timeout: int = 10, throw_exception: bool = True):
    def decorator(func):
        def wrapper(*args, **kwargs):
            for _ in range(timeout * 10):
                result = func(*args, **kwargs)
                if result:
                    return result
                time.sleep(0.1)
            if throw_exception:
                raise TimeoutError(f"Function {func.__name__} timed out after {timeout} seconds")
            return None
        return wrapper
    return decorator

# ----------------- Chrome helpers (restored) -----------------
def default_memory_limit() -> int:
    return 6000 if running_windows() else 4000

def locate_chrome_path() -> Optional[str]:
    if running_windows():
        possible_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
        for path in possible_paths:
            if os.path.exists(path):
                return path
    elif running_mac():
        path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        if os.path.exists(path):
            return path
    elif running_linux():
        try:
            path = shutil.which("google-chrome") or shutil.which("chromium")
            if path:
                return path
        except Exception:
            pass
    return None

def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('localhost', 0))
        return s.getsockname()[1]

class ChromePathNotFound(Exception):
    pass

class ChromeOptions(pydantic.BaseModel):
    binary_path: Optional[str] = None
    disable_images: bool = True
    start_maximized: bool = False
    headless: bool = True
    memory_limit: int = default_memory_limit()
    user_data_dir: Optional[str] = None
    proxy_file: Optional[str] = None
    proxy_list: List[Dict[str, str]] = pydantic.Field(default_factory=list, exclude=True)
    proxy_method: str = 'sxorg'
    sxorg_api_key: Optional[str] = None
    sxorg_proxy_string: Optional[str] = None   # login:pass@host:port
    sxorg_refresh_link: Optional[str] = None   # URL для смены IP

    @field_validator('proxy_file')
    @classmethod
    def validate_proxy_file(cls, v: str | None, info: pydantic.ValidationInfo) -> str | None:
        if v and info.data.get('proxy_method') == 'file' and not os.path.exists(v):
            raise ValueError(f"Файл прокси {v} не существует")
        return v

# ChromeBrowser and ChromeRemote are restored for completeness; implementation similar to earlier versions
class ChromeBrowser:
    def __init__(self, options: ChromeOptions):
        self.options = options
        self._temp_dir = None
        self._process = None
        self._debug_port = None
        self._proxy_user = None
        self._proxy_pass = None

    def start(self):
        chrome_path = self.options.binary_path or locate_chrome_path()
        if not chrome_path:
            raise ChromePathNotFound("Chrome binary not found")
        
        logger.info("🔧 Настройки Chrome:")
        logger.info("   - headless: %s", self.options.headless)
        logger.info("   - disable_images: %s", self.options.disable_images)
        logger.info("   - proxy_method: %s", self.options.proxy_method)
        
        self._temp_dir = tempfile.mkdtemp()
        
        # Загружаем прокси
        self.options.proxy_list = load_proxy_file(
            self.options.proxy_file,
            self.options.proxy_method,
            self.options.sxorg_api_key,
            self.options.sxorg_proxy_string
        )
        
        self._debug_port = free_port()
        args = [
            chrome_path, 
            f"--remote-debugging-port={self._debug_port}", 
            "--no-first-run", 
            "--no-default-browser-check",
            "--disable-gpu",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            f"--user-data-dir={self._temp_dir}"
        ]
        
        # Настройка прокси
        if self.options.proxy_list:
            proxy = self.options.proxy_list[0]
            proxy_host = proxy.get('host')
            proxy_port = proxy.get('port')
            self._proxy_user = proxy.get('username', '')
            self._proxy_pass = proxy.get('password', '')
            
            logger.info("=" * 60)
            logger.info("🔧 НАСТРОЙКА ПРОКСИ")
            logger.info("=" * 60)
            logger.info("🌐 %s:%s", proxy_host, proxy_port)
            
            # Всегда используем --proxy-server (работает во всех версиях Chrome)
            args.append(f"--proxy-server=http://{proxy_host}:{proxy_port}")
            
            if self._proxy_user and self._proxy_pass:
                logger.info("🔐 Прокси с авторизацией → CDP Fetch обработчик")
                logger.info("   👤 Логин: %s", self._proxy_user[:15] + "...")
            
            logger.info("✅ Прокси подключена!")
            logger.info("=" * 60)
        
        # Headless режим
        if self.options.headless:
            args.append("--headless=new")
            logger.info("👻 Headless режим включен")
            # Маскировка headless: подменяем user-agent и отключаем webdriver
            args.append('--disable-blink-features=AutomationControlled')
            args.append('--disable-infobars')
            ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            args.append(f'--user-agent={ua}')
            
        if self.options.disable_images:
            args.append("--blink-settings=imagesEnabled=false")
        if self.options.start_maximized:
            args.append("--start-maximized")

        self._process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        logger.info("✅ Chrome запущен на порту %d", self._debug_port)
        return self._process.pid
    
    def _create_proxy_auth_extension(self, host: str, port: str, username: str, password: str) -> str:
        """Создаёт расширение Chrome для установки прокси И авторизации (Manifest V2)
        
        Расширение управляет ВСЕМ:
        1. chrome.proxy.settings.set() - устанавливает прокси
        2. webRequest.onAuthRequired - автоматическая авторизация
        """
        ext_dir = os.path.join(self._temp_dir, 'proxy_auth_extension')
        os.makedirs(ext_dir, exist_ok=True)
        
        # manifest.json (Manifest V2 - полный набор permissions)
        manifest_json = """{
    "version": "1.0.0",
    "manifest_version": 2,
    "name": "Chrome Proxy",
    "permissions": [
        "proxy",
        "tabs",
        "unlimitedStorage",
        "storage",
        "<all_urls>",
        "webRequest",
        "webRequestBlocking"
    ],
    "background": {
        "scripts": ["background.js"]
    },
    "minimum_chrome_version": "22.0.0"
}"""
        
        with open(os.path.join(ext_dir, 'manifest.json'), 'w', encoding='utf-8') as f:
            f.write(manifest_json)
        
        # background.js - И прокси, И авторизация (проверенный подход со StackOverflow)
        background_js = """var config = {
    mode: "fixed_servers",
    rules: {
        singleProxy: {
            scheme: "http",
            host: "%s",
            port: parseInt(%s)
        },
        bypassList: ["localhost"]
    }
};

chrome.proxy.settings.set({value: config, scope: "regular"}, function() {
    console.log('[Proxy] Прокси установлен: %s:%s');
});

function callbackFn(details) {
    console.log('[Proxy Auth] Авторизация для:', details.url);
    return {
        authCredentials: {
            username: "%s",
            password: "%s"
        }
    };
}

chrome.webRequest.onAuthRequired.addListener(
    callbackFn,
    {urls: ["<all_urls>"]},
    ['blocking']
);

console.log('[Proxy] Расширение загружено. Прокси: %s:%s, Логин: %s');
""" % (host, port, host, port, username, password, host, port, username)
        
        with open(os.path.join(ext_dir, 'background.js'), 'w', encoding='utf-8') as f:
            f.write(background_js)
        
        logger.info("   📁 Расширение создано: %s", ext_dir)
        logger.info("   👤 Логин: %s", username)
        logger.info("   🔑 Пароль: ***")
        logger.info("   🌐 Прокси в расширении: %s:%s", host, port)
        
        return ext_dir
    
    def get_debug_port(self):
        """Get the debug port Chrome is using"""
        return self._debug_port

    def stop(self):
        if self._process:
            try:
                parent = psutil.Process(self._process.pid)
                for child in parent.children(recursive=True):
                    try:
                        child.terminate()
                    except Exception:
                        pass
                parent.terminate()
                psutil.wait_procs([parent] + parent.children(recursive=True), timeout=3)
            except Exception as e:
                logger.warning("Ошибка при остановке Chrome: %s", e)
        if self._temp_dir and os.path.exists(self._temp_dir):
            shutil.rmtree(self._temp_dir, ignore_errors=True)

# ChromeRemote left as earlier (kept)
class ChromeRemote:
    def _patch_headless(self):
        """Внедряет JS для маскировки headless-режима в текущей вкладке"""
        try:
            js_patch = '''
// 1. navigator.webdriver
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
// 2. window.chrome
window.chrome = { runtime: {} };
// 3. navigator.plugins
Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
// 4. navigator.languages
Object.defineProperty(navigator, 'languages', {get: () => ['ru-RU', 'ru', 'en']});
// 5. permissions
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
  parameters.name === 'notifications' ?
    Promise.resolve({ state: Notification.permission }) :
    originalQuery(parameters)
);
// 6. user-agent
Object.defineProperty(navigator, 'userAgent', {get: () => 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'});
'''
            if hasattr(self, '_tab') and self._tab:
                self._tab.Runtime.evaluate(expression=js_patch)
        except Exception as e:
            logger.warning(f"Не удалось внедрить маскировку headless: {e}")
    def __init__(self, chrome_options: ChromeOptions, response_patterns: List[str] = None):
        self._browser = ChromeBrowser(chrome_options)
        self._browser_pid = self._browser.start()
        
        # Get debug port directly from browser
        self._debug_port = self._browser.get_debug_port()
        if not self._debug_port:
            raise RuntimeError("Could not get Chrome debug port")
        
        logger.info("Подключение к Chrome на порту %d...", self._debug_port)
        
        # Wait for Chrome to start and DevTools to be ready
        time.sleep(3)
        
        # Try to connect with retries
        max_retries = 10
        for attempt in range(max_retries):
            try:
                self._browser_client = pychrome.Browser(url=f"http://127.0.0.1:{self._debug_port}")
                # Test connection
                self._browser_client.list_tab()
                logger.info("✓ Успешно подключились к Chrome")
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.debug("Попытка %d/%d: %s", attempt + 1, max_retries, e)
                    time.sleep(1)
                else:
                    raise RuntimeError(f"Не удалось подключиться к Chrome после {max_retries} попыток: {e}")
        
        self._tab = None
        self._response_patterns = response_patterns or []
        self._blocked_urls = []
        self._start_scripts: List[str] = []
        self._pending_requests: Dict[int, Dict[str, Any]] = {}
        self._collected_responses: List[Dict[str, Any]] = []

    def start(self):
        """Start a new tab and enable network monitoring"""
        logger.info("Создание новой вкладки...")
        
        # Create new tab with retries
        max_retries = 3
        for attempt in range(max_retries):
            try:
                self._tab = self._browser_client.new_tab()
                self._tab.start()
                logger.info("✓ Вкладка создана")
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning("Попытка создания вкладки %d/%d не удалась: %s", attempt + 1, max_retries, e)
                    time.sleep(2)
                else:
                    raise RuntimeError(f"Не удалось создать вкладку после {max_retries} попыток: {e}")
        
        # CDP Fetch для авторизации прокси (MV2 расширения не работают в Chrome 120+)
        proxy_user = getattr(self._browser, '_proxy_user', '')
        proxy_pass = getattr(self._browser, '_proxy_pass', '')
        if proxy_user and proxy_pass:
            try:
                def _on_auth_required(**kwargs):
                    request_id = kwargs.get('requestId')
                    logger.debug("🔐 Proxy auth required for: %s", kwargs.get('request', {}).get('url', '')[:80])
                    try:
                        self._tab.Fetch.continueWithAuth(
                            requestId=request_id,
                            authChallengeResponse={
                                'response': 'ProvideCredentials',
                                'username': proxy_user,
                                'password': proxy_pass,
                            }
                        )
                    except Exception as e:
                        logger.debug("Auth response error: %s", e)

                def _on_request_paused(**kwargs):
                    request_id = kwargs.get('requestId')
                    try:
                        self._tab.Fetch.continueRequest(requestId=request_id)
                    except Exception:
                        pass

                self._tab.Fetch.authRequired = _on_auth_required
                self._tab.Fetch.requestPaused = _on_request_paused
                self._tab.Fetch.enable(handleAuthRequests=True)
                logger.info("✓ CDP Fetch: авторизация прокси настроена")
            except Exception as e:
                logger.warning("⚠️ Не удалось настроить CDP Fetch auth: %s", e)
        
        # Enable network monitoring
        try:
            self._tab.Network.requestWillBeSent = self._on_request_will_be_sent
            self._tab.Network.responseReceived = self._on_response_received
            self._tab.Network.enable()
            logger.info("✓ Мониторинг сети включен")
        except Exception as e:
            logger.warning("Ошибка включения мониторинга сети: %s", e)
        
        # Маскировка headless (JS) если включен headless
        if self._browser.options.headless:
            self._patch_headless()
        
        # Execute start scripts
        for script in self._start_scripts:
            try:
                self._tab.Runtime.evaluate(expression=script)
            except Exception:
                pass

    def stop(self):
        """Безопасная остановка Chrome с подавлением всех ошибок"""
        # Сначала закрываем вкладку
        if self._tab:
            try:
                self._browser_client.close_tab(self._tab)
            except Exception:
                pass
            finally:
                self._tab = None
        
        # Потом останавливаем браузер
        if self._browser:
            try:
                self._browser.stop()
            except Exception:
                pass
        
        # Небольшая задержка для завершения процессов
        time.sleep(0.3)

    def navigate(self, url: str, timeout: int = 30):
        if not self._tab:
            raise RuntimeError("Tab not started")
        self._tab.Page.navigate(url=url)
        time.sleep(1)  # Уменьшено с 2 до 1 секунды

    def wait_for_selector(self, selector: str, timeout: int = 10):
        script = f"""
        (function() {{
            var end = Date.now() + {timeout * 1000};
            var interval = setInterval(function() {{
                if (document.querySelector('{selector}')) {{
                    clearInterval(interval);
                    return true;
                }}
                if (Date.now() > end) {{
                    clearInterval(interval);
                }}
            }}, 100);
        }})();
        """
        try:
            self._tab.Runtime.evaluate(expression=script)
            time.sleep(1)
        except Exception:
            pass

    def get_elements_by_selector(self, selector: str) -> List[Dict[str, Any]]:
        script = f"""
        (function() {{
            var elements = document.querySelectorAll('{selector}');
            return Array.from(elements).map(el => {{
                return {{
                    text: el.textContent,
                    href: el.href || '',
                    innerHTML: el.innerHTML
                }};
            }});
        }})();
        """
        try:
            result = self._tab.Runtime.evaluate(expression=script)
            if result and 'result' in result and 'value' in result['result']:
                return result['result']['value']
        except Exception as e:
            logger.warning("Selector error: %s", e)
        return []

    def click_element(self, selector: str):
        script = f"""
        (function() {{
            var el = document.querySelector('{selector}');
            if (el) {{
                el.click();
                return true;
            }}
            return false;
        }})();
        """
        try:
            result = self._tab.Runtime.evaluate(expression=script)
            time.sleep(0.5)
            return result
        except Exception as e:
            logger.warning("Click error: %s", e)
            return None

    def get_page_content(self) -> str:
        script = "document.documentElement.outerHTML"
        try:
            result = self._tab.Runtime.evaluate(expression=script)
            if result and 'result' in result and 'value' in result['result']:
                return result['result']['value']
        except Exception:
            pass
        return ""

    def get_collected_responses(self) -> List[Dict[str, Any]]:
        return self._collected_responses

    def _on_request_will_be_sent(self, **kwargs):
        self._pending_requests[kwargs['requestId']] = kwargs

    def _on_response_received(self, **kwargs):
        self._collected_responses.append(kwargs)
        url = kwargs.get('response', {}).get('url', '')
        for pattern in self._response_patterns:
            if pattern in url:
                try:
                    request_id = kwargs['requestId']
                    response_body = self._tab.Network.getResponseBody(requestId=request_id)
                    if response_body and 'body' in response_body:
                        kwargs['body'] = response_body['body']
                except Exception:
                    pass

# ----------------- Config, logging, writer, parser (restored) -----------------
class LogOptions(pydantic.BaseModel):
    gui_format: str = '%(asctime)s | %(message)s'
    cli_format: str = '%(asctime)s | %(levelname)-8s | %(message)s'
    gui_datefmt: str = '%H:%M:%S'
    cli_datefmt: str = '%Y-%-m-%d %H:%M:%S'
    level: str = 'INFO'

    @field_validator('level')
    @classmethod
    def valid_level(cls, v):
        if v.upper() not in logging._nameToLevel:
            raise ValueError(f"Invalid log level: {v}")
        return v

class WriterCSVOptions(pydantic.BaseModel):
    add_rubrics: bool = True
    add_comments: bool = True
    remove_empty_columns: bool = True
    remove_duplicates: bool = True
    columns_per_entity: int = 1

class WriterOptions(pydantic.BaseModel):
    verbose: bool = True
    encoding: str = 'utf8'
    csv: WriterCSVOptions = WriterCSVOptions()

class ParserOptions(pydantic.BaseModel):
    skip_404_response: bool = True
    delay_between_clicks: int = 0
    max_records: int = 0
    use_gc: bool = False
    gc_pages_interval: int = 5

class Configuration(pydantic.BaseModel):
    chrome: ChromeOptions = ChromeOptions()
    log: LogOptions = LogOptions()
    parser: ParserOptions = ParserOptions()
    writer: WriterOptions = WriterOptions()
    url_history: List[str] = pydantic.Field(default_factory=list)

    def merge_with(self, other: 'Configuration'):
        for key in Configuration.model_fields.keys():
            if hasattr(other, key):
                setattr(self, key, getattr(other, key))

    @classmethod
    def load_config(cls, auto_create: bool = False):
        try:
            cfg_file = user_path() / "config.json"
            if cfg_file.exists():
                with open(cfg_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return cls(**data)
        except Exception:
            pass
        return cls()

    def save_config(self):
        try:
            p = user_path()
            p.mkdir(parents=True, exist_ok=True)
            cfg_file = p / "config.json"
            with open(cfg_file, "w", encoding="utf-8") as f:
                json.dump(self.model_dump(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning("Не удалось сохранить конфиг: %s", e)

def setup_gui_logger(log_queue: queue.Queue, log_options: LogOptions):
    class QueueHandler(logging.Handler):
        def emit(self, record):
            try:
                log_queue.put(self.format(record))
            except Exception:
                pass
    handler = QueueHandler()
    handler.setFormatter(logging.Formatter(fmt=log_options.gui_format, datefmt=log_options.gui_datefmt))
    logger.addHandler(handler)
    logger.setLevel(log_options.level)

# ----------------- GUI: Settings (final with Parser and CSV tabs + paste fixes) -----------------
def gui_settings(config: Configuration) -> None:
    window = tk.Toplevel()
    window.title("Настройки")
    window.geometry("760x560")

    notebook = ttk.Notebook(window)
    notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

    # Browser tab
    browser_frame = ttk.Frame(notebook)
    notebook.add(browser_frame, text="Браузер")
    disable_images_var = tk.BooleanVar(value=config.chrome.disable_images)
    start_maximized_var = tk.BooleanVar(value=config.chrome.start_maximized)
    headless_var = tk.BooleanVar(value=config.chrome.headless)
    memory_limit_var = tk.IntVar(value=config.chrome.memory_limit)
    
    # Используем tk.Checkbutton вместо ttk.Checkbutton для корректной работы
    tk.Checkbutton(browser_frame, text="Отключить изображения", variable=disable_images_var, 
                   bg="#1B5E20", fg="white", selectcolor="#2E7D32", activebackground="#1B5E20", 
                   activeforeground="white").pack(anchor="w", padx=8, pady=4)
    tk.Checkbutton(browser_frame, text="Запускать развёрнутым", variable=start_maximized_var,
                   bg="#1B5E20", fg="white", selectcolor="#2E7D32", activebackground="#1B5E20", 
                   activeforeground="white").pack(anchor="w", padx=8, pady=4)
    tk.Checkbutton(browser_frame, text="Скрытый режим (headless)", variable=headless_var,
                   bg="#1B5E20", fg="white", selectcolor="#2E7D32", activebackground="#1B5E20", 
                   activeforeground="white").pack(anchor="w", padx=8, pady=4)
    ttk.Label(browser_frame, text="Лимит RAM (MB)").pack(anchor="w", padx=8, pady=(8,2))
    ttk.Spinbox(browser_frame, from_=256, to=65536, increment=256, textvariable=memory_limit_var).pack(anchor="w", padx=8, pady=2)

    # Proxy tab (left controls + right banner)
    proxy_frame = ttk.Frame(notebook)
    notebook.add(proxy_frame, text="Прокси")
    top_frame = ttk.Frame(proxy_frame)
    top_frame.pack(fill=tk.X, pady=(6,0), padx=8)
    ttk.Label(top_frame, text="Метод прокси:").pack(side=tk.LEFT)
    PROXY_DISPLAY_TO_VALUE = {"Из файла": "file", "SX.ORG (Рекомендовано)": "sxorg"}
    PROXY_VALUE_TO_DISPLAY = {v: k for k, v in PROXY_DISPLAY_TO_VALUE.items()}
    # Radio-переключатель вместо combobox
    proxy_method_var = tk.StringVar(value=config.chrome.proxy_method or "sxorg")
    tk.Radiobutton(top_frame, text="SX.ORG (Рекомендовано)", variable=proxy_method_var,
                   value="sxorg", bg="#1B5E20", fg="white", selectcolor="#2E7D32",
                   activebackground="#1B5E20", activeforeground="white",
                   font=("TkDefaultFont", 9, "bold")).pack(side=tk.LEFT, padx=(12,4))
    tk.Radiobutton(top_frame, text="Из файла", variable=proxy_method_var,
                   value="file", bg="#1B5E20", fg="white", selectcolor="#2E7D32",
                   activebackground="#1B5E20", activeforeground="white").pack(side=tk.LEFT, padx=4)

    main = ttk.Frame(proxy_frame)
    main.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)
    left = ttk.Frame(main)
    left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    right = tk.Frame(main, width=260, bg="#1B5E20", relief=tk.FLAT, bd=0)
    right.pack(side=tk.RIGHT, fill=tk.Y, padx=(8,0))

    # File controls
    proxy_file_var = tk.StringVar(value=config.chrome.proxy_file or "")
    proxy_file_label = ttk.Label(left, text="Файл прокси (IP:PORT или IP:PORT:USER:PASS)")
    proxy_file_entry = ttk.Entry(left, textvariable=proxy_file_var, width=60)
    proxy_file_browse = ttk.Button(left, text="Обзор", command=lambda: proxy_file_var.set(filedialog.askopenfilename(title="Файл прокси", filetypes=[("Текстовые файлы", "*.txt"), ("Все файлы", "*.*")]) or proxy_file_var.get()))

    # SX controls
    sx_api_var = tk.StringVar(value=config.chrome.sxorg_api_key or "")
    sx_frame = ttk.Frame(left)
    sx_label = ttk.Label(sx_frame, text="API-ключ SX.ORG:")
    sx_entry = ttk.Entry(sx_frame, textvariable=sx_api_var, show="*", width=36)
    sx_ok_btn = ttk.Button(sx_frame, text="OK")
    sx_paste_btn = ttk.Button(sx_frame, text="Вставить")
    sx_balance_var = tk.StringVar(value="Баланс: неизвестно")
    sx_balance_label = ttk.Label(left, textvariable=sx_balance_var)
    sx_create_btn = ttk.Button(left, text="🚀 Создать прокси для работы")
    sx_refresh_btn = ttk.Button(left, text="🔄 Сменить IP прокси")
    sx_proxy_var = tk.StringVar(value="")
    sx_proxy_label = ttk.Label(left, textvariable=sx_proxy_var, font=("TkDefaultFont", 9, "bold"))
    sx_status_var = tk.StringVar(value="Прокси: не создана")
    sx_status_label = ttk.Label(left, textvariable=sx_status_var)

    # Right banner — стиль в тон темы
    banner_title_lbl = tk.Label(right, text="Прокси", bg="#1B5E20", fg="#A5D6A7",
                                font=("TkDefaultFont", 18, "bold"))
    banner_brand = tk.Label(right, text="SX.ORG", bg="#1B5E20", fg="#FFFFFF",
                            font=("TkDefaultFont", 13, "bold"))
    banner_sub = tk.Label(right, text="Промокод: ZHdMCL", bg="#1B5E20", fg="#FFFFFF",
                          font=("TkDefaultFont", 10, "bold"))
    banner_text = tk.Label(right, text="+3 ГБ трафика бесплатно\nпри регистрации",
                          bg="#1B5E20", fg="#C8E6C9", justify="center", wraplength=220,
                          font=("TkDefaultFont", 9))
    banner_btn = tk.Button(right, text="Получить прокси SX.ORG",
                           bg="#43A047", fg="white", activebackground="#66BB6A",
                           activeforeground="white", relief=tk.FLAT, bd=0,
                           font=("TkDefaultFont", 10, "bold"), cursor="hand2", padx=12, pady=6,
                           command=lambda: webbrowser.open("https://my.sx.org/auth/login/?utm-source=parser2gis"))
    banner_title_lbl.pack(pady=(20, 2))
    banner_brand.pack(pady=(0, 4))
    banner_sub.pack(pady=(6, 2))
    banner_text.pack(pady=(2, 10), padx=12)
    banner_btn.pack(pady=(0, 16))



    # Parser tab (restore)
    parser_frame = ttk.Frame(notebook)
    notebook.add(parser_frame, text="Парсер")
    skip_404_var = tk.BooleanVar(value=config.parser.skip_404_response)
    delay_clicks_var = tk.IntVar(value=config.parser.delay_between_clicks)
    max_records_var = tk.IntVar(value=config.parser.max_records)
    use_gc_var = tk.BooleanVar(value=config.parser.use_gc)
    gc_pages_var = tk.IntVar(value=config.parser.gc_pages_interval)
    
    tk.Checkbutton(parser_frame, text="Пропускать 404 ответы", variable=skip_404_var,
                   bg="#1B5E20", fg="white", selectcolor="#2E7D32", activebackground="#1B5E20", 
                   activeforeground="white").pack(anchor="w", padx=8, pady=4)
    ttk.Label(parser_frame, text="Задержка между кликами (ms)").pack(anchor="w", padx=8, pady=(8,2))
    ttk.Spinbox(parser_frame, from_=0, to=10000, textvariable=delay_clicks_var).pack(anchor="w", padx=8, pady=2)
    ttk.Label(parser_frame, text="Макс. записей (0 = без лимита)").pack(anchor="w", padx=8, pady=(8,2))
    ttk.Spinbox(parser_frame, from_=0, to=1000000, textvariable=max_records_var).pack(anchor="w", padx=8, pady=2)
    
    tk.Checkbutton(parser_frame, text="Использовать GC", variable=use_gc_var,
                   bg="#1B5E20", fg="white", selectcolor="#2E7D32", activebackground="#1B5E20", 
                   activeforeground="white").pack(anchor="w", padx=8, pady=4)
    ttk.Label(parser_frame, text="Интервал GC (страниц)").pack(anchor="w", padx=8, pady=(8,2))
    ttk.Spinbox(parser_frame, from_=1, to=1000, textvariable=gc_pages_var).pack(anchor="w", padx=8, pady=2)

    # CSV/XLSX tab (restore)
    csv_frame = ttk.Frame(notebook)
    notebook.add(csv_frame, text="CSV/XLSX")
    add_rubrics_var = tk.BooleanVar(value=config.writer.csv.add_rubrics)
    add_comments_var = tk.BooleanVar(value=config.writer.csv.add_comments)
    remove_empty_var = tk.BooleanVar(value=config.writer.csv.remove_empty_columns)
    remove_duplicates_var = tk.BooleanVar(value=config.writer.csv.remove_duplicates)
    columns_per_entity_var = tk.IntVar(value=config.writer.csv.columns_per_entity)
    
    tk.Checkbutton(csv_frame, text='Добавить "Рубрики"', variable=add_rubrics_var,
                   bg="#1B5E20", fg="white", selectcolor="#2E7D32", activebackground="#1B5E20", 
                   activeforeground="white").pack(anchor="w", padx=8, pady=4)
    tk.Checkbutton(csv_frame, text="Добавлять комментарии", variable=add_comments_var,
                   bg="#1B5E20", fg="white", selectcolor="#2E7D32", activebackground="#1B5E20", 
                   activeforeground="white").pack(anchor="w", padx=8, pady=4)
    tk.Checkbutton(csv_frame, text="Удалить пустые колонки", variable=remove_empty_var,
                   bg="#1B5E20", fg="white", selectcolor="#2E7D32", activebackground="#1B5E20", 
                   activeforeground="white").pack(anchor="w", padx=8, pady=4)
    tk.Checkbutton(csv_frame, text="Удалить дубликаты", variable=remove_duplicates_var,
                   bg="#1B5E20", fg="white", selectcolor="#2E7D32", activebackground="#1B5E20", 
                   activeforeground="white").pack(anchor="w", padx=8, pady=4)
    ttk.Label(csv_frame, text="Сложные колонки (columns per entity)").pack(anchor="w", padx=8, pady=(8,2))
    ttk.Spinbox(csv_frame, from_=1, to=10, textvariable=columns_per_entity_var).pack(anchor="w", padx=8, pady=2)

    # Layout helpers for proxy controls
    def show_file_ui():
        sx_frame.pack_forget()
        sx_balance_label.pack_forget()
        sx_create_btn.pack_forget()
        sx_refresh_btn.pack_forget()
        sx_status_label.pack_forget()
        sx_proxy_label.pack_forget()
        proxy_file_label.pack(anchor="w", padx=6, pady=(6,2))
        proxy_file_entry.pack(anchor="w", padx=6, pady=2)
        proxy_file_browse.pack(anchor="w", padx=6, pady=2)

    def show_sx_ui():
        proxy_file_label.pack_forget()
        proxy_file_entry.pack_forget()
        proxy_file_browse.pack_forget()
        sx_frame.pack(anchor="w", fill=tk.X, padx=6, pady=(6,2))
        sx_label.pack(side=tk.LEFT)
        sx_entry.pack(side=tk.LEFT, padx=(6,6))
        sx_ok_btn.pack(side=tk.LEFT)
        sx_paste_btn.pack(side=tk.LEFT, padx=(6,0))
        sx_balance_label.pack(anchor="w", padx=6, pady=(8,2))
        sx_create_btn.pack(anchor="w", padx=6, pady=(8,4))
        sx_refresh_btn.pack(anchor="w", padx=6, pady=(4,4))
        sx_status_label.pack(anchor="w", padx=6, pady=(4,2))
        sx_proxy_label.pack(anchor="w", padx=6, pady=(2,6))
    
    def _update_proxy_display():
        """Обновляет отображение текущей прокси в UI"""
        ps = config.chrome.sxorg_proxy_string
        if ps:
            # Показываем логин скрыто
            parts = ps.split('@')
            if len(parts) == 2:
                sx_proxy_var.set(f"🌐 {parts[1]}")
            else:
                sx_proxy_var.set(f"🌐 {ps}")
            sx_status_var.set("Прокси: ✅ активна")
        else:
            sx_proxy_var.set("")
            sx_status_var.set("Прокси: не создана")

    def on_method_change(*args):
        value = proxy_method_var.get()
        if value == "file":
            show_file_ui()
        else:
            show_sx_ui()

    proxy_method_var.trace_add("write", on_method_change)
    # initial UI state
    on_method_change()

    # Paste support for API entry: Ctrl+V / Command+V / Shift-Insert
    def paste_to_entry(e=None):
        try:
            text = window.clipboard_get()
        except Exception:
            text = ""
        if text:
            sx_entry.delete(0, tk.END)
            sx_entry.insert(0, text)
        return "break"

    sx_entry.bind("<Control-v>", paste_to_entry)
    sx_entry.bind("<Control-V>", paste_to_entry)
    sx_entry.bind("<Command-v>", paste_to_entry)  # macOS
    sx_entry.bind("<Shift-Insert>", paste_to_entry)
    sx_paste_btn.config(command=paste_to_entry)

    # OK command: save key, update balance
    def sx_ok_cmd():
        key = sx_entry.get().strip()
        if not key:
            messagebox.showwarning("API-ключ", "Введите API-ключ SX.ORG.")
            return
        logger.info("💾 Сохранение API-ключа SX.ORG...")
        config.chrome.sxorg_api_key = key
        config.save_config()  # Сохраняем конфиг сразу!
        logger.info("✅ API-ключ сохранен в конфигурацию")
        sx_balance_var.set("Баланс: обновление...")
        def _fetch():
            bal = get_sxorg_balance(key)
            sx_balance_var.set(f"Баланс: {bal} $")
            logger.info("💰 Баланс SX.ORG: %s $", bal)
        threading.Thread(target=_fetch, daemon=True).start()
        messagebox.showinfo("API-ключ сохранён", f"API-ключ сохранён!\n\nКлюч: {key[:10]}...\n\nТеперь можете импортировать прокси.")
    sx_ok_btn.config(command=sx_ok_cmd)

    # Refresh IP command
    def sx_refresh_cmd():
        link = config.chrome.sxorg_refresh_link
        if not link:
            messagebox.showwarning("Нет прокси", "Сначала создайте прокси (кнопка Создать).")
            return
        logger.info("🔄 Смена IP прокси...")
        sx_status_var.set("Прокси: ⏳ смена IP...")
        def _refresh():
            try:
                ok = refresh_sxorg_ip(link)
                if ok:
                    sx_status_var.set("Прокси: ✅ IP обновлён")
                    logger.info("✅ IP прокси успешно обновлён")
                else:
                    sx_status_var.set("Прокси: ❌ ошибка смены IP")
                    logger.error("❌ Не удалось сменить IP")
            except Exception as e:
                sx_status_var.set("Прокси: ❌ ошибка")
                logger.error("❌ Ошибка смены IP: %s", e)
        threading.Thread(target=_refresh, daemon=True).start()
    sx_refresh_btn.config(command=sx_refresh_cmd)

    # Create proxy command — SHARED mobile proxy via SX.ORG API
    def sx_create_cmd():
        api = sx_entry.get().strip() or config.chrome.sxorg_api_key
        if not api:
            messagebox.showwarning("API-ключ", "Введите API-ключ SX.ORG и нажмите OK.")
            return
        
        logger.info("🚀 Создание прокси для работы...")
        sx_status_var.set("Прокси: ⏳ создаём...")
        
        def _create():
            try:
                result = create_sxorg_proxy(api)
                if result and result.get('proxy_string'):
                    config.chrome.sxorg_proxy_string = result['proxy_string']
                    config.chrome.sxorg_refresh_link = result.get('refresh_link', '')
                    config.chrome.sxorg_api_key = api
                    config.chrome.proxy_list = [{
                        'host': result['host'],
                        'port': result['port'],
                        'username': result['login'],
                        'password': result['password'],
                    }]
                    config.save_config()
                    _update_proxy_display()
                    logger.info("✅ Прокси создана: %s:%s", result['host'], result['port'])
                    messagebox.showinfo("Успех!",
                        f"✅ Прокси создана!\n\n"
                        f"Сервер: {result['host']}:{result['port']}\n\n"
                        f"Прокси сохранена и будет использоваться автоматически.\n"
                        f"Кнопка 'Сменить IP' — для ротации адреса.")
                else:
                    sx_status_var.set("Прокси: ❌ ошибка создания")
                    logger.error("❌ Не удалось создать прокси")
                    messagebox.showerror("Ошибка", "Не удалось создать прокси.\nПроверьте баланс и API-ключ.")
            except Exception as e:
                sx_status_var.set("Прокси: ❌ ошибка")
                logger.error("❌ Ошибка создания прокси: %s", e)
                messagebox.showerror("Ошибка", f"Ошибка создания прокси:\n{e}")
        threading.Thread(target=_create, daemon=True).start()
    
    sx_create_btn.config(command=sx_create_cmd)

    # Buttons Save/Cancel - include parser and csv settings save
    btn_frame = ttk.Frame(window)
    btn_frame.pack(fill=tk.X, padx=8, pady=(0,8))
    def on_save():
        config.chrome.disable_images = disable_images_var.get()
        config.chrome.start_maximized = start_maximized_var.get()
        config.chrome.headless = headless_var.get()
        config.chrome.memory_limit = memory_limit_var.get()
        config.chrome.proxy_method = proxy_method_var.get()
        if config.chrome.proxy_method == "file":
            config.chrome.proxy_file = proxy_file_var.get() or None
        else:
            if sx_entry.get().strip():
                config.chrome.sxorg_api_key = sx_entry.get().strip()
            # sxorg_proxy_string и sxorg_refresh_link уже сохранены при создании
        # parser options
        config.parser.skip_404_response = skip_404_var.get()
        config.parser.delay_between_clicks = delay_clicks_var.get()
        config.parser.max_records = max_records_var.get()
        config.parser.use_gc = use_gc_var.get()
        config.parser.gc_pages_interval = gc_pages_var.get()
        # writer csv options
        config.writer.csv.add_rubrics = add_rubrics_var.get()
        config.writer.csv.add_comments = add_comments_var.get()
        config.writer.csv.remove_empty_columns = remove_empty_var.get()
        config.writer.csv.remove_duplicates = remove_duplicates_var.get()
        config.writer.csv.columns_per_entity = columns_per_entity_var.get()
        config.save_config()
        window.destroy()
    ttk.Button(btn_frame, text="Сохранить", command=on_save).pack(side=tk.LEFT, padx=6)
    ttk.Button(btn_frame, text="Отмена", command=window.destroy).pack(side=tk.RIGHT, padx=6)

    # Preload if config has sxorg api
    if config.chrome.sxorg_api_key:
        sx_entry.delete(0, tk.END)
        sx_entry.insert(0, config.chrome.sxorg_api_key)
        _update_proxy_display()
        def _preload():
            try:
                bal = get_sxorg_balance(config.chrome.sxorg_api_key)
                sx_balance_var.set(f"Баланс: {bal} $")
            except Exception:
                sx_balance_var.set("Баланс: неизвестно")
        threading.Thread(target=_preload, daemon=True).start()

    window.transient()
    window.grab_set()
    window.wait_window()

# ----------------- URLs editor / generator (kept) -----------------
def gui_urls_editor(urls: List[str]) -> List[str] | None:
    window = tk.Toplevel()
    window.title("URLs")
    window.geometry("650x500")
    window.resizable(True, True)
    tk.Label(window, text="Ссылки").pack(pady=6)
    url_text = ScrolledText(window, height=18, width=70)
    url_text.insert(tk.END, '\n'.join(urls))
    url_text.pack(padx=10, pady=6, fill=tk.BOTH, expand=False)
    result = [None]
    def on_ok():
        result[0] = [x.strip() for x in url_text.get("1.0", tk.END).splitlines() if x.strip()]
        window.destroy()
    def on_generate():
        new_urls = gui_urls_generator()
        if new_urls:
            current = url_text.get("1.0", tk.END).splitlines()
            url_text.delete("1.0", tk.END)
            url_text.insert(tk.END, '\n'.join(current + new_urls))
    btn_frame = ttk.Frame(window)
    btn_frame.pack(fill=tk.X, pady=6, padx=6)
    ttk.Button(btn_frame, text="OK", command=on_ok).pack(side=tk.LEFT, padx=6)
    ttk.Button(btn_frame, text="Сгенерировать", command=on_generate).pack(side=tk.LEFT, padx=6)
    ttk.Button(btn_frame, text="Отмена", command=window.destroy).pack(side=tk.RIGHT, padx=6)
    window.transient()
    window.grab_set()
    window.wait_window()
    return result[0]

def gui_urls_generator() -> List[str]:
    window = tk.Toplevel()
    window.title("Генератор URL")
    window.geometry("550x380")
    
    # Подсказка
    hint_text = "ℹ️ Город/страна пишется на АНГЛИЙСКОМ!"
    ttk.Label(window, text=hint_text, foreground="yellow", font=("Arial", 10, "bold")).pack(pady=(8,4))
    
    # Тип поиска: город или страна
    search_type_var = tk.StringVar(value="city")
    type_frame = ttk.Frame(window)
    type_frame.pack(pady=(4, 6))
    ttk.Label(type_frame, text="Тип поиска:").pack(side=tk.LEFT, padx=(0,8))
    tk.Radiobutton(type_frame, text="По городу", variable=search_type_var, value="city",
                   bg="#1B5E20", fg="white", selectcolor="#2E7D32",
                   activebackground="#1B5E20", activeforeground="white").pack(side=tk.LEFT, padx=4)
    tk.Radiobutton(type_frame, text="По стране", variable=search_type_var, value="country",
                   bg="#1B5E20", fg="white", selectcolor="#2E7D32",
                   activebackground="#1B5E20", activeforeground="white").pack(side=tk.LEFT, padx=4)
    
    # Примеры
    examples_var = tk.StringVar(value="Примеры: moscow, spb, novosibirsk, ekaterinburg")
    examples_label = ttk.Label(window, textvariable=examples_var, font=("TkDefaultFont", 8))
    examples_label.pack(pady=(0, 4))
    
    def on_type_change(*_args):
        if search_type_var.get() == "city":
            location_label_var.set("Город (на английском):")
            examples_var.set("Примеры: moscow, spb, novosibirsk, ekaterinburg")
        else:
            location_label_var.set("Страна (на английском):")
            examples_var.set("Примеры: russia, kazakhstan, uzbekistan, kyrgyzstan")
    search_type_var.trace_add("write", on_type_change)
    
    location_label_var = tk.StringVar(value="Город (на английском):")
    ttk.Label(window, textvariable=location_label_var).pack(pady=(6,2))
    location_var = tk.StringVar()
    ttk.Entry(window, textvariable=location_var, width=40).pack(pady=4)
    
    ttk.Label(window, text="Рубрика (кафе, рестораны, магазины):").pack(pady=(6,2))
    rubric_var = tk.StringVar()
    ttk.Entry(window, textvariable=rubric_var, width=40).pack(pady=4)
    
    result: List[str] = []
    def on_generate():
        rubric = rubric_var.get().strip()
        location = location_var.get().strip()
        if rubric and location:
            if search_type_var.get() == "country":
                # Формат для страны: https://2gis.ru/search/рубрика/country/страна
                generated_url = f"https://2gis.ru/search/{rubric}/country/{location}"
            else:
                # Формат для города: https://2gis.ru/город/search/рубрика
                generated_url = f"https://2gis.ru/{location}/search/{rubric}"
            result.append(generated_url)
        window.destroy()
    btn_frame = ttk.Frame(window)
    btn_frame.pack(pady=8)
    ttk.Button(btn_frame, text="Генерировать", command=on_generate).pack(side=tk.LEFT, padx=6)
    ttk.Button(btn_frame, text="Отмена", command=window.destroy).pack(side=tk.LEFT, padx=6)
    window.transient()
    window.grab_set()
    window.wait_window()
    return result

# ----------------- Parser Engine -----------------
class Parser2GIS:
    def __init__(self, config: Configuration):
        self.config = config
        self.chrome_remote: Optional[ChromeRemote] = None
        self.collected_items: List[CatalogItem] = []
        
    def start(self):
        """Start Chrome browser"""
        self.chrome_remote = ChromeRemote(
            self.config.chrome,
            response_patterns=['/catalog/branch/list', '/catalog/geo/search']
        )
        self.chrome_remote.start()
        logger.info("Браузер запущен")
        
    def stop(self):
        """Stop Chrome browser"""
        if self.chrome_remote:
            self.chrome_remote.stop()
            logger.info("Браузер остановлен")
    
    def _parse_catalog_item(self, item_data: dict) -> Optional[CatalogItem]:
        """Парсит данные организации из API ответа"""
        try:
            # Извлекаем основные данные
            name = item_data.get('name', '')
            address = item_data.get('address_name', '')
            
            # Телефоны
            phones = []
            contact_groups = item_data.get('contact_groups', [])
            for group in contact_groups:
                for contact in group.get('contacts', []):
                    if contact.get('type') == 'phone':
                        phone = contact.get('text', '').strip()
                        if phone:
                            phones.append(phone)
            
            # Email
            email = None
            for group in contact_groups:
                for contact in group.get('contacts', []):
                    if contact.get('type') == 'email':
                        email = contact.get('text', '').strip()
                        break
                if email:
                    break
            
            # Сайт
            website = None
            for group in contact_groups:
                for contact in group.get('contacts', []):
                    if contact.get('type') == 'website':
                        website = contact.get('url', '').strip()
                        break
                if website:
                    break
            
            # Рейтинг
            rating = None
            reviews = item_data.get('reviews', {})
            if reviews:
                rating = reviews.get('rating')
            
            # Рубрики
            rubrics = []
            for rubric in item_data.get('rubrics', []):
                rubric_name = rubric.get('name', '')
                if rubric_name:
                    rubrics.append(rubric_name)
            
            # Координаты
            lat, lon = None, None
            point = item_data.get('point')
            if point:
                lat = point.get('lat')
                lon = point.get('lon')
            
            # Создаём объект CatalogItem
            return CatalogItem(
                id=item_data.get('id', ''),
                name=name,
                address=address,
                phones=phones,
                email=email,
                website=website,
                rating=rating,
                rubrics=rubrics,
                lat=lat,
                lon=lon
            )
        except Exception as e:
            logger.error(f"Ошибка парсинга item: {e}")
            return None
            
    def _scrape_firm_page(self, firm_url: str) -> Optional[Dict[str, Any]]:
        """Скрапинг данных напрямую со страницы фирмы через JavaScript (упрощённый метод)"""
        try:
            # Просто переходим на страницу фирмы
            self.chrome_remote.navigate(firm_url)
            time.sleep(1.2)  # Уменьшено с 2 до 1.2 секунд
            
            # JavaScript код для извлечения всех данных со страницы
            scrape_script = """
            (function() {
                const result = {
                    name: '',
                    address: '',
                    phones: [],
                    email: '',
                    website: '',
                    rating: '',
                    reviews: '',
                    category: '',
                    lat: null,
                    lon: null,
                    workingHours: '',
                    id: ''
                };
                
                // ID фирмы из URL
                const match = window.location.pathname.match(/\\/firm\\/(\\d+)/);
                if (match) result.id = match[1];
                
                // Название (селектор из Solrikk)
                const nameEl = document.querySelector('h1._1x89xo5');
                if (nameEl) result.name = nameEl.innerText.trim();
                
                // Адрес (селекторы из TheDenison)
                const addressEl1 = document.querySelector('span._14quei a._2lcm958');
                const addressEl2 = document.querySelector('span._oqoid a._2lcm958');
                if (addressEl1) result.address = addressEl1.innerText.trim().replace(/\\u200B/g, '').replace(/\\xa0/g, ' ');
                else if (addressEl2) result.address = addressEl2.innerText.trim().replace(/\\u200B/g, '').replace(/\\xa0/g, ' ');
                
                // Телефоны - пробуем раскрыть кнопку, потом извлекаем
                const phoneElements = document.querySelectorAll('div._b0ke8 a[href^="tel:"]');
                result.phones = Array.from(phoneElements)
                    .map(el => el.href.replace('tel:', ''))
                    .filter(text => text);
                
                // Email (из Solrikk)
                const emailEl = document.querySelector('a[href^="mailto:"]');
                if (emailEl) {
                    result.email = emailEl.innerText.trim() || emailEl.href.replace('mailto:', '');
                }
                
                // Сайт (из TheDenison)
                const siteLinks = document.querySelectorAll('a._1rehek');
                for (const link of siteLinks) {
                    const linkText = link.innerText.trim();
                    if (linkText && !linkText.includes(' ')) {
                        // Проверяем наличие http/https/www
                        if (linkText.includes('http') || linkText.includes('www.')) {
                            result.website = linkText;
                            break;
                        }
                    }
                }
                // Альтернативный способ - ищем ссылку с иконкой глобуса
                if (!result.website) {
                    const contactLinks = document.querySelectorAll('div._172gbf8 div._49kxlr a[href*="http"]');
                    for (const link of contactLinks) {
                        const href = link.href || '';
                        const parent = link.closest('div._172gbf8');
                        const hasGlobeIcon = parent && parent.querySelector('svg path[d*="M12 4a8 8 0 1 0 8 8"]');
                        if (hasGlobeIcon && href && !href.includes('tel:') && !href.includes('mailto:')) {
                            result.website = href;
                            break;
                        }
                    }
                }
                
                // Рейтинг (из TheDenison)
                const ratingEl = document.querySelector('div._y10azs');
                if (ratingEl) result.rating = ratingEl.innerText.trim().replace(',', '.');
                
                // Отзывы (из TheDenison)
                const reviewsEl = document.querySelector('div._jspzdm');
                if (reviewsEl) result.reviews = reviewsEl.innerText.trim();
                
                // Категория (из TheDenison)
                const categoryEl = document.querySelector('div._1idnaau');
                if (categoryEl) result.category = categoryEl.innerText.trim().replace(/\\u200B/g, '');
                
                // Режим работы (из Solrikk)
                const hoursEl = document.querySelector('div._ksc2xc');
                if (hoursEl) {
                    const hoursText = hoursEl.innerText.split('\\n')[0].trim();
                    if (hoursText) result.workingHours = hoursText;
                }
                
                // Координаты из мета-тега или data-атрибутов
                const metaLat = document.querySelector('meta[property="og:latitude"]');
                const metaLon = document.querySelector('meta[property="og:longitude"]');
                if (metaLat && metaLon) {
                    result.lat = parseFloat(metaLat.getAttribute('content'));
                    result.lon = parseFloat(metaLon.getAttribute('content'));
                }
                
                return JSON.stringify(result);
            })();
            """
            
            result = self.chrome_remote._tab.Runtime.evaluate(expression=scrape_script)
            result_json = result.get('result', {}).get('value')
            
            if result_json:
                data = json.loads(result_json)
                
                # Если телефонов нет, пробуем кликнуть кнопку "Показать телефоны"
                if not data.get('phones'):
                    click_phone_script = """
                    (function() {
                        const btn = document.querySelector('button._1tkj2hw');
                        if (btn) {
                            btn.click();
                            return true;
                        }
                        return false;
                    })();
                    """
                    clicked = self.chrome_remote._tab.Runtime.evaluate(expression=click_phone_script)
                    if clicked.get('result', {}).get('value'):
                        time.sleep(0.3)  # Уменьшено с 0.5 до 0.3 секунд
                        # Повторно извлекаем телефоны
                        phones_script = """
                        (function() {
                            const phoneElements = document.querySelectorAll('div._b0ke8 a[href^="tel:"]');
                            return JSON.stringify(Array.from(phoneElements)
                                .map(el => el.href.replace('tel:', ''))
                                .filter(text => text));
                        })();
                        """
                        phones_result = self.chrome_remote._tab.Runtime.evaluate(expression=phones_script)
                        phones_json = phones_result.get('result', {}).get('value')
                        if phones_json:
                            data['phones'] = json.loads(phones_json)
                
                return data
            
            return None
            
        except Exception as e:
            logger.error(f"Ошибка скрапинга {firm_url}: {e}")
            return None
    
    def parse_url(self, url: str) -> List[CatalogItem]:
        """Parse single URL - МЕТОД С ВЕБ-СКРАПИНГОМ (БЕЗ API)"""
        if not self.chrome_remote:
            raise RuntimeError("Chrome not started")
            
        logger.info("Открываем страницу: %s", url)
        
        # Navigate to page
        logger.info("Переход на страницу...")
        self.chrome_remote.navigate(url)
        
        # Wait for page to load
        logger.info("Ждём загрузки страницы...")
        time.sleep(2)  # Уменьшено с 5 до 2 секунд
        
        items = []
        collected_ids = set()
        
        # Главный цикл парсинга
        current_page = 1
        max_pages = 50  # Ограничение страниц
        
        while current_page <= max_pages:
            logger.info(f"\n{'='*60}")
            logger.info(f"СТРАНИЦА {current_page}")
            logger.info(f"{'='*60}")
            
            # Получаем все ссылки на фирмы на текущей странице
            logger.info("Поиск ссылок на фирмы...")
            
            # Получаем весь HTML и извлекаем ID фирм
            try:
                html_result = self.chrome_remote._tab.Runtime.evaluate(expression='document.documentElement.outerHTML')
                html_content = html_result.get('result', {}).get('value', '')
                
                # Ищем все /firm/ ID в HTML
                import re
                firm_ids = re.findall(r'/firm/(\d+)', html_content)
                
                # Удаляем дубликаты
                unique_firms = list(set(firm_ids))
                
                logger.info(f"📄 В HTML найдено: {len(unique_firms)} уникальных firm ID")
                
                # Формируем ссылки (максимум 50 за раз)
                links = []
                base_url = 'https://2gis.ru'
                
                for firm_id in unique_firms[:50]:
                    if firm_id not in collected_ids:  # Пропускаем уже собранные
                        links.append({
                            'href': f"{base_url}/moscow/firm/{firm_id}",
                            'id': firm_id
                        })
                
                logger.info(f"✅ Новых ссылок для парсинга: {len(links)}")
                
                if links:
                    logger.info(f"   Примеры ID: {', '.join([l['id'][:15] for l in links[:5]])}")
            except Exception as e:
                logger.error(f"Ошибка получения ссылок: {e}")
                import traceback
                traceback.print_exc()
                links = []
                break
            
            if not links:
                logger.info("Новых ссылок не найдено, завершаем")
                break
            
            # Скрапим каждую фирму напрямую со страницы
            for i, link_data in enumerate(links, 1):
                firm_id = link_data['id']
                firm_url = link_data['href']
                
                # Проверяем лимит
                if self.config.parser.max_records > 0 and len(items) >= self.config.parser.max_records:
                    logger.info(f"✓ Достигнут лимит записей: {self.config.parser.max_records}")
                    return items
                
                logger.info(f"  [{i}/{len(links)}] Скрапинг firm ID: {firm_id}...")
                
                try:
                    # Скрапим данные со страницы фирмы
                    firm_data = self._scrape_firm_page(firm_url)
                    
                    # Возвращаемся на страницу поиска
                    logger.debug(f"    Возврат на страницу поиска...")
                    self.chrome_remote.navigate(url)
                    time.sleep(0.8)  # Уменьшено с 1.5 до 0.8 секунд
                    
                    if firm_data and firm_data.get('name'):
                        # Добавляем в собранные
                        collected_ids.add(firm_id)
                        
                        # Создаём Contact objects для контактов
                        contact_groups = []
                        contacts = []
                        
                        # Телефоны
                        for phone in firm_data.get('phones', []):
                            contacts.append(Contact(
                                type='phone',
                                text=phone,
                                value=phone
                            ))
                        
                        # Email
                        if firm_data.get('email'):
                            contacts.append(Contact(
                                type='email',
                                text=firm_data['email'],
                                value=firm_data['email']
                            ))
                        
                        # Сайт
                        if firm_data.get('website'):
                            contacts.append(Contact(
                                type='website',
                                text=firm_data['website'],
                                value=firm_data['website'],
                                url=firm_data['website']
                            ))
                        
                        if contacts:
                            contact_groups.append(ContactGroup(contacts=contacts))
                        
                        # Рубрики
                        rubrics = []
                        if firm_data.get('category'):
                            rubrics.append(Rubric(
                                name=firm_data['category']
                            ))
                        
                        # Рейтинг
                        reviews_obj = None
                        if firm_data.get('rating'):
                            try:
                                rating_float = float(firm_data['rating'])
                                reviews_count = 0
                                if firm_data.get('reviews'):
                                    # Пытаемся извлечь число из строки типа "123 отзыва"
                                    import re
                                    match = re.search(r'(\d+)', firm_data['reviews'])
                                    if match:
                                        reviews_count = int(match.group(1))
                                
                                reviews_obj = Reviews(
                                    rating=rating_float,
                                    general_rating=rating_float,
                                    general_review_count=reviews_count
                                )
                            except:
                                pass
                        
                        # Point (координаты)
                        point_obj = None
                        if firm_data.get('lat') and firm_data.get('lon'):
                            point_obj = Point(
                                lat=firm_data['lat'],
                                lon=firm_data['lon']
                            )
                        
                        # Создаём CatalogItem из скрапленных данных
                        catalog_item = CatalogItem(
                            id=firm_data.get('id') or firm_id,
                            name=firm_data.get('name', 'Не указано'),
                            address_name=firm_data.get('address', ''),
                            contact_groups=contact_groups,
                            reviews=reviews_obj,
                            rubrics=rubrics,
                            point=point_obj
                        )
                        
                        items.append(catalog_item)
                        logger.info(f"    ✅ {catalog_item.name[:50]}")
                        logger.info(f"       Телефонов: {len(firm_data.get('phones', []))}, Email: {'✓' if firm_data.get('email') else '✗'}, Сайт: {'✓' if firm_data.get('website') else '✗'}")
                    else:
                        logger.warning(f"    ⚠️  Не удалось извлечь данные")
                        
                except Exception as e:
                    logger.error(f"    ❌ Ошибка: {e}")
                    import traceback
                    logger.error(traceback.format_exc()[:400])
                
                # Задержка между запросами
                if self.config.parser.delay_between_clicks > 0:
                    time.sleep(self.config.parser.delay_between_clicks / 1000.0)
                else:
                    time.sleep(0.5)  # Задержка для веб-скрапинга
            
            logger.info(f"\n✓ Собрано с страницы {current_page}: {len(items)} уникальных организаций")
            
            # Проверяем есть ли следующая страница
            logger.info(f"Поиск следующей страницы...")
            next_page_script = f"""
            (function() {{
                var nextPageNum = {current_page + 1};
                var link = document.querySelector('a[href*="/page/' + nextPageNum + '"]');
                if (link && link.offsetParent !== null) {{
                    link.click();
                    return true;
                }}
                return false;
            }})();
            """
            
            try:
                result = self.chrome_remote._tab.Runtime.evaluate(expression=next_page_script)
                if result.get('result', {}).get('value'):
                    logger.info(f"✓ Переход на страницу {current_page + 1}")
                    current_page += 1
                    time.sleep(1.5)  # Уменьшено с 3 до 1.5 секунд
                else:
                    logger.info("Следующая страница не найдена, завершаем")
                    break
            except Exception as e:
                logger.warning(f"Ошибка перехода на следующую страницу: {e}")
                break
        
        logger.info(f"\n{'='*60}")
        logger.info(f"ИТОГО СОБРАНО: {len(items)} уникальных организаций")
        logger.info(f"{'='*60}\n")
        
        return items
    
    
    def _extract_items_from_response(self, data: Dict[str, Any]) -> List[CatalogItem]:
        """Extract catalog items from API response"""
        items = []
        try:
            if 'result' in data and 'items' in data['result']:
                for item_data in data['result']['items']:
                    try:
                        item = CatalogItem(**item_data)
                        items.append(item)
                    except Exception as e:
                        logger.debug("Ошибка создания CatalogItem: %s", e)
        except Exception as e:
            logger.warning("Ошибка извлечения items: %s", e)
        return items

# ----------------- Writer -----------------
class Writer:
    def __init__(self, config: Configuration):
        self.config = config
        
    def write(self, items: List[CatalogItem], output_path: str, file_format: str):
        """Write items to file"""
        if file_format == 'json':
            self._write_json(items, output_path)
        elif file_format == 'csv':
            self._write_csv(items, output_path)
        elif file_format == 'xlsx':
            self._write_xlsx(items, output_path)
        else:
            raise ValueError(f"Unsupported format: {file_format}")
            
    def _write_json(self, items: List[CatalogItem], output_path: str):
        """Write to JSON file"""
        with open(output_path, 'w', encoding=self.config.writer.encoding) as f:
            data = [item.model_dump() for item in items]
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("Сохранено %d записей в JSON: %s", len(items), output_path)
        
    def _write_csv(self, items: List[CatalogItem], output_path: str):
        """Write to CSV file"""
        if not items:
            logger.warning("Нет данных для записи")
            return
            
        # Prepare rows
        rows = []
        headers = set()
        
        for item in items:
            row = {
                'ID': item.id,
                'Название': item.name or '',
                'Адрес': item.address_name or '',
                'URL': item.url,
                'Широта': item.point.lat if item.point else '',
                'Долгота': item.point.lon if item.point else '',
            }
            
            # Add contacts
            phones = []
            websites = []
            emails = []
            
            for group in item.contact_groups:
                for contact in group.contacts:
                    if contact.type == 'phone':
                        phones.append(contact.value)
                    elif contact.type == 'website':
                        websites.append(contact.url or contact.value)
                    elif contact.type == 'email':
                        emails.append(contact.value)
                        
            row['Телефон'] = ', '.join(phones)
            row['Сайт'] = ', '.join(websites)
            row['Email'] = ', '.join(emails)
            
            # Add rubrics if needed
            if self.config.writer.csv.add_rubrics and item.rubrics:
                rubrics = ', '.join([r.name for r in item.rubrics])
                row['Рубрики'] = rubrics
                
            rows.append(row)
            headers.update(row.keys())
            
        # Remove empty columns if needed
        if self.config.writer.csv.remove_empty_columns:
            headers_to_keep = set()
            for header in headers:
                for row in rows:
                    if row.get(header):
                        headers_to_keep.add(header)
                        break
            headers = headers_to_keep
            
        # Remove duplicates if needed
        if self.config.writer.csv.remove_duplicates:
            seen = set()
            unique_rows = []
            for row in rows:
                key = (row.get('ID'), row.get('Название'))
                if key not in seen:
                    seen.add(key)
                    unique_rows.append(row)
            rows = unique_rows
            
        # Write CSV
        fieldnames = ['ID', 'Название', 'Адрес', 'Телефон', 'Сайт', 'Email', 'URL', 'Широта', 'Долгота']
        if 'Рубрики' in headers:
            fieldnames.append('Рубрики')
            
        with open(output_path, 'w', encoding=self.config.writer.encoding, newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(rows)
            
        logger.info("Сохранено %d записей в CSV: %s", len(rows), output_path)
        
    def _write_xlsx(self, items: List[CatalogItem], output_path: str):
        """Write to XLSX file"""
        try:
            import openpyxl
            from openpyxl import Workbook
        except ImportError:
            logger.error("openpyxl не установлен. Установите: pip install openpyxl")
            return
            
        if not items:
            logger.warning("Нет данных для записи")
            return
            
        wb = Workbook()
        ws = wb.active
        ws.title = "Данные 2GIS"
        
        # Headers
        headers = ['ID', 'Название', 'Адрес', 'Телефон', 'Сайт', 'Email', 'URL', 'Широта', 'Долгота']
        if self.config.writer.csv.add_rubrics:
            headers.append('Рубрики')
        ws.append(headers)
        
        # Data
        for item in items:
            phones = []
            websites = []
            emails = []
            
            for group in item.contact_groups:
                for contact in group.contacts:
                    if contact.type == 'phone':
                        phones.append(contact.value)
                    elif contact.type == 'website':
                        websites.append(contact.url or contact.value)
                    elif contact.type == 'email':
                        emails.append(contact.value)
                        
            row = [
                item.id,
                item.name or '',
                item.address_name or '',
                ', '.join(phones),
                ', '.join(websites),
                ', '.join(emails),
                item.url,
                item.point.lat if item.point else '',
                item.point.lon if item.point else '',
            ]
            
            if self.config.writer.csv.add_rubrics:
                rubrics = ', '.join([r.name for r in item.rubrics])
                row.append(rubrics)
                
            ws.append(row)
            
        wb.save(output_path)
        logger.info("Сохранено %d записей в XLSX: %s", len(items), output_path)

# ----------------- GUIRunner (restored with real parsing) -----------------
class GUIRunner(threading.Thread):
    def __init__(self, urls: List[str], output_path: str, file_format: str, config: Configuration):
        super().__init__()
        self.urls = urls
        self.output_path = output_path
        self.file_format = file_format
        self.config = config
        self._stop_event = threading.Event()
        self.parser: Optional[Parser2GIS] = None
        
    def stop(self):
        self._stop_event.set()
        if self.parser:
            try:
                self.parser.stop()
            except Exception:
                pass
                
    def run(self):
        try:
            logger.info("🔧 Инициализация парсера...")
            logger.info("📊 URLs для парсинга: %d", len(self.urls))
            logger.info("💾 Формат вывода: %s", self.file_format.upper())
            logger.info("📁 Файл результата: %s", self.output_path)
            logger.info("")
            
            self.parser = Parser2GIS(self.config)
            self.parser.start()
            
            all_items = []
            
            for idx, url in enumerate(self.urls, 1):
                if self._stop_event.is_set():
                    logger.info("⏹ Парсинг остановлен пользователем")
                    break
                    
                try:
                    logger.info("")
                    logger.info("📌 [%d/%d] Парсинг URL: %s", idx, len(self.urls), url)
                    logger.info("-" * 60)
                    items = self.parser.parse_url(url)
                    all_items.extend(items)
                    
                    logger.info("✅ Найдено записей: %d", len(items))
                    logger.info("📊 Всего собрано: %d записей", len(all_items))
                    
                    if self.config.writer.verbose and items:
                        logger.info("")
                        logger.info("📋 Примеры найденных организаций:")
                        for i, item in enumerate(items[:5], 1):  # Show first 5
                            logger.info("  %d. %s", i, item.name)
                        if len(items) > 5:
                            logger.info("  ... и ещё %d", len(items) - 5)
                    
                    # Check max records limit
                    if self.config.parser.max_records > 0 and len(all_items) >= self.config.parser.max_records:
                        logger.info("")
                        logger.info("⚠️  Достигнут лимит записей: %d", self.config.parser.max_records)
                        all_items = all_items[:self.config.parser.max_records]
                        break
                        
                    # Delay between URLs
                    if self.config.parser.delay_between_clicks > 0:
                        time.sleep(self.config.parser.delay_between_clicks / 1000.0)
                        
                except Exception as e:
                    logger.error("❌ Ошибка при парсинге %s: %s", url, e)
                    if not self.config.parser.skip_404_response:
                        raise
                        
            # Stop browser
            logger.info("")
            logger.info("🔄 Закрытие браузера...")
            self.parser.stop()
            
            # Write results
            if all_items:
                logger.info("")
                logger.info("=" * 60)
                logger.info("💾 СОХРАНЕНИЕ РЕЗУЛЬТАТОВ")
                logger.info("=" * 60)
                logger.info("📊 Всего собрано записей: %d", len(all_items))
                logger.info("📁 Сохранение в: %s", self.output_path)
                writer = Writer(self.config)
                writer.write(all_items, self.output_path, self.file_format)
                logger.info("")
                logger.info("=" * 60)
                logger.info("✅ ПАРСИНГ ЗАВЕРШЁН УСПЕШНО!")
                logger.info("=" * 60)
                logger.info("📊 Собрано: %d записей", len(all_items))
                logger.info("📁 Файл: %s", self.output_path)
                logger.info("=" * 60)
            else:
                logger.warning("")
                logger.warning("⚠️  Не найдено ни одной записи")
                logger.warning("Проверьте URL и настройки прокси")
                
        except Exception as e:
            logger.error("")
            logger.error("=" * 60)
            logger.exception("❌ КРИТИЧЕСКАЯ ОШИБКА ПАРСЕРА")
            logger.error("=" * 60)
        finally:
            if self.parser:
                try:
                    self.parser.stop()
                except Exception:
                    pass

# ----------------- Main GUI -----------------
def gui_app(urls: List[str], output_path: str, format: str, config: Configuration) -> None:
    root = tk.Tk()
    root.title(f"Парсер 2GIS v{VERSION} - Профессиональный сбор данных")
    root.geometry("1000x750")
    style = ttk.Style()
    try:
        style.theme_create("2gisgreen", parent="default", settings={
            "TFrame": {"configure": {"background": "#1B5E20"}},
            "TLabel": {"configure": {"background": "#1B5E20", "foreground": "white"}},
            "TLabelFrame": {"configure": {"background": "#1B5E20", "foreground": "white"}},
            "TEntry": {"configure": {"fieldbackground": "white", "foreground": "black"}},
            "TCombobox": {"configure": {"fieldbackground": "white", "foreground": "black"}},
            "TButton": {"configure": {"background": "#2E7D32", "foreground": "white", "padding": 6}},
            "Horizontal.TProgressbar": {"configure": {"background": "#2E7D32"}},
            "TCheckbutton": {"configure": {"background": "#1B5E20", "foreground": "white"}},
            "TSpinbox": {"configure": {"fieldbackground": "white", "foreground": "black"}},
            "TNotebook": {"configure": {"background": "#1B5E20"}},
            "TNotebook.Tab": {"configure": {"background": "#2E7D32", "foreground": "white"}},
        })
        style.theme_use("2gisgreen")
        style.map('TButton', background=[('active', '#1B5E20')])
    except Exception:
        try:
            style.theme_use("default")
        except Exception:
            pass
    root.configure(bg="#1B5E20")
    log_queue: queue.Queue = queue.Queue()
    setup_gui_logger(log_queue, config.log)

    # --- Update banner (hidden by default, shown if new version found) ---
    update_bar = tk.Frame(root, bg="#FFF9C4", height=36)
    update_msg_var = tk.StringVar()
    update_url_holder = [None]  # mutable holder for URL
    tk.Label(update_bar, textvariable=update_msg_var, bg="#FFF9C4", fg="#333333",
             font=("TkDefaultFont", 9, "bold")).pack(side=tk.LEFT, padx=10)
    update_download_btn = tk.Button(update_bar, text="⬇ Скачать обновление",
                                     bg="#43A047", fg="white", activebackground="#66BB6A",
                                     activeforeground="white", relief=tk.FLAT, bd=0,
                                     font=("TkDefaultFont", 9, "bold"), cursor="hand2", padx=8, pady=2,
                                     command=lambda: webbrowser.open(update_url_holder[0]) if update_url_holder[0] else None)
    update_download_btn.pack(side=tk.LEFT, padx=6)
    update_close_btn = tk.Button(update_bar, text="✕", bg="#FFF9C4", fg="#666666",
                                  relief=tk.FLAT, bd=0, cursor="hand2",
                                  command=lambda: update_bar.pack_forget())
    update_close_btn.pack(side=tk.RIGHT, padx=6)

    def _check_updates_bg():
        info = check_for_updates()
        if info:
            update_msg_var.set(f"🔔  Доступна новая версия v{info['version']}!")
            update_url_holder[0] = info['url']
            update_bar.pack(fill=tk.X, before=main_frame)
            logger.info("🔔 Доступно обновление: v%s → v%s", VERSION, info['version'])
            if info.get('notes'):
                logger.info("   Изменения: %s", info['notes'][:120])
    threading.Thread(target=_check_updates_bg, daemon=True).start()
    
    # Welcome message
    logger.info("=" * 60)
    logger.info("🚀 Parser 2GIS v%s - Профессиональный парсер данных", VERSION)
    logger.info("=" * 60)
    logger.info("✨ Добро пожаловать!")
    logger.info("")
    logger.info("📋 Возможности:")
    logger.info("  • Парсинг организаций, телефонов, адресов из 2GIS")
    logger.info("  • Поддержка SX.ORG прокси (резидентские, мобильные)")
    logger.info("  • Headless режим для максимальной скорости")
    logger.info("  • Экспорт в CSV, XLSX, JSON")
    logger.info("")
    logger.info("⚙️  Текущие настройки:")
    logger.info("  • Headless: %s", "Да" if config.chrome.headless else "Нет")
    logger.info("  • Прокси: %s", config.chrome.proxy_method.upper())
    if config.chrome.proxy_method == "sxorg" and config.chrome.sxorg_api_key:
        logger.info("  • SX.ORG API: настроен ✅")
    elif config.chrome.proxy_method == "sxorg":
        logger.info("  • SX.ORG API: НЕ НАСТРОЕН ⚠️")
        logger.info("  • Откройте Настройки → Прокси для настройки")
    logger.info("")
    logger.info("💡 Подсказка: Используйте SX.ORG для надежного парсинга!")
    logger.info("   Получите +3 ГБ по промокоду: Настройки → Прокси")
    logger.info("=" * 60)
    logger.info("")
    
    main_frame = ttk.Frame(root, padding=8)
    main_frame.pack(fill=tk.BOTH, expand=True)
    url_frame = ttk.Frame(main_frame)
    url_frame.pack(fill=tk.X, pady=4)
    ttk.Label(url_frame, text="URL").pack(side=tk.LEFT, padx=6)
    
    # История URL (сохраняем в конфиге)
    url_history = getattr(config, 'url_history', []) if hasattr(config, 'url_history') else []
    
    url_var = tk.StringVar()
    url_combo = ttk.Combobox(url_frame, textvariable=url_var, values=url_history)
    url_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
    
    def add_to_history(url):
        """Добавляет URL в историю"""
        if url and url not in url_history:
            url_history.insert(0, url)
            if len(url_history) > 20:  # Максимум 20 URL
                url_history.pop()
            url_combo['values'] = url_history
            # Сохраняем в конфиг
            config.url_history = list(url_history)
            config.save_config()
    
    def open_urls_editor():
        new = gui_urls_editor(urls) or urls
        urls[:] = new
        update_urls_input()
    ttk.Button(url_frame, text="...", command=open_urls_editor).pack(side=tk.LEFT, padx=6)
    def update_urls_input():
        urls_length = len(urls)
        if urls_length == 0:
            url_var.set("")
        elif urls_length == 1:
            url_var.set(urls[0])
        else:
            url_var.set(f"<{urls_length} ссылок>")
    update_urls_input()
    # result
    result_frame = ttk.Frame(main_frame)
    result_frame.pack(fill=tk.X, pady=6)
    ttk.Label(result_frame, text="Тип").pack(side=tk.LEFT, padx=6)
    format_var = tk.StringVar(value=format)
    format_combo = ttk.Combobox(result_frame, textvariable=format_var, values=["csv", "xlsx", "json"], state="readonly", width=8)
    format_combo.pack(side=tk.LEFT, padx=6)
    output_var = tk.StringVar(value=output_path)
    ttk.Label(result_frame, text="Путь").pack(side=tk.LEFT, padx=6)
    ttk.Entry(result_frame, textvariable=output_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
    ttk.Button(result_frame, text="Обзор", command=lambda: output_var.set(filedialog.asksaveasfilename(defaultextension=f".{format_var.get()}", filetypes=[("CSV", "*.csv"), ("Excel", "*.xlsx"), ("JSON", "*.json")]) or output_var.get())).pack(side=tk.LEFT, padx=6)
    # log
    log_frame = ttk.LabelFrame(main_frame, text="Лог")
    log_frame.pack(fill=tk.BOTH, expand=True, pady=6)
    log_text = ScrolledText(log_frame, height=18)
    log_text.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
    progress = ttk.Progressbar(main_frame, orient='horizontal', length=400, mode='indeterminate')
    progress.pack(fill=tk.X, pady=6)
    bottom_frame = ttk.Frame(main_frame)
    bottom_frame.pack(fill=tk.X, pady=6)
    
    # Status label
    status_var = tk.StringVar(value="Готов к работе 🟢")
    status_label = ttk.Label(bottom_frame, textvariable=status_var, font=("TkDefaultFont", 9, "bold"))
    status_label.pack(side=tk.LEFT, padx=6)
    
    ttk.Label(bottom_frame, text=f"v{VERSION}").pack(side=tk.LEFT, padx=(0, 20))
    start_btn = ttk.Button(bottom_frame, text="▶ Запуск")
    start_btn.pack(side=tk.LEFT, padx=6)
    stop_btn = ttk.Button(bottom_frame, text="⏹ Стоп", state="disabled")
    stop_btn.pack(side=tk.LEFT, padx=6)
    ttk.Button(bottom_frame, text="⚙ Настройки", command=lambda: gui_settings(config)).pack(side=tk.LEFT, padx=6)
    ttk.Button(bottom_frame, text="❌ Выход", command=root.destroy).pack(side=tk.RIGHT, padx=6)
    parsing_thread: List[Optional[GUIRunner]] = [None]
    def parsing_thread_running() -> bool:
        return parsing_thread[0] is not None and parsing_thread[0].is_alive()
    def on_start():
        if not output_var.get():
            messagebox.showerror("Ошибка", "Отсутствует путь результирующего файла!")
            return
        current_url = url_var.get().strip()
        if not current_url or current_url.startswith("<"):
            if len(urls) == 0:
                messagebox.showerror("Ошибка", "Отсутствует URL!")
                return
        else:
            urls[:] = [current_url]
            add_to_history(current_url)  # Добавляем в историю
        if not parsing_thread_running():
            try:
                status_var.set("Запуск парсера... 🔄")
                logger.info("")
                logger.info("🚀 СТАРТ ПАРСИНГА")
                logger.info("=" * 60)
                progress.start()
                parsing_thread[0] = GUIRunner(list(urls), output_var.get(), format_var.get(), config)
                parsing_thread[0].start()
                start_btn.config(state="disabled")
                stop_btn.config(state="normal")
                status_var.set("Парсинг в процессе... ⚙️")
            except Exception as e:
                logger.exception("❌ Ошибка запуска парсера: %s", e)
                progress.stop()
                parsing_thread[0] = None
                status_var.set("Ошибка! 🔴")
    def on_stop():
        logger.info("⏹ Остановка парсера...")
        status_var.set("Остановка... ⏸️")
        if parsing_thread_running():
            parsing_thread[0].stop()
            parsing_thread[0].join(timeout=5)
            parsing_thread[0] = None
        stop_btn.config(state="disabled")
        start_btn.config(state="normal")
        progress.stop()
        status_var.set("Остановлено ⏹")
        logger.info("✓ Парсер остановлен")
    start_btn.config(command=on_start)
    stop_btn.config(command=on_stop)
    def update_log():
        while True:
            try:
                msg = log_queue.get(block=False)
                log_text.insert(tk.END, msg + "\n")
                log_text.see(tk.END)
            except queue.Empty:
                break
        if parsing_thread_running():
            start_btn.config(state="disabled")
            stop_btn.config(state="normal")
        else:
            # Thread stopped - check if it was manual stop or completion
            if parsing_thread[0] is not None and not parsing_thread[0].is_alive():
                # Thread completed
                status_var.set("Готов к работе 🟢")
            start_btn.config(state="normal")
            stop_btn.config(state="disabled")
            progress.stop()
        root.after(150, update_log)
    root.after(150, update_log)
    root.mainloop()

# ----------------- CLI / argparse (restored) -----------------
def unwrap_dot_dict(d: Dict[str, Any]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in d.items():
        if "." in key:
            parent, child = key.split(".", 1)
            result[parent] = result.get(parent, {})
            result[parent][child] = value
        else:
            result[key] = value
    return result

class ArgumentHelpFormatter(argparse.HelpFormatter):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._default_config = Configuration().model_dump()
    def _get_default_value(self, dest: str) -> Any:
        if dest == "version":
            return argparse.SUPPRESS
        fields = dest.split(".")
        value = self._default_config
        try:
            for field in fields:
                value = value[field]
            return value
        except Exception:
            return argparse.SUPPRESS
    def _get_help_string(self, action: argparse.Action) -> str | None:
        help_string = action.help
        if help_string:
            default_value = self._get_default_value(action.dest)
            if default_value != argparse.SUPPRESS:
                if isinstance(default_value, bool):
                    default_value = "yes" if default_value else "no"
                help_string += f" (по умолчанию: {default_value})"
        return help_string

def patch_argparse_translations() -> None:
    custom_translations = {"usage: ": "Использование: ", "one of the arguments %s is required": "один из аргументов %s обязателен", "unrecognized arguments: %s": "нераспознанные аргументы: %s", "the following arguments are required: %s": "следующие аргументы обязательны: %s", "%(prog)s: error: %(message)s\n": "%(prog)s: ошибка: %(message)s\n", "invalid choice: %(value)r (choose from %(choices)s)": "неверная опция: %(value)r (выберите одну из %(choices)s)"}
    try:
        orig_gettext = argparse._  # type: ignore[attr-defined]
    except Exception:
        orig_gettext = lambda s: s
    def gettext(message: str) -> str:
        return custom_translations.get(message, orig_gettext(message))
    argparse._ = gettext  # type: ignore[attr-defined]
    def argument_error__str__(self: argparse.ArgumentError) -> str:
        if self.argument_name is None:
            format = "%(message)s"
        else:
            format = "аргумент %(argument_name)s: %(message)s"
        return format % dict(message=self.message, argument_name=self.argument_name)
    argparse.ArgumentError.__str__ = argument_error__str__  # type: ignore

def parse_arguments() -> tuple[argparse.Namespace, Configuration]:
    patch_argparse_translations()
    arg_parser = argparse.ArgumentParser("Parser2GIS", description="Парсер данных сайта 2GIS", add_help=False, formatter_class=ArgumentHelpFormatter, argument_default=argparse.SUPPRESS)
    GUI_ENABLED = True
    main_parser_name = "Основные аргументы" if GUI_ENABLED else "Обязательные аргументы"
    main_parser_required = False if GUI_ENABLED else True
    main_parser = arg_parser.add_argument_group(main_parser_name)
    main_parser.add_argument("-i", "--url", nargs="+", default=None, required=main_parser_required, help="URL с выдачей")
    main_parser.add_argument("-o", "--output-path", metavar="PATH", default=None, required=main_parser_required, help="Путь до результирующего файла")
    main_parser.add_argument("-f", "--format", choices=["csv", "xlsx", "json"], default=None, required=main_parser_required, help="Формат результирующего файла")
    browser_parser = arg_parser.add_argument_group("Аргументы браузера")
    browser_parser.add_argument("--chrome.binary_path", metavar="PATH", help="Путь до исполняемого файла chromedriver")
    browser_parser.add_argument("--chrome.disable_images", choices=["yes", "no"], default="no", help="Отключить изображения")
    browser_parser.add_argument("--chrome.start_maximized", choices=["yes", "no"], default="no", help="Запускать развёрнутым")
    browser_parser.add_argument("--chrome.headless", choices=["yes", "no"], default="no", help="Скрытый режим")
    browser_parser.add_argument("--chrome.memory_limit", type=int, help="Лимит RAM")
    browser_parser.add_argument("--chrome.proxy_file", metavar="PATH", help="Путь до файла с прокси (IP:PORT или IP:PORT:USERNAME:PASSWORD)")
    browser_parser.add_argument("--chrome.proxy_method", choices=["file", "sxorg"], default="file", help="Метод получения прокси (file или sxorg)")
    browser_parser.add_argument("--chrome.sxorg_api_key", metavar="KEY", help="API-ключ для SX.ORG")
    other_parser = arg_parser.add_argument_group("Прочие аргументы")
    other_parser.add_argument("--writer.encoding", choices=["utf8", "1251"], default="utf8", help="Кодировка результирующего файла")
    other_parser.add_argument("--writer.verbose", choices=["yes", "no"], default="yes", help="Выводить имена парсируемых объектов")
    other_parser.add_argument("--writer.csv.add_rubrics", choices=["yes", "no"], default="yes", help='Добавить "Рубрики"')
    other_parser.add_argument("--writer.csv.add_comments", choices=["yes", "no"], default="yes", help="Добавлять комментарии")
    other_parser.add_argument("--writer.csv.remove_empty_columns", choices=["yes", "no"], default="yes", help="Удалить пустые колонки")
    other_parser.add_argument("--writer.csv.remove_duplicates", choices=["yes", "no"], default="yes", help="Удалить дубликаты")
    other_parser.add_argument("--writer.csv.columns_per_entity", type=int, help="Сложные колонки")
    other_parser.add_argument("--parser.skip_404_response", choices=["yes", "no"], default="yes", help="Пропускать 404 ответы")
    other_parser.add_argument("--parser.delay_between_clicks", type=int, help="Задержка кликов")
    other_parser.add_argument("--parser.max_records", type=int, help="Максимальное количество записей")
    other_parser.add_argument("--parser.use_gc", choices=["yes", "no"], default="no", help="Использовать сборщик мусора")
    other_parser.add_argument("--parser.gc_pages_interval", type=int, help="Интервал сборщика мусора")
    rest_parser = arg_parser.add_argument_group("Служебные аргументы")
    rest_parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {VERSION}", help="Показать версию программы и выйти")
    rest_parser.add_argument("-h", "--help", action="help", help="Показать это сообщение и выйти")
    args = arg_parser.parse_args()
    config_args = {k: v for k, v in vars(args).items() if v is not None}
    for k, v in list(config_args.items()):
        if v in ("yes", "no"):
            config_args[k] = v == "yes"
    config = Configuration.load_config(auto_create=True)
    try:
        if config_args:
            new_config = Configuration(**unwrap_dot_dict(config_args))
            config.merge_with(new_config)
            config.save_config()
    except pydantic.ValidationError as e:
        logger.error("Ошибка валидации аргументов: %s", e)
        sys.exit(1)
    return args, config

# ----------------- Main -----------------
def main():
    GUI_ENABLED = True
    args, config = parse_arguments()
    urls = getattr(args, 'url', []) or []
    output_path = getattr(args, 'output_path', '') or ''
    file_format = getattr(args, 'format', 'csv') or 'csv'
    if GUI_ENABLED:
        gui_app(urls, output_path, file_format, config)
    else:
        if not urls or not output_path or not file_format:
            logger.error("Необходимо указать URL, путь к файлу и формат вывода.")
            sys.exit(1)
        runner = GUIRunner(urls, output_path, file_format, config)
        runner.start()
        runner.join()

if __name__ == "__main__":
    main()