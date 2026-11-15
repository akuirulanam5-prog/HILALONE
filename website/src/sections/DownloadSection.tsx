import { Clock, Download, ExternalLink, ShieldAlert } from "lucide-react";
import { SectionHeader } from "../components/SectionHeader";
import { siteConfig } from "../data/siteConfig";

export function DownloadSection() {
  const ready = siteConfig.downloadAvailable && siteConfig.downloadUrl !== null;

  return (
    <section id="unduh" className="section">
      <div className="container">
        <div className="download-card">
          <div className="download-card__grid">
            <div>
              <SectionHeader
                eyebrow="Distribusi Aplikasi Desktop"
                title={`${siteConfig.appName} v${siteConfig.version} — Windows Desktop`}
                subtitle="Halaman distribusi resmi installer Windows. Tautan hanya diaktifkan setelah aset rilis resmi dan checksum SHA-256 diterbitkan."
                icon={<Download size={14} aria-hidden="true" />}
              />

              {ready && siteConfig.downloadUrl ? (
                <div>
                  <div className="download-actions">
                    <a
                      href={siteConfig.downloadUrl}
                      className="btn btn--primary"
                      download={siteConfig.installerFilename}
                      rel="noopener noreferrer"
                    >
                      <Download size={18} aria-hidden="true" />
                      <span>Unduh {siteConfig.installerFilename}</span>
                    </a>

                    {siteConfig.repoIsPublic ? (
                      <a
                        href={siteConfig.releasePageUrl ?? siteConfig.githubUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="btn btn--secondary"
                      >
                        <span>Lihat GitHub Releases</span>
                        <ExternalLink size={16} aria-hidden="true" />
                      </a>
                    ) : null}
                  </div>
                </div>
              ) : (
                <div>
                  <div
                    className="callout-box"
                    style={{ marginTop: 0, marginBottom: "1.15rem" }}
                    role="status"
                  >
                    <div style={{ display: "flex", alignItems: "flex-start", gap: "0.6rem" }}>
                      <Clock size={18} style={{ flexShrink: 0, marginTop: 2 }} aria-hidden="true" />
                      <div>
                        <strong>Installer HILALONE v{siteConfig.version} sedang dipersiapkan.</strong>{" "}
                        Build executable <code>ONE-DIR</code> telah selesai diuji di lingkungan
                        pengembangan terisolasi; paket installer resmi (
                        <code>{siteConfig.installerFilename}</code>) akan ditautkan di sini setelah
                        diterbitkan di GitHub Releases.
                      </div>
                    </div>
                  </div>

                  <div className="download-actions">
                    <button
                      type="button"
                      className="btn btn--primary"
                      disabled
                      aria-disabled="true"
                      title="Installer resmi belum tersedia untuk diunduh"
                    >
                      <Download size={18} aria-hidden="true" />
                      <span>Unduh Installer (Belum Tersedia)</span>
                    </button>

                    {siteConfig.repoIsPublic ? (
                      <a
                        href={siteConfig.githubUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="btn btn--secondary"
                      >
                        <span>Lihat Repositori GitHub</span>
                        <ExternalLink size={16} aria-hidden="true" />
                      </a>
                    ) : null}
                  </div>
                </div>
              )}
            </div>

            <div>
              <div className="download-meta-grid">
                <div>
                  <div className="meta-kv__k">Versi Rilis</div>
                  <div className="meta-kv__v">
                    v{siteConfig.version} ({siteConfig.mvpStage})
                  </div>
                </div>
                <div>
                  <div className="meta-kv__k">Nama Installer</div>
                  <div className="meta-kv__v" style={{ fontFamily: "var(--font-mono)" }}>
                    {siteConfig.installerFilename}
                  </div>
                </div>
                <div>
                  <div className="meta-kv__k">Ukuran Berkas</div>
                  <div className="meta-kv__v">
                    {siteConfig.fileSize ?? "Menunggu kompilasi installer"}
                  </div>
                </div>
                <div>
                  <div className="meta-kv__k">Tanggal Rilis</div>
                  <div className="meta-kv__v">
                    {siteConfig.releaseDate ?? "Menunggu penerbitan resmi"}
                  </div>
                </div>
                <div style={{ gridColumn: "1 / -1" }}>
                  <div className="meta-kv__k">Dukungan Windows</div>
                  <div className="meta-kv__v">{siteConfig.supportedWindows}</div>
                </div>
                <div style={{ gridColumn: "1 / -1" }}>
                  <div className="meta-kv__k">SHA-256 Checksum</div>
                  <div
                    className="meta-kv__v"
                    style={{ fontFamily: "var(--font-mono)", fontSize: "0.78rem" }}
                  >
                    {siteConfig.sha256 ?? "Akan diterbitkan bersama berkas installer resmi"}
                  </div>
                </div>
              </div>

              <div
                style={{
                  marginTop: "0.85rem",
                  display: "flex",
                  alignItems: "flex-start",
                  gap: "0.5rem",
                  fontSize: "0.82rem",
                  color: "var(--text-secondary)",
                }}
              >
                <ShieldAlert size={16} style={{ flexShrink: 0, marginTop: 2 }} aria-hidden="true" />
                <span>
                  Catatan rilis: instalasi default diarahkan ke profil pengguna (per-user) tanpa
                  menghapus konfigurasi atau log pengguna saat pencopotan aplikasi.
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
