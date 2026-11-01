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

#endif
