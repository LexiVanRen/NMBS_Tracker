# nmbs_monitor.py
import json
import sys
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

from PySide6.QtCore import Qt, QTimer, Signal, QObject, QThread
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QFrame,
    QHBoxLayout
)

IMPORTANT_TRAINS = {"16:38", "16:53", "17:37"}
API_URL = "https://api.irail.be/v1/connections/"


class FetchWorker(QObject):
    finished = Signal(list, str)
    error = Signal(str)

    def run(self):
        try:
            params = {
                "from": "Deinze",
                "to": "Gent-Sint-Pieters",
                "format": "json",
                "lang": "nl",
                "typeOfTransport": "trains",
                "timesel": "departure",
                "time": "1630",
                "date": datetime.now().strftime("%d%m%y"),
                "results": 12,
                "alerts": "true"
            }

            r = requests.get(API_URL, params=params, timeout=12)
            r.raise_for_status()
            data = r.json()
            print(json.dumps(data, indent=3))

            rows = []
            for conn in data.get("connection", []):
                dep = conn.get("departure", {})
                arr = conn.get("arrival", {})

                dep_time = datetime.fromtimestamp(int(dep["time"]))
                planned = dep_time.strftime("%H:%M")

                if planned not in IMPORTANT_TRAINS:
                    continue

                delay_sec = int(dep.get("delay", 0))
                delay_min = delay_sec // 60
                real_dep = datetime.fromtimestamp(int(dep["time"]) + delay_sec)

                rows.append({
                    "planned": planned,
                    "real": real_dep.strftime("%H:%M"),
                    "delay": delay_min,
                    "platform": dep.get("platform", "?"),
                    "vehicle": dep.get("vehicleinfo", {}).get("shortname", dep.get("vehicle", "?")),
                    "canceled": dep.get("canceled") == "1",
                    "occupancy": dep.get("occupancy", {}).get("name", "onbekend"),
                    "arrival": datetime.fromtimestamp(
                        int(arr["time"]) + int(arr.get("delay", 0))
                    ).strftime("%H:%M")
                })

            self.finished.emit(rows, datetime.now().strftime("%H:%M:%S"))

        except Exception as e:
            self.error.emit(str(e))


class TrainCard(QFrame):
    def __init__(self, train):
        super().__init__()
        delay = train["delay"]

        if train["canceled"]:
            color = "#ff4d4d"
            status = "AFGESCHAFT"
        elif delay > 0:
            color = "#ffb020"
            status = f"+{delay} min vertraging"
        else:
            color = "#25c281"
            status = "Op tijd"

        self.setStyleSheet(f"""
            QFrame {{
                background: #1f2937;
                border-left: 7px solid {color};
                border-radius: 14px;
                padding: 14px;
            }}
            QLabel {{
                color: #f9fafb;
                font-family: Segoe UI;
            }}
        """)

        layout = QVBoxLayout(self)

        title = QLabel(f"{train['planned']}  →  Gent-Sint-Pieters")
        title.setStyleSheet("font-size: 24px; font-weight: 700;")
        layout.addWidget(title)

        status_lbl = QLabel(status)
        status_lbl.setStyleSheet(f"font-size: 18px; color: {color}; font-weight: 700;")
        layout.addWidget(status_lbl)

        info = QLabel(
            f"Vertrek effectief: {train['real']}   |   Aankomst: {train['arrival']}\n"
            f"Trein: {train['vehicle']}   |   Perron: {train['platform']}   |   Bezetting: {train['occupancy']}"
        )
        info.setStyleSheet("font-size: 15px; color: #d1d5db;")
        layout.addWidget(info)


class App(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NMBS Monitor: Deinze → Gent-Sint-Pieters")
        self.resize(720, 520)

        self.setStyleSheet("""
            QWidget { background: #111827; }
            QLabel { color: white; font-family: Segoe UI; }
        """)

        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(14)

        header = QLabel("🚆 Deinze → Gent-Sint-Pieters")
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet("font-size: 30px; font-weight: 800; margin: 10px;")
        self.layout.addWidget(header)

        self.updated = QLabel("Data wordt geladen...")
        self.updated.setAlignment(Qt.AlignCenter)
        self.updated.setStyleSheet("font-size: 14px; color: #9ca3af;")
        self.layout.addWidget(self.updated)

        self.cards_layout = QVBoxLayout()
        self.layout.addLayout(self.cards_layout)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.fetch_data)
        self.timer.start(60_000)

        self.fetch_data()

    def clear_cards(self):
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def fetch_data(self):
        self.thread = QThread()
        self.worker = FetchWorker()
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.update_ui)
        self.worker.error.connect(self.show_error)

        self.worker.finished.connect(self.thread.quit)
        self.worker.error.connect(self.thread.quit)
        self.thread.start()

    def update_ui(self, rows, timestamp):
        self.clear_cards()
        self.updated.setText(f"Laatst bijgewerkt om {timestamp} — refresh elke minuut")

        if not rows:
            msg = QLabel("Geen treininfo gevonden voor 16:38, 16:53 of 17:37.")
            msg.setAlignment(Qt.AlignCenter)
            msg.setStyleSheet("font-size: 18px; color: #fbbf24;")
            self.cards_layout.addWidget(msg)
            return

        for train in sorted(rows, key=lambda x: x["planned"]):
            self.cards_layout.addWidget(TrainCard(train))

    def show_error(self, message):
        self.clear_cards()
        self.updated.setText("Fout bij ophalen van NMBS-data")
        err = QLabel(message)
        err.setWordWrap(True)
        err.setStyleSheet("color: #ff8080; font-size: 15px;")
        self.cards_layout.addWidget(err)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = App()
    window.show()
    sys.exit(app.exec())