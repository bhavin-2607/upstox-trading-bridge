"""Unit tests for GUI components, logger subsystem, and watchdog states."""

import os
import tempfile
import unittest
from pathlib import Path

from upstox_bridge.core.logger import get_gui_logs, setup_production_logging
from upstox_bridge.core.market_store import MarketStore
from upstox_bridge.destinations.bst_syncer import BSTSyncer
from upstox_bridge.core.config import update_env_variable
from upstox_bridge.gui.tray import create_tray_icon_image
from upstox_bridge.runner import BridgeRunner


class TestGuiAndLogger(unittest.TestCase):
    def setUp(self):
        setup_production_logging()

    def test_logger_ring_buffer(self):
        """Test that logs are captured in GUI memory ring buffer."""
        import logging
        test_msg = "TEST_LOG_MESSAGE_GUI_BUFFER_12345"
        logging.getLogger("TestLogger").info(test_msg)

        logs = get_gui_logs()
        self.assertTrue(any(test_msg in line for line in logs), "Expected test message in GUI log buffer")

    def test_update_env_variable(self):
        """Test updating and appending environment variables in .env cleanly."""
        with tempfile.NamedTemporaryFile("w+", delete=False, encoding="utf-8") as f:
            f.write('EXISTING_VAR="hello"\n')
            f.write('UPSTOX_ACCESS_TOKEN="old_token"\n')
            temp_path = Path(f.name)

        try:
            update_env_variable("UPSTOX_ACCESS_TOKEN", "new_token_999", temp_path)
            update_env_variable("NEW_VAR", "added_value", temp_path)

            content = temp_path.read_text(encoding="utf-8")
            self.assertIn('UPSTOX_ACCESS_TOKEN="new_token_999"', content)
            self.assertIn('EXISTING_VAR="hello"', content)
            self.assertIn('NEW_VAR="added_value"', content)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def test_tray_icon_generation(self):
        """Test generating sharp status tray icons."""
        img_green = create_tray_icon_image(color="#16a34a", text="U")
        self.assertEqual(img_green.size, (64, 64))

        img_red = create_tray_icon_image(color="#ef4444", text="U")
        self.assertEqual(img_red.size, (64, 64))

    def test_bst_syncer_status_properties(self):
        """Test BSTSyncer status states and properties."""
        store = MarketStore()
        syncer = BSTSyncer(market_store=store, file_path=Path("bst.xlsx"), sheet_name="BST")
        self.assertEqual(syncer.status, BSTSyncer.STATE_DISCONNECTED)
        self.assertEqual(syncer.last_sync_time, 0.0)
        self.assertEqual(syncer.last_error, "")

    def test_runner_status_properties(self):
        """Test BridgeRunner status properties when stopped."""
        runner = BridgeRunner(custom_file=Path("bst.xlsx"), custom_sheet="BST")
        self.assertFalse(runner.is_running)
        self.assertFalse(runner.is_simulation)
        self.assertEqual(runner.ticks_received, 0)
        self.assertEqual(runner.excel_status, "Disabled")


if __name__ == "__main__":
    unittest.main()
