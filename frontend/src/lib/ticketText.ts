// Match Python 3.12 str.strip(): Unicode White_Space plus U+001C–U+001F.
// JavaScript trim() also removes BOM (U+FEFF), which Python deliberately retains.
function isPythonWhitespace(character: string) {
  const code = character.charCodeAt(0);
  return /\p{White_Space}/u.test(character) || (code >= 0x1c && code <= 0x1f);
}

export function trimTicketText(text: string) {
  let start = 0;
  let end = text.length;
  while (start < end && isPythonWhitespace(text[start])) start += 1;
  while (end > start && isPythonWhitespace(text[end - 1])) end -= 1;
  return text.slice(start, end);
}

// Python len(str) counts code points, while JavaScript string.length counts UTF-16 units.
export const ticketLength = (text: string) => Array.from(trimTicketText(text)).length;
