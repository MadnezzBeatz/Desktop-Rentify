import asyncio
import os
import time
import winreg
import psutil
import subprocess
import win32gui
import win32process
import win32con
import ctypes
import cv2
import numpy as np
import pyautogui
from client_app import change_status_true, change_status_false,ping


import matplotlib.pyplot as plt
# -----------------------------------------------------------------------------
# 1. Работа с процессом Steam и steamwebhelper(окна авторизации)
# -----------------------------------------------------------------------------

def get_steam_install_path():
    """
    Считывает путь установки Steam из реестра.
    """
    try:
        key_path = r"SOFTWARE\Wow6432Node\Valve\Steam"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
            install_path, _ = winreg.QueryValueEx(key, "InstallPath")
            return install_path
    except Exception as e:
        print(f"[ERROR] Не удалось прочитать реестр Steam: {e}")
        return None

def kill_steam_processes():
    """
    Завершает процессы steam.exe и steamwebhelper.exe, если они запущены.
    """
    print("[INFO] Проверяем, запущен ли Steam. Если да — завершаем.")
    for proc in psutil.process_iter(attrs=["name"]):
        pname = (proc.info["name"] or "").lower()
        if "steam.exe" in pname or "steamwebhelper.exe" in pname:
            try:
                print(f"[INFO] Завершаем процесс: {proc.pid} ({proc.info['name']})")
                proc.kill()
            except Exception as e:
                print(f"[WARNING] Не удалось завершить процесс {proc.info['name']}: {e}")

def launch_steam(steam_exe_path):
    """
    Запускает Steam из указанного пути.
    """
    print(f"[INFO] Запускаем Steam: {steam_exe_path}")
    try:
        proc = subprocess.Popen([steam_exe_path])
        return proc
    except Exception as e:
        print(f"[ERROR] Не удалось запустить Steam: {e}")
        return None

def is_pid_running(pid):
    """
    Проверяет, запущен ли процесс с данным PID.
    """
    if pid <= 0:
        return False
    try:
        proc = psutil.Process(pid)
        return proc.is_running()
    except psutil.NoSuchProcess:
        return False
    except Exception:
        return False

# -----------------------------------------------------------------------------
# 2. Работа с файлом loginusers.vdf(это файл сохранения данных о пользователях(доп защита))
# -----------------------------------------------------------------------------

def delete_loginusers_vdf(steam_folder):
    """
    Удаляет файл loginusers.vdf, если он существует.
    """
    config_file = os.path.join(steam_folder, "config", "loginusers.vdf")
    if os.path.isfile(config_file):
        print("[INFO] Удаляем loginusers.vdf")
        try:
            os.remove(config_file)
        except Exception as e:
            print(f"[WARNING] Не удалось удалить {config_file}: {e}")
    else:
        print("[INFO] Файл loginusers.vdf не найден, пропускаем.")

def wait_for_file(filepath, timeout=30):
    """
    Ждёт появления файла до истечения таймаута.
    """
    print(f"[INFO] Ждём появления файла: {filepath} (до {timeout} секунд).")
    start = time.time()
    while time.time() - start < timeout:
        if os.path.isfile(filepath):
            return True
        time.sleep(1)
    return False

# -----------------------------------------------------------------------------
# 3. Работа с окном авторизации Steam (steamwebhelper.exe)
# -----------------------------------------------------------------------------

def find_steamwebhelper_window():
    """
    Ищет окно, принадлежащее steamwebhelper.exe.
    """
    arr = []
    def callback(hwnd, found):
        if not win32gui.IsWindowVisible(hwnd):
            return
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        try:
            p = psutil.Process(pid)
            if p.name().lower() == "steamwebhelper.exe":
                found.append(hwnd)
        except:
            pass
    win32gui.EnumWindows(callback, arr)
    return arr[0] if arr else None

def wait_for_steamwebhelper_window(timeout=20):
    """
    Ждёт появления окна авторизации Steam до истечения таймаута.
    """
    print(f"[INFO] Ждём до {timeout} секунд появления окна авторизации...")
    start = time.time()
    while time.time() - start < timeout:
        hwnd = find_steamwebhelper_window()
        if hwnd:
            return hwnd
        time.sleep(0.5)
    return None

# -----------------------------------------------------------------------------
# 4. Низкоуровневый ввод через SendInput(по другому не смог сделать т.к когда русская раскладка логин и пароль не правильно вводится)
# -----------------------------------------------------------------------------

user32 = ctypes.windll.user32

KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_KEYUP   = 0x0002
INPUT_KEYBOARD    = 1

PUL = ctypes.POINTER(ctypes.c_ulong)

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", PUL)
    ]

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", PUL)
    ]

class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.c_ulong),
        ("wParamL", ctypes.c_short),
        ("wParamH", ctypes.c_ushort)
    ]

class INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("ki", KEYBDINPUT),
        ("mi", MOUSEINPUT),
        ("hi", HARDWAREINPUT)
    ]

class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [
        ("type", ctypes.c_ulong),
        ("u", INPUT_UNION)
    ]

def press_unicode_char(ch: str):
    """
    Нажимает и отпускает символ через Unicode.
    """
    unicode_code = ord(ch)

    # keydown
    keydown = INPUT()
    keydown.type = INPUT_KEYBOARD
    keydown.ki.wScan = unicode_code
    keydown.ki.wVk = 0
    keydown.ki.dwFlags = KEYEVENTF_UNICODE
    keydown.ki.time = 0
    keydown.ki.dwExtraInfo = None

    # keyup
    keyup = INPUT()
    keyup.type = INPUT_KEYBOARD
    keyup.ki.wScan = unicode_code
    keyup.ki.wVk = 0
    keyup.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
    keyup.ki.time = 0
    keyup.ki.dwExtraInfo = None

    arr = (INPUT * 2)(keydown, keyup)
    user32.SendInput(2, ctypes.byref(arr), ctypes.sizeof(INPUT))

def type_text_unicode(text: str, interval: float = 0.0):
    """
    Вводит текст посимвольно через Unicode.
    """
    for ch in text:
        press_unicode_char(ch)
        if interval > 0:
            time.sleep(interval)

# -----------------------------------------------------------------------------
# 5. Поиск элементов на экране (OpenCV + pyautogui)
# -----------------------------------------------------------------------------

def move_window_to_top_left(hwnd):
    """
    Перемещает окно Steam в верхний левый угол экрана.
    """
    if hwnd:
        rect = win32gui.GetWindowRect(hwnd)
        width = rect[2] - rect[0]
        height = rect[3] - rect[1]
        win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, 0, 0, width, height, 0)
        print("[INFO] Окно Steam перемещено в (0,0).")

def find_image_on_screen(template_path, threshold=0.8):
    """
    Ищет шаблон на экране и возвращает координаты центра найденного элемента.
    """
    screenshot = pyautogui.screenshot()
    screenshot_cv = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2GRAY)

    template = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
    # print(template.shape)
    if template is None:
        print(f"[ERROR] Не удалось загрузить шаблон: {template_path}")
        return None

    result = cv2.matchTemplate(screenshot_cv, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)

    if max_val >= threshold:
        w, h = template.shape[1], template.shape[0]
        center_x = max_loc[0] + w // 2
        center_y = max_loc[1] + h // 2
        return (center_x, center_y)
    else:
        return None


def move_and_click(x, y):
    """
    Перемещает курсор в (x, y) и кликает левой кнопкой мыши.
    """
    pyautogui.moveTo(x, y, duration=0)
    pyautogui.click()

# -----------------------------------------------------------------------------
# 6. Проверка "Запомнить меня"
# -----------------------------------------------------------------------------

def find_any_image(image_paths, threshold=0.8):
    """
    Ищет любое изображение из списка и возвращает координаты и путь найденного.
    """
    for path in image_paths:
        coords = find_image_on_screen(path, threshold=threshold)
        if coords is not None:
            return coords, path
    return None, None

def ensure_remember_me_off():
    """
    Убеждается, что опция "Запомнить меня" отключена.
    """
    on_images = ["img/savemeon.png", "img/savemeon2.png"]
    off_images = ["img/savemeoff.png", "img/savemeoff2.png"]

    coords_on, on_path = find_any_image(on_images)
    if coords_on:
        print(f"[INFO] Найдена галочка (ON): {on_path}. Снимаем...")
        move_and_click(*coords_on)
        time.sleep(0.3)
        coords_off, off_path = find_any_image(off_images)
        if coords_off:
            print(f"[INFO] Галочка снята (OFF): {off_path}.")
        else:
            print("[ERROR] После клика не удалось найти OFF-состояние.")
    else:
        print("[INFO] Галочка 'Запомнить меня' уже снята (ON не найдена).")

# -----------------------------------------------------------------------------
# 7. Обработка ошибок
# -----------------------------------------------------------------------------

def show_error_message(msg):
    """
    Отображает системное окно с сообщением об ошибке.
    """
    ctypes.windll.user32.MessageBoxW(None, msg, "Ошибка", 0)

def check_for_error_windows():
    """
    Проверяет наличие окон ошибок на экране.
    """
    error_images = [
        "img/errors1.png",
        "img/errors2.png",
        "img/errors3.png",
        "img/errors4.png"
    ]
    for e_path in error_images:
        coords = find_image_on_screen(e_path, threshold=0.9)
        if coords:
            print(f"[ERROR] Найдено окно ошибки: {e_path}")
            return True
    return False

# -----------------------------------------------------------------------------
# Основной скрипт
# -----------------------------------------------------------------------------

def main(lines, launcher):
    """
    Основная функция скрипта.
    """

    # 1. Получаем путь к Steam
    steam_folder = get_steam_install_path()
    if not steam_folder or not os.path.isdir(steam_folder):
        print(f"[ERROR] Некорректный путь к папке Steam: {steam_folder}")
        exit(1)

    steam_exe_path = os.path.join(steam_folder, "steam.exe")

    # 2. Закрываем уже запущенный Steam
    kill_steam_processes()

    # 3. Удаляем loginusers.vdf (до входа)
    delete_loginusers_vdf(steam_folder)

    # 4. Запускаем Steam
    proc = launch_steam(steam_exe_path)
    if not proc:
        print("[ERROR] Steam не запустился. Выходим.")
        exit(1)

    # 5. Ждём появления окна авторизации
    hwnd = wait_for_steamwebhelper_window(timeout=30)
    if not hwnd:
        print("[ERROR] Окно авторизации не появилось. Закрываем Steam.")
        kill_steam_processes()
        exit(1)

    # Получаем PID окна авторизации
    _, steamwebhelper_pid = win32process.GetWindowThreadProcessId(hwnd)

    # 6. Перемещаем окно в (0,0)
    move_window_to_top_left(hwnd)
    time.sleep(1)

    # 7. Считываем логин, пароль и код Steam Guard
    try:
        if len(lines) < 3:
            print("[ERROR] Список должен содержать три строки: логин, пароль и код Steam Guard.")
            kill_steam_processes()
            exit(1)
        login = lines[0]           # Первая строка: логин
        password = lines[1]        # Вторая строка: пароль
        steamguard_code = lines[2] # Третья строка: код Steam Guard
    except Exception as e:
        print(f"[ERROR] Не удалось прочитать данные аккаунта: {e}")
        kill_steam_processes()
        exit(1)

    print(f"[INFO] Логин: {login}, пароль: {'*'*len(password)}, SteamGuard: {steamguard_code}")

    # 8. Отключаем "Запомнить меня"
    ensure_remember_me_off()
    time.sleep(1)

    # 9. Вводим логин
    login_field = find_image_on_screen(r"img/login_field.jpg", 0.8)
    print(login_field)

    if not login_field:
        print("[ERROR] Не найдено поле логина.")
        kill_steam_processes()
        exit(1)
    move_and_click(*login_field)
    type_text_unicode(login)
    time.sleep(1)

    # 10. Вводим пароль
    password_field = find_image_on_screen("img/password_field.png", 0.8)
    if not password_field:
        print("[ERROR] Не найдено поле пароля.")
        kill_steam_processes()
        exit(1)
    move_and_click(*password_field)
    type_text_unicode(password)
    time.sleep(1)

    # 11. Нажимаем кнопку "Войти"
    login_button = find_image_on_screen("img/login_button.png", 0.8)
    if not login_button:
        print("[ERROR] Не найдена кнопка входа.")
        kill_steam_processes()
        exit(1)
    move_and_click(*login_button)
    print("[INFO] Нажата кнопка входа в Steam.")


    # 12. Ждём, пока процесс авторизации не завершится, одновременно проверяя ошибки и вводя код Steam Guard
    guard_code_entered = False
    change_status_true(login)


    while is_pid_running(steamwebhelper_pid):
        # 12.0 Отправляем пинги на сервер
        pinger = ping()
        if pinger==200:
            print("[PING] Connection is good")
        else:
            print("[PING] Smth went wrong")
            kill_steam_processes()
            exit(1)
        # 12.1 Проверяем наличие ошибок
        if check_for_error_windows():
            kill_steam_processes()
            show_error_message("Произошла ошибка во время авторизации!")
            exit(1)

        # 12.2 Если код Steam Guard ещё не вводился
        if not guard_code_entered:
            # Сначала проверяем наличие steamguard_check.png
            steamguard_check_coords = find_image_on_screen("img/steamguard_check.png", 0.8)
            if steamguard_check_coords:
                print("[INFO] Найдено подтверждение Steam Guard (steamguard_check.png). Нажимаем для открытия поля ввода.")
                move_and_click(*steamguard_check_coords)
                time.sleep(1)  # Ждём, пока поле ввода откроется

                # Ищем поле ввода Steam Guard
                steamguard_field_coords = find_image_on_screen("img/steamguard_field.png", 0.8)
                if steamguard_field_coords:
                    print("[INFO] Найдено поле ввода Steam Guard.")
                    move_and_click(*steamguard_field_coords)
                    type_text_unicode(steamguard_code)
                    time.sleep(0.3)
                    print("[INFO] Код Steam Guard введён.")
                    guard_code_entered = True
                else:
                    print("[WARNING] Поле steamguard_field.png не найдено после нажатия на steamguard_check.png.")
            else:
                # Если steamguard_check.png не найден, пробуем найти поле ввода Steam Guard напрямую
                steamguard_field_coords = find_image_on_screen("img/steamguard_field.png", 0.8)
                if steamguard_field_coords:
                    print("[INFO] Поле ввода Steam Guard найдено напрямую.")
                    move_and_click(*steamguard_field_coords)
                    type_text_unicode(steamguard_code)
                    time.sleep(0.3)
                    print("[INFO] Код Steam Guard введён.")
                    guard_code_entered = True
                else:
                    # Поле ввода не найдено, возможно, Steam Guard не требуется в данный момент
                    pass

        time.sleep(1)  # Пауза между проверками

    print("[INFO] Окно steamwebhelper.exe закрылось. Авторизация завершена.")
    change_status_false(login)
    print("[INFO] Скрипт завершён. Steam запущен.")

if __name__ == "__main__":
    main(lines, launcher)
