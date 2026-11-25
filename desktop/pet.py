"""Windows desktop pet. Tk canvas + tray; the learning UI remains a single Web app."""

import atexit
import ctypes
import json
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
URL = "http://127.0.0.1:8765"


def healthy():
    try:
        with urllib.request.urlopen(URL + "/api/health", timeout=1) as response:
            return bool(json.loads(response.read()).get("ok"))
    except (OSError, ValueError):
        return False


def focus_existing():
    if sys.platform != "win32":
        return False
    found = []
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def callback(hwnd, _):
        buffer = ctypes.create_unicode_buffer(512)
        ctypes.windll.user32.GetWindowTextW(hwnd, buffer, 512)
        if (
            "LearNest" in buffer.value
            and "桌面小芽" not in buffer.value
            and ctypes.windll.user32.IsWindowVisible(hwnd)
        ):
            found.append(hwnd)
        return True

    ctypes.windll.user32.EnumWindows(callback_type(callback), 0)
    if found:
        ctypes.windll.user32.ShowWindow(found[0], 9)
        ctypes.windll.user32.SetForegroundWindow(found[0])
    return bool(found)


def main():
    import pystray
    from PIL import Image, ImageDraw

    self_test = "--self-test" in sys.argv

    if not (ROOT / "frontend" / "dist" / "index.html").exists():
        raise SystemExit("Please run npm run build in frontend first.")
    process = None
    if not healthy():
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "backend.app.main:create_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                "8765",
            ],
            cwd=ROOT,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(80):
            if healthy():
                break
            if process.poll() is not None:
                raise SystemExit("Backend failed to start. Run scripts/start.ps1 to inspect errors.")
            time.sleep(0.25)
        else:
            process.terminate()
            raise SystemExit("Backend startup timed out.")

    def stop_backend():
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()

    atexit.register(stop_backend)
    root = tk.Tk()
    if self_test:
        root.withdraw()
    root.title("LearNest 桌面小芽")
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    transparent = "#ff00ff"
    root.configure(bg=transparent)
    if sys.platform == "win32":
        root.wm_attributes("-transparentcolor", transparent)
    state_path = Path(os.getenv("LEARNEST_DATA_DIR", ROOT / "data")) / "pet-position.json"
    position = {"x": root.winfo_screenwidth() - 145, "y": root.winfo_screenheight() - 195}
    try:
        position.update(json.loads(state_path.read_text()))
    except (OSError, ValueError):
        pass
    position["x"] = max(0, min(position["x"], root.winfo_screenwidth() - 100))
    position["y"] = max(0, min(position["y"], root.winfo_screenheight() - 110))
    root.geometry(f"100x110+{position['x']}+{position['y']}")
    canvas = tk.Canvas(root, width=100, height=110, bg=transparent, highlightthickness=0)
    canvas.pack()
    canvas.create_oval(16, 30, 84, 97, fill="#fffdf3", outline="#245b46", width=2)
    canvas.create_line(50, 49, 50, 17, fill="#245b46", width=3)
    canvas.create_oval(22, 8, 49, 26, fill="#a8c17e", outline="#245b46", width=2)
    canvas.create_oval(50, 3, 80, 22, fill="#71975c", outline="#245b46", width=2)
    canvas.create_oval(34, 58, 39, 64, fill="#245b46", outline="")
    canvas.create_oval(61, 58, 66, 64, fill="#245b46", outline="")
    canvas.create_arc(43, 66, 58, 77, start=180, extent=180, style="arc", outline="#245b46", width=2)
    canvas.create_oval(26, 69, 36, 74, fill="#f5d977", outline="")
    canvas.create_oval(65, 69, 75, 74, fill="#f5d977", outline="")
    drag = {}

    def open_app(chat=False):
        if chat or not focus_existing():
            webbrowser.open(URL + ("/?chat=1" if chat else "/"))

    def press(event):
        drag.update(x=event.x_root, y=event.y_root, ox=root.winfo_x(), oy=root.winfo_y(), moved=False)

    def move(event):
        dx, dy = event.x_root - drag["x"], event.y_root - drag["y"]
        if abs(dx) + abs(dy) > 5:
            drag["moved"] = True
            root.geometry(f"+{max(0, drag['ox'] + dx)}+{max(0, drag['oy'] + dy)}")

    def release(_):
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps({"x": root.winfo_x(), "y": root.winfo_y()}))
        if not drag.get("moved"):
            open_app()

    canvas.bind("<ButtonPress-1>", press)
    canvas.bind("<B1-Motion>", move)
    canvas.bind("<ButtonRelease-1>", release)
    image = Image.new("RGBA", (64, 64), "#fafbf7")
    draw = ImageDraw.Draw(image)
    draw.ellipse((10, 20, 54, 60), fill="#f5d977", outline="#245b46", width=3)
    draw.line((32, 35, 32, 8), fill="#245b46", width=3)
    draw.ellipse((12, 5, 32, 19), fill="#71975c")
    draw.ellipse((32, 2, 55, 17), fill="#71975c")

    def exit_app():
        tray.stop()
        stop_backend()
        root.destroy()

    def schedule(fn):
        return lambda *_: root.after(0, fn)

    tray = pystray.Icon(
        "learnest",
        image,
        "LearNest 小芽",
        menu=pystray.Menu(
            pystray.MenuItem("打开学习空间", schedule(open_app), default=True),
            pystray.MenuItem("聊一聊", schedule(lambda: open_app(True))),
            pystray.MenuItem("显示小芽", schedule(root.deiconify)),
            pystray.MenuItem("退出应用", schedule(exit_app)),
        ),
    )
    if not self_test:
        threading.Thread(target=tray.run, daemon=True).start()
    menu = tk.Menu(root, tearoff=0)
    menu.add_command(label="打开学习空间", command=open_app)
    menu.add_command(label="聊一聊", command=lambda: open_app(True))
    menu.add_command(label="隐藏到托盘", command=root.withdraw)
    menu.add_separator()
    menu.add_command(label="退出应用", command=exit_app)
    canvas.bind("<Button-3>", lambda event: menu.tk_popup(event.x_root, event.y_root))
    if self_test:
        from types import SimpleNamespace

        root.update_idletasks()
        press(SimpleNamespace(x_root=100, y_root=100))
        move(SimpleNamespace(x_root=115, y_root=120))
        release(None)
        assert state_path.exists() and drag["moved"]
        assert menu.index("end") == 4
        assert len(canvas.find_all()) >= 8
        assert healthy()
        exit_app()
        print("Desktop self-test passed: canvas, drag, position persistence, menu, backend lifecycle.")
        return
    root.mainloop()


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="learnest-pet-test-") as temporary:
            os.environ["LEARNEST_DATA_DIR"] = temporary
            main()
    else:
        main()
