const siteBase = import.meta.env.VITE_SITE_BASE ?? "../";

export function siteHref(path = ""): string {
  return `${siteBase}${path}`;
}
