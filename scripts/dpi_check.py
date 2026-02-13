"""Quick DPI and pyautogui diagnostic."""
import pyautogui
import ctypes

print("=== pyautogui Settings ===")
print(f"  FAILSAFE: {pyautogui.FAILSAFE}")
print(f"  PAUSE: {pyautogui.PAUSE}")
print(f"  Screen size: {pyautogui.size()}")
print(f"  Version: {pyautogui.__version__}")

print("\n=== DPI / Scaling ===")
user32 = ctypes.windll.user32
dpi = user32.GetDpiForSystem()
print(f"  System DPI: {dpi}")
print(f"  Scale factor: {round(dpi / 96 * 100)}%")

awareness = ctypes.c_int()
ctypes.windll.shcore.GetProcessDpiAwareness(0, ctypes.byref(awareness))
awareness_names = {0: "UNAWARE", 1: "SYSTEM_AWARE", 2: "PER_MONITOR_AWARE"}
print(f"  Process DPI Awareness: {awareness.value} ({awareness_names.get(awareness.value, 'unknown')})")

sw = user32.GetSystemMetrics(0)
sh = user32.GetSystemMetrics(1)
print(f"  GetSystemMetrics (before DPI aware): {sw}x{sh}")

user32.SetProcessDPIAware()
sw2 = user32.GetSystemMetrics(0)
sh2 = user32.GetSystemMetrics(1)
print(f"  GetSystemMetrics (after SetProcessDPIAware): {sw2}x{sh2}")

if sw != sw2 or sh != sh2:
    print(f"  ⚠ DPI MISMATCH! Virtual coords {sw}x{sh} vs physical {sw2}x{sh2}")
    print(f"    pyautogui may be using WRONG coordinates!")
else:
    print(f"  ✓ No DPI mismatch detected")

print("\n=== pyautogui DPI Handling ===")
has_dpi = hasattr(pyautogui, '_pyautogui_win') or hasattr(pyautogui, 'platformModule')
print(f"  pyautogui uses win32 API: check pyautogui._pyautogui_win")
try:
    import pyautogui._pyautogui_win as paw
    print(f"  Win backend loaded OK")
except Exception as e:
    print(f"  Win backend: {e}")
