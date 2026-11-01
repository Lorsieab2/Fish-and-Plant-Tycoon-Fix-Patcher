/* unicode_draw.h -- "Unicode Text.dll", both games: how text is drawn and measured once a
   player's name has been put in (unicode_text.h). While the DLL draws the game's bytes, the
   game's own draw and measure do it (game_draw, game_width: unicode_hooks.h). */
#ifndef FTFP_UNICODE_DRAW_H
#define FTFP_UNICODE_DRAW_H


static void draw_text(void *graphics, const char *text, int x, int y, unsigned int colour, void *font) {
    game_draw(graphics, text, x, y, colour, font);
}

static int text_width(void *font, const char *text, float scale) {
    return game_width(font, text, scale);
}

static int measure(void *font, const char *text, float scale) {
    return text_width(font, text, scale);
}

#endif
