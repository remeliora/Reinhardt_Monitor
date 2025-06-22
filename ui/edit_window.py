from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QGroupBox, QComboBox,
    QLineEdit, QTextEdit, QTableWidget, QTableWidgetItem,
    QHBoxLayout, QPushButton
)


class EditDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Редактирование станции")
        self.setMinimumWidth(500)
        self.setStyleSheet("""
            QDialog {
                background-color: #F5F0FF;
                font-family: Arial;
                font-size: 11pt;
            }
            QGroupBox {
                border: 2px solid #925FE2;
                border-radius: 10px;
                margin-top: 10px;
            }
            QGroupBox:title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                background-color: #925FE2;
                color: white;
                font-weight: bold;
            }
            QLineEdit, QTextEdit, QComboBox {
                background-color: white;
                border: 2px solid #925FE2;
                border-radius: 5px;
                padding: 4px;
            }
            QTableWidget {
                background-color: white;
                border: 2px solid #925FE2;
                border-radius: 5px;
            }
            QHeaderView::section {
                background-color: #925FE2;
                color: white;
                font-weight: bold;
            }
            QPushButton {
                background-color: #925FE2;
                color: white;
                font-weight: bold;
                border-radius: 5px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #7E4ED6;
            }
            QPushButton:disabled {
                background-color: #CCCCCC;
                color: #666666;
            }
        """)

        layout = QVBoxLayout(self)

        # Настройки станции
        station_group = QGroupBox("Настройки станции")
        form_layout = QFormLayout()

        # Добавляем выбор станции в начало формы
        self.station_selector = QComboBox()
        self.station_selector.addItem("-- Новая станция --")

        # Тестовые данные существующих станций
        self.existing_stations = [
            "Reinhardt#1 (Офисное здание)",
            "Reinhardt#2 (Промзона)",
            "Reinhardt#3 (Складской комплекс)",
            "Reinhardt#4 (Метеоплощадка)"
        ]
        self.station_selector.addItems(self.existing_stations)
        self.station_selector.currentIndexChanged.connect(self.on_station_selected)
        form_layout.addRow("Выбор станции", self.station_selector)

        self.equipment_type = QComboBox()
        self.equipment_type.addItems(["Модель DFT 1MV", "Модель DFT 5MV"])

        self.station_name = QLineEdit()
        self.location = QLineEdit()
        self.acronym = QLineEdit()
        self.ip_address = QLineEdit()
        self.port = QLineEdit()
        self.description = QTextEdit()

        form_layout.addRow("Тип оборудования", self.equipment_type)
        form_layout.addRow("Название станции", self.station_name)
        form_layout.addRow("Местоположение", self.location)
        form_layout.addRow("Акроним места", self.acronym)
        form_layout.addRow("IP адрес конвектора", self.ip_address)
        form_layout.addRow("Порт конвектора", self.port)
        form_layout.addRow("Описание", self.description)

        station_group.setLayout(form_layout)
        layout.addWidget(station_group)

        # Таблица допустимых диапазонов
        range_group = QGroupBox("Допустимые диапазоны параметров")
        range_layout = QVBoxLayout()

        self.range_table = QTableWidget(0, 3)
        self.range_table.setHorizontalHeaderLabels(["Параметр", "Мин", "Макс"])
        self.range_table.verticalHeader().setVisible(False)
        self.range_table.horizontalHeader().setStretchLastSection(True)
        self.range_table.setEditTriggers(QTableWidget.AllEditTriggers)

        parameters = ["Температура", "Влажность", "Давление", "Скорость ветра", "Направление", "CVF"]
        for param in parameters:
            row = self.range_table.rowCount()
            self.range_table.insertRow(row)
            self.range_table.setItem(row, 0, QTableWidgetItem(param))
            self.range_table.setItem(row, 1, QTableWidgetItem("-50"))
            self.range_table.setItem(row, 2, QTableWidgetItem("50"))

        range_layout.addWidget(self.range_table)
        range_group.setLayout(range_layout)
        layout.addWidget(range_group)

        # Кнопки
        btn_box = QHBoxLayout()
        self.btn_delete = QPushButton("Удалить")  # Сохраняем ссылку для изменения состояния
        btn_save = QPushButton("Сохранить")
        btn_close = QPushButton("Закрыть")
        self.btn_delete.clicked.connect(self.delete_station)
        btn_save.clicked.connect(self.save)
        btn_close.clicked.connect(self.close)

        btn_box.addStretch()
        btn_box.addWidget(self.btn_delete)
        btn_box.addWidget(btn_save)
        btn_box.addWidget(btn_close)
        layout.addLayout(btn_box)

        # Инициализация состояния формы
        self.current_station_id = None
        self.on_station_selected(0)  # Выбираем "Новую станцию" по умолчанию

    def on_station_selected(self, index):
        """Обработчик выбора станции из списка"""
        if index == 0:  # Выбрана новая станция
            self.clear_form()
            self.current_station_id = None
            # Делаем кнопку "Удалить" неактивной и серой
            self.btn_delete.setEnabled(False)
        else:
            # Индекс станции (для реального приложения - ID из БД)
            station_index = index - 1  # -1 т.к. первый элемент - новая станция

            # Загружаем данные станции
            self.load_station_data(station_index)
            self.current_station_id = station_index

            # Активируем кнопку удаления
            self.btn_delete.setEnabled(True)

    def clear_form(self):
        """Очистка формы для создания новой станции"""
        self.equipment_type.setCurrentIndex(0)
        self.station_name.clear()
        self.location.clear()
        self.acronym.clear()
        self.ip_address.clear()
        self.port.clear()
        self.description.clear()

        # Сбрасываем таблицу диапазонов к значениям по умолчанию
        parameters = ["Температура", "Влажность", "Давление", "Скорость ветра", "Направление", "CVF"]
        for row in range(self.range_table.rowCount()):
            self.range_table.item(row, 1).setText("-50")
            self.range_table.item(row, 2).setText("50")

    def load_station_data(self, station_id):
        """Загрузка данных станции (заглушка для демонстрации)"""
        # В реальном приложении здесь будет запрос к БД
        station_data = {
            "name": self.existing_stations[station_id],
            "equipment": "Модель DFT 5MV" if station_id % 2 == 0 else "Модель DFT 1MV",
            "location": "Офисное здание" if station_id == 0 else "Промзона" if station_id == 1 else "Складской комплекс" if station_id == 2 else "Метеоплощадка",
            "acronym": "OF" if station_id == 0 else "PZ" if station_id == 1 else "SK" if station_id == 2 else "MP",
            "ip": f"192.168.1.{10 + station_id}",
            "port": "502",
            "description": "Основная метеостанция офисного здания" if station_id == 0 else
            "Станция контроля в промзоне" if station_id == 1 else
            "Складская метеостанция" if station_id == 2 else
            "Главная метеоплощадка"
        }

        # Заполняем форму данными
        self.station_name.setText(station_data["name"])
        self.equipment_type.setCurrentText(station_data["equipment"])
        self.location.setText(station_data["location"])
        self.acronym.setText(station_data["acronym"])
        self.ip_address.setText(station_data["ip"])
        self.port.setText(station_data["port"])
        self.description.setText(station_data["description"])

        # Устанавливаем тестовые диапазоны
        for row in range(self.range_table.rowCount()):
            param = self.range_table.item(row, 0).text()
            min_val = "-40" if "Температура" in param else "0" if "Влажность" in param else "950" if "Давление" in param else "0"
            max_val = "50" if "Температура" in param else "100" if "Влажность" in param else "1050" if "Давление" in param else "100"

            self.range_table.item(row, 1).setText(min_val)
            self.range_table.item(row, 2).setText(max_val)

    def delete_station(self):
        if self.current_station_id is not None:
            print(f"🗑️ Станция {self.existing_stations[self.current_station_id]} удалена")
            # Здесь будет код удаления станции из БД
        else:
            print("Невозможно удалить - станция не выбрана")
        self.accept()

    def save(self):
        if self.station_selector.currentIndex() == 0:
            print("💾 Создана новая станция:")
        else:
            print(f"💾 Настройки станции {self.existing_stations[self.current_station_id]} сохранены:")

        # Выводим данные станции
        print(f"  Название: {self.station_name.text()}")
        print(f"  Тип оборудования: {self.equipment_type.currentText()}")
        print(f"  IP: {self.ip_address.text()}:{self.port.text()}")

        # Выводим диапазоны
        for row in range(self.range_table.rowCount()):
            param = self.range_table.item(row, 0).text()
            min_val = self.range_table.item(row, 1).text()
            max_val = self.range_table.item(row, 2).text()
            print(f"  {param}: от {min_val} до {max_val}")

        self.close()