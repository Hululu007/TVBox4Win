#ifndef TVBOX_H
#define TVBOX_H

#include <stddef.h>

typedef struct {
    char *name;   /* site name, UTF-8 */
    char *api;    /* base api url */
    int   type;   /* 0=json, 1=xml(unsupported->skipped), 3=spider(unsupported) */
} Site;

typedef struct {
    Site *items;
    int   count;
} SiteList;

typedef struct {
    char *id;
    char *name;
} VodItem;

typedef struct {
    VodItem *items;
    int      count;
} VodList;

/* Parse TVBox config JSON text (the "sites" array). Skips spider sites. */
int tv_sites_parse(SiteList *out, const char *config_json);

/* Build URL: api + "?ac=..." style request. Returns malloc'd string. */
char *tv_site_url(const Site *s, const char *query);

/* Parse catalog classes from ?ac=class response -> VodList (id=type_id, name) */
int tv_classes_parse(VodList *out, const char *json);

/* Parse video list from ?ac=detail&t=xx response -> VodList (id=vod_id) */
int tv_vods_parse(VodList *out, const char *json);

/* Parse detail: find vod_play_url of first play-from, first episode.
 * out_url = first playable URL; out_eps = episode list ("name" each). */
int tv_detail_parse(const char *json, char **out_url, VodList *out_eps);

void tv_vodlist_free(VodList *l);
void tv_sitelist_free(SiteList *l);
char *tv_strdup(const char *s);
void tv_strfree(char *s);

#endif
