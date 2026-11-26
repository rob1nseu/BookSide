"""Small transparent Qt companion. Model requests belong to the web application."""

import subprocess
import sys
import time
import webbrowser
from pathlib import Path

import json
import urllib.request


def healthy():
    try:
        with urllib.request.urlopen("http://127.0.0.1:8765/api/health", timeout=1) as response:
            return bool(json.loads(response.read()).get("ok"))
    except (OSError, ValueError):
        return False


def focus_existing():
    # Browser focus is best-effort; opening the URL remains the reliable fallback.
    if sys.platform != "win32":
        return False
    import ctypes

    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def visit(hwnd, _):
        title = ctypes.create_unicode_buffer(512)
        ctypes.windll.user32.GetWindowTextW(hwnd, title, 512)
        if "LearNest" in title.value and ctypes.windll.user32.IsWindowVisible(hwnd):
            found.append(hwnd)
        return True

    ctypes.windll.user32.EnumWindows(visit, 0)
    if found:
        ctypes.windll.user32.ShowWindow(found[0], 9)
        return bool(ctypes.windll.user32.SetForegroundWindow(found[0]))
    return False


def main():
    import os
    from PySide6.QtCore import Qt, QTimer, QLockFile, QSettings
    from PySide6.QtGui import QPixmap, QIcon, QAction
    from PySide6.QtWidgets import QApplication, QLabel, QMenu, QSystemTrayIcon, QMessageBox

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    lock = QLockFile(str(Path(os.environ["LEARNEST_DATA_DIR"]) / "desktop.lock"))
    if not lock.tryLock(0):
        webbrowser.open("http://127.0.0.1:8765")
        return
    settings = QSettings("LearNest", "Companion")
    process = None
    if not healthy():
        command = (
            [sys.executable, "--server"]
            if getattr(sys, "frozen", False)
            else [sys.executable, "-m", "desktop.launcher", "--server"]
        )
        process = subprocess.Popen(
            command, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        )
        for _ in range(100):
            if healthy():
                break
            if process.poll() is not None:
                break
            time.sleep(0.1)
        if not healthy():
            if process.poll() is None:
                process.terminate()
            QMessageBox.critical(None, "LearNest", "本地服务启动失败，请检查端口 8765 是否被其他程序占用。")
            return
    root = Path(__file__).resolve().parents[1]
    sheet = QPixmap(str(root / "desktop/assets/companion.png"))
    frames = [sheet.copy(i * sheet.width() // 4, 0, sheet.width() // 4, sheet.height()) for i in range(4)]

    class Pet(QLabel):
        def __init__(self):
            super().__init__()
            self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
            self.setAttribute(Qt.WA_TranslucentBackground)
            self.resize(170, 220)
            self.setAlignment(Qt.AlignCenter)
            self.origin = None
            self.moved = False
            self.tick = 0
            self.paused = False
            self.timer = QTimer(self)
            self.timer.timeout.connect(self.animate)
            self.timer.start(150)
            self.animate()
            area = app.primaryScreen().availableGeometry()
            self.move(area.right() - 190, area.bottom() - 240)
            saved = settings.value("position")
            if saved is not None and any(s.availableGeometry().contains(saved) for s in app.screens()):
                self.move(saved)

        def animate(self):
            self.tick += 1
            frame = 3 if self.origin is not None else 2 if self.underMouse() else 1 if self.tick % 30 == 0 else 0
            if self.paused:
                frame = 0
            self.setPixmap(frames[frame].scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

        def mousePressEvent(self, event):
            if event.button() == Qt.LeftButton:
                self.origin = event.globalPosition().toPoint() - self.pos()
                self.moved = False

        def mouseMoveEvent(self, event):
            if self.origin is not None:
                target = event.globalPosition().toPoint() - self.origin
                if (target - self.pos()).manhattanLength() > 3:
                    self.moved = True
                self.move(target)

        def mouseReleaseEvent(self, event):
            if event.button() == Qt.LeftButton and self.origin is not None:
                if not self.moved:
                    open_app()
                self.origin = None
                settings.setValue("position", self.pos())

        def contextMenuEvent(self, event):
            menu.exec(event.globalPos())

    def open_app():
        if not focus_existing():
            webbrowser.open("http://127.0.0.1:8765")

    pet = Pet()
    tray = QSystemTrayIcon(QIcon(frames[0]), app)
    menu = QMenu()

    def add(label, fn):
        action = QAction(label, menu)
        action.triggered.connect(fn)
        menu.addAction(action)

    add("打开学习网页", open_app)
    add("显示 / 隐藏宠物", lambda: pet.setVisible(not pet.isVisible()))
    add("暂停 / 恢复动画", lambda: setattr(pet, "paused", not pet.paused))
    add("小号", lambda: pet.resize(130, 170))
    add("标准大小", lambda: pet.resize(170, 220))
    add("大号", lambda: pet.resize(220, 285))
    add("退出 LearNest", app.quit)
    tray.setContextMenu(menu)
    tray.setToolTip("LearNest")
    tray.show()
    pet.show()
    open_app()
    try:
        app.exec()
    finally:
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
