export function displayChar(character) {
  return character && !["?", "??", ""].includes(character) ? character : null;
}
