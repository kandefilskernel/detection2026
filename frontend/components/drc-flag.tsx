/** Drapeau de la République démocratique du Congo (proportions 4:3), en SVG. */
function starPoints(cx: number, cy: number, R: number, r: number) {
  return Array.from({ length: 10 }, (_, i) => {
    const a = -Math.PI / 2 + (i * Math.PI) / 5;
    const d = i % 2 ? r : R;
    return `${(cx + d * Math.cos(a)).toFixed(1)},${(cy + d * Math.sin(a)).toFixed(1)}`;
  }).join(" ");
}

export function DrcFlag({ className, title = "Drapeau de la République démocratique du Congo" }: { className?: string; title?: string }) {
  return (
    <svg viewBox="0 0 800 600" className={className} role="img" aria-label={title}>
      <title>{title}</title>
      <defs><clipPath id="drc-flag-clip"><rect width="800" height="600" /></clipPath></defs>
      <g clipPath="url(#drc-flag-clip)">
        <rect width="800" height="600" fill="#007FFF" />
        {/* Bande rouge bordée de jaune, du coin inférieur gauche au coin supérieur droit */}
        <line x1="-40" y1="630" x2="840" y2="-30" stroke="#F7D618" strokeWidth="190" />
        <line x1="-40" y1="630" x2="840" y2="-30" stroke="#CE1021" strokeWidth="128" />
        <polygon points={starPoints(135, 125, 95, 36)} fill="#F7D618" />
      </g>
    </svg>
  );
}
