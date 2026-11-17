import { useEffect, useRef, useState } from "react";
import { Download, Menu, X } from "lucide-react";
import { siteConfig } from "../data/siteConfig";

interface NavItem {
  readonly href: string;
  readonly id: string;
  readonly label: string;
}

const NAV_ITEMS: readonly NavItem[] = [
  { href: "#fitur", id: "fitur", label: "Fitur" },
  { href: "#alur-kerja", id: "alur-kerja", label: "Alur Kerja" },
  { href: "#antarmuka", id: "antarmuka", label: "Antarmuka" },
  { href: "#tentang", id: "tentang", label: "Tentang" },
  { href: "#spesifikasi", id: "spesifikasi", label: "Spesifikasi" },
  { href: "#roadmap", id: "roadmap", label: "Roadmap" },
  { href: "#faq", id: "faq", label: "FAQ" },
];

export function Navbar() {
  const headerRef = useRef<HTMLElement>(null);
  const innerRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLUListElement>(null);

  const [isWide, setIsWide] = useState(true);
  const [isMeasuring, setIsMeasuring] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [activeId, setActiveId] = useState<string>("fitur");

  // Pantau seksi aktif untuk penanda lokasi saat scroll
  useEffect(() => {
    const sections = NAV_ITEMS.map((item) => document.getElementById(item.id)).filter(
      (el): el is HTMLElement => el !== null
    );
    if (sections.length === 0 || typeof IntersectionObserver === "undefined") {
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio);
        if (visible.length > 0 && visible[0].target.id) {
          setActiveId(visible[0].target.id);
        }
      },
      {
        rootMargin: "-24% 0px -56% 0px",
        threshold: [0.1, 0.35, 0.6],
      }
    );

    sections.forEach((sec) => observer.observe(sec));
    return () => observer.disconnect();
  }, []);

  // Pengukuran dinamis lebar header (tanpa breakpoint kaku & adaptif terhadap zoom / skala font OS)
  useEffect(() => {
    const headerEl = headerRef.current;
    const innerEl = innerRef.current;
    const menuEl = menuRef.current;
    if (!headerEl || !innerEl || !menuEl || typeof ResizeObserver === "undefined") {
      return;
    }

    let lastHeaderWidth = headerEl.clientWidth;
    let rafId = 0;

    const measure = () => {
      const supportsPopover = Object.hasOwn(HTMLElement.prototype, "popover");
      const wasPopoverOpen =
        supportsPopover && menuEl.matches(":popover-open");

      setIsMeasuring(true);
      headerEl.classList.add("is-wide", "is-measuring");
      if (supportsPopover) {
        menuEl.removeAttribute("popover");
      }

      const fitsInline = innerEl.scrollWidth <= innerEl.clientWidth + 1;

      if (fitsInline) {
        setIsWide(true);
        setMenuOpen(false);
      } else {
        headerEl.classList.remove("is-wide");
        if (supportsPopover) {
          menuEl.setAttribute("popover", "auto");
          if (wasPopoverOpen) {
            try {
              (menuEl as HTMLElement & { showPopover?: () => void }).showPopover?.();
            } catch {
              // Abaikan jika browser menolak re-open otomatis saat resize ekstrem
            }
          }
        }
        setIsWide(false);
      }

      cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(() => {
        headerEl.classList.remove("is-measuring");
        setIsMeasuring(false);
      });
    };

    measure();

    const ro = new ResizeObserver(() => {
      const currentW = headerEl.clientWidth;
      if (headerEl.classList.contains("is-wide") || currentW > lastHeaderWidth) {
        measure();
      }
      lastHeaderWidth = currentW;
    });

    ro.observe(headerEl);
    ro.observe(menuEl);

    return () => {
      ro.disconnect();
      cancelAnimationFrame(rafId);
    };
  }, []);

  // Sinkronkan event toggle bawaan Popover API agar state tombol hamburger akurat
  useEffect(() => {
    const menuEl = menuRef.current;
    if (!menuEl || !Object.hasOwn(HTMLElement.prototype, "popover")) {
      return;
    }
    const onToggle = (event: Event) => {
      const toggleEvt = event as Event & { newState?: string };
      if (toggleEvt.newState) {
        setMenuOpen(toggleEvt.newState === "open");
      }
    };
    menuEl.addEventListener("toggle", onToggle);
    return () => menuEl.removeEventListener("toggle", onToggle);
  }, []);

  const closeNarrowMenu = () => {
    const menuEl = menuRef.current as (HTMLUListElement & { hidePopover?: () => void }) | null;
    if (menuEl && Object.hasOwn(HTMLElement.prototype, "popover") && menuEl.matches(":popover-open")) {
      try {
        menuEl.hidePopover?.();
      } catch {
        // fallback state
      }
    }
    setMenuOpen(false);
  };

  const handleToggleFallback = () => {
    if (!Object.hasOwn(HTMLElement.prototype, "popover")) {
      setMenuOpen((prev) => !prev);
    }
  };

  return (
    <header
      ref={headerRef}
      className={`navbar${isWide ? " is-wide" : ""}${isMeasuring ? " is-measuring" : ""}`}
    >
      <div ref={innerRef} className="container navbar__inner">
        <a className="brand-link" href="#beranda" aria-label="Beranda HILALONE">
          <picture>
            <source srcSet="/branding/hilalone-icon-standard-96.webp" type="image/webp" />
            <img
              className="brand-link__logo"
              src="/branding/hilalone-icon-standard-96.png"
              alt="Ikon resmi HILALONE"
              width={40}
              height={40}
            />
          </picture>
          <span className="brand-link__text">
            <span className="brand-link__name">{siteConfig.appName}</span>
            <span className="brand-link__sub">Automated Hilal Image Processing</span>
          </span>
        </a>

        <nav className="site-nav" aria-label="Utama">
          <button
            type="button"
            className="menu-toggle"
            popoverTarget="site-menu"
            popoverTargetAction="toggle"
            aria-controls="site-menu"
            aria-expanded={!isWide ? menuOpen : undefined}
            aria-label={menuOpen ? "Tutup menu" : "Buka menu"}
            onClick={handleToggleFallback}
          >
            {menuOpen ? <X size={18} aria-hidden="true" /> : <Menu size={18} aria-hidden="true" />}
            <span>Menu</span>
          </button>

          <ul
            ref={menuRef}
            id="site-menu"
            className={`nav-links${!isWide && menuOpen ? " is-open-fallback" : ""}`}
          >
            {NAV_ITEMS.map((item) => (
              <li key={item.id}>
                <a
                  href={item.href}
                  className={activeId === item.id ? "is-active" : undefined}
                  aria-current={activeId === item.id ? "location" : undefined}
                  onClick={closeNarrowMenu}
                >
                  {item.label}
                </a>
              </li>
            ))}
            {!isWide ? (
              <li className="nav-links__mobile-cta">
                <a href="#unduh" className="btn btn--primary btn--sm" onClick={closeNarrowMenu}>
                  <Download size={16} aria-hidden="true" />
                  <span>Unduh v{siteConfig.version}</span>
                </a>
              </li>
            ) : null}
          </ul>
        </nav>

        <div className="navbar__actions">
          <a href="#unduh" className="btn btn--primary btn--sm nav-cta-desktop">
            <Download size={16} aria-hidden="true" />
            <span>Unduh HILALONE</span>
          </a>
        </div>
      </div>
    </header>
  );
}
