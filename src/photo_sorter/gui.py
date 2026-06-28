from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .network_guard import install_network_guard
from .core import (
    DATE_RULE_LABELS,
    OPERATION_LABELS,
    DateRule,
    Operation,
    build_safety_report,
    build_preview,
    generate_powershell,
    is_network_path,
    load_json,
    save_json,
    scan_forbidden_powershell,
    summarize_items,
)

try:
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QFont, QFontDatabase, QKeySequence, QShortcut
    from PySide6.QtWidgets import (
        QApplication,
        QComboBox,
        QDialog,
        QFileDialog,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QPlainTextEdit,
        QSpinBox,
        QSplitter,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover - exercised by real desktop runtime.
    raise SystemExit(
        "缺少 PySide6。請先安裝依賴：python -m pip install -e ."
    ) from exc


APP_NAME = "離線照片分類器"
CONFIG_PATH = Path.home() / "AppData" / "Roaming" / "OfflinePhotoSorter" / "config.json"


DEFAULT_SETTINGS = {
    "theme": "dark",
    "font_size": 14,
    "font_family": "Times New Roman",
    "date_rule": "modified",
    "operation": "copy",
}


class SettingsDialog(QDialog):
    def __init__(self, parent: "MainWindow") -> None:
        super().__init__(parent)
        self.parent_window = parent
        self.setWindowTitle("設定")

        layout = QGridLayout(self)

        self.theme_combo = QComboBox()
        self.theme_combo.addItem("黑底白字", "dark")
        self.theme_combo.addItem("白底黑字", "light")
        self.theme_combo.setCurrentIndex(0 if parent.settings["theme"] == "dark" else 1)

        self.font_size = QSpinBox()
        self.font_size.setRange(8, 32)
        self.font_size.setValue(int(parent.settings["font_size"]))

        self.font_combo = QComboBox()
        families = QFontDatabase.families()
        self.font_combo.addItems(families)
        current_font = str(parent.settings["font_family"])
        if current_font in families:
            self.font_combo.setCurrentText(current_font)

        save_button = QPushButton("套用")
        cancel_button = QPushButton("取消")
        save_button.clicked.connect(self.accept)
        cancel_button.clicked.connect(self.reject)

        layout.addWidget(QLabel("主題"), 0, 0)
        layout.addWidget(self.theme_combo, 0, 1)
        layout.addWidget(QLabel("字級"), 1, 0)
        layout.addWidget(self.font_size, 1, 1)
        layout.addWidget(QLabel("字型"), 2, 0)
        layout.addWidget(self.font_combo, 2, 1)
        layout.addWidget(save_button, 3, 0)
        layout.addWidget(cancel_button, 3, 1)

    def selected_settings(self) -> dict:
        return {
            "theme": self.theme_combo.currentData(),
            "font_size": self.font_size.value(),
            "font_family": self.font_combo.currentText(),
        }


class ConfirmDialog(QDialog):
    def __init__(self, script: str, parent: "MainWindow") -> None:
        super().__init__(parent)
        self.setWindowTitle("確認 PowerShell 指令")
        self.resize(1000, 640)
        self.script = script
        self.executed = False

        layout = QVBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal)

        self.script_box = QPlainTextEdit()
        self.script_box.setPlainText(script)
        self.script_box.setReadOnly(True)

        safety_panel = QWidget()
        safety_layout = QVBoxLayout(safety_panel)
        title = QLabel("PowerShell 刪除指令提醒")
        title_font = QFont(parent.settings["font_family"], 16)
        title.setFont(title_font)
        title.setWordWrap(True)

        body = QLabel(
            "請檢查左方欄位是否出現常見刪除指令，例如 Remove-Item、del、erase、rm、rd、rmdir。\n\n"
            "本程式正常產生的指令只應包含建立資料夾、複製或搬移。\n\n"
            "若左方出現任何刪除相關字樣，請按「取消」。"
        )
        body.setWordWrap(True)
        body_font = QFont(parent.settings["font_family"], 14)
        body.setFont(body_font)

        self.safety_status = QLabel()
        self.safety_status.setWordWrap(True)

        safety_layout.addWidget(title)
        safety_layout.addWidget(body)
        safety_layout.addStretch(1)
        safety_layout.addWidget(self.safety_status)

        splitter.addWidget(self.script_box)
        splitter.addWidget(safety_panel)
        splitter.setSizes([650, 350])

        button_row = QHBoxLayout()
        self.run_button = QPushButton("執行")
        save_button = QPushButton("另存指令")
        cancel_button = QPushButton("取消")
        self.run_button.clicked.connect(self.run_script)
        save_button.clicked.connect(self.save_script)
        cancel_button.clicked.connect(self.reject)
        button_row.addStretch(1)
        button_row.addWidget(save_button)
        button_row.addWidget(cancel_button)
        button_row.addWidget(self.run_button)

        layout.addWidget(splitter)
        layout.addLayout(button_row)

        problems = scan_forbidden_powershell(script)
        if problems:
            self.safety_status.setText("安全檢查：偵測到刪除指令，已禁止執行。")
            self.run_button.setEnabled(False)
        else:
            self.safety_status.setText("安全檢查：未偵測到刪除指令。")

    def save_script(self) -> None:
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "另存 PowerShell 指令",
            "photo_sorter_commands.ps1",
            "PowerShell Script (*.ps1);;Text File (*.txt)",
        )
        if not file_path:
            return
        target_path = Path(file_path)
        if is_network_path(target_path):
            QMessageBox.critical(self, "已阻止", "不可將 PowerShell 指令儲存到網路位置。")
            return
        target_path.write_text(self.script, encoding="utf-8")
        QMessageBox.information(self, "已儲存", "PowerShell 指令已儲存。")

    def run_script(self) -> None:
        if scan_forbidden_powershell(self.script):
            QMessageBox.critical(self, "安全檢查失敗", "偵測到刪除指令，已取消執行。")
            return

        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", "-"],
            input=self.script,
            text=True,
            capture_output=True,
            check=False,
        )
        self.executed = result.returncode == 0
        if result.returncode == 0:
            QMessageBox.information(self, "完成", "PowerShell 指令已執行完成。")
            self.accept()
        else:
            QMessageBox.critical(
                self,
                "執行失敗",
                (result.stderr or result.stdout or "PowerShell 回傳失敗，但沒有提供詳細訊息。"),
            )


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1180, 760)
        self.settings = DEFAULT_SETTINGS | load_json(CONFIG_PATH, DEFAULT_SETTINGS)
        self.preview_items = []

        self.source_edit = QLineEdit()
        self.target_edit = QLineEdit()
        self.date_combo = QComboBox()
        self.operation_combo = QComboBox()
        self.preview_table = QTableWidget(0, 8)
        self.result_box = QPlainTextEdit()
        self.open_target_button = QPushButton("開啟輸出資料夾")

        self.build_ui()
        self.apply_settings()
        QApplication.instance().installEventFilter(self)

        zoom_in = QShortcut(QKeySequence.ZoomIn, self)
        zoom_out = QShortcut(QKeySequence.ZoomOut, self)
        zoom_in.activated.connect(lambda: self.adjust_font_size(1))
        zoom_out.activated.connect(lambda: self.adjust_font_size(-1))

    def build_ui(self) -> None:
        central = QWidget()
        layout = QVBoxLayout(central)

        path_group = QGroupBox("資料夾")
        path_layout = QGridLayout(path_group)
        path_layout.setContentsMargins(12, 30, 12, 12)
        path_layout.setVerticalSpacing(10)
        source_button = QPushButton("選擇來源")
        target_button = QPushButton("選擇目標")
        source_button.clicked.connect(lambda: self.choose_folder(self.source_edit))
        target_button.clicked.connect(lambda: self.choose_folder(self.target_edit))
        path_layout.addWidget(QLabel("來源資料夾"), 0, 0)
        path_layout.addWidget(self.source_edit, 0, 1)
        path_layout.addWidget(source_button, 0, 2)
        path_layout.addWidget(QLabel("輸出資料夾"), 1, 0)
        path_layout.addWidget(self.target_edit, 1, 1)
        path_layout.addWidget(target_button, 1, 2)

        control_row = QHBoxLayout()
        for value, label in DATE_RULE_LABELS.items():
            self.date_combo.addItem(label, value)
        self.date_combo.setCurrentIndex(self.date_combo.findData(self.settings["date_rule"]))

        for value, label in OPERATION_LABELS.items():
            self.operation_combo.addItem(label, value)
        self.operation_combo.setCurrentIndex(self.operation_combo.findData(self.settings["operation"]))

        preview_button = QPushButton("產生預覽")
        ps_button = QPushButton("產生 PowerShell")
        settings_button = QPushButton("設定")
        preview_button.clicked.connect(self.refresh_preview)
        ps_button.clicked.connect(self.confirm_powershell)
        settings_button.clicked.connect(self.open_settings)
        self.open_target_button.clicked.connect(self.open_target_folder)

        control_row.addWidget(QLabel("日期規則"))
        control_row.addWidget(self.date_combo)
        control_row.addWidget(QLabel("檔案動作"))
        control_row.addWidget(self.operation_combo)
        control_row.addStretch(1)
        control_row.addWidget(settings_button)
        control_row.addWidget(preview_button)
        control_row.addWidget(ps_button)

        self.preview_table.setHorizontalHeaderLabels(["圖示", "分類", "狀態", "檔名", "來源", "目標", "日期來源", "動作"])
        self.preview_table.horizontalHeader().setStretchLastSection(True)
        self.result_box.setReadOnly(True)

        layout.addWidget(path_group)
        layout.addLayout(control_row)
        layout.addWidget(self.preview_table, stretch=1)
        layout.addWidget(QLabel("結果"))
        layout.addWidget(self.result_box, stretch=0)
        layout.addWidget(self.open_target_button)
        self.setCentralWidget(central)

    def choose_folder(self, target: QLineEdit) -> None:
        folder = QFileDialog.getExistingDirectory(self, "選擇資料夾")
        if folder:
            target.setText(folder)

    def open_settings(self) -> None:
        dialog = SettingsDialog(self)
        if dialog.exec() == QDialog.Accepted:
            self.settings.update(dialog.selected_settings())
            self.save_settings()
            self.apply_settings()

    def apply_settings(self) -> None:
        font_family = str(self.settings["font_family"])
        font_size = int(self.settings["font_size"])
        self.setFont(QFont(font_family, font_size))

        if self.settings["theme"] == "light":
            background = "#ffffff"
            foreground = "#111111"
            panel = "#f2f2f2"
            border = "#999999"
        else:
            background = "#0f0f0f"
            foreground = "#ffffff"
            panel = "#1b1b1b"
            border = "#777777"

        self.setStyleSheet(
            f"""
            QWidget {{
                background: {background};
                color: {foreground};
                font-family: "{font_family}", "Times New Roman", "Microsoft JhengHei";
                font-size: {font_size}pt;
            }}
            QLineEdit, QComboBox, QPlainTextEdit, QTableWidget, QGroupBox {{
                background: {panel};
                color: {foreground};
                border: 1px solid {border};
            }}
            QGroupBox {{
                margin-top: 18px;
                padding-top: 10px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 8px;
                padding: 0 4px;
                background: {background};
            }}
            QPushButton {{
                background: {panel};
                color: {foreground};
                border: 1px solid {border};
                padding: 6px 12px;
            }}
            QPushButton:disabled {{
                color: #888888;
            }}
            """
        )

    def save_settings(self) -> None:
        self.settings["date_rule"] = self.date_combo.currentData()
        self.settings["operation"] = self.operation_combo.currentData()
        save_json(CONFIG_PATH, self.settings)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt API.
        if event.type() == QEvent.Wheel and event.modifiers() & Qt.ControlModifier:
            delta = 1 if event.angleDelta().y() > 0 else -1
            self.adjust_font_size(delta)
            return True
        return super().eventFilter(watched, event)

    def adjust_font_size(self, delta: int) -> None:
        current = int(self.settings["font_size"])
        self.settings["font_size"] = max(8, min(32, current + delta))
        self.save_settings()
        self.apply_settings()

    def refresh_preview(self) -> None:
        source = Path(self.source_edit.text().strip())
        target = Path(self.target_edit.text().strip())
        date_rule: DateRule = self.date_combo.currentData()
        operation: Operation = self.operation_combo.currentData()

        if operation == "move":
            confirm = QMessageBox.warning(
                self,
                "搬移確認",
                "搬移會讓照片離開原本資料夾，但不會刪除照片。是否繼續產生預覽？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if confirm != QMessageBox.Yes:
                return

        self.settings["date_rule"] = date_rule
        self.settings["operation"] = operation
        self.save_settings()

        self.preview_items = build_preview(source, target, date_rule, operation)
        self.populate_preview_table()

    def populate_preview_table(self) -> None:
        self.preview_table.setRowCount(len(self.preview_items))
        for row, item in enumerate(self.preview_items):
            values = [
                item.issue_icon,
                item.issue_label,
                self.status_text(item.status, item.reason),
                item.source_path.name,
                str(item.source_path),
                "" if item.target_path is None else str(item.target_path),
                item.date_source,
                item.operation_label,
            ]
            for column, value in enumerate(values):
                self.preview_table.setItem(row, column, QTableWidgetItem(value))
        self.preview_table.resizeColumnsToContents()

        summary = summarize_items(self.preview_items)
        operation: Operation = self.operation_combo.currentData()
        safety_report = build_safety_report(self.preview_items, operation)
        self.result_box.setPlainText(
            "分類前安全報告\n"
            f"{safety_report.to_text()}\n\n"
            "明細統計\n"
            f"可處理：{len(summary.success)}\n略過：{len(summary.skipped)}\n錯誤：{len(summary.errors)}"
        )

    @staticmethod
    def status_text(status: str, reason: str) -> str:
        if status == "ready":
            return "可執行"
        if status == "skipped":
            return f"略過：{reason}"
        return f"錯誤：{reason}"

    def confirm_powershell(self) -> None:
        if not self.preview_items:
            self.refresh_preview()
        ready_items = [item for item in self.preview_items if item.status == "ready"]
        if not ready_items:
            QMessageBox.information(self, "沒有可執行項目", "目前沒有可執行的照片分類項目。")
            return

        try:
            script = generate_powershell(self.preview_items)
        except ValueError as exc:
            QMessageBox.critical(self, "安全檢查失敗", str(exc))
            return

        dialog = ConfirmDialog(script, self)
        if dialog.exec() == QDialog.Accepted and dialog.executed:
            summary = summarize_items(self.preview_items)
            self.result_box.setPlainText(
                "分類完成\n"
                f"成功：{len(summary.success)}\n"
                f"略過：{len(summary.skipped)}\n"
                f"錯誤：{len(summary.errors)}"
            )

    def open_target_folder(self) -> None:
        target = Path(self.target_edit.text().strip())
        if is_network_path(target):
            QMessageBox.information(self, "已阻止", "不可開啟網路位置作為輸出資料夾。")
            return
        if not target.exists():
            QMessageBox.information(self, "資料夾不存在", "輸出資料夾目前不存在。")
            return
        subprocess.Popen(["explorer", str(target)])


def main() -> None:
    install_network_guard()
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
