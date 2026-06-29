import json
import sys
from datetime import datetime

import requests
from plyer import notification
# After
from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,

    QScrollArea,
    QVBoxLayout,
    QWidget,
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
                "alerts": "true",
            }

            response = requests.get(API_URL, params=params, timeout=12)
            response.raise_for_status()
            data = response.json()
            #print(json.dumps(data, indent=3))

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
                real_arr = datetime.fromtimestamp(int(arr["time"]) + int(arr.get("delay", 0)))

                rows.append(
                    {
                        "planned": planned,
                        "real_departure": real_dep.strftime("%H:%M"),
                        "real_arrival": real_arr.strftime("%H:%M"),
                        "delay": delay_min,
                        "canceled": dep.get("canceled") == "1",
                    }
                )

            self.finished.emit(rows, datetime.now().strftime("%H:%M:%S"))
        except Exception as exc:
            self.error.emit(str(exc))


class TrainCard(QFrame):
    def __init__(self, train):
        super().__init__()

        delay = train["delay"]
        canceled = train["canceled"]

        if canceled:
            accent = "#f87171"
            status = "AFGELAST"
            # solid red badge, clearly distinct
            badge_bg = "#f87171"
            badge_color = "#1a0000"
        elif delay > 0:
            accent = "#fbbf24"
            status = f"+{delay} min vertraging"
            # fully yellow badge — no dark/red background
            badge_bg = "#fbbf24"
            badge_color = "#1c1000"
        else:
            accent = "#34d399"
            status = "Op tijd"
            badge_bg = "#34d399"
            badge_color = "#001a0d"

        self.setStyleSheet(
            f"""
            QFrame#card {{
                background: #225794;
                border: 1px solid rgba(255,255,255,0.07);
                border-left: 4px solid {accent};
                border-radius: 14px;
            }}
            """
        )
        self.setObjectName("card")

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(14)

        # ── Top row: planned time + route + badge ───────────────────────────
        top = QHBoxLayout()
        top.setSpacing(10)

        time_lbl = QLabel(train["planned"])
        time_lbl.setStyleSheet(
            f"font-size: 28px; font-weight: 900; color: {accent}; font-family: 'Segoe UI';"
        )

        route_lbl = QLabel("→  Gent-Sint-Pieters")
        route_lbl.setStyleSheet(
            "font-size: 18px; font-weight: 600; color: #cbd5e1; font-family: 'Segoe UI';"
        )
        route_lbl.setAlignment(Qt.AlignVCenter)

        top.addWidget(time_lbl)
        top.addWidget(route_lbl)
        top.addStretch(1)

        badge = QLabel(status)
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet(
            f"""
            QLabel {{
                background: {badge_bg};
                color: {badge_color};
                font-size: 13px;
                font-weight: 800;
                padding: 5px 16px;
                border-radius: 999px;
                font-family: 'Segoe UI';
            }}
            """
        )
        top.addWidget(badge)
        root.addLayout(top)

        # ── If canceled: show a clear message, no times ─────────────────────
        if canceled:
            divider = QFrame()
            divider.setFrameShape(QFrame.HLine)
            divider.setStyleSheet("color: rgba(255,255,255,0.06);")
            root.addWidget(divider)

            msg = QLabel("Deze trein rijdt vandaag niet.")
            msg.setAlignment(Qt.AlignCenter)
            msg.setStyleSheet(
                "font-size: 15px; font-weight: 600; color: #f87171; font-family: 'Segoe UI';"
                "padding: 8px 0px;"
            )
            root.addWidget(msg)
            return

        # ── Divider ──────────────────────────────────────────────────────────
        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setStyleSheet("color: rgba(255,255,255,0.06);")
        root.addWidget(divider)

        # ── Bottom row: dep  →  arr ──────────────────────────────────────────
        times_row = QHBoxLayout()
        times_row.setSpacing(0)

        def time_block(label_text, time_text, align_right=False):
            col = QVBoxLayout()
            col.setSpacing(3)
            t = QLabel(time_text)
            t.setStyleSheet(
                "font-size: 22px; font-weight: 800; color: #f1f5f9; font-family: 'Segoe UI';"
            )
            lbl = QLabel(label_text)
            lbl.setStyleSheet(
                "font-size: 11px; font-weight: 600; color: #64748b; font-family: 'Segoe UI';"
                " letter-spacing: 0.5px;"
            )
            if align_right:
                t.setAlignment(Qt.AlignRight)
                lbl.setAlignment(Qt.AlignRight)
            col.addWidget(t)
            col.addWidget(lbl)
            return col

        times_row.addLayout(time_block("ECHT VERTREK", train["real_departure"]))
        times_row.addStretch(1)

        # Simple arrow in the centre — no duration label that reads as delay
        arrow_lbl = QLabel("→")
        arrow_lbl.setAlignment(Qt.AlignCenter)
        arrow_lbl.setStyleSheet(
            f"font-size: 35px; font-weight: 900; color: #ffffff; font-family: 'Segoe UI';"
        )
        times_row.addWidget(arrow_lbl)

        times_row.addStretch(1)
        times_row.addLayout(time_block("ECHTE AANKOMST", train["real_arrival"], align_right=True))
        root.addLayout(times_row)


class App(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NMBS Monitor: Deinze → Gent-Sint-Pieters")
        self.resize(720, 620)
        self.setWindowIcon(QIcon("assets/nmbs.ico"))
        self.setStyleSheet(
            """
            QWidget {
                background: #FFFFFF;
            }
            QLabel {
                color: white;
                font-family: Segoe UI;
            }
            """
        )

        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(24, 20, 24, 20)

        # ── Top bar: route title  +  live clock ─────────────────────────────
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 4)

        # After
        logo_lbl = QLabel()
        pixmap = QPixmap("assets/nmbs.png")
        logo_lbl.setPixmap(pixmap.scaledToHeight(36, Qt.SmoothTransformation))
        logo_lbl.setFixedSize(logo_lbl.pixmap().size())
        top_bar.addWidget(logo_lbl)

        header = QLabel("  Deinze → Gent-Sint-Pieters")
        header.setStyleSheet(
            "font-size: 22px; font-weight: 900; color: #2B6ABD; font-family: 'Segoe UI';"
        )
        top_bar.addWidget(header)
        top_bar.addStretch(1)

        self.clock_lbl = QLabel()
        self.clock_lbl.setStyleSheet(
            "font-size: 32px; font-weight: 900; color: #2B6ABD; font-family: 'Segoe UI';"
        )
        top_bar.addWidget(self.clock_lbl)
        self.layout.addLayout(top_bar)

        self.updated = QLabel("Data wordt geladen...")
        self.updated.setAlignment(Qt.AlignLeft)
        self.updated.setStyleSheet(
            "font-size: 11px; color: #475569; font-family: 'Segoe UI'; margin-bottom: 12px;"
        )
        self.layout.addWidget(self.updated)

        # Live clock ticks every second
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._tick_clock)
        self._clock_timer.start(1000)
        self._tick_clock()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        cards_container = QWidget()
        cards_container.setStyleSheet("background: transparent;")
        self.cards_layout = QVBoxLayout(cards_container)
        self.cards_layout.setSpacing(12)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.addStretch(1)

        scroll.setWidget(cards_container)
        self.layout.addWidget(scroll)

        # key: planned time  →  {"delay": int, "canceled": bool}
        self._prev_state: dict = {}
        """
        self._prev_state = {
            "16:38": {"delay": 0, "canceled": False},
            "16:53": {"delay": 2, "canceled": False},
            "17:37": {"delay": 0, "canceled": True},
        }
        """
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.fetch_data)
        self.timer.start(60_000)

        self.fetch_data()

    def _notify(self, title: str, message: str):
        """Fire a system notification (best-effort; silently ignored if unsupported)."""
        try:
            notification.notify(
                title=title,
                message=message,
                app_name="NMBS Monitor",
                timeout=6,
            )
        except Exception:
            pass

    def _check_changes(self, rows: list):
        """Diff new rows against previous state and fire notifications for changes."""
        new_state = {r["planned"]: {"delay": r["delay"], "canceled": r["canceled"]} for r in rows}

        for planned, new in new_state.items():
            prev = self._prev_state.get(planned)


            if prev is None:
                # First fetch — establish baseline silently
                continue

            was_canceled = prev["canceled"]
            is_canceled  = new["canceled"]
            prev_delay   = prev["delay"]
            new_delay    = new["delay"]

            if not was_canceled and is_canceled:
                self._notify(
                    f"🚫 {planned} AFGELAST",
                    f"De trein van {planned} naar Gent-Sint-Pieters is afgelast.",
                )
            elif was_canceled and not is_canceled:
                if new_delay > 0:
                    self._notify(
                        f"✅ {planned} terug in dienst (⚠️+{new_delay} min)",
                        f"De trein van {planned} rijdt weer, maar heeft {new_delay} min vertraging.",
                    )
                else:
                    self._notify(
                        f"✅ {planned} terug in dienst",
                        f"De trein van {planned} naar Gent-Sint-Pieters rijdt weer op tijd.",
                    )
            elif not is_canceled and prev_delay != new_delay:
                if new_delay == 0:
                    self._notify(
                        f"✅ {planned} op tijd",
                        f"De trein van {planned} heeft geen vertraging meer.",
                    )
                elif prev_delay == 0:
                    self._notify(
                        f"⚠️ {planned} +{new_delay} min vertraging",
                        f"De trein van {planned} heeft nu {new_delay} min vertraging.",
                    )
                elif new_delay > prev_delay:
                    self._notify(
                        f"⚠️ {planned} vertraging toegenomen",
                        f"Vertraging gestegen van {prev_delay} naar {new_delay} min.",
                    )
                else:
                    self._notify(
                        f"⚠️ {planned} vertraging gedaald",
                        f"Vertraging gedaald van {prev_delay} naar {new_delay} min.",
                    )

        self._prev_state = new_state

    def _tick_clock(self):
        self.clock_lbl.setText(datetime.now().strftime("%H:%M:%S"))

    def clear_cards(self):
        # Remove all items except the trailing stretch
        while self.cards_layout.count() > 1:
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
        self._check_changes(rows)
        self.updated.setText(f"Laatst bijgewerkt om {timestamp}")

        if not rows:
            msg = QLabel("Geen treininfo gevonden voor 16:38, 16:53 of 17:37.")
            msg.setAlignment(Qt.AlignCenter)
            msg.setStyleSheet("font-size: 18px; color: #fbbf24;")
            self.cards_layout.addWidget(msg)
            return

        for i, train in enumerate(sorted(rows, key=lambda x: x["planned"])):
            self.cards_layout.insertWidget(i, TrainCard(train))

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