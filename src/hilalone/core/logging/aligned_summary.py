"""Formatter Terpusat untuk Ringkasan Pemrosesan Ilmiah HILALONE (Addendum Typography & Alignment).

Menyediakan satu fungsi terpusat ``format_aligned_summary`` untuk seluruh ringkasan
manusia (Console Processing Summary, Automated Processing Summary, Output Save Summary,
Session Summary, berkas .log/.txt, dan ringkasan teks dari JSON Report v2.0).

Aturan Tata Letak Tiga Kolom Visual:
  1. LABEL     : Rata kiri dengan lebar kolom seragam di seluruh blok.
  2. SEPARATOR : Tanda titik dua (`` : ``) yang sejajar vertikal sempurna di seluruh baris.
  3. VALUE     : Dimulai pada kolom horizontal yang persis sama; nilai panjang
                 dibungkus (*line-wrapped*) ke baris berikutnya tepat di bawah kolom VALUE.
"""

from __future__ import annotations

import math
from typing import Any, Sequence


def format_duration_seconds(
    duration_ms: float | None = None,
    *,
    duration_s: float | None = None,
) -> str:
    """Memformat durasi numerik (ms atau s) menjadi string standar ``0.00 s``.

    - Mengonversi milidetik menjadi detik tepat satu kali.
    - Membulatkan tampilan menjadi dua angka desimal (``0.00 s``).
    - Tidak mengubah nilai pengukuran presisi penuh internal.
    """
    if duration_s is not None:
        try:
            sec = float(duration_s)
        except (TypeError, ValueError):
            sec = 0.0
    elif duration_ms is not None:
        try:
            sec = float(duration_ms) / 1000.0
        except (TypeError, ValueError):
            sec = 0.0
    else:
        sec = 0.0

    if not math.isfinite(sec) or sec < 0.0:
        sec = 0.0
    return f"{sec:.2f} s"


def _wrap_value_text(value_str: str, max_width: int | None) -> list[str]:
    """Membungkus teks nilai yang panjang tanpa memotong karakter penting.

    Jika ``max_width`` adalah ``None`` atau ``<= 0``, hanya memecah berdasarkan baris baru eksplisit.
    Jika panjang baris melebihi ``max_width``, memecah secara cerdas pada spasi, garis miring path
    (``\\`` atau ``/``), koma, atau batas karakter.
    """
    raw_lines = value_str.splitlines() if value_str else ["-"]
    if not raw_lines:
        raw_lines = ["-"]

    if max_width is None or max_width <= 0:
        return [line if line else "-" for line in raw_lines]

    wrapped: list[str] = []
    for raw_line in raw_lines:
        text = raw_line.strip() if raw_line.strip() else "-"
        if len(text) <= max_width:
            wrapped.append(text)
            continue

        remaining = text
        while len(remaining) > max_width:
            window = remaining[:max_width]
            # Cari titik potong alami dari kanan: spasi, pemisah path, koma, atau garis bawah
            split_pos = -1
            for sep in (" ", "\\", "/", ","):
                pos = window.rfind(sep)
                if pos > max_width // 3:
                    # Sertakan pemisah path/koma di akhir baris pertama, kecuali spasi
                    split_pos = pos if sep == " " else pos + 1
                    break

            if split_pos <= 0:
                split_pos = max_width

            chunk = remaining[:split_pos].rstrip()
            if not chunk:
                chunk = remaining[:max_width]
                split_pos = max_width
            wrapped.append(chunk)
            remaining = remaining[split_pos:].lstrip(" ")

        if remaining:
            wrapped.append(remaining)

    return wrapped if wrapped else ["-"]


def format_aligned_row(
    label: str,
    value: Any,
    label_width: int,
    *,
    max_value_width: int | None = 68,
) -> list[str]:
    """Memformat satu pasangan ``(label, value)`` dengan titik dua sejajar dan line-wrapping rapi."""
    clean_label = str(label or "").strip()
    if value is None:
        val_str = "N/A"
    elif isinstance(value, bool):
        val_str = "YES" if value else "NO"
    else:
        val_str = str(value).strip()
        if not val_str:
            val_str = "N/A"

    eff_width = max(int(label_width), len(clean_label))
    prefix_first = f"{clean_label.ljust(eff_width)} : "
    prefix_cont = " " * len(prefix_first)

    value_lines = _wrap_value_text(val_str, max_value_width)
    out_lines: list[str] = [f"{prefix_first}{value_lines[0]}"]
    for cont_line in value_lines[1:]:
        out_lines.append(f"{prefix_cont}{cont_line}")
    return out_lines


def format_aligned_summary(
    sections_or_items: Sequence[tuple[str, Any]],
    *,
    title: str | None = "PROCESSING SUMMARY",
    footer: str | None = None,
    label_width: int = 25,
    max_value_width: int | None = 68,
    min_separator_width: int = 52,
) -> str:
    """Memformat blok ringkasan ilmiah dengan seluruh tanda titik dua (``:``) sejajar vertikal.

    Parameter ``sections_or_items`` dapat berupa:
      1. Daftar pasangan ``(label, value)`` biasa, ATAU
      2. Daftar grup bagian ``(section_title, [(label, value), ...])``.

    Lebar kolom label dihitung otomatis dari ``max(label_width, len(label_terpanjang))``
    di seluruh blok sehingga tidak ada satu pun label yang terpotong atau menggeser titik dua.
    """
    if not sections_or_items:
        return ""

    # Deteksi apakah input berupa daftar section bertingkat atau daftar (label, value) datar
    is_grouped = False
    first_elem = sections_or_items[0]
    if (
        isinstance(first_elem, tuple)
        and len(first_elem) == 2
        and isinstance(first_elem[1], (list, tuple))
        and (
            len(first_elem[1]) == 0
            or (isinstance(first_elem[1][0], tuple) and len(first_elem[1][0]) == 2)
        )
    ):
        is_grouped = True

    grouped_sections: list[tuple[str | None, list[tuple[str, Any]]]] = []
    if is_grouped:
        for sec_title, sec_items in sections_or_items:
            valid_items = [(str(k).strip(), v) for k, v in sec_items if str(k).strip()]
            if valid_items:
                grouped_sections.append((str(sec_title).strip().upper() if sec_title else None, valid_items))
    else:
        flat_items = [(str(k).strip(), v) for k, v in sections_or_items if str(k).strip()]
        if flat_items:
            grouped_sections.append((None, flat_items))

    if not grouped_sections:
        return ""

    # Hitung lebar label efektif untuk seluruh blok agar 100% titik dua sejajar vertikal
    max_lbl_len = max(
        (len(lbl) for _, items in grouped_sections for lbl, _ in items),
        default=label_width,
    )
    eff_label_width = max(int(label_width), max_lbl_len)

    # Susun baris-baris isi per bagian terlebih dahulu
    rendered_sections: list[tuple[str | None, list[str]]] = []
    max_line_len = min_separator_width
    for sec_title, items in grouped_sections:
        sec_lines: list[str] = []
        for lbl, val in items:
            row_lines = format_aligned_row(
                lbl,
                val,
                eff_label_width,
                max_value_width=max_value_width,
            )
            for rl in row_lines:
                max_line_len = max(max_line_len, len(rl))
            sec_lines.extend(row_lines)
        rendered_sections.append((sec_title, sec_lines))

    # Panjang garis pemisah mengikuti lebar blok (dibatasi agar nyaman di jendela Console sempit)
    sep_width = max(min_separator_width, min(max_line_len, 76))
    main_sep = "=" * sep_width
    sub_sep = "-" * sep_width

    output_lines: list[str] = []
    if title:
        clean_title = title.strip()
        pad_left = max(0, (sep_width - len(clean_title)) // 2)
        output_lines.append(main_sep)
        output_lines.append((" " * pad_left) + clean_title)
        output_lines.append(main_sep)

    for sec_idx, (sec_title, sec_lines) in enumerate(rendered_sections):
        if sec_title:
            if output_lines and output_lines[-1] != main_sep:
                output_lines.append("")
            output_lines.append(sec_title)
            output_lines.append(sub_sep)
        elif sec_idx > 0:
            output_lines.append(sub_sep)

        output_lines.extend(sec_lines)

    if footer:
        clean_footer = footer.strip()
        pad_left = max(0, (sep_width - len(clean_footer)) // 2)
        output_lines.append(main_sep)
        output_lines.append((" " * pad_left) + clean_footer)
        output_lines.append(main_sep)
    elif title:
        output_lines.append(main_sep)

    return "\n".join(output_lines)
