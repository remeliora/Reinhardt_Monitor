import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QPalette, QColor
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QLineEdit, QTextEdit, QFrame
)

from edit_window import EditDialog  # Импорт класса окна редактирования


class CustomTitleBar(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.setFixedHeight(40)

        palette = self.palette()
        palette.setColor(QPalette.Window, QColor("#925FE2"))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)

        self.title = QLabel("Reinhardt")
        self.title.setStyleSheet("color: white; font-weight: bold;")
        self.title.setFont(QFont("Arial", 12))
        layout.addWidget(self.title)
        layout.addStretch()

        self.btn_min = QPushButton("—")
        self.btn_max = QPushButton("▭")
        self.btn_close = QPushButton("✕")

        for btn in (self.btn_min, self.btn_max, self.btn_close):
            btn.setFixedSize(30, 30)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: white;
                    font-size: 14px;
                    border: none;
                }
                QPushButton:hover {
                    background-color: #7E4ED6;
                }
            """)

        layout.addWidget(self.btn_min)
        layout.addWidget(self.btn_max)
        layout.addWidget(self.btn_close)

        self.btn_min.clicked.connect(self.parent.showMinimized)
        self.btn_max.clicked.connect(self.toggle_max_restore)
        self.btn_close.clicked.connect(self.parent.close)

    def toggle_max_restore(self):
        if self.parent.isMaximized():
            self.parent.showNormal()
        else:
            self.parent.showMaximized()


class MeteoMonitor(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setMinimumSize(910, 450)
        self.old_pos = None

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 10)

        self.title_bar = CustomTitleBar(self)
        main_layout.addWidget(self.title_bar)

        content = QHBoxLayout()
        main_layout.addLayout(content)

        # Левая панель
        left_panel_widget = QWidget()
        left_panel_widget.setStyleSheet("background-color: #E5DFF7;")
        left_panel = QVBoxLayout()
        left_panel.setSpacing(15)

        btn_main = QPushButton("Главная")
        btn_edit = QPushButton("Редактировать")
        btn_edit.clicked.connect(self.open_edit_dialog)
        btn_stop = QPushButton("Остановить опрос")

        for btn in (btn_main, btn_edit, btn_stop):
            btn.setFixedHeight(40)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #925FE2;
                    color: white;
                    font-weight: bold;
                    border-radius: 5px;
                }
                QPushButton:hover {
                    background-color: #7E4ED6;
                }
            """)

        lbl_period = QLabel("Период опроса")
        lbl_period.setAlignment(Qt.AlignCenter)
        lbl_period.setFont(QFont("Arial", 11, QFont.Bold))
        lbl_period.setStyleSheet("""
            QLabel {
                background-color: #F5F0FF;
                color: #925FE2;
                border-radius: 8px;
                padding: 6px 10px;
            }
        """)

        self.period_input = QLineEdit("10")
        self.period_input.setAlignment(Qt.AlignCenter)
        self.period_input.setFixedHeight(30)
        self.period_input.setStyleSheet("""
            QLineEdit {
                background-color: #FFFFFF;
                border: 2px solid #925FE2;
                border-radius: 5px;
                padding: 5px;
                font-weight: bold;
            }
            QLineEdit:focus {
                border-color: #7E4ED6;
            }
        """)
        self.period_input.returnPressed.connect(self.update_polling_period)

        left_panel.addWidget(btn_main)
        left_panel.addWidget(btn_edit)
        left_panel.addSpacing(10)
        left_panel.addWidget(lbl_period)
        left_panel.addWidget(self.period_input)
        left_panel.addWidget(btn_stop)
        left_panel.addStretch()
        left_panel_widget.setLayout(left_panel)

        # Центральная панель
        center_panel = QVBoxLayout()

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([
            "Датчик", "Температура", "Влажность", "Давление",
            "Скорость ветра", "Направление", "CVF"
        ])
        self.table.setStyleSheet("""
            QHeaderView::section {
                background-color: #925FE2;
                color: white;
                font-weight: bold;
            }
        """)
        self.table.setFixedHeight(180)
        self.table.verticalHeader().setVisible(False)

        data = [
            ["Reinhardt#1", "20,38", "55,5", "99,165", "---", "---", "---"],
            ["Reinhardt#2", "21,4", "30,23", "99,059", "---", "---", "---"],
            ["Reinhardt#3", "19,02", "64,41", "98,953", "---", "---", "---"],
            ["Reinhardt#4", "17,97", "98,74", "99,104", "10,12", "341,08", "16,58"],
            ["Reinhardt#5", "25,38", "84,21", "98,714", "0", "266,58", "25,38"],
            ["Reinhardt#13", "25,38", "84,21", "98,714", "0", "266,58", "25,38"]
        ]
        for row_data in data:
            row_idx = self.table.rowCount()
            self.table.insertRow(row_idx)
            for col_idx, value in enumerate(row_data):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row_idx, col_idx, item)

        # Лог событий
        log_frame = QFrame()
        log_frame.setFixedHeight(220)
        log_frame.setStyleSheet("""
            background-color: #EAEAEA;
            border-radius: 15px;
        """)
        log_layout = QVBoxLayout(log_frame)
        log_label = QLabel("События")
        log_label.setFont(QFont("Arial", 10, QFont.Bold))
        log_text = QTextEdit()
        log_text.setReadOnly(True)
        log_text.setStyleSheet("background-color: #F8F8F8; border: none;")
        log_text.setText("\n".join([
            "01.08.2024 10:34:20 Станция контроля метеорологических параметров №2 (ОС2): Температура выше порога: (24.0 > 23.8999996185303)"
        ] * 12))
        log_layout.addWidget(log_label)
        log_layout.addWidget(log_text)

        center_panel.addWidget(self.table)
        center_panel.addWidget(log_frame)

        content.addWidget(left_panel_widget, 1)
        content.addLayout(center_panel, 4)

    def update_polling_period(self):
        try:
            value = int(self.period_input.text())
            print(f"✅ Новый период опроса: {value} сек.")
        except ValueError:
            print("❌ Введите целое число")

    def open_edit_dialog(self):
        dialog = EditDialog(self)
        dialog.exec()

    # Перемещение окна
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.old_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self.old_pos:
            delta = event.globalPosition().toPoint() - self.old_pos
            self.move(self.pos() + delta)
            self.old_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self.old_pos = None


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MeteoMonitor()
    window.show()
    sys.exit(app.exec())