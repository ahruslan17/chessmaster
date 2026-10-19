/** SSE data parser. Preserve payload whitespace; remove only the optional single space. */
export function createSseParser(onData: (data: string) => void) {
  let buffer = "";
  let data: string[] = [];

  const dispatch = () => {
    if (data.length > 0) onData(data.join("\n"));
    data = [];
  };
  const line = (value: string) => {
    if (value === "") {
      dispatch();
    } else if (value === "data") {
      data.push("");
    } else if (value.startsWith("data:")) {
      const payload = value.slice(5);
      data.push(payload.startsWith(" ") ? payload.slice(1) : payload);
    }
  };
  return {
    push(chunk: string) {
      buffer += chunk;
      let index = 0;
      let start = 0;
      while (index < buffer.length) {
        if (buffer[index] !== "\r" && buffer[index] !== "\n") {
          index += 1;
          continue;
        }
        // A CR may be the first half of CRLF split across network chunks.
        if (buffer[index] === "\r" && index === buffer.length - 1) break;
        line(buffer.slice(start, index));
        index += buffer[index] === "\r" && buffer[index + 1] === "\n" ? 2 : 1;
        start = index;
      }
      buffer = buffer.slice(start);
    },
    finish() {
      if (buffer.endsWith("\r")) buffer = buffer.slice(0, -1);
      if (buffer) line(buffer);
      buffer = "";
      dispatch();
    },
  };
}
