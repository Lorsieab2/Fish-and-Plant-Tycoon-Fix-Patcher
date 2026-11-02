/* Every place "Unicode Text.dll" (Plant Tycoon) writes in the game, with its stock bytes
   (checked before anything is written; all or none). */
#ifndef FTFP_PLANT_UNICODE_SITES_H
#define FTFP_PLANT_UNICODE_SITES_H

/* 0x40439B: cmp eax, 1; jne 0x404467 -- SDL_TEXTINPUT's "one byte only" */
#define SITE_INPUT_VA 0x0040439Bu
#define SITE_INPUT_LEN 9
static const unsigned char SITE_INPUT_EXPECT[SITE_INPUT_LEN] = {0x83, 0xF8, 0x01, 0x0F, 0x85, 0xC3, 0x00, 0x00, 0x00};

/* PTfontsmall's set-up: push table 0x47A550; push name 0x4673D0 (0x402300's arguments) */
#define SITE_FONT_VA 0x00412D9Fu
#define SITE_FONT_LEN 10
static const unsigned char SITE_FONT_EXPECT[SITE_FONT_LEN] = {0x68, 0x50, 0xA5, 0x47, 0x00, 0x68, 0xD0, 0x73, 0x46, 0x00};

/* ---- names and text (../common/unicode_names.h, ../common/unicode_text.h) */

/* 0x40C380: the text box's setText: push esi; mov esi, ecx; mov eax, [esi+0x30] */
#define SITE_SET_TEXT_VA 0x0040C380u
#define SITE_SET_TEXT_LEN 6
static const unsigned char SITE_SET_TEXT_EXPECT[SITE_SET_TEXT_LEN] = {0x56, 0x8B, 0xF1, 0x8B, 0x46, 0x30};

/* 0x40C740: the box's getText(dst, size): mov eax, [ecx+0x10]; mov ecx, [eax+0x30] */
#define SITE_GET_TEXT_VA 0x0040C740u
#define SITE_GET_TEXT_LEN 6
static const unsigned char SITE_GET_TEXT_EXPECT[SITE_GET_TEXT_LEN] = {0x8B, 0x41, 0x10, 0x8B, 0x48, 0x30};

/* 0x40C6E0: the box's setLimit(fixed, limit): mov ecx, [ecx+0x10]; jmp 0x40C2C0 */
#define SITE_SET_LIMIT_VA 0x0040C6E0u
#define SITE_SET_LIMIT_LEN 8
static const unsigned char SITE_SET_LIMIT_EXPECT[SITE_SET_LIMIT_LEN] = {0x8B, 0x49, 0x10, 0xE9, 0xD8, 0xFB, 0xFF, 0xFF};

/* 0x40C1B3: the box measures its text: call 0x402380 */
#define SITE_BOX_WIDTH_VA 0x0040C1B3u
#define SITE_BOX_WIDTH_LEN 5
static const unsigned char SITE_BOX_WIDTH_EXPECT[SITE_BOX_WIDTH_LEN] = {0xE8, 0xC8, 0x61, 0xFF, 0xFF};

/* 0x40C1FD: je 0x40C217, past the box's cut of its own text while too wide (made jmp) */
#define SITE_BOX_CUT_VA 0x0040C1FDu
#define SITE_BOX_CUT_LEN 2
static const unsigned char SITE_BOX_CUT_EXPECT[SITE_BOX_CUT_LEN] = {0x74, 0x18};

/* 0x40C239: the box draws its text: call 0x4092A0 */
#define SITE_BOX_DRAW_VA 0x0040C239u
#define SITE_BOX_DRAW_LEN 5
static const unsigned char SITE_BOX_DRAW_EXPECT[SITE_BOX_DRAW_LEN] = {0xE8, 0x62, 0xD0, 0xFF, 0xFF};

/* 0x408E20: the text draw: sub esp, 0x44; mov eax, [esp+0x58] */
#define SITE_DRAW_VA 0x00408E20u
#define SITE_DRAW_LEN 7
static const unsigned char SITE_DRAW_EXPECT[SITE_DRAW_LEN] = {0x83, 0xEC, 0x44, 0x8B, 0x44, 0x24, 0x58};

/* 0x402380: the text measure: sub esp, 0x10; push ebp; mov ebp, [ecx+4] */
#define SITE_WIDTH_VA 0x00402380u
#define SITE_WIDTH_LEN 7
static const unsigned char SITE_WIDTH_EXPECT[SITE_WIDTH_LEN] = {0x83, 0xEC, 0x10, 0x55, 0x8B, 0x69, 0x04};

/* 0x40CAC9: the text box's character path: cmp byte [ecx+0x2f], 0; push ebx; push esi */
#define SITE_BOX_CHAR_VA 0x0040CAC9u
#define SITE_BOX_CHAR_LEN 6
static const unsigned char SITE_BOX_CHAR_EXPECT[SITE_BOX_CHAR_LEN] = {0x80, 0x79, 0x2F, 0x00, 0x53, 0x56};

/* 0x40C280: the focused box's caret blink reads the time: call 0x402060 (made a call to stub_caret_tick, which notes the box with typing focus, empty or not;
   Copy and Paste in Text Boxes) */
#define SITE_CARET_TICK_VA 0x0040C280u
#define SITE_CARET_TICK_LEN 5
static const unsigned char SITE_CARET_TICK_EXPECT[SITE_CARET_TICK_LEN] = {0xE8, 0xDB, 0x5D, 0xFF, 0xFF};

#endif
