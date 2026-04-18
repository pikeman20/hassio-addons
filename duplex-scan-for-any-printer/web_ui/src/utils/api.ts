/**
 * Build an absolute URL for an API path (works for both axios and EventSource).
 *
 * Uses document.baseURI which automatically respects the <base> tag that
 * HA Supervisor injects when serving through ingress.
 */
export function apiUrl(path: string): string {
  return new URL(path, document.baseURI).href
}
