# -*- coding: utf-8 -*-
"""
纯净桌面切换器  —  唐完了 出品
================================
在「正常桌面」和「纯净桌面(只留壁纸)」之间一键切换。
不移动、不删除任何文件——只是隐藏/显示桌面图标这一层。

用法:
  双击运行              常驻托盘，全局热键 Ctrl+Alt+D 随时切换
  python 本文件 --toggle  切换一次后退出
  python 本文件 --show    强制显示桌面图标后退出(恢复用)
  python 本文件 --hide    强制隐藏桌面图标后退出
  python 本文件 --status  查看当前状态
"""

import ctypes
from ctypes import wintypes as wt
import winreg
import os
import sys
import time
import subprocess

user32   = ctypes.WinDLL("user32",   use_last_error=True)
gdi32    = ctypes.WinDLL("gdi32",    use_last_error=True)
shell32  = ctypes.WinDLL("shell32",  use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# ---------------- 常量 ----------------
WM_DESTROY       = 0x0002
WM_COMMAND       = 0x0111
WM_HOTKEY        = 0x0312
WM_LBUTTONUP     = 0x0202
WM_RBUTTONUP     = 0x0205
WM_APP_TRAY      = 0x8300          # 托盘回调消息
WM_SETTINGCHANGE = 0x001A

MOD_ALT, MOD_CONTROL, MOD_NOREPEAT = 0x0001, 0x0002, 0x4000
VK_D = 0x44

SW_HIDE, SW_SHOW = 0, 5
NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO = 0x01, 0x02, 0x04, 0x10
NIIF_INFO = 0x01
MF_SEPARATOR = 0x800
MFS_CHECKED = 0x0008
TPM_RIGHTBUTTON, TPM_BOTTOMALIGN, TPM_RETURNCMD = 0x0002, 0x0020, 0x0100
HWND_BROADCAST   = 0xFFFF
SMTO_ABORTIFHUNG = 0x0002
PATBLT_BLACKNESS = 0x00000042

CMD_TOGGLE = 0x7402              # explorer 原生“显示桌面图标”切换命令

APP_NAME = "PureDesktopSwitcher"
TITLE    = "纯净桌面切换器"
ADV_KEY  = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"
RUN_KEY  = r"Software\Microsoft\Windows\CurrentVersion\Run"
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])),
                        "PureDesktopSwitcher.log")

def log(msg):
    """无控制台模式下排障用: 写日志文件"""
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write("[%s] %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
    except Exception:
        pass

# ---------------- 结构体 ----------------
LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)

class RECT(ctypes.Structure):
    _fields_ = [("left", wt.LONG), ("top", wt.LONG),
                ("right", wt.LONG), ("bottom", wt.LONG)]

class POINT(ctypes.Structure):
    _fields_ = [("x", wt.LONG), ("y", wt.LONG)]

class MSG(ctypes.Structure):
    _fields_ = [("hwnd", wt.HWND), ("message", wt.UINT),
                ("wParam", wt.WPARAM), ("lParam", wt.LPARAM),
                ("time", wt.DWORD), ("pt", POINT)]

class NID(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("uTimeout", wt.UINT), ("uVersion", wt.UINT)]
    _fields_ = [("cbSize", wt.DWORD), ("hWnd", wt.HWND), ("uID", wt.UINT),
                ("uFlags", wt.UINT), ("uCallbackMessage", wt.UINT),
                ("hIcon", wt.HICON), ("szTip", wt.WCHAR * 128),
                ("dwState", wt.DWORD), ("dwStateMask", wt.DWORD),
                ("szInfo", wt.WCHAR * 256), ("uTimeoutOrVersion", _U),
                ("szInfoTitle", wt.WCHAR * 64), ("dwInfoFlags", wt.DWORD)]

class ICONINFO(ctypes.Structure):
    _fields_ = [("fIcon", wt.BOOL), ("xHotspot", wt.DWORD), ("yHotspot", wt.DWORD),
                ("hbmMask", wt.HBITMAP), ("hbmColor", wt.HBITMAP)]

class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wt.UINT), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON),
                ("hCursor", wt.HICON), ("hbrBackground", wt.HBRUSH),
                ("lpszMenuName", wt.LPCWSTR), ("lpszClassName", wt.LPCWSTR)]

# 64 位系统关键: 完整声明参数类型, 防止句柄按 32 位截断/溢出
H = ctypes.c_void_p  # 通用句柄类型
_ptr = ctypes.POINTER

user32.FindWindowW.argtypes         = [wt.LPCWSTR, wt.LPCWSTR]
user32.FindWindowW.restype          = H
user32.FindWindowExW.argtypes       = [H, H, wt.LPCWSTR, wt.LPCWSTR]
user32.FindWindowExW.restype        = H
user32.CreateWindowExW.argtypes     = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
                                       ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                       H, H, H, H]
user32.CreateWindowExW.restype      = H
user32.SendMessageW.argtypes        = [H, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.SendMessageW.restype         = LRESULT
user32.SendMessageTimeoutW.argtypes = [H, wt.UINT, wt.WPARAM, wt.LPARAM,
                                       wt.UINT, wt.UINT, _ptr(wt.DWORD)]
user32.ShowWindow.argtypes          = [H, ctypes.c_int]
user32.IsWindowVisible.argtypes     = [H]
user32.IsWindowVisible.restype      = wt.BOOL
user32.SetForegroundWindow.argtypes = [H]
user32.RegisterHotKey.argtypes      = [H, ctypes.c_int, wt.UINT, wt.UINT]
user32.UnregisterHotKey.argtypes    = [H, ctypes.c_int]
user32.CreatePopupMenu.restype      = H
user32.AppendMenuW.argtypes         = [H, wt.UINT, ctypes.c_size_t, wt.LPCWSTR]
user32.TrackPopupMenu.argtypes      = [H, wt.UINT, ctypes.c_int, ctypes.c_int,
                                       ctypes.c_int, H, H]
user32.TrackPopupMenu.restype       = wt.BOOL
user32.DestroyMenu.argtypes         = [H]
user32.DestroyWindow.argtypes       = [H]
user32.DefWindowProcW.argtypes      = [H, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.DefWindowProcW.restype       = LRESULT
user32.GetCursorPos.argtypes        = [_ptr(POINT)]
user32.GetDC.argtypes               = [H]
user32.GetDC.restype                = H
user32.ReleaseDC.argtypes           = [H, H]
user32.FillRect.argtypes            = [H, _ptr(RECT), H]
user32.FrameRect.argtypes           = [H, _ptr(RECT), H]
user32.CreateIconIndirect.argtypes  = [_ptr(ICONINFO)]
user32.CreateIconIndirect.restype   = H
user32.LoadIconW.argtypes           = [H, H]
user32.LoadIconW.restype            = H
user32.LoadImageW.argtypes          = [H, wt.LPCWSTR, wt.UINT, ctypes.c_int,
                                       ctypes.c_int, wt.UINT]
user32.LoadImageW.restype           = H
user32.MessageBoxW.argtypes         = [H, wt.LPCWSTR, wt.LPCWSTR, wt.UINT]
gdi32.CreateCompatibleDC.argtypes     = [H]
gdi32.CreateCompatibleDC.restype      = H
gdi32.CreateCompatibleBitmap.argtypes = [H, ctypes.c_int, ctypes.c_int]
gdi32.CreateCompatibleBitmap.restype  = H
gdi32.CreateBitmap.argtypes           = [ctypes.c_int, ctypes.c_int, wt.UINT, wt.UINT, H]
gdi32.CreateBitmap.restype            = H
gdi32.CreateSolidBrush.argtypes       = [wt.DWORD]
gdi32.CreateSolidBrush.restype        = H
gdi32.SelectObject.argtypes           = [H, H]
gdi32.SelectObject.restype            = H
gdi32.DeleteObject.argtypes           = [H]
gdi32.DeleteDC.argtypes               = [H]
gdi32.PatBlt.argtypes                 = [H, ctypes.c_int, ctypes.c_int,
                                         ctypes.c_int, ctypes.c_int, wt.DWORD]
kernel32.GetModuleHandleW.argtypes = [wt.LPCWSTR]
kernel32.GetModuleHandleW.restype  = H
kernel32.CreateMutexW.argtypes     = [H, wt.BOOL, wt.LPCWSTR]
kernel32.CreateMutexW.restype      = H
shell32.Shell_NotifyIconW.argtypes = [wt.DWORD, _ptr(NID)]
shell32.SHChangeNotify.argtypes    = [ctypes.c_long, wt.UINT, H, H]

# ---------------- 桌面图标核心逻辑 ----------------
def icons_hidden_reg():
    """读注册表 HideIcons (1=隐藏)"""
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, ADV_KEY)
        v, _ = winreg.QueryValueEx(k, "HideIcons")
        winreg.CloseKey(k)
        return bool(v)
    except OSError:
        return False

def set_reg_hidden(hidden):
    k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, ADV_KEY, 0, winreg.KEY_SET_VALUE)
    winreg.SetValueEx(k, "HideIcons", 0, winreg.REG_DWORD, 1 if hidden else 0)
    winreg.CloseKey(k)

def get_defview():
    """找桌面图标列表: Progman 或 WorkerW 下的 SHELLDLL_DefView -> SysListView32"""
    progman = user32.FindWindowW("Progman", None)
    dv = user32.FindWindowExW(progman, None, "SHELLDLL_DefView", None) if progman else None
    if not dv:
        hw = None
        while True:
            hw = user32.FindWindowExW(None, hw, "WorkerW", None)
            if not hw:
                break
            dv = user32.FindWindowExW(hw, None, "SHELLDLL_DefView", None)
            if dv:
                break
    lv = user32.FindWindowExW(dv, None, "SysListView32", "FolderView") if dv else None
    return dv, lv

def set_icons(hidden):
    """切换桌面图标显示/隐藏。返回所用方法。"""
    target = bool(hidden)
    if icons_hidden_reg() == target:
        # 状态已一致，兜底修正一下可见层
        _, lv = get_defview()
        if lv:
            user32.ShowWindow(lv, SW_HIDE if target else SW_SHOW)
        return "already"

    # 方法A: 资源管理器原生命令 (即“右键桌面->查看->显示桌面图标”)
    progman = user32.FindWindowW("Progman", None)
    if progman:
        user32.SendMessageW(progman, WM_COMMAND, CMD_TOGGLE, 0)
    for _ in range(12):
        time.sleep(0.05)
        if icons_hidden_reg() == target:
            return "native"

    # 方法B: 注册表 + 直接隐藏桌面列表控件
    set_reg_hidden(target)
    _, lv = get_defview()
    if lv:
        user32.ShowWindow(lv, SW_HIDE if target else SW_SHOW)
    res = wt.DWORD(0)
    user32.SendMessageTimeoutW(HWND_BROADCAST, WM_SETTINGCHANGE, 0, 0,
                               SMTO_ABORTIFHUNG, 1000, ctypes.byref(res))
    shell32.SHChangeNotify(0x08000000, 0x0000, None, None)  # 关联变更,促使桌面重绘
    return "fallback" if lv else "regonly"

# ---------------- 任务栏 ----------------
def taskbar_visible():
    t = user32.FindWindowW("Shell_TrayWnd", None)
    return bool(t and user32.IsWindowVisible(t))

def set_taskbar(hidden):
    t = user32.FindWindowW("Shell_TrayWnd", None)
    if t:
        user32.ShowWindow(t, SW_HIDE if hidden else SW_SHOW)
    hw = None
    while True:  # 多显示器的副任务栏
        hw = user32.FindWindowExW(None, hw, "Shell_SecondaryTrayWnd", None)
        if not hw:
            break
        user32.ShowWindow(hw, SW_HIDE if hidden else SW_SHOW)

# ---------------- 托盘图标(纯 GDI 手绘) ----------------
def make_icon(pure):
    """画一个 32x32 图标: 蓝色屏幕。pure=空屏幕(只有白框), 正常=屏幕上有白色内容"""
    try:
        BLUE, WHITE = 0x00D77800, 0x00FFFFFF   # COLORREF = 0x00BBGGRR
        hscreen = user32.GetDC(None)
        mdc = gdi32.CreateCompatibleDC(hscreen)
        hbmp = gdi32.CreateCompatibleBitmap(hscreen, 32, 32)
        old = gdi32.SelectObject(mdc, hbmp)
        b1 = gdi32.CreateSolidBrush(BLUE)
        r = RECT(0, 0, 32, 32)
        user32.FillRect(mdc, ctypes.byref(r), b1)
        gdi32.DeleteObject(b1)
        b2 = gdi32.CreateSolidBrush(WHITE)
        r2 = RECT(7, 7, 25, 25)
        if pure:
            user32.FrameRect(mdc, ctypes.byref(r2), b2)   # 空屏幕: 只画边框
        else:
            user32.FillRect(mdc, ctypes.byref(r2), b2)    # 正常: 满内容
        gdi32.DeleteObject(b2)
        gdi32.SelectObject(mdc, old)
        gdi32.DeleteDC(mdc)

        mask = gdi32.CreateBitmap(32, 32, 1, 1, None)
        mdc2 = gdi32.CreateCompatibleDC(hscreen)
        old2 = gdi32.SelectObject(mdc2, mask)
        gdi32.PatBlt(mdc2, 0, 0, 32, 32, PATBLT_BLACKNESS)  # 全不透明
        gdi32.SelectObject(mdc2, old2)
        gdi32.DeleteDC(mdc2)

        ii = ICONINFO(1, 0, 0, mask, hbmp)
        hicon = user32.CreateIconIndirect(ctypes.byref(ii))
        gdi32.DeleteObject(hbmp)
        gdi32.DeleteObject(mask)
        user32.ReleaseDC(None, hscreen)
        return hicon
    except Exception:
        return user32.LoadIconW(None, 32512)

# ---------------- 开机自启 ----------------
def autostart_on():
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY)
        winreg.QueryValueEx(k, APP_NAME)
        winreg.CloseKey(k)
        return True
    except OSError:
        return False

def set_autostart(on):
    if on:
        script = os.path.abspath(sys.argv[0])
        exe = sys.executable
        if os.path.basename(exe).lower() == "python.exe":
            pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")
            if os.path.exists(pyw):
                exe = pyw
        data = '"%s" "%s"' % (exe, script)
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, data)
        winreg.CloseKey(k)
    else:
        try:
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE)
            winreg.DeleteValue(k, APP_NAME)
            winreg.CloseKey(k)
        except OSError:
            pass

def restart_explorer():
    subprocess.run(["taskkill", "/f", "/im", "explorer.exe"], capture_output=True)
    time.sleep(1.2)
    subprocess.Popen(["explorer.exe"])

# ---------------- 托盘常驻主程序 ----------------
class App:
    def __init__(self):
        # 单实例
        kernel32.CreateMutexW(None, True, APP_NAME)
        if ctypes.get_last_error() == 183:
            user32.MessageBoxW(None, "纯净桌面切换器已经在运行了(托盘里)。",
                               TITLE, 0x40)
            sys.exit(0)

        self.hinstance = kernel32.GetModuleHandleW(None)
        self.proc = WNDPROC(self._wndproc)      # 保引用防 GC
        wc = WNDCLASSW()
        wc.style = 8                             # CS_DBLCLKS
        wc.lpfnWndProc = self.proc
        wc.hInstance = self.hinstance
        wc.lpszClassName = APP_NAME
        if not user32.RegisterClassW(ctypes.byref(wc)):
            raise OSError("RegisterClass 失败")
        self.hwnd = user32.CreateWindowExW(0, APP_NAME, TITLE, 0, 0, 0, 0, 0,
                                           None, None, self.hinstance, None)
        if not self.hwnd:
            raise OSError("创建窗口失败")

        ok = bool(user32.RegisterHotKey(self.hwnd, 1,
                                        MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_D))
        log("托盘启动, 热键 Ctrl+Alt+D 注册: %s" % ("成功" if ok else "失败(可能被其他程序占用)"))

        self.icon_normal = (self._load_ico("icon_normal.ico") or make_icon(False))
        self.icon_pure   = (self._load_ico("icon_pure.ico") or make_icon(True))
        self._tray_set(NIM_ADD)
        self.balloon("纯净桌面切换器已启动",
                     "Ctrl+Alt+D 随时切换：正常桌面 <-> 纯净桌面(只留壁纸)。\n"
                     "左键点托盘图标也能切换，右键有更多选项。\n— 唐完了 出品")
        self._run()

    # ---- 图标 ----
    def _load_ico(self, name):
        """从程序目录或 icons/ 子目录加载 ico 文件; 失败返回 None(回退到自绘图标)"""
        base = os.path.dirname(os.path.abspath(sys.argv[0]))
        for d in (base, os.path.join(base, "icons")):
            p = os.path.join(d, name)
            if os.path.exists(p):
                hicon = user32.LoadImageW(None, p, 1, 32, 32, 0x10)  # IMAGE_ICON|LR_LOADFROMFILE
                if hicon:
                    return hicon
        return None

    # ---- 消息循环 ----
    def _run(self):
        msg = MSG()
        while True:
            r = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if r <= 0:
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _wndproc(self, hwnd, msg, wp, lp):
        try:
            if msg == WM_HOTKEY and wp == 1:
                log("热键触发 -> 切换")
                self.toggle()
                return 0
            if msg == WM_APP_TRAY:
                m = lp & 0xFFFF
                if m == WM_LBUTTONUP:
                    log("托盘左键 -> 切换")
                    self.toggle()
                elif m == WM_RBUTTONUP:
                    self.menu()
                return 0
            if msg == WM_DESTROY:
                self.cleanup()
                user32.PostQuitMessage(0)
                return 0
        except Exception as e:
            log("消息处理异常: %r" % e)
        return user32.DefWindowProcW(hwnd, msg, wp, lp)

    # ---- 托盘 ----
    def _tray_set(self, action, balloon=None):
        nid = NID()
        nid.cbSize = ctypes.sizeof(NID)
        nid.hWnd = self.hwnd
        nid.uID = 1
        pure = icons_hidden_reg()
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP | (NIF_INFO if balloon else 0)
        nid.uCallbackMessage = WM_APP_TRAY
        nid.hIcon = self.icon_pure if pure else self.icon_normal
        nid.szTip = ("当前: 纯净桌面 (只留壁纸) | Ctrl+Alt+D 切换"
                     if pure else
                     "当前: 正常桌面 | Ctrl+Alt+D 切换")
        if balloon:
            tip_title, tip_text = balloon
            nid.szInfo = tip_text
            nid.szInfoTitle = tip_title
            nid.dwInfoFlags = NIIF_INFO
            nid.uTimeoutOrVersion.uTimeout = 4000
        return shell32.Shell_NotifyIconW(action, ctypes.byref(nid))

    def balloon(self, title, text):
        self._tray_set(NIM_MODIFY, balloon=(title, text))

    def refresh_tray(self):
        self._tray_set(NIM_MODIFY)

    # ---- 动作 ----
    def toggle(self, target=None):
        if target is None:
            target = not icons_hidden_reg()
        r = set_icons(target)
        label = "纯净桌面 (只留壁纸)" if target else "正常桌面"
        extra = "" if r != "regonly" else \
            "\n若桌面未刷新，请右键托盘图标选「重启资源管理器」。"
        self.balloon("已切换到 " + label,
                     "放心，桌面上的文件都还在，只是被隐藏了。" + extra)
        self.refresh_tray()

    def menu(self):
        user32.SetForegroundWindow(self.hwnd)
        m = user32.CreatePopupMenu()
        pure = icons_hidden_reg()
        user32.AppendMenuW(m, 0, 1, ("切换到 正常桌面" if pure else "切换到 纯净桌面")
                           + "\tCtrl+Alt+D")
        user32.AppendMenuW(m, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(m, 0 if taskbar_visible() else MFS_CHECKED, 2, "同时隐藏任务栏")
        user32.AppendMenuW(m, MFS_CHECKED if autostart_on() else 0, 3, "开机自动启动")
        user32.AppendMenuW(m, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(m, 0, 4, "重启资源管理器 (桌面没刷新时用)")
        user32.AppendMenuW(m, 0, 5, "关于")
        user32.AppendMenuW(m, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(m, 0, 6, "退出")
        pt = POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        cmd = user32.TrackPopupMenu(m, TPM_RIGHTBUTTON | TPM_BOTTOMALIGN | TPM_RETURNCMD,
                                    pt.x, pt.y, 0, self.hwnd, None)
        user32.DestroyMenu(m)
        if cmd:
            self.on_menu(cmd)

    def on_menu(self, cmd):
        if cmd == 1:
            self.toggle()
        elif cmd == 2:
            if taskbar_visible():
                set_taskbar(True)
                self.balloon("任务栏已隐藏", "再点一次菜单里的「同时隐藏任务栏」即可恢复。")
            else:
                set_taskbar(False)
        elif cmd == 3:
            on = not autostart_on()
            set_autostart(on)
            self.balloon("开机自启已" + ("开启" if on else "关闭"),
                         "路径已写入注册表 HKCU\\...\\Run。")
        elif cmd == 4:
            restart_explorer()
        elif cmd == 5:
            user32.MessageBoxW(self.hwnd,
                "纯净桌面切换器\n\n"
                "一键切换：正常桌面 <-> 纯净桌面(只留壁纸)。\n"
                "不移动、不删除任何文件，只是隐藏/显示桌面图标。\n\n"
                "快捷键: Ctrl+Alt+D\n"
                "托盘左键: 切换    托盘右键: 菜单\n\n"
                "恢复方法: 再按一次 Ctrl+Alt+D，或\n"
                "右键桌面 -> 查看 -> 显示桌面图标\n\n"
                "唐完了 出品", "关于", 0x40)
        elif cmd == 6:
            if not taskbar_visible():
                set_taskbar(False)   # 退出时确保任务栏被找回
            self.balloon("已退出",
                "桌面图标保持当前状态。\n恢复方法: 右键桌面->查看->显示桌面图标，"
                "或重新运行本程序。")
            time.sleep(0.6)
            user32.DestroyWindow(self.hwnd)

    def cleanup(self):
        user32.UnregisterHotKey(self.hwnd, 1)
        nid = NID()
        nid.cbSize = ctypes.sizeof(NID)
        nid.hWnd = self.hwnd
        nid.uID = 1
        shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))

# ---------------- 命令行模式 ----------------
def cli():
    args = [a.lower() for a in sys.argv[1:]]
    if "--status" in args:
        dv, lv = get_defview()
        hidden = icons_hidden_reg()
        vis = bool(lv) and bool(user32.IsWindowVisible(lv))
        state = "隐藏" if (hidden or not vis) else "显示"
        print(f"桌面图标: {state}  (HideIcons={1 if hidden else 0}, 图标层可见={vis})")
        print(f"任务栏  : {'隐藏' if not taskbar_visible() else '显示'}")
        return 0
    taskbar_arg = "--taskbar" in args
    if "--toggle" in args or "-t" in args:
        target = not icons_hidden_reg()
    elif "--show" in args:
        target = False
    elif "--hide" in args:
        target = True
    else:
        return None  # 无参数 -> 常驻模式
    method = set_icons(target)
    print(f"完成: 桌面图标已{'隐藏(纯净模式)' if target else '显示'}  [方法: {method}]")
    if taskbar_arg:
        set_taskbar(target)
        print(f"任务栏已{'隐藏' if target else '显示'}")
    print("再运行一次 --toggle 即可切回; 或右键桌面->查看->显示桌面图标。")
    return 0

def main():
    code = cli()
    if code is not None:
        sys.exit(code)
    App()

if __name__ == "__main__":
    try:
        log("程序启动 (argv=%s)" % " ".join(sys.argv))
        main()
    except Exception as e:
        log("致命错误: %r" % e)
        try:
            user32.MessageBoxW(None, "纯净桌面切换器出错:\n%s" % e, TITLE, 0x10)
        except Exception:
            print(e)
        sys.exit(1)
