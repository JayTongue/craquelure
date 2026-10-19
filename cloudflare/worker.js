// Route: craquelure.net/*
// Render redirects any plain-http request to https, so fetch http visitors' requests over https instead
// and tell the app the visitor's real scheme. Flask then serves curl as-is and redirects browsers.
export default {
  async fetch(request) {
    const url = new URL(request.url);
    if (url.protocol !== 'http:') return fetch(request);

    url.protocol = 'https:';
    const headers = new Headers(request.headers);
    headers.set('X-Visitor-Scheme', 'http');
    return fetch(url, { method: request.method, headers, body: request.body, redirect: 'manual' });
  },
};
