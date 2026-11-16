/** Parse CLI arguments, never evaluate shell expansions or commands. */
export function parseArguments(text: string): string[] {
  const args: string[] = [];
  let value = "",
    quote = "",
    started = false;
  for (let i = 0; i < text.length; i++) {
    const char = text[i];
    if (
      char === "\\" &&
      quote !== "'" &&
      i + 1 < text.length &&
      (text[i + 1] === '"' ||
        text[i + 1] === "'" ||
        text[i + 1] === "\\" ||
        /\s/.test(text[i + 1]))
    ) {
      value += text[++i];
      started = true;
    } else if (quote) {
      if (char === quote) quote = "";
      else value += char;
    } else if (char === '"' || char === "'") {
      quote = char;
      started = true;
    } else if (/\s/.test(char)) {
      if (started) {
        args.push(value);
        value = "";
        started = false;
      }
    } else {
      value += char;
      started = true;
    }
  }
  if (quote) throw new Error("Close the quoted argument.");
  if (started) args.push(value);
  return args;
}
export function quoteArguments(args: string[]): string {
  return args
    .map((arg) => (/^[\w./:=@-]+$/.test(arg) ? arg : JSON.stringify(arg)))
    .join(" ");
}
