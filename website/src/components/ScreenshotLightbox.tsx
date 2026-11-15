import { useEffect } from "react";
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
  useEffect(() => {
    if (activeIndex === null) {
      return;
    }
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      } else if (event.key === "ArrowLeft") {
        onChangeIndex((activeIndex - 1 + items.length) % items.length);
      } else if (event.key === "ArrowRight") {
        onChangeIndex((activeIndex + 1) % items.length);
      }
    };

    window.addEventListener("keydown", handleKey);
    return () => {
      document.body.style.overflow = prevOverflow;
      window.removeEventListener("keydown", handleKey);
    };
  }, [activeIndex, items.length, onChangeIndex, onClose]);

  if (activeIndex === null) {
    return null;
  }

  const current = items[activeIndex];
  const prevIdx = (activeIndex - 1 + items.length) % items.length;
  const nextIdx = (activeIndex + 1) % items.length;

  return (
    <div
      className="modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="lightbox-title"
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          onClose();
        }
      }}
    >
      <div className="modal-panel">
        <div className="modal-panel__head">
          <div>
            <div className="eyebrow" style={{ marginBottom: "0.2rem" }}>
              {current.category}
            </div>
            <h3 id="lightbox-title" style={{ margin: 0, fontSize: "1.08rem" }}>
              {current.title}
            </h3>
          </div>
          <button
            type="button"
            className="btn btn--secondary btn--sm"
            onClick={onClose}
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
          />
        </div>

        <div className="modal-panel__foot">
          <p className="card__text" style={{ maxWidth: "68ch" }}>
            {current.caption}
          </p>
          <div style={{ display: "flex", gap: "0.5rem" }}>
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
    </div>
  );
}
