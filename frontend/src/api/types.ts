export type PlayerColor = "white" | "black";
export type EngineStatus = "pending" | "queued" | "in_progress" | "done" | "failed";

export interface AccessConfigRead {
  enabled: boolean;
}

export interface AccessStatusRead {
  active: boolean;
  expires_at: string | null;
}

export interface EngineScore {
  cp: number | null;
  mate: number | null;
  mate_winner: PlayerColor | null;
  perspective: "white";
}

export interface ReviewMoment {
  move_index: number;
  move_number: number;
  color: PlayerColor;
  fen_before: string;
  fen_after: string;
  move_san: string;
  best_move_san: string | null;
  score_before: EngineScore | null;
  score_after: EngineScore | null;
  centipawn_loss: number | null;
  classification: string | null;
  played_line: unknown;
  best_line: unknown;
  facts: unknown;
  verification: unknown;
}

export interface SideReview {
  player_color: PlayerColor;
  status: EngineStatus | "partial";
  error: string | null;
  context: { version: 1; player_color: PlayerColor; moments: ReviewMoment[] } | null;
  comments: Record<string, {
    reason: string;
    consequence: string;
    alternative: string;
    principle: string;
    limitation: string;
  }>;
  summary: string | null;
  recommendations: string[];
  attempt_id: string | null;
  task_id: string | null;
  usage: unknown;
}

export interface GameListItem {
  id: string;
  white_player: string;
  black_player: string;
  result: string;
  opening_name: string | null;
  eco_code: string | null;
  time_control: string | null;
  played_at: string | null;
  player_color: string | null;
  created_at: string;
}

export interface GameRead extends GameListItem {
  pgn_text: string;
}

export interface MoveAnalysisRead {
  id: string;
  move_number: number;
  color: string;
  move_san: string;
  best_move_san: string | null;
  eval_before: number | null;
  eval_after: number | null;
  score_before?: EngineScore | null;
  score_after?: EngineScore | null;
  played_line?: unknown;
  centipawn_loss: number | null;
  classification: string | null;
  top_moves: unknown;
  continuation_lines: unknown;
  llm_comment: string | null;
}

export interface GameAnalysisRead {
  id: string;
  game_id: string;
  summary: string | null;
  opening_assessment: string | null;
  middlegame_assessment: string | null;
  endgame_assessment: string | null;
  key_moments: unknown;
  coach_feedback: unknown;
  accuracy_white: number | null;
  accuracy_black: number | null;
  status: string;
  engine_status?: EngineStatus;
  engine_error?: string | null;
  progress_current?: number;
  progress_total?: number;
  engine_attempt_id?: string | null;
  engine_task_id?: string | null;
  heartbeat_at?: string | null;
  score_version?: number | null;
  review?: SideReview | null;
  created_at: string;
  moves: MoveAnalysisRead[];
}

export interface AnalysisStatusRead {
  game_id: string;
  status: EngineStatus;
  engine_status?: EngineStatus;
  engine_error?: string | null;
  progress_current?: number;
  progress_total?: number;
  heartbeat_at?: string | null;
  review_status?: SideReview["status"] | null;
  review_error?: string | null;
}

export interface ReportPattern {
  pattern: string;
  description: string;
  frequency?: string;
}

export interface ReportRead {
  id: string;
  period_start: string;
  period_end: string;
  period_type: string;
  recommendations: string | null;
  weakness_patterns: ReportPattern[] | null;
  strength_patterns: ReportPattern[] | null;
  coach_feedback: unknown;
  comparison_metrics: Record<string, unknown> | null;
  comparison_summary: string | null;
  game_ids: string[] | null;
  created_at: string;
}

export interface GameNoteRead {
  id: string;
  game_id: string;
  content: string | null;
  created_at: string;
  updated_at: string;
}

export interface GameNoteListItem {
  game_id: string;
  white_player: string;
  black_player: string;
  played_at: string | null;
  opening_name: string | null;
  content: string | null;
  updated_at: string;
}

export interface OpeningRead {
  id: string;
  eco_code: string;
  name: string;
  moves_san: string[];
  move_count: number;
}
