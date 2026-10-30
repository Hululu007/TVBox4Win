#include "tvbox.h"
#include "cJSON.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <stdint.h>

char *tv_strdup(const char *s)
{
    if (!s) return NULL;
    size_t n = strlen(s) + 1;
    char *p = malloc(n);
    memcpy(p, s, n);
    return p;
}

void tv_strfree(char *s) { free(s); }

void tv_vodlist_free(VodList *l)
{
    if (!l || !l->items) return;
    for (int i = 0; i < l->count; i++) {
        free(l->items[i].id);
        free(l->items[i].name);
    }
    free(l->items);
    l->items = NULL; l->count = 0;
}

void tv_sitelist_free(SiteList *l)
{
    if (!l || !l->items) return;
    for (int i = 0; i < l->count; i++) {
        free(l->items[i].name);
        free(l->items[i].api);
    }
    free(l->items);
    l->items = NULL; l->count = 0;
}

static cJSON *get_root_object(const char *json)
{
    cJSON *root = cJSON_Parse(json);
    return root; /* caller checks object/array */
}

int tv_sites_parse(SiteList *out, const char *config_json)
{
    memset(out, 0, sizeof(*out));
    cJSON *root = get_root_object(config_json);
    if (!root) return 0;
    cJSON *sites = cJSON_GetObjectItem(root, "sites");
    if (!cJSON_IsArray(sites)) { cJSON_Delete(root); return 0; }

    int cap = cJSON_GetArraySize(sites);
    out->items = calloc(cap ? cap : 1, sizeof(Site));
    cJSON *it;
    cJSON_ArrayForEach(it, sites) {
        cJSON *jtype = cJSON_GetObjectItem(it, "type");
        int type = cJSON_IsNumber(jtype) ? jtype->valueint : -1;
        if (type != 0 && type != 1) continue; /* spider (3) & others unsupported */
        cJSON *jname = cJSON_GetObjectItem(it, "name");
        cJSON *japi  = cJSON_GetObjectItem(it, "api");
        cJSON *jact  = cJSON_GetObjectItem(it, "active");
        if (!cJSON_IsString(jname) || !cJSON_IsString(japi)) continue;
        if (jact && cJSON_IsBool(jact) && !cJSON_IsTrue(jact)) continue;
        Site *s = &out->items[out->count++];
        s->name = tv_strdup(jname->valuestring);
        s->api  = tv_strdup(japi->valuestring);
        s->type = type;
    }
    cJSON_Delete(root);
    return out->count;
}

char *tv_site_url(const Site *s, const char *query)
{
    size_t n = strlen(s->api) + strlen(query) + 2;
    char *url = malloc(n);
    snprintf(url, n, "%s?%s", s->api, query);
    return url;
}

/* detail responses: {"list":[{...}]}, class responses: {"class":[{type_id,type_name}]} */
int tv_classes_parse(VodList *out, const char *json)
{
    memset(out, 0, sizeof(*out));
    cJSON *root = get_root_object(json);
    if (!root) return 0;
    cJSON *arr = cJSON_IsObject(root) ? cJSON_GetObjectItem(root, "class") : root;
    if (!cJSON_IsArray(arr)) { cJSON_Delete(root); return 0; }
    int n = cJSON_GetArraySize(arr);
    out->items = calloc(n ? n : 1, sizeof(VodItem));
    cJSON *it;
    cJSON_ArrayForEach(it, arr) {
        cJSON *jid = cJSON_GetObjectItem(it, "type_id");
        cJSON *jnm = cJSON_GetObjectItem(it, "type_name");
        if (!cJSON_IsString(jnm)) continue;
        VodItem *v = &out->items[out->count++];
        v->name = cJSON_IsString(jid) ? tv_strdup(jid->valuestring)
                                       : NULL;
        char idbuf[32];
        if (cJSON_IsNumber(jid)) snprintf(idbuf, sizeof idbuf, "%d", jid->valueint);
        v->id   = tv_strdup(cJSON_IsString(jid) ? jid->valuestring : idbuf);
        v->name = tv_strdup(jnm->valuestring);
    }
    cJSON_Delete(root);
    return out->count;
}

static void fill_vods(VodList *out, cJSON *arr)
{
    int n = cJSON_GetArraySize(arr);
    out->items = calloc(n ? n : 1, sizeof(VodItem));
    cJSON *it;
    cJSON_ArrayForEach(it, arr) {
        cJSON *jid = cJSON_GetObjectItem(it, "vod_id");
        cJSON *jnm = cJSON_GetObjectItem(it, "vod_name");
        if (!cJSON_IsString(jnm)) continue;
        VodItem *v = &out->items[out->count++];
        char idbuf[32];
        if (cJSON_IsNumber(jid)) snprintf(idbuf, sizeof idbuf, "%d", jid->valueint);
        v->id   = tv_strdup(cJSON_IsString(jid) ? jid->valuestring : idbuf);
        v->name = tv_strdup(jnm->valuestring);
    }
}

int tv_vods_parse(VodList *out, const char *json)
{
    memset(out, 0, sizeof(*out));
    cJSON *root = get_root_object(json);
    if (!root) return 0;
    cJSON *arr = cJSON_IsObject(root) ? cJSON_GetObjectItem(root, "list") : root;
    if (cJSON_IsArray(arr)) fill_vods(out, arr);
    cJSON_Delete(root);
    return out->count;
}

int tv_detail_parse(const char *json, char **out_url, VodList *out_eps)
{
    memset(out_eps, 0, sizeof(*out_eps));
    *out_url = NULL;
    cJSON *root = get_root_object(json);
    if (!root) return 0;
    cJSON *list = cJSON_IsObject(root) ? cJSON_GetObjectItem(root, "list") : root;
    if (!cJSON_IsArray(list) || cJSON_GetArraySize(list) == 0) {
        cJSON_Delete(root); return 0;
    }
    cJSON *vod = cJSON_GetArrayItem(list, 0);
    cJSON *jpu = cJSON_GetObjectItem(vod, "vod_play_url");
    if (!cJSON_IsString(jpu)) { cJSON_Delete(root); return 0; }

    /* vod_play_url: "from1$ep1#ep2#ep3$$$from2$..." — take first group */
    char *dup = tv_strdup(jpu->valuestring);
    char *group = dup;
    char *dollar = strstr(group, "$$$");
    if (dollar) *dollar = 0;
    char *dollar2 = strchr(group, '$');
    if (dollar2) {
        *dollar2 = 0;
        group = dollar2 + 1;
    }
    /* group = "ep1#ep2#..." */
    int n = 1;
    for (char *p = group; *p; p++) if (*p == '#') n++;
    out_eps->items = calloc(n, sizeof(VodItem));
    char *save = NULL;
    for (char *ep = strtok_r(group, "#", &save); ep; ep = strtok_r(NULL, "#", &save)) {
        /* each ep: "name$url" */
        char *d = strchr(ep, '$');
        if (!d) continue;
        *d = 0;
        VodItem *v = &out_eps->items[out_eps->count++];
        v->name = tv_strdup(ep);
        v->id   = tv_strdup(d + 1);
        if (!*out_url) *out_url = tv_strdup(d + 1);
    }
    free(dup);
    cJSON_Delete(root);
    return out_eps->count;
}
