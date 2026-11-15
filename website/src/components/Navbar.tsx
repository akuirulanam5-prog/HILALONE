import { useEffect, useState } from "react";
import { Download, Menu, X } from "lucide-react";
import { siteConfig } from "../data/siteConfig";

interface NavItem {
  readonly href: string;
  readonly id: string;
  readonly label: string;
}

const NAV_ITEMS: readonly NavItem[] = [
  { href: "#tentang", id: "tentang", label: "Tentang" },
  { href: "#fitur", id: "fitur", label: "Fitur" },
  { href: "#antarmuka", id: "antarmuka", label: "Antarmuka" },
  { href: "#alur-kerja", id: "alur-kerja", label: "Alur Kerja" },
  { href: "#roadmap", id: "roadmap", label: "Roadmap" },
  { href: "#spesifikasi", id: "spesifikasi", label: "Spesifikasi" },
];

export function Navbar() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [activeId, setActiveId] = useState<string>("tentang");

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
        rootMargin: "-25% 0px -55% 0px",
        threshold: [0.1, 0.35, 0.6],
      }
    );

    sections.forEach((sec) => observer.observe(sec));
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!menuOpen) {
      return;
    }
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setMenuOpen(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [menuOpen]);

  return (
    <header className="navbar">
      <div className="container navbar__inner">
        <a className="brand-link" href="#beranda" aria-label="Beranda HILALONE">
          <picture>
            <source srcSet="/branding/hilalone-logo-standard-96.webp" type="image/webp" />
            <img
              className="brand-link__logo"
              src="/branding/hilalone-logo-standard-96.png"
              alt="Logo resmi HILALONE"
              width={40}
              height={40}
            />
          </picture>
          <span className="brand-link__text">
            <span className="brand-link__name">{siteConfig.appName}</span>
            <span className="brand-link__sub">Automated Hilal Image Processing</span>
          </span>
        </a>

        <nav aria-label="Navigasi utama">
          <ul className="nav-links">
            {NAV_ITEMS.map((item) => (
              <li key={item.id}>
                <a
                  href={item.href}
                  className={activeId === item.id ? "is-active" : undefined}
                  aria-current={activeId === item.id ? "location" : undefined}
                >
                  {item.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>

        <div className="navbar__actions">
          <a href="#unduh" className="btn btn--primary btn--sm nav-cta-desktop">
            <Download size={16} aria-hidden="true" />
            <span>Unduh HILALONE</span>
          </a>
          <button
            type="button"
            className="menu-toggle"
            aria-label={menuOpen ? "Tutup menu navigasi" : "Buka menu navigasi"}
            aria-expanded={menuOpen}
            aria-controls="mobile-navigation-drawer"
            onClick={() => setMenuOpen((prev) => !prev)}
          >
            {menuOpen ? <X size={20} aria-hidden="true" /> : <Menu size={20} aria-hidden="true" />}
          </button>
        </div>
      </div>

      {menuOpen ? (
        <nav
          id="mobile-navigation-drawer"
          className="mobile-drawer"
          aria-label="Menu navigasi seluler"
        >
          {NAV_ITEMS.map((item) => (
            <a
              key={item.id}
              href={item.href}
              className={activeId === item.id ? "is-active" : undefined}
              onClick={() => setMenuOpen(false)}
            >
              {item.label}
            </a>
          ))}
          <a href="#faq" onClick={() => setMenuOpen(false)}>
            FAQ
          </a>
          <a
            href="#unduh"
            className="btn btn--primary"
            style={{ marginTop: "0.75rem" }}
            onClick={() => setMenuOpen(false)}
          >
            <Download size={18} aria-hidden="true" />
            <span>Unduh HILALONE v{siteConfig.version}</span>
          </a>
        </nav>
      ) : null}
    </header>
  );
}
