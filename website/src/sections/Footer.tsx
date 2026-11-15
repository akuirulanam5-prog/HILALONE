import { siteConfig } from "../data/siteConfig";

export function Footer() {
  return (
    <footer className="footer">
      <div className="container">
        <div className="footer__grid">
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.75rem" }}>
              <picture>
                <source srcSet="/branding/hilalone-logo-standard-96.webp" type="image/webp" />
                <img
                  src="/branding/hilalone-logo-standard-96.png"
                  alt="Logo HILALONE"
                  width={38}
                  height={38}
                />
              </picture>
              <div>
                <div style={{ fontWeight: 800, letterSpacing: "0.06em" }}>{siteConfig.fullTitle}</div>
                <div style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>
                  Versi {siteConfig.version} ({siteConfig.mvpStage})
                </div>
              </div>
            </div>
            <p className="card__text" style={{ maxWidth: "44ch" }}>
              Filosofi pengembangan: &ldquo;{siteConfig.philosophy}&rdquo; — pengolahan citra
              astronomi yang menjaga integritas data linear dari hulu hingga ekspor.
            </p>
          </div>

          <div>
            <h3 className="footer__heading">Navigasi Utama</h3>
            <ul className="footer__links">
              <li>
                <a href="#tentang">Tentang HILALONE</a>
              </li>
              <li>
                <a href="#fitur">Fitur Utama</a>
              </li>
              <li>
                <a href="#antarmuka">Pratinjau Antarmuka</a>
              </li>
              <li>
                <a href="#alur-kerja">Alur Kerja Pipeline</a>
              </li>
              <li>
                <a href="#roadmap">Roadmap</a>
              </li>
              <li>
                <a href="#spesifikasi">Spesifikasi Teknis</a>
              </li>
            </ul>
          </div>

          <div>
            <h3 className="footer__heading">Sumber &amp; Dokumentasi</h3>
            <ul className="footer__links">
              {siteConfig.repoIsPublic ? (
                <li>
                  <a href={siteConfig.githubUrl} target="_blank" rel="noopener noreferrer">
                    GitHub Repository
                  </a>
                </li>
              ) : null}
              {siteConfig.repoIsPublic ? (
                <li>
                  <a
                    href={`${siteConfig.githubUrl}/blob/main/BUILD_README.md`}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Dokumentasi Build &amp; Arsitektur
                  </a>
                </li>
              ) : null}
              {siteConfig.repoIsPublic && siteConfig.releasePageUrl ? (
                <li>
                  <a href={siteConfig.releasePageUrl} target="_blank" rel="noopener noreferrer">
                    Release Notes (GitHub Releases)
                  </a>
                </li>
              ) : null}
              <li>
                <a href="#unduh">Distribusi Windows v{siteConfig.version}</a>
              </li>
              <li>
                <a href="#faq">FAQ</a>
              </li>
            </ul>
          </div>
        </div>

        <div className="footer__bottom">
          <span>
            &copy; {siteConfig.copyrightYear} {siteConfig.copyrightHolder}. Seluruh hak cipta sesuai lisensi proyek.
          </span>
          <span>HILALONE — {siteConfig.tagline}</span>
        </div>
      </div>
    </footer>
  );
}
