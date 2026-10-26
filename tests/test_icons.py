import unittest
from PyQt6.QtWidgets import QApplication
import sys

class TestIcons(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_icons_render(self):
        from sakukelly.ui.icons import render_icon_pixmap, get_icon, _REGISTRY
        for name in _REGISTRY:
            pix = render_icon_pixmap(name, "#ffffff", size=32)
            self.assertFalse(pix.isNull(), f"Icon {name} produced a null pixmap")
            self.assertGreater(pix.width(), 0)
            icon = get_icon(name, "#ff4d6d", size=24)
            self.assertFalse(icon.isNull(), f"Icon {name} produced a null QIcon")

if __name__ == "__main__":
    unittest.main()
