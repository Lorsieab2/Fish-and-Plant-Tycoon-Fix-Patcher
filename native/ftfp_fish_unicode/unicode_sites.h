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

/* ---- names and text (../common/unicode_names.h, ../common/unicode_text.h) */

/* 0x40B970: the text box's setText: push esi; mov esi, ecx; mov eax, [esi+0x30] */
#define SITE_SET_TEXT_VA 0x0040B970u
#define SITE_SET_TEXT_LEN 6
static const unsigned char SITE_SET_TEXT_EXPECT[SITE_SET_TEXT_LEN] = {0x56, 0x8B, 0xF1, 0x8B, 0x46, 0x30};

/* 0x40BC90: the box's getText(dst, size): mov eax, [ecx+0x10]; mov ecx, [eax+0x30] */
#define SITE_GET_TEXT_VA 0x0040BC90u
#define SITE_GET_TEXT_LEN 6
static const unsigned char SITE_GET_TEXT_EXPECT[SITE_GET_TEXT_LEN] = {0x8B, 0x41, 0x10, 0x8B, 0x48, 0x30};

/* 0x40BC30: the box's setLimit(fixed, limit): mov ecx, [ecx+0x10]; jmp 0x40B8B0 */
#define SITE_SET_LIMIT_VA 0x0040BC30u
#define SITE_SET_LIMIT_LEN 8
static const unsigned char SITE_SET_LIMIT_EXPECT[SITE_SET_LIMIT_LEN] = {0x8B, 0x49, 0x10, 0xE9, 0x78, 0xFC, 0xFF, 0xFF};

/* 0x40B7A3: the box measures its text: call 0x4023D0 */
#define SITE_BOX_WIDTH_VA 0x0040B7A3u
#define SITE_BOX_WIDTH_LEN 5
static const unsigned char SITE_BOX_WIDTH_EXPECT[SITE_BOX_WIDTH_LEN] = {0xE8, 0x28, 0x6C, 0xFF, 0xFF};

/* 0x40B7ED: je 0x40B807, past the box's cut of its own text while too wide (made jmp) */
#define SITE_BOX_CUT_VA 0x0040B7EDu
#define SITE_BOX_CUT_LEN 2
static const unsigned char SITE_BOX_CUT_EXPECT[SITE_BOX_CUT_LEN] = {0x74, 0x18};

/* 0x40B829: the box draws its text: call 0x408B80 */
#define SITE_BOX_DRAW_VA 0x0040B829u
#define SITE_BOX_DRAW_LEN 5
static const unsigned char SITE_BOX_DRAW_EXPECT[SITE_BOX_DRAW_LEN] = {0xE8, 0x52, 0xD3, 0xFF, 0xFF};

/* 0x4087E0: the text draw: sub esp, 0x34; mov eax, [esp+0x48] */
#define SITE_DRAW_VA 0x004087E0u
#define SITE_DRAW_LEN 7
static const unsigned char SITE_DRAW_EXPECT[SITE_DRAW_LEN] = {0x83, 0xEC, 0x34, 0x8B, 0x44, 0x24, 0x48};

/* 0x4023D0: the text measure: sub esp, 0x10; push ebp; mov ebp, [ecx+4] */
#define SITE_WIDTH_VA 0x004023D0u
#define SITE_WIDTH_LEN 7
static const unsigned char SITE_WIDTH_EXPECT[SITE_WIDTH_LEN] = {0x83, 0xEC, 0x10, 0x55, 0x8B, 0x69, 0x04};

/* 0x40BFF9: the text box's character path: cmp byte [ecx+0x2f], 0; push ebx; push esi */
#define SITE_BOX_CHAR_VA 0x0040BFF9u
#define SITE_BOX_CHAR_LEN 6
static const unsigned char SITE_BOX_CHAR_EXPECT[SITE_BOX_CHAR_LEN] = {0x80, 0x79, 0x2F, 0x00, 0x53, 0x56};

#endif
