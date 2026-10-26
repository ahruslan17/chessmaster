import { createSseParser } from "./sse";
import type { AccessConfigRead, AccessStatusRead, PlayerColor } from "./types";

const API_BASE = "/api";

export class ApiError extends Error {
  constructor(message: string, public status: number, public detail: unknown) {
    super(message);
  }
}

async function responseError(res: Response, fallback: string): Promise<ApiError> {
  const body = await res.json().catch(() => ({ detail: res.statusText }));
  const detail = body.detail;
  const message = typeof detail === "string" ? detail
    : detail && typeof detail.message === "string" ? detail.message
    : res.status === 409 ? "Задача уже выполняется или импорт конфликтует с существующей партией."
    : res.status === 503 ? "Сервис объяснений или очередь недоступны. Результаты сохранены; повторите позже."
    : fallback;
  return new ApiError(message, res.status, detail);
}

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
    throw await responseError(res, "Ошибка запроса");
  }
  return res.json();
}

export async function getAccessConfig(): Promise<AccessConfigRead> {
  return fetchApi("access/config");
}

export async function getAccessStatus(): Promise<AccessStatusRead> {
  return fetchApi("access/status");
}

export async function activateAccess(code: string): Promise<AccessStatusRead> {
  return fetchApi("access/activate", {
    method: "POST",
    body: JSON.stringify({ code }),
  });
}

function toQuery(params: Record<string, string | number | undefined>): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value != null && value !== "") {
      query.set(key, String(value));
    }
  }
  const encoded = query.toString();
  return encoded ? `?${encoded}` : "";
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
  return fetchApi(`games${toQuery(params)}`);
}

export async function getGame(gameId: string): Promise<import("./types").GameRead> {
  return fetchApi(`games/${gameId}`);
}

export async function getGameNote(gameId: string): Promise<import("./types").GameNoteRead> {
  return fetchApi(`games/${gameId}/note`);
}

export async function upsertGameNote(
  gameId: string,
  body: { content: string }
): Promise<import("./types").GameNoteRead> {
  return fetchApi(`games/${gameId}/note`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export async function listGameNotes(params?: {
  offset?: number;
  limit?: number;
}): Promise<import("./types").GameNoteListItem[]> {
  return fetchApi(`games/notes${toQuery(params ?? {})}`);
}

export async function getAnalysis(
  gameId: string,
  playerColor?: PlayerColor
): Promise<import("./types").GameAnalysisRead> {
  return fetchApi(`games/${gameId}/analysis${toQuery({ player_color: playerColor })}`);
}

export async function getAnalysisStatus(
  gameId: string,
  playerColor?: PlayerColor
): Promise<import("./types").AnalysisStatusRead> {
  return fetchApi(`games/${gameId}/analysis/status${toQuery({ player_color: playerColor })}`);
}

export function startAnalysis(gameId: string, recover = false, expectedAttemptId?: string | null): Promise<import("./types").AnalysisStatusRead> {
  return fetchApi(`games/${gameId}/analysis/start`, {
    method: "POST",
    body: JSON.stringify({ recover, ...(recover ? { expected_attempt_id: expectedAttemptId ?? null } : {}) }),
  });
}

export function startExplanations(gameId: string, playerColor: PlayerColor, recover = false, expectedAttemptId?: string | null, detailed = false): Promise<import("./types").AnalysisStatusRead> {
  return fetchApi(`games/${gameId}/analysis/explanations`, {
    method: "POST",
    body: JSON.stringify({ player_color: playerColor, recover, ...(recover ? { expected_attempt_id: expectedAttemptId ?? null } : {}), ...(detailed ? { detailed: true } : {}) }),
  });
}

export async function streamMoveCommentary(
  gameId: string,
  moveIndex: number,
  onChunk?: (chunk: string) => void,
  signal?: AbortSignal,
  playerColor?: PlayerColor
): Promise<string> {
  const res = await fetch(
    `${API_BASE}/games/${gameId}/analysis/moves/${moveIndex}/commentary/stream${toQuery({ player_color: playerColor })}`,
    {
      headers: { Accept: "text/event-stream" },
      signal,
    }
  );

  if (!res.ok) {
    throw await responseError(res, "Не удалось получить поток комментария");
  }

  if (!res.body) {
    return "";
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let fullText = "";
  const parser = createSseParser((chunk) => {
    fullText += chunk;
    onChunk?.(chunk);
  });

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }

    parser.push(decoder.decode(value, { stream: true }));
  }

  parser.push(decoder.decode());
  parser.finish();
  return fullText;
}

export async function uploadPgn(
  file: File,
  playerColor?: "white" | "black"
): Promise<import("./types").GameRead[]> {
  const form = new FormData();
  form.append("file", file);
  if (playerColor) {
    form.append("player_color", playerColor);
  }

  const res = await fetch(`${API_BASE}/games/upload${toQuery({ player_color: playerColor })}`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    throw await responseError(res, "Не удалось загрузить файл");
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
  period_type?: "daily" | "weekly" | "monthly";
  offset?: number;
  limit?: number;
}): Promise<import("./types").ReportRead[]> {
  return fetchApi(`reports${toQuery(params ?? {})}`);
}

export async function getReport(
  reportId: string
): Promise<import("./types").ReportRead> {
  return fetchApi(`reports/${reportId}`);
}

export async function createReport(body: {
  period_start: string;
  period_end: string;
  period_type: "daily" | "weekly" | "monthly";
}): Promise<import("./types").ReportRead> {
  return fetchApi("reports", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function listOpenings(params?: {
  q?: string;
  limit?: number;
}): Promise<import("./types").OpeningRead[]> {
  return fetchApi(`openings${toQuery(params ?? {})}`);
}
