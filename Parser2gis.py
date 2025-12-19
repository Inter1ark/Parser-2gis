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
VERSION = "1.2.1"

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
def load_sxorg_proxies(api_key: str, country: Optional[str] = None, city: Optional[str] = None, state: Optional[str] = None) -> List[Dict[str, str]]:
    proxies = []
    url = "https://api.sx.org/v2/proxy/ports"
    params = {"apiKey": api_key, "per_page": 100}
    if country:
        params["countryName"] = country
    if city:
        params["cityName"] = city
    if state:
        params["stateName"] = state

    session = requests.Session()
    retries = Retry(total=5, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retries))
    try:
        logger.info("Запрос SX.ORG %s %s", url, params)
        resp = session.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if not data.get('success', False):
            logger.error("SX.ORG API returned error: %s", data.get('message'))
            return []
        proxies_src = []
        if 'message' in data and isinstance(data['message'], dict):
            proxies_src = data['message'].get('proxies', [])
        elif 'proxies' in data:
            proxies_src = data.get('proxies', [])
        for proxy in proxies_src:
            proxy_str = proxy.get('proxy') or proxy.get('server') or ''
            if ':' in proxy_str:
                host, port = proxy_str.split(':', 1)
            else:
                host = proxy_str
                port = str(proxy.get('port', ''))
            proxies.append({
                'host': host,
                'port': port,
                'username': proxy.get('login') or proxy.get('username') or '',
                'password': proxy.get('password') or '',
                'country': proxy.get('countryCode') or proxy.get('country', ''),
                'city': proxy.get('cityName') or proxy.get('city', ''),
                'state': proxy.get('stateName') or proxy.get('state', ''),
                'type': 'Residential' if proxy.get('proxy_type_id') == 1 else 'Mobile' if proxy.get('proxy_type_id') == 3 else 'Corporate' if proxy.get('proxy_type_id') == 4 else 'Unknown',
                'name': proxy.get('name', ''),
                'traffic_used': proxy.get('spent_traffic_current_month', 0),
                'traffic_limit': proxy.get('traffic_limit', 0)
            })
        logger.info("Загружено %d прокси", len(proxies))
        return proxies
    except requests.exceptions.RequestException as e:
        logger.error("Ошибка SX.ORG: %s", e)
        return []
    finally:
        session.close()

def get_sxorg_balance(api_key: str) -> str:
    url = "https://api.sx.org/v2/user/balance"
    params = {"apiKey": api_key}
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=Retry(total=3)))
    try:
        resp = session.get(url, params=params, timeout=10)
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

def create_sxorg_proxy(api_key: str, country_code: str, proxy_type_id: str, connection_type_id: str, name: Optional[str] = None, traffic_limit: Optional[int] = None, state: Optional[str] = None, city: Optional[str] = None, asn: Optional[int] = None) -> Dict[str, Any]:
    url = "https://api.sx.org/v2/proxy/create-port"
    params = {"apiKey": api_key}
    payload = {
        "country_code": country_code,
        "proxy_type_id": proxy_type_id,
        "server_port_type_id": "1",
        "type_id": connection_type_id
    }
    if name:
        payload["name"] = name
    if traffic_limit:
        payload["traffic_limit"] = traffic_limit
    if state:
        payload["state"] = state
    if city:
        payload["city"] = city
    if asn:
        payload["asn"] = asn

    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=Retry(total=3)))
    try:
        resp = session.post(url, params=params, json=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if not data.get('success', False):
            logger.error("SX.ORG create error: %s", data.get('message'))
            return {}
        proxy = data.get('data', {}) or {}
        if isinstance(proxy, list):
            proxy = proxy[0] if proxy else {}
        return {
            'host': proxy.get('server', ''),
            'port': str(proxy.get('port', '')),
            'username': proxy.get('login', ''),
            'password': proxy.get('password', ''),
            'country': proxy.get('country_code', ''),
            'city': proxy.get('city', ''),
            'state': proxy.get('state', ''),
            'type': 'Residential' if proxy.get('proxy_type_id') == 1 else 'Mobile' if proxy.get('proxy_type_id') == 3 else 'Corporate' if proxy.get('proxy_type_id') == 4 else 'Unknown',
            'name': proxy.get('name', ''),
            'traffic_used': proxy.get('spent_traffic_month', 0),
            'traffic_limit': proxy.get('traffic_limit', 0)
        }
    except Exception as e:
        logger.error("Ошибка создания SX.ORG прокси: %s", e)
        return {}
    finally:
        session.close()

# ----------------- proxy file loader -----------------
def load_proxy_file(file_path: str, proxy_method: str, api_key: Optional[str] = None, country: Optional[str] = None, city: Optional[str] = None, state: Optional[str] = None) -> List[Dict[str, str]]:
    """Загрузка прокси. SX.ORG не мешает запуску без ключа, file работает как раньше"""
    if proxy_method == 'sxorg':
        logger.info("Прокси SX.ORG успешно загружены!")
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
    disable_images: bool = True  # Отключаем картинки для скорости
    start_maximized: bool = False
    headless: bool = True  # Включаем headless по умолчанию
    memory_limit: int = default_memory_limit()
    user_data_dir: Optional[str] = None
    proxy_file: Optional[str] = None
    proxy_list: List[Dict[str, str]] = []
    proxy_method: str = 'sxorg'
    sxorg_api_key: Optional[str] = None
    sxorg_country: Optional[str] = None
    sxorg_city: Optional[str] = None
    sxorg_state: Optional[str] = None

    @field_validator('proxy_file')
    @classmethod
    def validate_proxy_file(cls, v: str | None, info: pydantic.ValidationInfo) -> str | None:
        if v and info.data.get('proxy_method') == 'file' and not os.path.exists(v):
            raise ValueError(f"Файл прокси {v} не существует")
        return v

    @field_validator('sxorg_api_key')
    @classmethod
    def validate_sxorg_api_key(cls, v: str | None, info: pydantic.ValidationInfo) -> str | None:
        if info.data.get('proxy_method') == 'sxorg' and not v:
            raise ValueError("API-ключ SX.ORG обязателен при выборе метода SX.ORG")
        return v

# ChromeBrowser and ChromeRemote are restored for completeness; implementation similar to earlier versions
class ChromeBrowser:
    def __init__(self, options: ChromeOptions):
        self.options = options
        self._temp_dir = None
        self._process = None
        self._debug_port = None

    def start(self):
        chrome_path = self.options.binary_path or locate_chrome_path()
        if not chrome_path:
            raise ChromePathNotFound("Chrome binary not found")
        
        # Логируем настройки браузера
        logger.info("🔧 Настройки Chrome:")
        logger.info("   - headless: %s", self.options.headless)
        logger.info("   - disable_images: %s", self.options.disable_images)
        logger.info("   - proxy_method: %s", self.options.proxy_method)
        
        # Создаём временную директорию СНАЧАЛА
        self._temp_dir = tempfile.mkdtemp()
        
        # Загружаем прокси ПЕРЕД запуском браузера
        self.options.proxy_list = load_proxy_file(
            self.options.proxy_file,
            self.options.proxy_method,
            self.options.sxorg_api_key,
            self.options.sxorg_country,
            self.options.sxorg_city,
            self.options.sxorg_state
        )
        
        # Generate port once and save it
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
        
        # Если есть прокси с авторизацией - ОТКЛЮЧАЕМ headless (он не поддерживает прокси-авторизацию)
        proxy_has_auth = False
        if self.options.proxy_list:
            proxy = random.choice(self.options.proxy_list)
            proxy_host = proxy.get('host')
            proxy_port = proxy.get('port')
            proxy_user = proxy.get('username')
            proxy_pass = proxy.get('password')
            
            logger.info("🔍 Прокси данные:")
            logger.info("   Host: %s", proxy_host)
            logger.info("   Port: %s", proxy_port)
            logger.info("   User: %s", proxy_user)
            logger.info("   Pass: %s", '***' if proxy_pass else None)
            
            if proxy_user and proxy_pass:
                proxy_has_auth = True
                logger.warning("⚠️  Прокси требует авторизацию - headless режим ОТКЛЮЧЕН")
                # Создаём расширение Chrome для автоматической авторизации
                logger.info("🔐 Создание расширения для автоматической авторизации прокси...")
                proxy_auth_ext = self._create_proxy_auth_extension(
                    proxy_host, proxy_port, proxy_user, proxy_pass
                )
                args.append(f"--load-extension={proxy_auth_ext}")
                logger.info("✅ Расширение создано")
            
            proxy_str = f"{proxy_host}:{proxy_port}"
            args.append(f"--proxy-server={proxy_str}")
            logger.info("🌐 Используется прокси: %s (RU резидентский)", proxy_str)
        
        # Headless режим только если НЕТ прокси с авторизацией
        if self.options.headless and not proxy_has_auth:
            args.append("--headless=new")
            logger.info("👻 Headless режим включен")
            # Маскировка headless: подменяем user-agent и отключаем webdriver
            args.append('--disable-blink-features=AutomationControlled')
            args.append('--disable-infobars')
            # Пример обычного user-agent Chrome для Mac
            ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            args.append(f'--user-agent={ua}')
        elif proxy_has_auth:
            logger.info("🖥️  Браузер запускается с GUI (требуется для прокси-авторизации)")
            
        if self.options.disable_images:
            args.append("--blink-settings=imagesEnabled=false")
        if self.options.start_maximized and not proxy_has_auth:
            args.append("--start-maximized")

        self._process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        logger.info("✅ Chrome запущен на порту %d", self._debug_port)
        return self._process.pid
    
    def _create_proxy_auth_extension(self, host: str, port: str, username: str, password: str) -> str:
        """Создаёт расширение Chrome для автоматической авторизации в прокси"""
        ext_dir = os.path.join(self._temp_dir, 'proxy_auth_extension')
        os.makedirs(ext_dir, exist_ok=True)
        
        # manifest.json
        manifest = {
            "version": "1.0.0",
            "manifest_version": 2,
            "name": "Proxy Auto Auth",
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
        }
        
        with open(os.path.join(ext_dir, 'manifest.json'), 'w') as f:
            json.dump(manifest, f)
        
        # background.js
        background_js = f"""
var config = {{
    mode: "fixed_servers",
    rules: {{
        singleProxy: {{
            scheme: "http",
            host: "{host}",
            port: parseInt({port})
        }},
        bypassList: ["localhost"]
    }}
}};

chrome.proxy.settings.set({{value: config, scope: "regular"}}, function() {{}});

function callbackFn(details) {{
    return {{
        authCredentials: {{
            username: "{username}",
            password: "{password}"
        }}
    }};
}}

chrome.webRequest.onAuthRequired.addListener(
    callbackFn,
    {{urls: ["<all_urls>"]}},
    ['blocking']
);
"""
        
        with open(os.path.join(ext_dir, 'background.js'), 'w') as f:
            f.write(background_js)
        
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
        
        # Enable Fetch domain for proxy authentication
        if self._browser.options.proxy_list:
            proxy = self._browser.options.proxy_list[0]  # Используем первый прокси из списка
            proxy_user = proxy.get('username')
            proxy_pass = proxy.get('password')
            
            if proxy_user and proxy_pass:
                logger.info("🔐 Настройка автоматической авторизации прокси через DevTools...")
                try:
                    # Enable Fetch domain
                    self._tab.Fetch.enable(
                        patterns=[{
                            "urlPattern": "*",
                            "requestStage": "Request"
                        }]
                    )
                    
                    # Set up auth handler
                    def handle_auth_required(**params):
                        request_id = params.get('requestId')
                        auth_challenge = params.get('authChallenge')
                        
                        if auth_challenge:
                            logger.info("🔓 Автоматическая авторизация прокси...")
                            try:
                                self._tab.Fetch.continueWithAuth(
                                    requestId=request_id,
                                    authChallengeResponse={
                                        "response": "ProvideCredentials",
                                        "username": proxy_user,
                                        "password": proxy_pass
                                    }
                                )
                                logger.info("✅ Прокси авторизован")
                            except Exception as e:
                                logger.error("❌ Ошибка авторизации: %s", e)
                                # Continue without auth on error
                                try:
                                    self._tab.Fetch.continueRequest(requestId=request_id)
                                except:
                                    pass
                        else:
                            # No auth required, continue normally
                            try:
                                self._tab.Fetch.continueRequest(requestId=request_id)
                            except:
                                pass
                    
                    self._tab.Fetch.requestPaused = handle_auth_required
                    logger.info("✅ Автоматическая авторизация настроена")
                except Exception as e:
                    logger.warning("⚠️ Не удалось настроить автоматическую авторизацию: %s", e)
        
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
    max_records: int = 100000
    use_gc: bool = False
    gc_pages_interval: int = 5

class Configuration(pydantic.BaseModel):
    chrome: ChromeOptions = ChromeOptions()
    log: LogOptions = LogOptions()
    parser: ParserOptions = ParserOptions()
    writer: WriterOptions = WriterOptions()

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
    # SX.ORG is default
    proxy_method_var = tk.StringVar(value=PROXY_VALUE_TO_DISPLAY.get(config.chrome.proxy_method, "SX.ORG (Рекомендовано)"))
    proxy_method_combo = ttk.Combobox(top_frame, textvariable=proxy_method_var, values=list(PROXY_DISPLAY_TO_VALUE.keys()), state="readonly", width=36)
    proxy_method_combo.pack(side=tk.LEFT, padx=(8,0))

    main = ttk.Frame(proxy_frame)
    main.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)
    left = ttk.Frame(main)
    left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    right = tk.Frame(main, width=260, bg="#FFF9C4", relief=tk.GROOVE, bd=1)
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
    sx_import_btn = ttk.Button(left, text="Импортировать прокси SX.ORG")
    sx_create_btn = ttk.Button(left, text="Создать новый прокси SX.ORG")
    sx_listbox = tk.Listbox(left, height=8, width=72)

    # Right banner
    banner_title = tk.Label(right, text="SX.ORG — промокод 2GiS", bg="#FFF9C4", fg="#2E7D32", font=("TkDefaultFont", 11, "bold"), anchor="w")
    banner_text = tk.Label(right, text="Получите +3 ГБ трафика по промокоду.\nНажмите кнопку для перехода на сайт.", bg="#FFF9C4", fg="#000000", justify="left", wraplength=220)
    banner_btn = ttk.Button(right, text="Получить прокси SX.ORG", command=lambda: webbrowser.open("https://sx.org/ru/?c=parse"))
    banner_title.pack(anchor="n", fill=tk.X, pady=(12,4), padx=8)
    banner_text.pack(anchor="n", fill=tk.X, padx=8)
    banner_btn.pack(anchor="n", pady=(8,12))

    ttk.Button(left, text="Инструкция по настройке ПРОКСИ", command=lambda: webbrowser.open("https://docs.google.com/document/d/1V5TB00h8W3B9arFZUK9uhuYxk_fxjAj5AXK9qgnL7lk/edit?usp=sharing")).pack(anchor="w", padx=4, pady=(0,8))

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
    ttk.Label(parser_frame, text="Макс. записей").pack(anchor="w", padx=8, pady=(8,2))
    ttk.Spinbox(parser_frame, from_=1, to=1000000, textvariable=max_records_var).pack(anchor="w", padx=8, pady=2)
    
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
        sx_import_btn.pack_forget()
        sx_listbox.pack_forget()
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
        sx_import_btn.pack(anchor="w", padx=6, pady=(8,4))
        sx_create_btn.pack(anchor="w", padx=6, pady=(4,4))
        sx_listbox.pack(anchor="w", padx=6, pady=(4,6))

    def on_method_change(*args):
        value = PROXY_DISPLAY_TO_VALUE.get(proxy_method_var.get(), "file")
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
        config.chrome.sxorg_api_key = key
        config.save_config()
        sx_balance_var.set("Баланс: обновление...")
        def _fetch():
            bal = get_sxorg_balance(key)
            sx_balance_var.set(f"Баланс: {bal} $")
        threading.Thread(target=_fetch, daemon=True).start()
        messagebox.showinfo("API-ключ", "API-ключ сохранён.")
    sx_ok_btn.config(command=sx_ok_cmd)

    # Import command: load proxies
    def sx_import_cmd():
        api = sx_entry.get().strip() or config.chrome.sxorg_api_key
        if not api:
            messagebox.showwarning("API-ключ", "Введите API-ключ SX.ORG и нажмите OK.")
            return
        sx_listbox.delete(0, tk.END)
        sx_listbox.insert(tk.END, "Загрузка...")
        def _load():
            proxies = load_sxorg_proxies(api)
            sx_listbox.delete(0, tk.END)
            config.chrome.proxy_list = proxies
            for p in proxies:
                auth = f" ({p.get('username')}:{p.get('password')})" if p.get('username') else ""
                sx_listbox.insert(tk.END, f"{p.get('host')}:{p.get('port')}{auth} [{p.get('type')}] {p.get('country')} {p.get('city')}")
            config.chrome.sxorg_api_key = api
            config.save_config()
            messagebox.showinfo("Импорт", f"Импортировано {len(proxies)} прокси" if proxies else "Список прокси пуст или произошла ошибка.")
        threading.Thread(target=_load, daemon=True).start()
    sx_import_btn.config(command=sx_import_cmd)

    # Create proxy command
    def sx_create_cmd():
        api = sx_entry.get().strip() or config.chrome.sxorg_api_key
        if not api:
            messagebox.showwarning("API-ключ", "Введите API-ключ SX.ORG и нажмите OK.")
            return
        
        # Автоматическое создание русского резидентского прокси без диалогов
        result_msg = "Создание русского резидентского прокси..."
        logger.info("🚀 %s", result_msg)
        
        try:
            proxy = create_sxorg_proxy(
                api_key=api,
                country_code="RU",
                proxy_type_id="1",  # Residential
                connection_type_id="1",  # HTTP/HTTPS
                name=None,
                traffic_limit=None
            )
            
            if proxy and proxy.get('host'):
                success_msg = f"✅ Создан: {proxy['host']}:{proxy['port']}\nЛогин: {proxy.get('username', '')}\nПароль: {proxy.get('password', '')}"
                logger.info(success_msg)
                # Refresh list
                sx_import_cmd()
                messagebox.showinfo("Успех", success_msg)
            else:
                error_msg = "❌ Не удалось создать прокси. Проверьте баланс SX.ORG"
                logger.error(error_msg)
                messagebox.showerror("Ошибка", error_msg)
        except Exception as e:
            error_msg = f"❌ Ошибка создания прокси: {str(e)}"
            logger.error(error_msg)
            messagebox.showerror("Ошибка", error_msg)
    
    sx_create_btn.config(command=sx_create_cmd)

    # Buttons Save/Cancel - include parser and csv settings save
    btn_frame = ttk.Frame(window)
    btn_frame.pack(fill=tk.X, padx=8, pady=(0,8))
    def on_save():
        config.chrome.disable_images = disable_images_var.get()
        config.chrome.start_maximized = start_maximized_var.get()
        config.chrome.headless = headless_var.get()
        config.chrome.memory_limit = memory_limit_var.get()
        selected_display = proxy_method_var.get()
        config.chrome.proxy_method = PROXY_DISPLAY_TO_VALUE.get(selected_display, "file")
        if config.chrome.proxy_method == "file":
            config.chrome.proxy_file = proxy_file_var.get() or None
        else:
            if sx_entry.get().strip():
                config.chrome.sxorg_api_key = sx_entry.get().strip()
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
        def _preload():
            try:
                bal = get_sxorg_balance(config.chrome.sxorg_api_key)
                sx_balance_var.set(f"Баланс: {bal} $")
            except Exception:
                sx_balance_var.set("Баланс: неизвестно")
            try:
                proxies = load_sxorg_proxies(config.chrome.sxorg_api_key)
                sx_listbox.delete(0, tk.END)
                for p in proxies:
                    auth = f" ({p.get('username')}:{p.get('password')})" if p.get('username') else ""
                    sx_listbox.insert(tk.END, f"{p.get('host')}:{p.get('port')}{auth} [{p.get('type')}] {p.get('country')} {p.get('city')}")
                config.chrome.proxy_list = proxies
            except Exception:
                pass
        threading.Thread(target=_preload, daemon=True).start()

    window.transient()
    window.grab_set()
    window.wait_window()

# ----------------- URLs editor / generator (kept) -----------------
def gui_urls_editor(urls: List[str]) -> List[str] | None:
    window = tk.Toplevel()
    window.title("URLs")
    window.geometry("600x400")
    window.resizable(False, False)
    tk.Label(window, text="Ссылки").pack(pady=6)
    url_text = ScrolledText(window, height=20, width=70)
    url_text.insert(tk.END, '\n'.join(urls))
    url_text.pack(padx=6, pady=6)
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
    window.geometry("500x300")
    
    # Подсказка
    hint_text = "⚠️ ВАЖНО: Город пишется на АНГЛИЙСКОМ!\nПримеры: moscow, spb, novosibirsk, ekaterinburg"
    ttk.Label(window, text=hint_text, foreground="yellow", font=("Arial", 10, "bold")).pack(pady=6)
    
    ttk.Label(window, text="Город (АНГЛИЙСКИМ! moscow, spb, ekaterinburg):").pack(pady=6)
    city_var = tk.StringVar()
    city_entry = ttk.Entry(window, textvariable=city_var, width=40)
    city_entry.pack(pady=6)
    
    ttk.Label(window, text="Рубрика (кафе, рестораны, магазины):").pack(pady=6)
    rubric_var = tk.StringVar()
    rubric_entry = ttk.Entry(window, textvariable=rubric_var, width=40)
    rubric_entry.pack(pady=6)
    
    result: List[str] = []
    def on_generate():
        rubric = rubric_var.get().strip()
        city = city_var.get().strip()
        if rubric and city:
            # НЕ кодируем рубрику - 2GIS принимает кириллицу в URL напрямую
            generated_url = f"https://2gis.ru/{city}/search/{rubric}"
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
                    .map(el => el.innerText.trim())
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
                                .map(el => el.innerText.trim())
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
                if len(items) >= self.config.parser.max_records:
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
            logger.info("Запуск парсера...")
            self.parser = Parser2GIS(self.config)
            self.parser.start()
            
            all_items = []
            
            for url in self.urls:
                if self._stop_event.is_set():
                    logger.info("Парсинг остановлен пользователем")
                    break
                    
                try:
                    logger.info("Парсинг URL: %s", url)
                    items = self.parser.parse_url(url)
                    all_items.extend(items)
                    
                    if self.config.writer.verbose:
                        for item in items:
                            logger.info("  ✓ %s", item.name)
                    
                    # Check max records limit
                    if len(all_items) >= self.config.parser.max_records:
                        logger.info("Достигнут лимит записей: %d", self.config.parser.max_records)
                        all_items = all_items[:self.config.parser.max_records]
                        break
                        
                    # Delay between URLs
                    if self.config.parser.delay_between_clicks > 0:
                        time.sleep(self.config.parser.delay_between_clicks / 1000.0)
                        
                except Exception as e:
                    logger.error("Ошибка при парсинге %s: %s", url, e)
                    if not self.config.parser.skip_404_response:
                        raise
                        
            # Stop browser
            self.parser.stop()
            
            # Write results
            if all_items:
                logger.info("Всего собрано записей: %d", len(all_items))
                writer = Writer(self.config)
                writer.write(all_items, self.output_path, self.file_format)
                logger.info("✓ Парсинг завершён успешно!")
            else:
                logger.warning("Не найдено ни одной записи")
                
        except Exception as e:
            logger.exception("Критическая ошибка парсера: %s", e)
        finally:
            if self.parser:
                try:
                    self.parser.stop()
                except Exception:
                    pass

# ----------------- Main GUI -----------------
def gui_app(urls: List[str], output_path: str, format: str, config: Configuration) -> None:
    root = tk.Tk()
    root.title("Парсер 2GIS")
    root.geometry("900x700")
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
    main_frame = ttk.Frame(root, padding=8)
    main_frame.pack(fill=tk.BOTH, expand=True)
    url_frame = ttk.Frame(main_frame)
    url_frame.pack(fill=tk.X, pady=4)
    ttk.Label(url_frame, text="URL").pack(side=tk.LEFT, padx=6)
    url_entry = ttk.Entry(url_frame)
    url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
    def open_urls_editor():
        new = gui_urls_editor(urls) or urls
        urls[:] = new
        update_urls_input()
    ttk.Button(url_frame, text="...", command=open_urls_editor).pack(side=tk.LEFT, padx=6)
    ttk.Button(url_frame, text="Настройки", command=lambda: gui_settings(config)).pack(side=tk.LEFT, padx=6)
    def update_urls_input():
        urls_length = len(urls)
        if urls_length == 0:
            url_entry.config(state="normal")
            url_entry.delete(0, tk.END)
        elif urls_length == 1:
            url_entry.config(state="normal")
            url_entry.delete(0, tk.END)
            url_entry.insert(0, urls[0])
        else:
            url_entry.config(state="normal")
            url_entry.delete(0, tk.END)
            url_entry.insert(0, f"<{urls_length} ссылок>")
            url_entry.config(state="disabled")
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
    ttk.Label(bottom_frame, text=f"v{VERSION}").pack(side=tk.LEFT, padx=6)
    start_btn = ttk.Button(bottom_frame, text="Запуск")
    start_btn.pack(side=tk.LEFT, padx=6)
    stop_btn = ttk.Button(bottom_frame, text="Стоп", state="disabled")
    stop_btn.pack(side=tk.LEFT, padx=6)
    ttk.Button(bottom_frame, text="Выход", command=root.destroy).pack(side=tk.RIGHT, padx=6)
    parsing_thread: List[Optional[GUIRunner]] = [None]
    def parsing_thread_running() -> bool:
        return parsing_thread[0] is not None and parsing_thread[0].is_alive()
    def on_start():
        if not output_var.get():
            messagebox.showerror("Ошибка", "Отсутствует путь результирующего файла!")
            return
        if url_entry.cget("state") == "normal" and not url_entry.get():
            messagebox.showerror("Ошибка", "Отсутствует URL!")
            return
        if url_entry.cget("state") == "normal" and url_entry.get():
            urls[:] = [url_entry.get()]
        if not parsing_thread_running():
            try:
                progress.start()
                parsing_thread[0] = GUIRunner(list(urls), output_var.get(), format_var.get(), config)
                parsing_thread[0].start()
                start_btn.config(state="disabled")
                stop_btn.config(state="normal")
            except Exception as e:
                logger.exception("Ошибка запуска парсера: %s", e)
                progress.stop()
                parsing_thread[0] = None
    def on_stop():
        if parsing_thread_running():
            parsing_thread[0].stop()
            parsing_thread[0].join(timeout=5)
            parsing_thread[0] = None
        stop_btn.config(state="disabled")
        start_btn.config(state="normal")
        progress.stop()
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
    browser_parser.add_argument("--chrome.sxorg_country", metavar="COUNTRY", help="Страна для прокси SX.ORG (например, US)")
    browser_parser.add_argument("--chrome.sxorg_state", metavar="STATE", help="Штат для прокси SX.ORG (например, New York)")
    browser_parser.add_argument("--chrome.sxorg_city", metavar="CITY", help="Город для прокси SX.ORG (например, New York)")
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