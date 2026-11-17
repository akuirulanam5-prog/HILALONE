import { useRef, useState } from "react";
import { HelpCircle } from "lucide-react";
import { SectionHeader } from "../components/SectionHeader";
import { FAQ_ITEMS } from "../data/hilaloneData";

export function FaqSection() {
  const listRef = useRef<HTMLDivElement>(null);
  const [allExpanded, setAllExpanded] = useState(false);

  const handleToggleAll = () => {
    const container = listRef.current;
    if (!container) {
      return;
    }
    const nextExpand = !allExpanded;
    for (const details of container.querySelectorAll<HTMLDetailsElement>(":scope > details")) {
      details.open = nextExpand;
    }
    setAllExpanded(nextExpand);
  };

  const syncAllState = () => {
    const container = listRef.current;
    if (!container) {
      return;
    }
    const items = Array.from(container.querySelectorAll<HTMLDetailsElement>(":scope > details"));
    setAllExpanded(items.length > 0 && items.every((d) => d.open));
  };

  return (
    <section id="faq" className="section section--light">
      <div className="container">
        <div className="faq-wrap">
          <div className="section-head-row">
            <SectionHeader
              eyebrow="Pertanyaan Umum"
              title="FAQ HILALONE"
              subtitle="Jawaban ringkas mengenai kemampuan aktual, format berkas, pemisahan data ilmiah, dan rencana versi mendatang."
              icon={<HelpCircle size={14} aria-hidden="true" />}
            />

            <button
              type="button"
              className="btn btn--secondary btn--sm"
              aria-expanded={allExpanded}
              onClick={handleToggleAll}
            >
              {allExpanded ? "Tutup Semua Jawaban" : "Buka Semua Jawaban"}
            </button>
          </div>

          {/* Native <details> + <summary> tanpa elemen heading di dalam summary */}
          <div ref={listRef} className="faq-list">
            {FAQ_ITEMS.map((item, idx) => (
              <details
                key={item.id}
                className="faq-item"
                open={idx === 0}
                onToggle={syncAllState}
              >
                <summary className="faq-item__trigger">{item.question}</summary>
                <div className="faq-item__body">
                  <p>{item.answer}</p>
                </div>
              </details>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
