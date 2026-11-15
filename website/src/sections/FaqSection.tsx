import { useState } from "react";
import { ChevronDown, HelpCircle } from "lucide-react";
import { SectionHeader } from "../components/SectionHeader";
import { FAQ_ITEMS } from "../data/hilaloneData";

export function FaqSection() {
  const [openId, setOpenId] = useState<string | null>(FAQ_ITEMS[0]?.id ?? null);

  return (
    <section id="faq" className="section section--alt">
      <div className="container">
        <SectionHeader
          eyebrow="Pertanyaan Umum"
          title="FAQ HILALONE"
          subtitle="Jawaban ringkas mengenai kemampuan aktual, format berkas, pemisahan data ilmiah, dan rencana versi mendatang."
          centered
          icon={<HelpCircle size={14} aria-hidden="true" />}
        />

        <div className="faq-list">
          {FAQ_ITEMS.map((item) => {
            const isOpen = openId === item.id;
            const panelId = `faq-panel-${item.id}`;
            return (
              <div key={item.id} className="faq-item">
                <button
                  type="button"
                  className="faq-item__trigger"
                  aria-expanded={isOpen}
                  aria-controls={panelId}
                  onClick={() => setOpenId(isOpen ? null : item.id)}
                >
                  <span>{item.question}</span>
                  <ChevronDown
                    size={18}
                    style={{
                      flexShrink: 0,
                      transform: isOpen ? "rotate(180deg)" : "rotate(0deg)",
                      transition: "transform 0.18s ease",
                    }}
                    aria-hidden="true"
                  />
                </button>
                {isOpen ? (
                  <div id={panelId} className="faq-item__body">
                    {item.answer}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
