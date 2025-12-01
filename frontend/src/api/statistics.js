import api from "./index";

export const statisticsApi = {
  // 获取统计概览（完整数据，兼容旧接口）
  getOverview(hours = 24) {
    return api.get("/statistics/overview", {
      params: { hours },
    });
  },

  // 获取实时统计数据
  getRealtime() {
    return api.get("/statistics/realtime");
  },

  // 获取基础统计数据（轻量级）
  getSummary(hours = 24) {
    return api.get("/statistics/summary", {
      params: { hours },
    });
  },

  // 获取时间趋势数据
  getTrend(hours = 24) {
    return api.get("/statistics/trend", {
      params: { hours },
    });
  },

  // 获取Top IPs
  getTopIPs(hours = 24, limit = 10) {
    return api.get("/statistics/top-ips", {
      params: { hours, limit },
    });
  },

  // 获取Top Paths
  getTopPaths(hours = 24, limit = 10) {
    return api.get("/statistics/top-paths", {
      params: { hours, limit },
    });
  },

  // 获取状态码分布
  getStatusDistribution(hours = 24) {
    return api.get("/statistics/status-distribution", {
      params: { hours },
    });
  },

  // 获取攻击检测记录（延迟加载）
  getAttacks(hours = 24, limit = 50) {
    return api.get("/statistics/attacks", {
      params: { hours, limit },
    });
  },

  // 手动触发统计分析
  // full = true 表示全量分析（适合手动从页面触发），false 为默认模式（后续可扩展为增量）
  triggerAnalyze(hours = 24, full = true) {
    return api.post("/statistics/analyze", null, {
      params: { hours, full },
    });
  },
};
