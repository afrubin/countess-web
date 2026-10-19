// The server's access token. It arrives once in the address the server prints (?token=...), is
// kept in this tab's session storage (which no other site, or other port, can read) and is taken
// out of the address bar so it is not left in history or a shared screenshot.

const KEY = 'countess-web-token'

export function takeToken(): string | null {
  const url = new URL(location.href)
  const fromUrl = url.searchParams.get('token')
  if (fromUrl) {
    sessionStorage.setItem(KEY, fromUrl)
    url.searchParams.delete('token')
    history.replaceState(null, '', url.pathname + url.search + url.hash)
  }
  return sessionStorage.getItem(KEY)
}

export function token(): string {
  return sessionStorage.getItem(KEY) ?? ''
}

export function forgetToken() {
  sessionStorage.removeItem(KEY)
}
