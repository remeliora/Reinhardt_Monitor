import sys
from threading import Thread

import asyncio
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QPalette, QColor
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QLineEdit,
    QTextEdit, QFrame, QMessageBox
)

from ui.edit_window import EditDialog

# ==============================================
# КОНСТАНТЫ ДЛЯ НАСТРОЙКИ ИНТЕРФЕЙСА
# (Здесь можно менять цвета, размеры и другие параметры)
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


# ==============================================
# КЛАСС ПАНЕЛИ ЗАГОЛОВКА (можно не менять)
# ==============================================
class CustomTitleBar(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
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
        self.btn_min = self._create_title_button("—")
        self.btn_max = self._create_title_button("▭")
        self.btn_close = self._create_title_button("✕")

        layout.addWidget(self.btn_min)
        layout.addWidget(self.btn_max)
        layout.addWidget(self.btn_close)

        # Подключение событий
        self.btn_min.clicked.connect(self.parent.showMinimized)
        self.btn_max.clicked.connect(self.toggle_max_restore)
        self.btn_close.clicked.connect(self.parent.close)

    def _create_title_button(self, text):
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

    def toggle_max_restore(self):
        """Переключение между максимизацией и нормальным режимом"""
        if self.parent.isMaximized():
            self.parent.showNormal()
        else:
            self.parent.showMaximized()


# ==============================================
# ГЛАВНОЕ ОКНО ПРИЛОЖЕНИЯ
# (Основные изменения для интеграции будут здесь)
# ==============================================
class MeteoMonitor(QWidget):
    data_updated = Signal(dict)
    log_updated = Signal(str)

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setMinimumSize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        self.old_pos = None
        self.is_polling_active = False

        # Инициализация UI
        self.init_ui()

        # Подключение сигналов
        self.data_updated.connect(self.update_sensor_data)
        self.log_updated.connect(self._add_log_message)

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

    def init_left_panel(self, parent_layout):
        """Инициализация левой панели с кнопками"""
        left_panel = QWidget()
        left_panel.setStyleSheet(f"background-color: {BG_COLOR};")

        layout = QVBoxLayout(left_panel)
        layout.setSpacing(15)

        # Кнопки управления
        self.btn_main = self._create_menu_button("Главная")
        self.btn_edit = self._create_menu_button("Редактировать")
        self.btn_start = self._create_menu_button("Запустить опрос")
        self.btn_stop = self._create_menu_button("Остановить опрос")
        self.btn_stop.setEnabled(False)

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
        layout.addWidget(self.btn_main)
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
            "Датчик", "Температура", "Влажность", "Давление",
            "Скорость ветра", "Направление", "CVF"
        ])
        self.table.setStyleSheet(f"""
            QHeaderView::section {{
                background-color: {TABLE_HEADER_COLOR};
                color: {TEXT_COLOR};
                font-weight: bold;
            }}
        """)
        self.table.setFixedHeight(TABLE_HEIGHT)
        self.table.verticalHeader().setVisible(False)

        # TODO: Заменить тестовые данные на реальные из сервиса опроса
        self._fill_table_with_test_data()

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
        self.log_text.setStyleSheet(f"background-color: {LOG_TEXT_BG}; border: none;")

        # TODO: Заменить тестовые данные на реальные логи
        self.log_text.setText("\n".join([
                                            "01.08.2024 10:34:20 Станция контроля метеорологических параметров №2 (ОС2): Температура выше порога: (24.0 > 23.8999996185303)"
                                        ] * 3))

        log_layout.addWidget(log_label)
        log_layout.addWidget(self.log_text)

        parent_layout.addWidget(log_frame)

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

    def _fill_table_with_test_data(self):
        """Заполнение таблицы тестовыми данными (для демонстрации)"""
        test_data = [
            ["Reinhardt#1", "20,38", "55,5", "99,165", "---", "---", "---"],
            ["Reinhardt#2", "21,4", "30,23", "99,059", "---", "---", "---"],
            ["Reinhardt#3", "19,02", "64,41", "98,953", "---", "---", "---"],
            ["Reinhardt#4", "17,97", "98,74", "99,104", "10,12", "341,08", "16,58"],
            ["Reinhardt#5", "25,38", "84,21", "98,714", "0", "266,58", "25,38"],
            ["Reinhardt#13", "25,38", "84,21", "98,714", "---", "---", "---"]
        ]

        for row_data in test_data:
            row_idx = self.table.rowCount()
            self.table.insertRow(row_idx)
            for col_idx, value in enumerate(row_data):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row_idx, col_idx, item)

    # ==============================================
    # МЕТОДЫ ДЛЯ ИНТЕГРАЦИИ С СЕРВИСОМ ОПРОСА
    # (Эти методы нужно будет доработать)
    # ==============================================
    def update_polling_period(self):
        """Обновление периода опроса"""
        try:
            period = int(self.period_input.text())
            if period <= 0:
                raise ValueError("Период должен быть положительным числом")

            # Устанавливаем новый период в сервисе опроса
            self.app.polling_service.polling_interval = period
            self._add_log_message(f"Период опроса изменен на {period} сек.")
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
                self._add_log_message("Опрос датчиков запущен")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось запустить опрос: {str(e)}")

    def stop_polling(self):
        """Остановка опроса датчиков"""
        if self.is_polling_active:
            try:
                # Запускаем остановку в отдельном потоке, чтобы не блокировать GUI
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
            self.log_updated.emit("Опрос датчиков остановлен")
            self.is_polling_active = False
            # Обновляем кнопки в основном потоке через сигнал
            self.btn_start.setEnabled(True)
            self.btn_stop.setEnabled(False)
        except Exception as e:
            self.log_updated.emit(f"Ошибка при остановке опроса: {str(e)}")
        finally:
            loop.close()

    def open_edit_dialog(self):
        """Открытие диалога редактирования"""
        # TODO: Реализовать диалог редактирования
        self._add_log_message("Открыто окно редактирования")
        # Создаем и показываем диалоговое окно
        dialog = EditDialog(self)
        dialog.exec()

    def update_sensor_data(self, sensor_name, data):
        """Обновление данных датчика в таблице"""
        # TODO: Реализовать обновление данных в таблице
        # data - словарь с значениями параметров
        pass

    def _add_log_message(self, message):
        """Добавление сообщения в лог"""
        # timestamp = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        # self.log_text.append(f"{timestamp} {message}")

    # ==============================================
    # ОБРАБОТЧИКИ ПЕРЕМЕЩЕНИЯ ОКНА
    # ==============================================
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


# ==============================================
# ЗАПУСК ПРИЛОЖЕНИЯ
# ==============================================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MeteoMonitor(app)
    window.show()
    sys.exit(app.exec())
