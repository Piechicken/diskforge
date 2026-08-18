from __future__ import annotations

from PySide6.QtWidgets import QApplication

from diskforge.gui.main_window import MainWindow
from diskforge.gui.workers import FunctionWorker


def _application() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_task_center_records_and_clears_completed_items() -> None:
    _application()
    window = MainWindow()
    worker = FunctionWorker("Task center test", lambda: "done")
    window._task_item(worker, "Task center test")
    window._set_task_state(worker, "Completed", "Completed successfully")
    assert window.task_view.topLevelItemCount() == 1
    assert window.task_view.topLevelItem(0).text(0) == "Completed"
    window._clear_completed_tasks()
    assert window.task_view.topLevelItemCount() == 0
