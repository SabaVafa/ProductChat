// Shared formatting/safety helpers (audit findings H3 + M5).

// Only http(s) URLs may be rendered into href/src — a catalog record carrying
// a javascript: URL must never become a clickable link (XSS guard).
export function safeUrl(u?: string | null): string | undefined {
  return u && /^https?:\/\//i.test(u) ? u : undefined;
}

// German price format: 1.234,56 €
const eur = new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' });
export function formatPrice(v: number): string {
  return eur.format(v);
}
