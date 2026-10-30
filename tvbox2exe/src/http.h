#ifndef TVBOX_HTTP_H
#define TVBOX_HTTP_H

/* Fetch URL, return malloc'd UTF-8 body (NUL-terminated) or NULL on failure.
 * Caller frees. Handles gzip transparently? No — server sends plain unless
 * Accept-Encoding requested; we never request it. */
char *http_get(const char *url);

#endif
