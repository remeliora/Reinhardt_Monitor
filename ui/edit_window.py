from PySide6.QtCore import Qt
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
        """)

        layout = QVBoxLayout(self)

        # Настройки станции
        station_group = QGroupBox("Настройки станции")
        form_layout = QFormLayout()

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
        btn_delete = QPushButton("Удалить")
        btn_save = QPushButton("Сохранить")
        btn_close = QPushButton("Закрыть")
        btn_delete.clicked.connect(self.delete_station)
        btn_save.clicked.connect(self.save)
        btn_close.clicked.connect(self.close)

        btn_box.addStretch()
        btn_box.addWidget(btn_delete)
        btn_box.addWidget(btn_save)
        btn_box.addWidget(btn_close)
        layout.addLayout(btn_box)

    def delete_station(self):
        print("🗑️ Станция удалена")
        self.accept()

    def save(self):
        print("💾 Настройки сохранены:")
        for row in range(self.range_table.rowCount()):
            param = self.range_table.item(row, 0).text()
            min_val = self.range_table.item(row, 1).text()
            max_val = self.range_table.item(row, 2).text()
            print(f"  {param}: от {min_val} до {max_val}")
        self.close()