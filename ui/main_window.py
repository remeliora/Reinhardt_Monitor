import json
import logging
import sys
from pathlib import Path
from threading import Thread
import asyncio
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont, QPalette, QColor
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QLineEdit,
    QTextEdit, QFrame, QMessageBox, QDialog
)

from ui.edit_window import EditDialog

# ==============================================
# КОНСТАНТЫ ДЛЯ НАСТРОЙКИ ИНТЕРФЕЙСА
# ==============================================
APP_NAME = "Reinhardt"
MAIN_COLOR = "#925FE2"
SECONDARY_COLOR = "#7E4ED6"
BG_COLOR = "#E5DFF7"
TEXT_COLOR = "white"
TABLE_HEADER_COLOR = MAIN_COLOR
LOG_BG_COLOR = "#EAEAEA"
LOG_TEXT_BG = "#F8F8F8"

WINDOW_MIN_WIDTH = 910
WINDOW_MIN_HEIGHT = 450
TITLE_BAR_HEIGHT = 40
BUTTON_HEIGHT = 40
TABLE_HEIGHT = 180
LOG_HEIGHT = 220


def _create_title_button(text):
    """Создает кнопку для панели заголовка"""
    btn = QPushButton(text)
    btn.setFixedSize(30, 30)
    btn.setStyleSheet(f"""
        QPushButton {{
            background-color: transparent;
            color: {TEXT_COLOR};
            font-size: 14px;
            border: none;
        }}
        QPushButton:hover {{
            background-color: {SECONDARY_COLOR};
        }}
    """)
    return btn


class CustomTitleBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(TITLE_BAR_HEIGHT)

        # Настройка цвета фона
        palette = self.palette()
        palette.setColor(QPalette.Window, QColor(MAIN_COLOR))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        # Основной layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)

        # Название приложения
        self.title = QLabel(APP_NAME)
        self.title.setStyleSheet(f"color: {TEXT_COLOR}; font-weight: bold;")
        self.title.setFont(QFont("Arial", 12))
        layout.addWidget(self.title)
        layout.addStretch()

        # Кнопки управления окном
        self.btn_min = _create_title_button("—")
        self.btn_max = _create_title_button("▭")
        self.btn_close = _create_title_button("✕")

        layout.addWidget(self.btn_min)
        layout.addWidget(self.btn_max)
        layout.addWidget(self.btn_close)

        # Подключение событий
        if parent is not None:
            self.btn_min.clicked.connect(parent.showMinimized)
            self.btn_max.clicked.connect(self.toggle_max_restore)
            self.btn_close.clicked.connect(parent.close)

    def toggle_max_restore(self):
        """Переключение между максимизацией и нормальным режимом"""
        if self.parent().isMaximized():
            self.parent().showNormal()
        else:
            self.parent().showMaximized()


class GUILogHandler(logging.Handler):
    def __init__(self, log_signal):
        super().__init__()
        self.log_signal = log_signal

    def emit(self, record):
        log_entry = self.format(record)
        self.log_signal.emit(log_entry)


class MeteoMonitor(QWidget):
    log_updated = Signal(str)
    update_triggered = Signal()  # Новый сигнал для обновления данных

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setMinimumSize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        self.old_pos = None
        self.is_polling_active = False
        self.update_timer = QTimer(self)  # Таймер для автоматического обновления

        # Инициализация UI
        self.init_ui()

        # Подключение сигналов
        self.log_updated.connect(self._add_log_message)
        self.update_triggered.connect(self.update_all_sensors)

        # Настройка таймера обновления
        self.setup_update_timer()

        # Первоначальная загрузка данных
        self.update_all_sensors()

    def setup_update_timer(self):
        """Настраивает таймер для автоматического обновления данных"""
        self.update_timer.timeout.connect(self.update_all_sensors)
        self.start_auto_update()

    def start_auto_update(self):
        """Запускает автоматическое обновление с текущим интервалом"""
        interval = self.app.polling_service.polling_interval * 1000  # в миллисекундах
        self.update_timer.start(interval)
        self._add_log_message(f"Автообновление данных каждые {self.app.polling_service.polling_interval} сек.")

    def stop_auto_update(self):
        """Останавливает автоматическое обновление"""
        self.update_timer.stop()
        self._add_log_message("Автообновление данных остановлено")

    def init_ui(self):
        """Инициализация пользовательского интерфейса"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 10)

        # Добавляем кастомную панель заголовка
        self.title_bar = CustomTitleBar(self)
        main_layout.addWidget(self.title_bar)

        # Основное содержимое
        content_layout = QHBoxLayout()
        main_layout.addLayout(content_layout)

        # Левая панель (меню)
        self.init_left_panel(content_layout)

        # Центральная панель (таблица и лог)
        self.init_center_panel(content_layout)

        self.is_polling_active = True
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)

    def init_left_panel(self, parent_layout):
        """Инициализация левой панели с кнопками"""
        left_panel = QWidget()
        left_panel.setStyleSheet(f"background-color: {BG_COLOR};")

        layout = QVBoxLayout(left_panel)
        layout.setSpacing(15)

        # Кнопки управления
        self.btn_edit = self._create_menu_button("Редактировать")
        self.btn_start = self._create_menu_button("Запустить опрос")
        self.btn_stop = self._create_menu_button("Остановить опрос")

        # Подключение событий
        self.btn_edit.clicked.connect(self.open_edit_dialog)
        self.btn_start.clicked.connect(self.start_polling)
        self.btn_stop.clicked.connect(self.stop_polling)

        # Поле ввода периода опроса
        lbl_period = QLabel("Период опроса")
        lbl_period.setAlignment(Qt.AlignCenter)
        lbl_period.setFont(QFont("Arial", 11, QFont.Bold))
        lbl_period.setStyleSheet(f"""
            QLabel {{
                background-color: #F5F0FF;
                color: {MAIN_COLOR};
                border-radius: 8px;
                padding: 6px 10px;
            }}
        """)

        self.period_input = QLineEdit(str(self.app.polling_service.polling_interval))
        self.period_input.setAlignment(Qt.AlignCenter)
        self.period_input.setFixedHeight(30)
        self.period_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: #FFFFFF;
                border: 2px solid {MAIN_COLOR};
                border-radius: 5px;
                padding: 5px;
                font-weight: bold;
            }}
            QLineEdit:focus {{
                border-color: {SECONDARY_COLOR};
            }}
        """)
        self.period_input.returnPressed.connect(self.update_polling_period)

        # Добавление виджетов на панель
        layout.addWidget(self.btn_edit)
        layout.addSpacing(10)
        layout.addWidget(lbl_period)
        layout.addWidget(self.period_input)
        layout.addWidget(self.btn_start)
        layout.addWidget(self.btn_stop)
        layout.addStretch()

        parent_layout.addWidget(left_panel, 1)

    def init_center_panel(self, parent_layout):
        """Инициализация центральной панели с таблицей и логом"""
        center_layout = QVBoxLayout()

        # Таблица с данными
        self.init_data_table(center_layout)

        # Лог событий
        self.init_event_log(center_layout)

        parent_layout.addLayout(center_layout, 4)

    def init_data_table(self, parent_layout):
        """Инициализация таблицы с данными датчиков"""
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([
            "Датчик", "Температура (°С)", "Влажность (%)", "Давление (kPa)",
            "Скорость ветра (km/h)", "Направление (°)", "Коэф. охлаждения (°С)"
        ])
        self.table.setStyleSheet(f"""
                QTableWidget {{
                    border: 1px solid {MAIN_COLOR};
                }}
                QHeaderView::section {{
                    background-color: {TABLE_HEADER_COLOR};
                    color: {TEXT_COLOR};
                    font-weight: bold;
                    padding: 5px;
                }}
                QScrollBar:vertical {{
                    border: none;
                    background: {BG_COLOR};
                    width: 8px;
                    margin: 0px 0px 0px 0px;
                }}
                QScrollBar::handle:vertical {{
                    background: {MAIN_COLOR};
                    min-height: 20px;
                    border-radius: 4px;
                }}
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                    height: 0px;
                    background: none;
                }}
                QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                    background: none;
                }}
                QScrollBar:horizontal {{
                    border: none;
                    background: {BG_COLOR};
                    height: 8px;
                    margin: 0px 0px 0px 0px;
                }}
                QScrollBar::handle:horizontal {{
                    background: {MAIN_COLOR};
                    min-width: 20px;
                    border-radius: 4px;
                }}
                QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                    width: 0px;
                    background: none;
                }}
                QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
                    background: none;
                }}
            """)

        self.table.setFixedHeight(TABLE_HEIGHT)
        self.table.verticalHeader().setVisible(False)
        parent_layout.addWidget(self.table)

    def init_event_log(self, parent_layout):
        """Инициализация лога событий"""
        log_frame = QFrame()
        log_frame.setFixedHeight(LOG_HEIGHT)
        log_frame.setStyleSheet(f"""
            background-color: {LOG_BG_COLOR};
            border-radius: 15px;
        """)

        log_layout = QVBoxLayout(log_frame)
        log_layout.setContentsMargins(10, 10, 10, 10)

        log_label = QLabel("События")
        log_label.setFont(QFont("Arial", 10, QFont.Bold))

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet(f"""
                QTextEdit {{
                    background-color: {LOG_TEXT_BG}; 
                    border: none;
                    font-family: Consolas, monospace;
                }}
                QScrollBar:vertical {{
                    border: none;
                    background: {LOG_BG_COLOR};
                    width: 8px;
                    margin: 0px 0px 0px 0px;
                }}
                QScrollBar::handle:vertical {{
                    background: {MAIN_COLOR};
                    min-height: 20px;
                    border-radius: 4px;
                }}
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                    height: 0px;
                    background: none;
                }}
                QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                    background: none;
                }}
            """)

        log_layout.addWidget(log_label)
        log_layout.addWidget(self.log_text)

        parent_layout.addWidget(log_frame)

    def open_edit_dialog(self):
        """Открывает диалоговое окно редактирования станций"""
        try:
            dialog = EditDialog(self)

            if dialog.exec() == QDialog.Accepted:
                self._add_log_message("Изменения в настройках станций сохранены")
                self.update_all_sensors()
        except Exception as e:
            error_msg = f"Ошибка при открытии окна редактирования: {str(e)}"
            self._add_log_message(error_msg)
            QMessageBox.critical(self, "Ошибка", error_msg)

    def _create_menu_button(self, text):
        """Создает кнопку для меню"""
        btn = QPushButton(text)
        btn.setFixedHeight(BUTTON_HEIGHT)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {MAIN_COLOR};
                color: {TEXT_COLOR};
                font-weight: bold;
                border-radius: 5px;
            }}
            QPushButton:hover {{
                background-color: {SECONDARY_COLOR};
            }}
        """)
        return btn

    def load_sensor_data(self, sensor_name):
        """Загружает данные датчика из JSON-файла"""
        try:
            file_path = Path(__file__).parent.parent / "device_data" / f"{sensor_name}.json"
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            self.log_updated.emit(f"Ошибка загрузки данных датчика {sensor_name}: {str(e)}")
            return None

    def _get_sensor_files(self):
        """Возвращает список файлов с данными датчиков"""
        sensor_dir = Path(__file__).parent.parent / "device_data"
        return list(sensor_dir.glob("Reinhardt#*.json"))

    def update_all_sensors(self):
        """Обновляет данные всех датчиков"""
        sensor_files = self._get_sensor_files()
        for sensor_file in sensor_files:
            sensor_name = sensor_file.stem
            data = self.load_sensor_data(sensor_name)
            if data:
                self.update_sensor_data(sensor_name, data, True)

    def update_sensor_data(self, sensor_name: str, data: dict, is_enabled: bool):
        """Обновление данных датчика в таблице"""
        # Ищем датчик в таблице
        row_found = -1
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0).text() == sensor_name:
                row_found = row
                break

        # Если датчик не найден, добавляем новую строку
        if row_found == -1:
            row_found = self.table.rowCount()
            self.table.insertRow(row_found)
            self.table.setItem(row_found, 0, self._create_table_item(sensor_name))
            for col in range(1, self.table.columnCount()):
                self.table.setItem(row_found, col, self._create_table_item("---"))

        # Устанавливаем стиль строки в зависимости от статуса
        color = QColor(240, 240, 240) if not is_enabled else QColor(255, 255, 255)
        for col in range(self.table.columnCount()):
            item = self.table.item(row_found, col)
            item.setBackground(color)

            if not is_enabled and col > 0:
                item.setText("---")

        # Обновляем данные только для включенных устройств
        if is_enabled and data.get("parameters"):
            params = data["parameters"]
            self.table.item(row_found, 1).setText(str(params.get("Temperature", {}).get("value", "---")))
            self.table.item(row_found, 2).setText(str(params.get("Humidity", {}).get("value", "---")))
            self.table.item(row_found, 3).setText(str(params.get("Pressure", {}).get("value", "---")))
            self.table.item(row_found, 4).setText(str(params.get("Wind speed", {}).get("value", "---")))
            self.table.item(row_found, 5).setText(str(params.get("Wind direction", {}).get("value", "---")))
            self.table.item(row_found, 6).setText(str(params.get("Cooling coefficient", {}).get("value", "---")))

    def _create_table_item(self, text):
        """Создает элемент таблицы с выравниванием по центру"""
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignCenter)
        return item

    def update_polling_period(self):
        """Обновление периода опроса и интервала обновления"""
        try:
            period = int(self.period_input.text())
            if period <= 0:
                raise ValueError("Период должен быть положительным числом")

            self.app.polling_service.polling_interval = period
            self._add_log_message(f"Период опроса изменен на {period} сек.")

            # Перезапускаем таймер с новым интервалом
            if self.update_timer.isActive():
                self.stop_auto_update()
                self.start_auto_update()

        except ValueError as e:
            QMessageBox.warning(self, "Ошибка", "Период опроса должен быть положительным целым числом")
            self.period_input.setText(str(self.app.polling_service.polling_interval))

    def start_polling(self):
        """Запуск опроса датчиков"""
        if not self.is_polling_active:
            try:
                self.app.run_polling_service()
                self.is_polling_active = True
                self.btn_start.setEnabled(False)
                self.btn_stop.setEnabled(True)
                self.start_auto_update()  # Запускаем автообновление
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось запустить опрос: {str(e)}")

    def stop_polling(self):
        """Остановка опроса датчиков"""
        if self.is_polling_active:
            try:
                self.stop_auto_update()  # Останавливаем автообновление
                Thread(
                    target=self._async_stop_polling,
                    daemon=True
                ).start()
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось остановить опрос: {str(e)}")

    def _async_stop_polling(self):
        """Асинхронная остановка опроса (выполняется в отдельном потоке)"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self.app.stop_polling_service())
            self.is_polling_active = False
            # Обновляем кнопки в основном потоке
            self.btn_start.setEnabled(True)
            self.btn_stop.setEnabled(False)
        except Exception as e:
            self.log_updated.emit(f"Ошибка при остановке опроса: {str(e)}")
        finally:
            loop.close()

    def _add_log_message(self, message):
        """Добавление сообщения в лог"""
        max_lines = 1000
        if self.log_text.document().lineCount() > max_lines:
            cursor = self.log_text.textCursor()
            cursor.movePosition(cursor.Start)
            cursor.select(cursor.LineUnderCursor)
            cursor.removeSelectedText()
            cursor.deleteChar()

        self.log_text.append(message)
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())

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
    window = MeteoMonitor(app)
    window.show()
    sys.exit(app.exec())
