import os
import random
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from dotenv import load_dotenv

load_dotenv()

# ─── Realistic Chrome User-Agent pool ─────────────────────────────────────────
# Real-world Chrome UAs on Windows/Mac (updated mid-2024)
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]

# ─── JS injected before every page load via CDP ───────────────────────────────
# Patches common fingerprinting vectors that automation-detection scripts probe.
_STEALTH_JS = """
// 1. Remove navigator.webdriver entirely
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});

// 2. Realistic plugins list (mimics normal Chrome install)
Object.defineProperty(navigator, 'plugins', {
  get: () => {
    const makePlugin = (name, filename, desc, mimeTypes) => {
      const plugin = Object.create(Plugin.prototype);
      Object.defineProperties(plugin, {
        name:        {value: name,     enumerable: true},
        filename:    {value: filename, enumerable: true},
        description: {value: desc,     enumerable: true},
        length:      {value: mimeTypes.length, enumerable: true},
      });
      mimeTypes.forEach((mt, i) => { plugin[i] = mt; });
      return plugin;
    };
    const plugins = [
      makePlugin('Chrome PDF Plugin',        'internal-pdf-viewer', 'Portable Document Format', []),
      makePlugin('Chrome PDF Viewer',        'mhjfbmdgcfjbbpaeojofohoefgiehjai', '', []),
      makePlugin('Native Client',            'internal-nacl-plugin', '', []),
    ];
    const list = Object.create(PluginArray.prototype);
    plugins.forEach((p, i) => { list[i] = p; });
    Object.defineProperty(list, 'length', {value: plugins.length});
    return list;
  }
});

// 3. Realistic languages
Object.defineProperty(navigator, 'languages', {get: () => ['es-ES', 'es', 'en-US', 'en']});

// 4. Realistic platform (Windows)
Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});

// 5. window.chrome must exist (headless strips it)
if (!window.chrome) {
  Object.defineProperty(window, 'chrome', {
    value: {
      app:    {isInstalled: false, InstallState: {DISABLED:'d',INSTALLED:'i',NOT_INSTALLED:'n'}, RunningState: {CANNOT_RUN:'c',READY_TO_RUN:'r',RUNNING:'g'}},
      csi:    function(){},
      loadTimes: function(){},
      runtime:{}
    },
    writable: true,
    enumerable: true,
    configurable: false
  });
}

// 6. Notification permission (headless defaults to 'default' which is suspicious)
const origQuery = window.Notification ? Notification.requestPermission : undefined;
try {
  Object.defineProperty(Notification, 'permission', {get: () => 'default'});
} catch(e) {}

// 7. Canvas fingerprint noise: add imperceptible random pixel variation
(function() {
  const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
  HTMLCanvasElement.prototype.toDataURL = function(type) {
    const ctx = this.getContext('2d');
    if (ctx) {
      const imgData = ctx.getImageData(0, 0, this.width || 1, this.height || 1);
      for (let i = 0; i < 4; i++) {
        imgData.data[i] = imgData.data[i] ^ (Math.random() * 2 | 0);
      }
      ctx.putImageData(imgData, 0, 0);
    }
    return origToDataURL.apply(this, arguments);
  };
  const origGetContext = HTMLCanvasElement.prototype.getContext;
  const origFillText  = CanvasRenderingContext2D.prototype.fillText;
  CanvasRenderingContext2D.prototype.fillText = function(text, x, y, maxWidth) {
    return origFillText.apply(this, [text, x + Math.random() * 0.1, y + Math.random() * 0.1, maxWidth]);
  };
})();

// 8. WebGL vendor/renderer: return generic strings instead of real GPU name
(function() {
  const origGetParam = WebGLRenderingContext.prototype.getParameter;
  WebGLRenderingContext.prototype.getParameter = function(param) {
    if (param === 37445) return 'Intel Inc.';        // UNMASKED_VENDOR_WEBGL
    if (param === 37446) return 'Intel Iris OpenGL Engine'; // UNMASKED_RENDERER_WEBGL
    return origGetParam.call(this, param);
  };
})();

// 9. Hide automation-related properties on navigator
delete navigator.__proto__.webdriver;
"""


def create_driver(headless: bool = True) -> webdriver.Chrome:
    options = Options()

    if headless:
        options.add_argument("--headless=new")   # new headless mode: less detectable than legacy

    # ── Core stealth arguments ─────────────────────────────────────────────────
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-features=IsolateOrigins,site-per-process")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--ignore-certificate-errors")

    # ── Randomised User-Agent ──────────────────────────────────────────────────
    ua = random.choice(_USER_AGENTS)
    options.add_argument(f"--user-agent={ua}")

    # ── Randomised window size (realistic desktop resolutions) ────────────────
    width  = random.randint(1280, 1920)
    height = random.randint(768,  1080)
    options.add_argument(f"--window-size={width},{height}")

    # ── Accept-Language header matches navigator.languages ────────────────────
    options.add_argument("--lang=es-ES")

    # ── Suppress automation flags via experimental options ─────────────────────
    options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    options.add_experimental_option("useAutomationExtension", False)

    # ── Prefs: disable password manager popups, notifications ─────────────────
    options.add_experimental_option("prefs", {
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False,
        "profile.default_content_setting_values.notifications": 2,
    })

    # ── Locate correct chromedriver binary ────────────────────────────────────
    driver_path = ChromeDriverManager().install()
    if "THIRD_PARTY_NOTICES" in driver_path:
        driver_path = driver_path.replace("THIRD_PARTY_NOTICES.chromedriver", "chromedriver")
    if os.path.isfile(driver_path) and not os.access(driver_path, os.X_OK):
        parent = os.path.dirname(driver_path)
        for name in ("chromedriver", "chromedriver.exe"):
            candidate = os.path.join(parent, name)
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                driver_path = candidate
                break
    elif os.path.isdir(driver_path):
        for name in ("chromedriver", "chromedriver.exe"):
            candidate = os.path.join(driver_path, name)
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                driver_path = candidate
                break

    service = Service(driver_path)
    driver  = webdriver.Chrome(service=service, options=options)

    # ── CDP: inject stealth script before every document ──────────────────────
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": _STEALTH_JS},
    )

    # ── Also patch immediately for the first blank page ───────────────────────
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )

    return driver


def quit_driver(driver) -> None:
    if driver:
        driver.quit()