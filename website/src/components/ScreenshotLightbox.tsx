import { useEffect, useRef } from "react";
import { ChevronLeft, ChevronRight, X } from "lucide-react";
import type { ScreenshotItem } from "../data/hilaloneData";

interface ScreenshotLightboxProps {
  readonly items: readonly ScreenshotItem[];
  readonly activeIndex: number | null;
  readonly onClose: () => void;
  readonly onChangeIndex: (nextIndex: number) => void;
}

export function ScreenshotLightbox({
  items,
  activeIndex,
  onClose,
  onChangeIndex,
}: ScreenshotLightboxProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  // Sinkronkan pembukaan/penutupan native <dialog> dengan showModal()
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) {
      return;
    }
    if (activeIndex !== null) {
      if (!dialog.open) {
        dialog.showModal();
      }
    } else if (dialog.open) {
      dialog.close();
    }
  }, [activeIndex]);

  // Fallback wajib light-dismiss pada browser yang belum mendukung attribute closedby="any"
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog || "closedBy" in HTMLDialogElement.prototype) {
      return;
    }

    const isOutside = (event: PointerEvent) => {
      const rect = dialog.getBoundingClientRect();
      return (
        event.clientX < rect.left ||
        event.clientX > rect.right ||
        event.clientY < rect.top ||
        event.clientY > rect.bottom
      );
    };

    let pressedOutside = false;
    const onPointerDown = (event: PointerEvent) => {
      pressedOutside = isOutside(event);
    };
    const onPointerUp = (event: PointerEvent) => {
      if (pressedOutside && isOutside(event)) {
        dialog.close();
      }
      pressedOutside = false;
    };

    dialog.addEventListener("pointerdown", onPointerDown);
    dialog.addEventListener("pointerup", onPointerUp);
    return () => {
      dialog.removeEventListener("pointerdown", onPointerDown);
      dialog.removeEventListener("pointerup", onPointerUp);
    };
  }, []);

  // Navigasi panah kiri/kanan antar screenshot saat dialog terbuka (Esc ditangani native <dialog>)
  useEffect(() => {
    if (activeIndex === null) {
      return;
    }
    const handleArrows = (event: KeyboardEvent) => {
      if (event.key === "ArrowLeft") {
        onChangeIndex((activeIndex - 1 + items.length) % items.length);
      } else if (event.key === "ArrowRight") {
        onChangeIndex((activeIndex + 1) % items.length);
      }
    };
    window.addEventListener("keydown", handleArrows);
    return () => window.removeEventListener("keydown", handleArrows);
  }, [activeIndex, items.length, onChangeIndex]);

  const current = activeIndex !== null ? items[activeIndex] : null;
  const prevIdx = activeIndex !== null ? (activeIndex - 1 + items.length) % items.length : 0;
  const nextIdx = activeIndex !== null ? (activeIndex + 1) % items.length : 0;

  return (
    <dialog
      ref={dialogRef}
      className="lightbox-dialog"
      aria-labelledby="lightbox-title"
      onClose={() => {
        const dialog = dialogRef.current;
        if (dialog) {
          dialog.returnValue = "";
        }
        onClose();
      }}
      {...({ closedby: "any" } as Record<string, string>)}
    >
      {current ? (
        <div className="modal-panel">
          <div className="modal-panel__head">
            <div>
              <div className="eyebrow" style={{ marginBottom: "0.2rem" }}>
                {current.category}
              </div>
              <h2 id="lightbox-title" className="modal-panel__title">
                {current.title}
              </h2>
            </div>
            <button
              type="button"
              className="btn btn--secondary btn--sm"
              autoFocus
              onClick={() => dialogRef.current?.close()}
              aria-label="Tutup pratinjau screenshot"
            >
              <X size={18} aria-hidden="true" />
              <span>Tutup</span>
            </button>
          </div>

          <div className="modal-panel__body">
            <img
              className="modal-panel__img"
              src={current.src1600}
              alt={current.alt}
              width={1600}
              height={900}
            />
          </div>

          <div className="modal-panel__foot">
            <p className="card__text" style={{ maxWidth: "68ch" }}>
              {current.caption}
            </p>
            <div className="modal-panel__nav">
              <button
                type="button"
                className="btn btn--secondary btn--sm"
                onClick={() => onChangeIndex(prevIdx)}
                aria-label="Screenshot sebelumnya"
              >
                <ChevronLeft size={16} aria-hidden="true" />
                <span>Sebelumnya</span>
              </button>
              <button
                type="button"
                className="btn btn--secondary btn--sm"
                onClick={() => onChangeIndex(nextIdx)}
                aria-label="Screenshot berikutnya"
              >
                <span>Berikutnya</span>
                <ChevronRight size={16} aria-hidden="true" />
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </dialog>
  );
}
