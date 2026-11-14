"""Komponen Reusable Collapsible Accordion untuk Antarmuka HILALONE.

Menyediakan sistem panel akordeon buka-tutup (collapsible accordion):
- AccordionSection: Kartu kelompok interaktif dengan header tombol, ikon chevron vektor
  (kanan saat tertutup, bawah saat terbuka), judul, badge ringkasan dinamis saat tertutup,
  dan container konten yang disembunyikan/ditampilkan tanpa menghapus widget.
- AccordionGroup: Pengelola grup accordion dengan dukungan mode eksklusif (membuka satu
  section otomatis menutup section lainnya) untuk efisiensi ruang vertikal.

Prinsip Ilmiah & UI/UX:
- Widget dipertahankan (tidak dibuat ulang atau dihancurkan saat buka/tutup).
- Nilai checkbox, input, combobox, worker signals, dan progress bar tetap utuh 100%.
- Aksesibilitas keyboard dan navigasi visual presisi tanpa emoji (vektor Lucide).
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from hilalone.gui.icons import create_vector_icon


class AccordionHeader(QPushButton):
    """Header tombol interaktif untuk AccordionSection.

    Menampilkan:
    - Ikon chevron SVG tajam (chevron-right saat tertutup, chevron-down saat terbuka).
    - Label judul bagian (title).
    - Label ringkasan dinamis (summary badge) yang tampil saat section tertutup.
    """

    def __init__(
        self,
        title: str,
        is_nested: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.is_nested = is_nested
        self.setCheckable(True)
        self.setChecked(False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        if is_nested:
            self.setObjectName("nestedAccordionHeader")
            self.setMinimumHeight(28)
        else:
            self.setObjectName("accordionHeader")
            self.setMinimumHeight(34)

        header_layout = QHBoxLayout(self)
        header_layout.setContentsMargins(8 if is_nested else 10, 4, 8 if is_nested else 10, 4)
        header_layout.setSpacing(8)

        # 1. Chevron Icon
        self.chevron_icon = QLabel()
        self.chevron_icon.setObjectName("accordionChevron")
        self.chevron_icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.chevron_icon.setFixedSize(14, 14)
        header_layout.addWidget(self.chevron_icon)

        # 2. Title Label
        self.title_label = QLabel(title)
        self.title_label.setObjectName("nestedAccordionTitle" if is_nested else "accordionTitle")
        self.title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.title_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        header_layout.addWidget(self.title_label)

        header_layout.addStretch(1)

        # 3. Dynamic Summary Label (Badge saat tertutup)
        self.summary_label = QLabel("")
        self.summary_label.setObjectName("nestedAccordionSummary" if is_nested else "accordionSummary")
        self.summary_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.summary_label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        self.summary_label.setVisible(False)
        header_layout.addWidget(self.summary_label)

        self._is_night_vision = False
        self._summary_text = ""
        self._update_chevron()

    def set_night_vision(self, active: bool) -> None:
        """Memperbarui palet warna ikon chevron mengikuti status Night Vision."""
        self._is_night_vision = active
        self._update_chevron()

    def _update_chevron(self) -> None:
        """Merender ikon chevron sesuai status buka/tutup dan mode tema."""
        icon_name = "chevron-down" if self.isChecked() else "chevron-right"
        size = 12 if self.is_nested else 14
        if self._is_night_vision:
            icon = create_vector_icon(
                icon_name,
                normal_color="#ef4444",
                hover_color="#f87171",
                active_color="#b91c1c",
                size=size,
            )
        else:
            icon = create_vector_icon(
                icon_name,
                normal_color="#94a3b8",
                hover_color="#38bdf8",
                active_color="#38bdf8",
                size=size,
            )
        self.chevron_icon.setPixmap(icon.pixmap(QSize(size, size)))

    def setText(self, text: str) -> None:  # noqa: N802
        """Kompatibilitas dengan pemanggilan setText pada header label."""
        self.title_label.setText(text)

    def text(self) -> str:
        """Mengembalikan teks judul."""
        return self.title_label.text()

    def set_title(self, title: str) -> None:
        """Mengatur judul header."""
        self.title_label.setText(title)

    def title(self) -> str:
        """Mengambil teks judul."""
        return self.title_label.text()

    def set_summary(self, summary: str) -> None:
        """Mengatur teks ringkasan pada header."""
        self._summary_text = summary or ""
        self.summary_label.setText(self._summary_text)
        # Summary hanya tampil jika accordion tertutup dan teks tidak kosong / bukan '-'
        txt = self._summary_text.strip()
        if not self.isChecked() and txt and txt != "-":
            self.summary_label.setVisible(True)
        else:
            self.summary_label.setVisible(False)

    def summary(self) -> str:
        """Mengambil teks ringkasan."""
        return self._summary_text


class AccordionSection(QFrame):
    """Satu panel accordion lipat dengan header interaktif dan area konten."""

    toggled = Signal(bool)

    def __init__(
        self,
        title: str,
        is_nested: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.is_nested = is_nested
        self._is_expanded = False
        self._is_night_vision = False

        self.setObjectName("nestedAccordionSection" if is_nested else "accordionSection")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # 1. Header Button
        self.header_button = AccordionHeader(title, is_nested=is_nested, parent=self)
        self.header_button.clicked.connect(self.toggle)
        self.main_layout.addWidget(self.header_button)

        # 2. Content Container
        self.content_container = QFrame(self)
        self.content_container.setObjectName("nestedAccordionContent" if is_nested else "accordionContent")
        self.content_layout = QVBoxLayout(self.content_container)
        self.content_layout.setContentsMargins(8 if is_nested else 10, 8, 8 if is_nested else 10, 8)
        self.content_layout.setSpacing(6)
        self.content_container.setVisible(False)
        self.main_layout.addWidget(self.content_container)

    @property
    def title_label(self) -> QLabel:
        return self.header_button.title_label

    @property
    def summary_label(self) -> QLabel:
        return self.header_button.summary_label

    def setText(self, text: str) -> None:  # noqa: N802
        """Kompatibilitas setText."""
        self.header_button.set_title(text)

    def text(self) -> str:
        return self.header_button.title()

    def set_title(self, title: str) -> None:
        """Mengatur judul header."""
        self.header_button.set_title(title)

    def title(self) -> str:
        return self.header_button.title()

    def set_summary(self, summary: str) -> None:
        """Mengatur ringkasan header yang tampil saat tertutup."""
        self.header_button.set_summary(summary)

    def summary(self) -> str:
        return self.header_button.summary()

    def is_expanded(self) -> bool:
        """Mengembalikan True jika accordion sedang dalam posisi terbuka."""
        return self._is_expanded

    def set_expanded(self, expanded: bool, emit_signal: bool = True) -> None:
        """Membuka atau menutup accordion."""
        if self._is_expanded == expanded:
            return
        self._is_expanded = expanded
        self.header_button.setChecked(expanded)
        self.header_button._update_chevron()
        self.content_container.setVisible(expanded)

        # Kelola visibilitas summary badge
        sum_txt = self.summary().strip()
        if not expanded and sum_txt and sum_txt != "-":
            self.header_button.summary_label.setVisible(True)
        else:
            self.header_button.summary_label.setVisible(False)

        if emit_signal:
            self.toggled.emit(expanded)

    def toggle(self) -> None:
        """Membalikkan status buka / tutup."""
        self.set_expanded(not self._is_expanded)

    def set_night_vision(self, active: bool) -> None:
        """Memperbarui palet tema Night Vision pada header."""
        self._is_night_vision = active
        self.header_button.set_night_vision(active)

    def add_widget(self, widget: QWidget) -> None:
        """Menambahkan widget ke dalam layout konten accordion."""
        self.content_layout.addWidget(widget)

    def add_layout(self, layout) -> None:
        """Menambahkan sub-layout ke dalam layout konten accordion."""
        self.content_layout.addLayout(layout)


class AccordionGroup:
    """Pengelola kelompok AccordionSection dengan dukungan mode eksklusif.

    Ketika exclusive=True, membuka satu section akan otomatis menutup section lain
    di dalam kelompok yang sama.
    """

    def __init__(self, exclusive: bool = True) -> None:
        self.exclusive = exclusive
        self.sections: list[AccordionSection] = []

    def add_section(self, section: AccordionSection) -> None:
        """Mendaftarkan section ke dalam grup."""
        if section in self.sections:
            return
        self.sections.append(section)
        section.toggled.connect(lambda exp, s=section: self._on_section_toggled(s, exp))

    def _on_section_toggled(self, section: AccordionSection, expanded: bool) -> None:
        if expanded and self.exclusive:
            for s in self.sections:
                if s is not section and s.is_expanded():
                    s.set_expanded(False)

    def collapse_all(self) -> None:
        """Menutup seluruh section dalam grup."""
        for s in self.sections:
            s.set_expanded(False)

    def expand_section(self, section: AccordionSection) -> None:
        """Membuka section tertentu dan memicu penutupan section lain jika eksklusif."""
        section.set_expanded(True)

    def set_night_vision(self, active: bool) -> None:
        """Memperbarui mode night vision untuk semua section dalam grup."""
        for s in self.sections:
            s.set_night_vision(active)
