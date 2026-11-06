import ctypes, time
from ctypes import wintypes

user32 = ctypes.WinDLL('user32', use_last_error=True)
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL

def find():
    r = []
    EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _):
        n = user32.GetWindowTextLengthW(h)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(h, buf, n + 1)
            if 'AI一手工具箱' in buf.value and user32.IsWindowVisible(h):
                r.append(h)
        return True
    user32.EnumWindows(EnumProc(cb), 0)
    return r

h = find()
print('可见窗口:', h)
if not h:
    raise SystemExit(1)
hwnd = h[0]
t0 = time.time()
user32.PostMessageW(hwnd, 0x0010, 0, 0)   # WM_CLOSE
gone = None
while time.time() - t0 < 8:
    if not user32.IsWindowVisible(hwnd):
        gone = int((time.time() - t0) * 1000)
        break
    time.sleep(0.03)
print('窗口消失耗时:', f'{gone}ms' if gone is not None else '8 秒内未消失')
time.sleep(4)
print('4 秒后窗口仍存在:', bool(user32.IsWindowVisible(hwnd)) if user32.IsWindow(hwnd) else False)
