/* unicode_draw.h -- "Unicode Text.dll", both games: how text is drawn and measured once a
   player's name has been put in (unicode_text.h): as UTF-8, each letter from the first source
   that has it (unicode_glyphs.h), or, while the DLL draws the game's bytes (utf8_drawing 0),
   by the game's own draw and measure (game_draw, game_width: unicode_hooks.h). */
#ifndef FTFP_UNICODE_DRAW_H
#define FTFP_UNICODE_DRAW_H

#include "unicode_glyphs.h"

static void draw_text(void *graphics, const char *text, int x, int y, unsigned int colour, void *font) {
    if (utf8_drawing) unicode_draw(graphics, text, x, y, colour, font);
    else game_draw(graphics, text, x, y, colour, font);
}

static int text_width(void *font, const char *text, float scale) {
    return utf8_drawing ? unicode_width(font, text, scale) : game_width(font, text, scale);
}

static int measure(void *font, const char *text, float scale) {
    return text_width(font, text, scale);
}

#endif
