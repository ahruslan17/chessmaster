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
  accuracy_white: number | null;
  accuracy_black: number | null;
  status: string;
  created_at: string;
  moves: MoveAnalysisRead[];
}

export interface AnalysisStatusRead {
  game_id: string;
  status: "pending" | "in_progress" | "done" | "failed";
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
  game_ids: string[] | null;
  created_at: string;
}
