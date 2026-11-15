import type { ReactNode } from "react";

interface SectionHeaderProps {
  readonly eyebrow: string;
  readonly title: string;
  readonly subtitle?: string;
  readonly centered?: boolean;
  readonly icon?: ReactNode;
}

export function SectionHeader({
  eyebrow,
  title,
  subtitle,
  centered = false,
  icon,
}: SectionHeaderProps) {
  return (
    <header className={`section-header${centered ? " section-header--center" : ""}`}>
      <div className="eyebrow">
        {icon}
        <span>{eyebrow}</span>
      </div>
      <h2 className="section-title">{title}</h2>
      {subtitle ? <p className="section-subtitle">{subtitle}</p> : null}
    </header>
  );
}
