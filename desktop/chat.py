"""Desktop-only companion chat, using the existing isolated partner thread."""

import html
import json
import uuid

from PySide6.QtCore import QObject, QTimer, QUrl, Qt
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QTextBrowser, QVBoxLayout,
)


class LocalClient(QObject):
    """Nonblocking loopback requests; retries reuse the original idempotency key."""

    def __init__(self, base_url, parent=None):
        super().__init__(parent)
        self.base_url = base_url.rstrip("/")
        self.network = QNetworkAccessManager(self)

    def request(self, method, path, payload, callback, attempt=0):
        request = QNetworkRequest(QUrl(self.base_url + "/api" + path))
        request.setRawHeader(b"X-BookSide", b"1")
        request.setHeader(QNetworkRequest.ContentTypeHeader, "application/json")
        request.setTransferTimeout(8000)
        if method == "GET":
            reply = self.network.get(request)
        else:
            reply = self.network.post(request, json.dumps(payload).encode("utf-8"))

        def finished():
            status = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute) or 0
            ok = reply.error() == QNetworkReply.NoError
            try:
                data = json.loads(bytes(reply.readAll())) if ok else None
            except (ValueError, TypeError):
                data, ok = None, False
            reply.deleteLater()
            if not ok and (not status or status >= 500) and attempt < 2:
                QTimer.singleShot(600 * (attempt + 1), self, lambda: self.request(
                    method, path, payload, callback, attempt + 1,
                ))
                return
            callback(data if ok else None, status)

        reply.finished.connect(finished)


class ChatWindow(QDialog):
    def __init__(self, base_url, parent=None, client=None):
        super().__init__(parent)
        self.setWindowTitle("BookSide · 桌宠陪聊")
        font = QFont()
        font.setFamilies(["Microsoft YaHei UI", "PingFang SC", "Noto Sans CJK SC", "sans-serif"])
        self.setFont(font)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.resize(420, 540)
        self.setMinimumSize(320, 380)
        self.client = client or LocalClient(base_url, self)
        self.run_id = None
        self.submission = None
        self.busy = False
        self.setStyleSheet("""
            QDialog { background: #faf9f3; color: #30483a; }
            QLabel, QCheckBox { color: #536d59; font-size: 13px; }
            QTextBrowser, QPlainTextEdit { background: #fffef9; color: #30483a;
                border: 1px solid #dce2d5; border-radius: 10px; padding: 10px; font-size: 14px; }
            QPushButton { background: #536d59; color: white; border: none;
                border-radius: 8px; padding: 9px 16px; }
            QPushButton:disabled { background: #a4afa2; }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        heading = QLabel("休息一下，慢慢聊。")
        heading.setStyleSheet("font-size: 20px; font-weight: 600; color: #30483a;")
        layout.addWidget(heading)
        note = QLabel("学习之外的陪伴 · 课程问题请回学习区")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.history = QTextBrowser()
        self.history.setAccessibleName("桌宠聊天记录")
        self.history.setOpenLinks(False)
        layout.addWidget(self.history, 1)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setAccessibleName("陪聊状态")
        layout.addWidget(self.status)
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("今天有什么想分享的？（Ctrl+Enter 发送）")
        self.editor.setAccessibleName("发送给桌宠")
        self.editor.setMaximumHeight(90)
        layout.addWidget(self.editor)
        self.private = QCheckBox("本次不进入长期记忆")
        self.private.setToolTip("对话仍保留在本地聊天记录中，不用于长期记忆与摘要。")
        layout.addWidget(self.private)
        buttons = QHBoxLayout()
        self.reconnect = QPushButton("重新连接")
        self.reconnect.hide()
        self.reconnect.clicked.connect(self.resume)
        buttons.addWidget(self.reconnect)
        buttons.addStretch()
        self.send = QPushButton("发送")
        self.send.setDefault(False)
        self.send.setAutoDefault(False)
        self.send.clicked.connect(self.submit)
        self.send.setEnabled(False)
        self.editor.textChanged.connect(self.update_send)
        buttons.addWidget(self.send)
        layout.addLayout(buttons)
        shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        shortcut.activated.connect(self.submit)

    def open_chat(self):
        # Closing hides this window. In-flight work continues and reuses the same window.
        self.show()
        self.raise_()
        self.activateWindow()
        self.editor.setFocus()
        if not self.busy:
            self.refresh()

    def update_send(self):
        length = len(self.editor.toPlainText().strip())
        self.send.setEnabled(not self.busy and 0 < length <= 10000)

    def set_busy(self, busy):
        self.busy = busy
        self.editor.setReadOnly(busy)
        self.private.setEnabled(not busy)
        self.update_send()

    def refresh(self, message=""):
        self.set_busy(True)
        self.status.setText(message or "正在读取聊天记录…")

        def loaded(data, _status):
            if not isinstance(data, list):
                self.disconnected("聊天记录暂时没连上，点击重新连接即可。")
                return
            self.render_messages(data)
            self.status.setText(message)
            self.reconnect.hide()
            self.set_busy(False)

        self.client.request("GET", "/messages", None, loaded)

    def render_messages(self, messages):
        # Treat model/user content as text: no remote images or executable rich markup.
        blocks = []
        for item in messages:
            who = "你" if item.get("role") == "user" else "桌宠"
            text = html.escape(str(item.get("text", ""))).replace("\n", "<br>")
            blocks.append(f'<p style="color:#536d59"><b>{who}</b></p><p>{text}</p>')
        self.history.setHtml("".join(blocks) or "<p>我在这里。今天有什么想分享的？</p>")
        scroll = self.history.verticalScrollBar()
        scroll.setValue(scroll.maximum())

    def disconnected(self, text="有点小问题，已保留这次对话。点击重新连接继续。"):
        self.status.setText(text)
        self.reconnect.show()
        # Keep submission locked: reconnect must reuse its key, never duplicate a turn.

    def submit(self):
        text = self.editor.toPlainText().strip()
        if self.busy or not text or len(text) > 10000:
            return
        self.submission = {"action": "partner", "text": text, "private": self.private.isChecked(),
                           "request_key": str(uuid.uuid4())}
        self.set_busy(True)
        self.start_run()

    def start_run(self):
        self.reconnect.hide()
        self.status.setText("正在回应你，稍等一下…")

        def started(data, status):
            if not isinstance(data, dict) or not data.get("id"):
                if status in (400, 409, 422):
                    self.submission = None
                    self.set_busy(False)
                    self.status.setText("上一条对话可能仍在处理，请稍后再发。")
                else:
                    self.disconnected()
                return
            self.run_id = data["id"]
            self.poll()

        self.client.request("POST", "/partner/actions", self.submission, started)

    def poll(self):
        def received(data, status):
            if status == 404:
                data = {"status": "interrupted"}
            if not isinstance(data, dict) or data.get("status") not in (
                "running", "done", "failed", "cancelled", "interrupted",
            ):
                self.disconnected()
                return
            if data["status"] == "running":
                QTimer.singleShot(750, self, self.poll)
                return
            done = data["status"] == "done"
            self.run_id = self.submission = None
            if done:
                self.editor.clear()
            self.refresh("" if done else "这次没能完成，输入已保留。可稍后重发，或在学习网页检查模型设置。")

        self.client.request("GET", f"/runs/{self.run_id}", None, received)

    def resume(self):
        self.reconnect.hide()
        self.status.setText("正在重新连接…")
        if self.run_id:
            self.poll()
        elif self.submission:
            self.start_run()
        else:
            self.refresh()
