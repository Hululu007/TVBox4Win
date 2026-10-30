#include "http.h"
#include <windows.h>
#include <winhttp.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#pragma comment(lib, "winhttp.lib")

static int parse_url(const char *url, wchar_t *host, size_t hostlen,
                     wchar_t *path, size_t pathlen, int *https, INTERNET_PORT *port)
{
    URL_COMPONENTS uc = {0};
    wchar_t wurl[2048];
    MultiByteToWideChar(CP_UTF8, 0, url, -1, wurl, 2048);
    uc.dwStructSize = sizeof(uc);
    uc.lpszHostName = host;  uc.dwHostNameLength = hostlen;
    uc.lpszUrlPath  = path;  uc.dwUrlPathLength  = pathlen;
    if (!WinHttpCrackUrl(wurl, 0, 0, &uc)) return 0;
    *https = (uc.nScheme == INTERNET_SCHEME_HTTPS);
    *port  = uc.nPort;
    return 1;
}

char *http_get(const char *url)
{
    wchar_t host[512], path[1024];
    int https; INTERNET_PORT port;
    if (!parse_url(url, host, 512, path, 1024, &https, &port)) return NULL;

    char *result = NULL;
    HINTERNET sess = WinHttpOpen(L"tvbox2exe/1.0", WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
                                 WINHTTP_NO_PROXY_NAME, WINHTTP_NO_PROXY_BYPASS, 0);
    if (!sess) return NULL;
    HINTERNET conn = WinHttpConnect(sess, host, port, 0);
    if (conn) {
        HINTERNET req = WinHttpOpenRequest(conn, L"GET", path,
            https ? L"HTTP/1.1" : NULL,
            WINHTTP_NO_REFERER, WINHTTP_DEFAULT_ACCEPT_TYPES,
            https ? WINHTTP_FLAG_SECURE : 0);
        if (req) {
            /* Many TVBox source APIs are plain http with cert problems on https */
            DWORD flags = SECURITY_FLAG_IGNORE_UNKNOWN_CA |
                          SECURITY_FLAG_IGNORE_CERT_CN_INVALID |
                          SECURITY_FLAG_IGNORE_CERT_DATE_INVALID |
                          SECURITY_FLAG_IGNORE_CERT_WRONG_USAGE;
            WinHttpSetOption(req, WINHTTP_OPTION_SECURITY_FLAGS, &flags, sizeof(flags));
            wchar_t hdr[] = L"User-Agent: okhttp/4.9.3\r\n";
            if (WinHttpSendRequest(req, hdr, -1L, WINHTTP_NO_REQUEST_DATA, 0, 0, 0) &&
                WinHttpReceiveResponse(req, NULL)) {
                DWORD status = 0, sz = sizeof(status);
                WinHttpQueryHeaders(req, WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER,
                                    WINHTTP_HEADER_NAME_BY_INDEX, &status, &sz, WINHTTP_NO_HEADER_INDEX);
                if (status == 200) {
                    size_t cap = 65536, len = 0;
                    result = malloc(cap);
                    DWORD read = 0;
                    for (;;) {
                        if (len + 65536 > cap) { cap *= 2; result = realloc(result, cap); }
                        if (!WinHttpReadData(req, result + len, 65536, &read) || read == 0) break;
                        len += read;
                    }
                    result[len] = 0;
                }
            }
            WinHttpCloseHandle(req);
        }
        WinHttpCloseHandle(conn);
    }
    WinHttpCloseHandle(sess);
    return result;
}
