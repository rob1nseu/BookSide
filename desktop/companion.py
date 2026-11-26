"""Optional source-run Qt companion: frontal reading pet and reliable URL entry."""

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from backend.app.config import setting
from desktop.chat import ChatWindow

from PySide6.QtCore import Qt, QTimer, QLockFile, QSettings, QUrl, QObject, QProcess
from PySide6.QtGui import QPixmap, QIcon, QAction, QDesktopServices
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PySide6.QtWidgets import QApplication, QLabel, QMenu, QSystemTrayIcon, QMessageBox

ROOT = Path(__file__).resolve().parents[1]
URL = "http://127.0.0.1:8765"


def healthy():
    try:
        with urllib.request.urlopen(URL + "/api/health", timeout=1) as response:
            return bool(json.loads(response.read()).get("ok"))
    except (OSError, ValueError):
        return False


def open_learning_page():
    # Never infer browser state from arbitrary window titles (editors also say BookSide).
    return QDesktopServices.openUrl(QUrl(URL))


class PageOpener(QObject):
    """Native browser activation runs off the GUI thread; coalesce repeated clicks."""
    def __init__(self, parent=None, fallback=open_learning_page):
        super().__init__(parent)
        self.fallback = fallback
        self.process = None
        self.pending = False
        self.last_open = -100.0
        self.network = QNetworkAccessManager(self)
        self.on_existing = lambda: None

    def open(self):
        if self.process or self.pending or time.monotonic() - self.last_open < 3:
            return
        if sys.platform != "win32":
            self.reuse_or_open()
            return
        process = self.process = QProcess(self)
        process.finished.connect(self.finished)
        process.errorOccurred.connect(lambda _: self.finished(1))
        process.start("powershell.exe", ["-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
            "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "desktop/focus-browser.ps1")])
        QTimer.singleShot(8000, lambda: process.kill() if self.process is process else None)

    def finished(self, code, *_):
        if not self.process:
            return
        process, self.process = self.process, None
        process.deleteLater()
        self.last_open = time.monotonic()
        if code != 0:
            self.reuse_or_open()

    def reuse_or_open(self):
        self.pending = True
        request = QNetworkRequest(QUrl(URL + "/api/companion/open"))
        request.setRawHeader(b"X-BookSide", b"1")
        request.setTransferTimeout(2500)
        reply = self.network.post(request, b"")

        def finished():
            try:
                if reply.error() == QNetworkReply.NoError and json.loads(bytes(reply.readAll())).get("existing"):
                    self.on_existing()
                else:
                    self.fallback()
                    # Allow time for a cold browser launch before accepting another click.
                    self.last_open = time.monotonic() + 5
            except (ValueError, TypeError):
                self.fallback()
            finally:
                self.pending = False
                reply.deleteLater()
        reply.finished.connect(finished)


class ActivityMonitor(QObject):
    def __init__(self, pet):
        super().__init__(pet)
        self.pet = pet
        self.network = QNetworkAccessManager(self)
        self.pending = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(1000)
        self.poll()

    def poll(self):
        if self.pending:
            return
        self.pending = True
        request = QNetworkRequest(QUrl(URL + "/api/companion/activity"))
        request.setTransferTimeout(2500)
        reply = self.network.get(request)
        reply.finished.connect(lambda: self.finish(reply))

    def finish(self, reply):
        try:
            if reply.error() == QNetworkReply.NoError:
                value = json.loads(bytes(reply.readAll()))
                self.pet.set_activity(value["active"], value["last_activity"])
            else:
                self.pet.model_active = False
        except (ValueError, KeyError, TypeError):
            self.pet.model_active = False
        finally:
            self.pending = False
            reply.deleteLater()


def load_frames():
    sheet = QPixmap(str(ROOT / "desktop/assets/companion.png"))
    if sheet.isNull() or sheet.width() % 4:
        raise RuntimeError("宠物素材缺失或尺寸不正确")
    return [sheet.copy(i * sheet.width() // 4, 0, sheet.width() // 4, sheet.height()) for i in range(4)]


class Pet(QLabel):
    def __init__(self, frames, open_page, settings=None):
        super().__init__()
        self.frames, self.open_page, self.settings = frames, open_page, settings
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAutoFillBackground(False)
        self.setFrameStyle(0)
        self.setStyleSheet("background: transparent; border: none; padding: 0;")
        self.setFixedSize(130, 170)
        self.setAlignment(Qt.AlignCenter)
        self.setToolTip("点击打开 BookSide · 拖动移动 · 右键更多")
        self.origin = self.press_position = None
        self.moved = self.paused = False
        self.tick = 0
        self.model_active = False
        self.last_interaction = time.monotonic()
        self.last_model_activity = 0
        self.sleep_after = 300
        self.current_frame = 0
        self.menu = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(120)
        self.animate()

    def set_activity(self, active, last_activity):
        self.model_active = active > 0
        if last_activity > self.last_model_activity or self.model_active:
            self.last_interaction = time.monotonic()
        self.last_model_activity = last_activity

    def animate(self):
        self.tick += 1
        asleep = time.monotonic() - self.last_interaction >= self.sleep_after
        frame = 2 if self.model_active else 3 if asleep else 1 if self.tick % 43 in (28, 29) else 0
        if self.paused and frame == 1:
            frame = 0  # Pause motion, retain the truthful activity/sleep state.
        self.current_frame = frame
        pixmap = self.frames[frame].scaled(self.size(), Qt.KeepAspectRatio, Qt.FastTransformation)
        self.setPixmap(pixmap)
        # No rectangular hit area around the transparent sprite.
        from PySide6.QtGui import QRegion

        mask = QRegion(pixmap.mask())
        mask.translate((self.width() - pixmap.width()) // 2, (self.height() - pixmap.height()) // 2)
        self.setMask(mask)

    def mousePressEvent(self, event):
        self.last_interaction = time.monotonic()
        if event.button() == Qt.LeftButton:
            self.press_position = event.globalPosition().toPoint()
            self.origin = self.press_position - self.pos()
            self.moved = False

    def mouseMoveEvent(self, event):
        if self.origin is not None:
            point = event.globalPosition().toPoint()
            if (point - self.press_position).manhattanLength() >= QApplication.startDragDistance():
                self.moved = True
            if self.moved:
                self.move(point - self.origin)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.origin is not None:
            clicked = not self.moved
            self.origin = self.press_position = None
            if self.settings:
                self.settings.setValue("position", self.pos())
            if clicked:
                self.open_page()

    def contextMenuEvent(self, event):
        self.last_interaction = time.monotonic()
        if self.menu:
            self.menu.exec(event.globalPos())


def main():
    app = QApplication(sys.argv)
    app_icon = QIcon(str(ROOT / "frontend/public/app-icon.svg"))
    app.setWindowIcon(app_icon)
    app.setQuitOnLastWindowClosed(False)
    data = Path(setting("BOOKSIDE_DATA_DIR", ROOT / "data"))
    data.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(data / "desktop.lock"))

    def fallback_open():
        if not open_learning_page():
            QMessageBox.warning(None, "打开学习网页", f"系统未能打开默认浏览器，请访问：{URL}")

    opener = PageOpener(app, fallback_open)
    open_app = opener.open

    if not lock.tryLock(0):
        open_app()
        QTimer.singleShot(10000, app.quit)
        app.exec()
        return
    if not (ROOT / "frontend/dist/index.html").is_file():
        QMessageBox.warning(
            None, "需要构建前端", "请先运行根目录 BookSide.ps1 -Desktop，或在 frontend 中运行 npm run build。"
        )
        return
    process = log = None
    try:
        if not healthy():
            log = (data / "desktop-server.log").open("a", encoding="utf-8")
            process = subprocess.Popen(
                [sys.executable, "-m", "desktop.launcher", "--server"],
                cwd=ROOT,
                stdout=log,
                stderr=log,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            for _ in range(150):
                if healthy():
                    break
                if process.poll() is not None:
                    break
                time.sleep(0.1)
            if not healthy():
                QMessageBox.critical(
                    None, "BookSide", "本地服务启动失败。请检查 8765 端口与 data/desktop-server.log。"
                )
                return
        frames = load_frames()
        settings = QSettings("BookSide", "Companion")
        if settings.value("position") is None:
            previous = QSettings("LearNest", "Companion").value("position")
            if previous is not None:
                settings.setValue("position", previous)
        pet = Pet(frames, open_app, settings)
        chat = ChatWindow(URL, parent=pet)

        def open_chat():
            pet.last_interaction = time.monotonic()
            chat.open_chat()

        pet.activity_monitor = ActivityMonitor(pet)
        area = app.primaryScreen().availableGeometry()
        pet.move(area.right() - pet.width() - 20, area.bottom() - pet.height() - 20)
        saved = settings.value("position")
        if saved is not None and any(s.availableGeometry().contains(saved) for s in app.screens()):
            pet.move(saved)
        tray = QSystemTrayIcon(app_icon, app)
        opener.on_existing = lambda: tray.showMessage("BookSide 已打开", "已唤回学习页面；若浏览器限制自动置前，请切换到已有的 BookSide 标签页。", QSystemTrayIcon.Information, 3000)
        menu = QMenu()
        for label, callback in (
            ("打开学习网页", open_app),
            ("和桌宠聊一聊", open_chat),
            ("显示 / 隐藏宠物", lambda: pet.setVisible(not pet.isVisible())),
            ("暂停 / 恢复动画", lambda: setattr(pet, "paused", not pet.paused)),
            ("退出 BookSide", app.quit),
        ):
            action = QAction(label, menu)
            action.triggered.connect(callback)
            menu.addAction(action)
        pet.menu = menu
        tray.setContextMenu(menu)
        tray.setToolTip("BookSide")
        tray.show()
        pet.show()
        open_app()
        app.exec()
    finally:
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        if log:
            log.close()
