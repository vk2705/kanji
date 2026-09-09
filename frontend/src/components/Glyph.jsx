import { displayChar } from "../utils";
import { resolveImageUrl } from "../api";

// The one place that decides what a kanji/primitive *looks* like, shared by the
// result card, the detail header and the decomposition part chips (all three had
// their own copy of this before).
//
// A picture wins over the character when there is one. That is the opposite of the
// original rule ("character, or a picture if there isn't one"), and the reason is
// that image_url is now set for two different situations:
//
//   - a user-invented primitive that has no Unicode glyph at all (character is
//     null or a "?" placeholder) — the original case, unaffected;
//   - a primitive whose codepoint is real but unrenderable, like 𭕄 (owl crown,
//     CJK Ext G) or 𢦏 (harvest festival, Ext B). Here `character` is present and
//     correct, and displaying it is exactly what shows the reader an empty box.
//     The backend attaches a rendered PNG for these (make_primitive_images.py),
//     and it only ever does so deliberately — so if a picture exists, it is
//     because the glyph alone was judged not good enough.
export default function Glyph({ character, imageUrl, keyword, id, imgClassName }) {
  if (imageUrl) {
    return <img className={imgClassName} src={resolveImageUrl(imageUrl)} alt={keyword || id} />;
  }
  return <>{displayChar(character) ?? "·"}</>;
}
