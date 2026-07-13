import api from "./index";

export interface StatisticsSummary {
  total_requests: number;
  success_requests: number;
  error_requests: number;
  error_rate: number;
  attack_count: number;
  error_log_count: number;
}

export interface TrendData {
  hours: string[];
  counts: number[];
}

export interface TopIp { ip: string; count: number }
export interface TopPath { path: string; count: number }
export interface AttackRecord {
  time: string;
  ip: string;
  path: string;
  status: number;
  attacks: string[];
}

interface StatisticsResponseBase {
  success: boolean;
  message?: string;
  time_range_hours?: number;
}

export interface SummaryResponse extends StatisticsResponseBase { summary?: StatisticsSummary }
export interface TrendResponse extends StatisticsResponseBase { hourly_trend: TrendData }
export interface TopIpsResponse extends StatisticsResponseBase { top_ips: TopIp[] }
export interface TopPathsResponse extends StatisticsResponseBase { top_paths: TopPath[] }
export interface StatusDistributionResponse extends StatisticsResponseBase { status_distribution: Record<string, number> }
export interface AttacksResponse extends StatisticsResponseBase { attacks: AttackRecord[]; total_count: number }
export interface AnalysisTaskStatusResponse extends StatisticsResponseBase {
  status?: 'unknown' | 'ready' | 'not_ready' | 'analyzing' | 'failed';
  is_running?: boolean;
  last_analysis_time?: string | null;
  analyzed_lines?: number;
  last_start_time?: string | null;
  last_end_time?: string | null;
  last_error?: string | null;
  last_success?: boolean | null;
  last_trigger?: string | null;
  last_duration_seconds?: number;
  running_duration_seconds?: number | null;
}

export const statisticsApi = {
  // 获取基础统计数据（轻量级）
  getSummary(hours = 24) {
    return api.get<SummaryResponse>("/statistics/summary", {
      params: { hours },
    });
  },

  // 获取时间趋势数据
  getTrend(hours = 24) {
    return api.get<TrendResponse>("/statistics/trend", {
      params: { hours },
    });
  },

  // 获取Top IPs
  getTopIPs(hours = 24, limit = 10) {
    return api.get<TopIpsResponse>("/statistics/top-ips", {
      params: { hours, limit },
    });
  },

  // 获取Top Paths
  getTopPaths(hours = 24, limit = 10) {
    return api.get<TopPathsResponse>("/statistics/top-paths", {
      params: { hours, limit },
    });
  },

  // 获取状态码分布
  getStatusDistribution(hours = 24) {
    return api.get<StatusDistributionResponse>("/statistics/status-distribution", {
      params: { hours },
    });
  },

  // 获取攻击检测记录（延迟加载）
  getAttacks(hours = 24, limit = 50) {
    return api.get<AttacksResponse>("/statistics/attacks", {
      params: { hours, limit },
    });
  },

  // 手动触发统计分析
  // 一次分析会同时分析5分钟、1小时、1天三个时间范围，所以不需要 hours 参数
  // full = true 表示全量分析（适合手动从页面触发），false 为默认模式（后续可扩展为增量）
  triggerAnalyze(full = true) {
    return api.post<StatisticsResponseBase>("/statistics/analyze", null, {
      params: { full },
    });
  },

  // 获取分析任务状态（独立接口，不依赖时间范围）
  getTaskStatus() {
    return api.get<AnalysisTaskStatusResponse>("/statistics/task-status");
  },
};
