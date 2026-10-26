/* install_sites.h -- every write the companion makes into the game's code:
   all of them, or none.

   Same rules as the Virtual Villagers Fun Patcher's native/shared/install_sites.h
   (the owner: "I do not want any half-assed patches"):

     1. every site is checked first: committed, readable, and holding exactly
        the stock bytes the companion expects;
     2. every site is made writable -- if any VirtualProtect fails, the ones
        already unlocked get their old protection back and NOTHING is written;
     3. only then is every site written;
     4. every protection is restored, last first, and the instruction cache
        flushed.

   ftfp_install_sites() returns 1 only when every site was written, 0 when
   nothing was. The companion's stubs are compiled into its own code section
   (read/execute), so no page is ever writable and executable at once. */
#ifndef FTFP_INSTALL_SITES_H
#define FTFP_INSTALL_SITES_H

#include <windows.h>
#include <string.h>

#define FTFP_SITE_MAX_BYTES 32

typedef struct ftfp_site_write {
    unsigned int va;
    int length;
    const unsigned char *expect;
    unsigned char bytes[FTFP_SITE_MAX_BYTES];
    DWORD old;
} ftfp_site_write;

static int ftfp_site_holds(unsigned int va, const unsigned char *bytes, int length) {
    MEMORY_BASIC_INFORMATION info;
    const void *at = (const void *)(UINT_PTR)va;
    if (va == 0 || length <= 0 || bytes == NULL
        || VirtualQuery(at, &info, sizeof info) != sizeof info || info.State != MEM_COMMIT
        || (info.Protect & (PAGE_NOACCESS | PAGE_GUARD)) != 0
        || (UINT_PTR)at + (unsigned int)length > (UINT_PTR)info.BaseAddress + info.RegionSize) {
        return 0;
    }
    return memcmp(at, bytes, (size_t)length) == 0;
}

/* A `jmp` (0xE9) or `call` (0xE8) from the site to `to`, nops to `length`. */
static void ftfp_site_branch(ftfp_site_write *w, unsigned int va, int length,
                             const unsigned char *expect, unsigned char opcode, const void *to) {
    unsigned int rel = (unsigned int)((UINT_PTR)to - ((UINT_PTR)va + 5u));
    int i;
    w->va = va;
    w->length = length;
    w->expect = expect;
    w->bytes[0] = opcode;
    memcpy(w->bytes + 1, &rel, 4);
    for (i = 5; i < length && i < FTFP_SITE_MAX_BYTES; ++i) {
        w->bytes[i] = 0x90;
    }
}

/* The site's stock bytes with one 32-bit immediate or displacement replaced. */
static void ftfp_site_imm32(ftfp_site_write *w, unsigned int va, int length,
                            const unsigned char *expect, int imm_at, unsigned int value) {
    w->va = va;
    w->length = length;
    w->expect = expect;
    if (length > 0 && length <= FTFP_SITE_MAX_BYTES) {
        memcpy(w->bytes, expect, (size_t)length);
        if (imm_at >= 0 && imm_at + 4 <= length) {
            memcpy(w->bytes + imm_at, &value, 4);
        }
    }
}

/* The first site that did not hold its expected bytes (0 when none), for the install log. */
static unsigned int ftfp_failed_site = 0;

static int ftfp_install_sites(ftfp_site_write *w, int count) {
    int i, unlocked;
    if (count <= 0) {
        return 0;
    }
    for (i = 0; i < count; ++i) {
        if (w[i].length <= 0 || w[i].length > FTFP_SITE_MAX_BYTES
            || !ftfp_site_holds(w[i].va, w[i].expect, w[i].length)) {
            ftfp_failed_site = w[i].va;
            return 0;
        }
    }
    for (unlocked = 0; unlocked < count; ++unlocked) {
        if (!VirtualProtect((void *)(UINT_PTR)w[unlocked].va, (SIZE_T)w[unlocked].length,
                            PAGE_EXECUTE_READWRITE, &w[unlocked].old)) {
            while (unlocked-- > 0) {
                DWORD ignored;
                VirtualProtect((void *)(UINT_PTR)w[unlocked].va, (SIZE_T)w[unlocked].length,
                               w[unlocked].old, &ignored);
            }
            return 0;
        }
    }
    for (i = 0; i < count; ++i) {
        memcpy((void *)(UINT_PTR)w[i].va, w[i].bytes, (size_t)w[i].length);
    }
    for (i = count; i-- > 0;) {
        DWORD ignored;
        VirtualProtect((void *)(UINT_PTR)w[i].va, (SIZE_T)w[i].length, w[i].old, &ignored);
    }
    for (i = 0; i < count; ++i) {
        FlushInstructionCache(GetCurrentProcess(), (const void *)(UINT_PTR)w[i].va, (SIZE_T)w[i].length);
    }
    return 1;
}

#endif /* FTFP_INSTALL_SITES_H */
