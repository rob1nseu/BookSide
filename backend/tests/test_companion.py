import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from desktop import companion


@pytest.fixture(scope="module")
def qt():
    return QApplication.instance() or QApplication([])


def test_system_url_opener_does_not_depend_on_window_titles(monkeypatch):
    calls = []
    monkeypatch.setattr(
        companion.QDesktopServices, "openUrl", lambda url: calls.append(url.toString()) or True
    )
    assert companion.open_learning_page()
    assert calls == ["http://127.0.0.1:8765"]
    monkeypatch.setattr(companion.QDesktopServices, "openUrl", lambda _: False)
    assert not companion.open_learning_page()


def test_pixel_icon_loads_in_native_tray(qt):
    from xml.etree import ElementTree
    icon_path = companion.ROOT / "frontend/public/app-icon.svg"
    tree = ElementTree.parse(icon_path)
    assert {node.attrib["fill"] for node in tree.iter() if "fill" in node.attrib} == {"#F2CF55", "#536D59"}
    icon = companion.QIcon(str(icon_path))
    assert not icon.pixmap(32, 32).isNull()
    import tempfile
    icon.pixmap(256, 256).save(str(Path(tempfile.gettempdir()) / "learnest-pixel-icon.png"))


def test_click_opens_but_drag_does_not(qt):
    opened = []
    pet = companion.Pet(companion.load_frames(), lambda: opened.append(True))
    assert (pet.width(), pet.height()) == (130, 170)
    assert pet.minimumSize() == pet.maximumSize()
    pet.timer.stop()
    pet.show()
    qt.processEvents()
    QTest.mouseClick(pet, Qt.LeftButton, pos=QPoint(85, 110))
    assert opened == [True]
    QTest.mousePress(pet, Qt.LeftButton, pos=QPoint(85, 110))
    QTest.mouseMove(pet, QPoint(120, 120))
    QTest.mouseRelease(pet, Qt.LeftButton, pos=QPoint(120, 120))
    assert opened == [True]
    assert pet.testAttribute(Qt.WA_TranslucentBackground)
    assert pet.frameWidth() == 0
    pet.close()


def test_sprite_border_transparency_and_frame_rendering(qt):
    from PIL import Image

    sprite = Image.open(companion.ROOT / "desktop/assets/companion.png")
    alpha = sprite.getchannel("A")
    width = sprite.width // 4
    for i in range(4):
        assert alpha.crop((i * width, 0, (i + 1) * width, 20)).getextrema()[1] <= 1
        frame = alpha.crop((i * width, 0, (i + 1) * width, sprite.height))
        assert frame.getextrema() == (0, 255)
    pet = companion.Pet(companion.load_frames(), lambda: None)
    pet.timer.stop()
    import tempfile

    for tick in (0, 27, 68):
        pet.tick = tick
        pet.animate()
        assert not pet.pixmap().isNull()
    pet.grab().save(str(Path(tempfile.gettempdir()) / "learnest-reading-pet.png"))
    pet.close()


def test_pet_reads_only_during_model_work_and_sleeps_after_idle(qt, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(companion.time, "monotonic", lambda: clock[0])
    pet = companion.Pet(companion.load_frames(), lambda: None)
    pet.timer.stop()
    clock[0] += 301
    pet.animate()
    assert pet.current_frame == 3
    pet.set_activity(2, 200)
    pet.animate()
    assert pet.current_frame == 2
    import tempfile
    pet.grab().save(str(Path(tempfile.gettempdir()) / "learnest-pet-reading.png"))
    pet.set_activity(1, 201)
    clock[0] += 301
    pet.animate()
    assert pet.current_frame == 2  # A long call does not put the pet to sleep.
    pet.set_activity(0, 202)
    pet.animate()
    assert pet.current_frame in (0, 1)
    clock[0] += 301
    pet.animate()
    assert pet.current_frame == 3
    pet.grab().save(str(Path(tempfile.gettempdir()) / "learnest-pet-sleeping.png"))
    QTest.mouseClick(pet, Qt.LeftButton, pos=QPoint(85, 110))
    pet.animate()
    assert pet.current_frame in (0, 1)
    pet.close()
