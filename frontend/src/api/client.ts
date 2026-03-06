const API_BASE = "/api";

async function fetchApi<T>(path: string, options?: RequestInit): Promise<T> {
  const url = path.startsWith("/") ? path : `${API_BASE}/${path}`;
  const res = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error((err as { detail?: string }).detail ?? "Ошибка запроса");
  }
  return res.json();
}

export async function listGames(params: {
  result?: string;
  opening_name?: string;
  eco_code?: string;
  played_after?: string;
  played_before?: string;
  offset?: number;
  limit?: number;
} = {}): Promise<import("./types").GameListItem[]> {
  const q = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v != null && v !== "") q.set(k, String(v));
  });
  const query = q.toString();
  return fetchApi(`games${query ? `?${query}` : ""}`);
}

export async function getGame(gameId: string): Promise<import("./types").GameRead> {
  return fetchApi(`games/${gameId}`);
}

export async function getAnalysis(
  gameId: string
): Promise<import("./types").GameAnalysisRead> {
  return fetchApi(`games/${gameId}/analysis`);
}

export async function getAnalysisStatus(
  gameId: string
): Promise<import("./types").AnalysisStatusRead> {
  return fetchApi(`games/${gameId}/analysis/status`);
}

export async function streamMoveCommentary(
  gameId: string,
  moveIndex: number,
  onChunk?: (chunk: string) => void,
  signal?: AbortSignal
): Promise<string> {
  const res = await fetch(
    `${API_BASE}/games/${gameId}/analysis/moves/${moveIndex}/commentary/stream`,
    {
      headers: { Accept: "text/event-stream" },
      signal,
    }
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error((err as { detail?: string }).detail ?? "Не удалось получить поток комментария");
  }

  if (!res.body) return "";

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let fullText = "";
  let eventData: string[] = [];

  const flushEvent = () => {
    if (eventData.length === 0) return;
    const chunk = eventData.join("\n");
    fullText += chunk;
    onChunk?.(chunk);
    eventData = [];
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const rawLine of lines) {
      const line = rawLine.trimEnd();
      if (line.startsWith("data:")) {
        eventData.push(line.startsWith("data: ") ? line.slice(6) : "");
        continue;
      }
      if (line === "") flushEvent();
    }
  }

  const tail = buffer.trimEnd();
  if (tail.startsWith("data:")) {
    eventData.push(tail.startsWith("data: ") ? tail.slice(6) : "");
  }
  flushEvent();
  return fullText.trim();
}

export async function uploadPgn(
  file: File,
  playerColor?: "white" | "black"
): Promise<import("./types").GameRead[]> {
  const form = new FormData();
  form.append("file", file);
  if (playerColor) form.append("player_color", playerColor);

  const res = await fetch(`${API_BASE}/games/upload`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error((err as { detail?: string }).detail ?? "Не удалось загрузить файл");
  }
  return res.json();
}

export async function importPgnText(
  pgnText: string,
  playerColor?: "white" | "black"
): Promise<import("./types").GameRead[]> {
  return fetchApi("games/import", {
    method: "POST",
    body: JSON.stringify({
      pgn_text: pgnText,
      player_color: playerColor ?? null,
    }),
  });
}

export async function listReports(params?: {
  period_type?: string;
  offset?: number;
  limit?: number;
}): Promise<import("./types").ReportRead[]> {
  const query = params
    ? new URLSearchParams(
        Object.fromEntries(
          Object.entries(params).filter(
            ([, v]) => v != null && v !== ""
          ) as [string, string][]
        )
      ).toString()
    : "";
  return fetchApi(`reports${query ? `?${query}` : ""}`);
}

export async function getReport(
  reportId: string
): Promise<import("./types").ReportRead> {
  return fetchApi(`reports/${reportId}`);
}

export async function createReport(body: {
  period_start: string;
  period_end: string;
  period_type: string;
}): Promise<import("./types").ReportRead> {
  const res = await fetch(`/api/reports`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error((err as { detail?: string }).detail ?? "Не удалось создать отчет");
  }
  return res.json();
}
