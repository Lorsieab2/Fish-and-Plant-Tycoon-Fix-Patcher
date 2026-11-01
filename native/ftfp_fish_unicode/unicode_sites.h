/* Every place "Unicode Text.dll" (Fish Tycoon) writes in the game, with its stock bytes
   (checked before anything is written; all or none). */
#ifndef FTFP_FISH_UNICODE_SITES_H
#define FTFP_FISH_UNICODE_SITES_H

/* 0x403ED4: lea ebx, [edx-0x20]; cmp ebx, 0x5e; ja 0x403f4f -- the event loop's printable test */
#define SITE_INPUT_VA 0x00403ED4u
#define SITE_INPUT_LEN 8
static const unsigned char SITE_INPUT_EXPECT[SITE_INPUT_LEN] = {0x8D, 0x5A, 0xE0, 0x83, 0xFB, 0x5E, 0x77, 0x73};

/* Each font's set-up: push table; push name (0x402350's arguments), 10 bytes. */
#define SITE_FONT_LEN 10
#define SITE_FONT_PADDINGTON_18_VA 0x0042A45Fu
#define SITE_FONT_PADDINGTON_18_LEN 10
#define SITE_FONT_PADDINGTON_18_EXPECT {0x68, 0x80, 0x85, 0x45, 0x00, 0x68, 0x94, 0xC5, 0x44, 0x00}
#define SITE_FONT_PADDINGTON_30_VA 0x0042A4CFu
#define SITE_FONT_PADDINGTON_30_LEN 10
#define SITE_FONT_PADDINGTON_30_EXPECT {0x68, 0xC8, 0x8D, 0x45, 0x00, 0x68, 0xB4, 0xC5, 0x44, 0x00}
#define SITE_FONT_TRIPLEX_16_VA 0x00410A9Fu
#define SITE_FONT_TRIPLEX_16_LEN 10
#define SITE_FONT_TRIPLEX_16_EXPECT {0x68, 0xB8, 0x44, 0x45, 0x00, 0x68, 0x90, 0x21, 0x44, 0x00}

#endif
