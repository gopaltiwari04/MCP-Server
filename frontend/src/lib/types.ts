export type PersonaId = "alice" | "bob";

export interface Persona {
  id: PersonaId;
  user_id: string;
  display_name: string;
  role_title: string;
  scopes: string[];
}

export interface DataMetadata {
  source: string;
  data_timestamp: string;
  fetched_at: string;
  is_stale: boolean;
  staleness_threshold_seconds: number;
  currency: string | null;
  units: string | null;
  calendar_type: "TRADING_DAYS" | "CALENDAR_DAYS";
  cache_hit: boolean;
  request_id: string;
}

export interface ErrorDetail {
  code: string;
  message: string;
  retryable: boolean;
  details: Record<string, unknown>;
}

export interface ResponseEnvelope<T = Record<string, unknown>> {
  status: string;
  data: T | null;
  metadata: DataMetadata;
  warnings: string[];
  error: ErrorDetail | null;
}

export interface ProgressUpdate {
  progress: number;
  total: number | null;
  message: string | null;
}

export interface ToolTrace<T = Record<string, unknown>> {
  tool_name: string;
  arguments: Record<string, unknown>;
  is_error: boolean;
  elapsed_ms: number;
  request_id: string;
  progress_updates: ProgressUpdate[];
  envelope: ResponseEnvelope<T> | null;
  markdown: string | null;
}

export interface ProvenanceCitation {
  tool: string;
  status: string;
  source: string;
  data_timestamp: string;
  cache_hit: boolean;
  is_stale: boolean;
  request_id: string;
}

export interface ChatResponse {
  mode: string;
  model?: string;
  assistant_markdown: string;
  tool_traces: ToolTrace[];
  provenance: ProvenanceCitation[];
}

export interface HealthResponse {
  orchestrator: string;
  llm_mode: string;
  mcp_gateway: {
    reachable: boolean;
    status_code: number;
    details: {
      status?: string;
      circuit_breaker?: {
        state: string;
        consecutive_failures: number;
      };
      cache?: {
        entries: number;
        hits: number;
        misses: number;
        coalesced_hits: number;
      };
      backend?: {
        reachable: boolean;
      };
    };
  };
}

export interface McpCatalog {
  request_id: string;
  persona: string;
  tools: Array<{
    name: string;
    description: string;
    input_schema: Record<string, unknown>;
  }>;
  resources: Array<{
    uri: string;
    name: string;
    title: string | null;
    description: string | null;
    mime_type: string | null;
  }>;
  resource_templates: Array<{
    uri_template: string;
    name: string;
    title: string | null;
    description: string | null;
    mime_type: string | null;
  }>;
  prompts: Array<{
    name: string;
    title: string | null;
    description: string | null;
    arguments: Array<{ name: string; description: string | null; required: boolean }>;
  }>;
}

export interface QuoteData {
  symbol: string;
  last_price: number;
  bid: number | null;
  ask: number | null;
  spread_bps: number | null;
  open: number | null;
  high: number | null;
  low: number | null;
  previous_close: number | null;
  change: number | null;
  change_pct: number | null;
  volume: number | null;
  market_cap: number | null;
  currency: string;
  exchange: string;
  is_delayed: boolean;
}

export interface OHLCVBar {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface HistoricalPricesData {
  symbol: string;
  interval: string;
  bars_count: number;
  currency: string;
  summary_stats: {
    period_high: number;
    period_low: number;
    vwap: number | null;
    mean_close: number;
    std_close: number;
    total_volume: number;
    trading_days_count: number;
  } | null;
  bars: OHLCVBar[];
}

export interface IndicatorSnapshot {
  indicator: string;
  latest: Record<string, number | null>;
  regime_signal: string | null;
  crossover_timestamp: string | null;
}

export interface TechnicalIndicatorsData {
  symbol: string;
  latest_price: number | null;
  overall_regime: string | null;
  snapshots: IndicatorSnapshot[];
}

export interface CompareInstrumentsData {
  symbols: string[];
  period: string;
  aligned_start_date: string | null;
  aligned_end_date: string | null;
  aligned_observations: number;
  dropped_dates_by_symbol: Record<string, string[]>;
  comparison_table: Array<{
    symbol: string;
    cumulative_return_pct: number | null;
    annualized_volatility_pct: number | null;
    sharpe_ratio: number | null;
    max_drawdown_pct: number | null;
    pe_ratio: number | null;
    ev_to_ebitda: number | null;
  }>;
  correlation_matrix: Record<string, Record<string, number>>;
  rankings: Array<{ metric: string; ordered_symbols: string[] }>;
}

export interface PortfolioAnalysisData {
  portfolio_id: string;
  portfolio_name: string | null;
  base_currency: string;
  nav: number;
  cash_balance: number;
  cash_weight_pct: number;
  portfolio_beta: number | null;
  annualized_volatility_pct: number | null;
  sharpe_ratio: number | null;
  sortino_ratio: number | null;
  historical_var_pct: number | null;
  parametric_var_pct: number | null;
  expected_shortfall_cvar_pct: number | null;
  historical_var_amount: number | null;
  positions: Array<{
    symbol: string;
    name: string | null;
    sector: string | null;
    quantity: number;
    market_price: number;
    market_value: number;
    weight_pct: number;
    unrealized_pnl: number | null;
    unrealized_pnl_pct: number | null;
  }>;
  sector_allocation: Array<{ category: string; weight_pct: number; market_value: number }>;
  top_concentration_contributors: Array<{ symbol: string; weight_pct: number }>;
}

export interface RebalanceSimulationData {
  portfolio_id: string;
  estimated_cash_impact: number;
  beta_shift: number | null;
  var_delta_pct: number | null;
  pre_trade: {
    cash_balance: number;
    portfolio_beta: number | null;
    var_95_pct: number | null;
  };
  post_trade: {
    cash_balance: number;
    portfolio_beta: number | null;
    var_95_pct: number | null;
    position_weights_pct: Record<string, number>;
  };
  constraint_violations: Array<{
    rule_code: string;
    severity: "WARNING" | "BREACH";
    message: string;
    symbol: string | null;
  }>;
}
