"""
Nginx 统计路由
提供访问量、错误率、攻击检测等统计数据
"""
from typing import Optional, Dict, List
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import re
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user, User
from app.config import get_config
from app.utils.nginx_versions import get_active_version
from app.routers.logs import (
    _resolve_access_log_path,
    _resolve_error_log_path,
    parse_log_date,
    read_log_file
)

router = APIRouter(prefix="/api/statistics", tags=["statistics"])

# 攻击特征关键词（可以后续扩展）
ATTACK_PATTERNS = [
    r'(union.*select)',
    r'(select.*from)',
    r'(insert.*into)',
    r'(delete.*from)',
    r'(update.*set)',
    r'(drop.*table)',
    r'(exec.*\(\))',
    r'(script.*>)',
    r'(javascript:)',
    r'(<iframe)',
    r'(\.\.\/)',
    r'(\.\.\\\\)',
    r'(\.\.\/\.\.\/)',
    r'(eval\()',
    r'(base64_decode)',
    r'(phpinfo)',
    r'(system\(\))',
    r'(cmd=)',
    r'(passwd)',
    r'(shadow)',
    r'(\.bashrc)',
    r'(\.ssh)',
    r'(sqlmap)',
    r'(nmap)',
    r'(nikto)',
]


def parse_access_log_line(line: str) -> Optional[Dict]:
    """
    解析 Nginx 访问日志行
    
    标准格式: IP - - [date] "method path protocol" status size "referer" "user-agent"
    示例: 127.0.0.1 - - [27/Nov/2025:00:27:04 +0800] "GET / HTTP/1.1" 200 579 "-" "Mozilla/5.0..."
    """
    # Nginx 访问日志正则表达式
    pattern = r'^(\S+) - - \[([^\]]+)\] "(\S+) (\S+) ([^"]+)" (\d+) (\S+) "([^"]*)" "([^"]*)"'
    match = re.match(pattern, line)
    
    if not match:
        return None
    
    try:
        ip = match.group(1)
        date_str = match.group(2)
        method = match.group(3)
        path = match.group(4)
        protocol = match.group(5)
        status = int(match.group(6))
        size = match.group(7)
        referer = match.group(8)
        user_agent = match.group(9)
        
        # 解析日期
        try:
            # 格式: 27/Nov/2025:00:27:04 +0800
            date_part = date_str.split()[0]  # 27/Nov/2025:00:27:04
            log_date = datetime.strptime(date_part, '%d/%b/%Y:%H:%M:%S')
        except:
            log_date = None
        
        return {
            'ip': ip,
            'date': log_date,
            'method': method,
            'path': path,
            'protocol': protocol,
            'status': status,
            'size': size,
            'referer': referer,
            'user_agent': user_agent,
            'raw': line
        }
    except:
        return None


def detect_attack(log_entry: Dict) -> List[str]:
    """检测可能的攻击特征"""
    attacks = []
    path = log_entry.get('path', '').lower()
    user_agent = log_entry.get('user_agent', '').lower()
    referer = log_entry.get('referer', '').lower()
    
    # 检查状态码（4xx和5xx可能表示攻击尝试）
    status = log_entry.get('status', 0)
    if status >= 400 and status < 500:
        # 403可能是目录遍历等攻击
        if status == 403:
            attacks.append('可疑访问被拒绝')
        # 404可能是扫描探测
        elif status == 404 and ('/admin' in path or '/wp-admin' in path or '/phpmyadmin' in path):
            attacks.append('目录扫描探测')
    
    # 检查路径中的攻击模式
    text_to_check = path + ' ' + user_agent + ' ' + referer
    for pattern in ATTACK_PATTERNS:
        if re.search(pattern, text_to_check, re.IGNORECASE):
            attacks.append(f'检测到攻击模式: {pattern}')
    
    return attacks


def analyze_logs(time_range_hours: int = 24) -> Dict:
    """分析日志并返回统计数据"""
    access_log_path = _resolve_access_log_path()
    error_log_path = _resolve_error_log_path()
    
    # 计算时间范围
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=time_range_hours)
    
    # 读取访问日志
    access_log_file = Path(access_log_path)
    all_lines = []
    # 如果日志文件存在，尝试读取；不存在或读取失败时返回空统计数据，不报错
    if access_log_file.exists():
        try:
            with open(access_log_file, 'r', encoding='utf-8', errors='ignore') as f:
                all_lines = f.readlines()
        except Exception:
            # 读取失败时返回空统计数据，不报错
            pass
    
    # 解析日志
    log_entries = []
    ip_stats: Dict[str, int] = defaultdict(int)
    status_stats: Dict[int, int] = defaultdict(int)
    path_stats: Dict[str, int] = defaultdict(int)
    method_stats: Dict[str, int] = defaultdict(int)
    # 通用时间桶统计（根据 time_range_hours 决定粒度）
    bucket_stats: Dict[str, int] = defaultdict(int)
    attack_count = 0
    attack_details = []
    
    for line in all_lines:
        entry = parse_access_log_line(line.strip())
        if not entry or not entry.get('date'):
            continue
        
        # 过滤时间范围
        if entry['date'] < start_time:
            continue
        
        log_entries.append(entry)
        
        # 统计IP访问
        ip_stats[entry['ip']] += 1
        
        # 统计状态码
        status = entry['status']
        status_stats[status] += 1
        
        # 统计路径
        path_stats[entry['path']] += 1
        
        # 统计HTTP方法
        method_stats[entry['method']] += 1
        
        # 按时间桶统计
        # - 当 time_range_hours <= 1 小时时，按 5 分钟粒度统计
        # - 当 time_range_hours >= 7 天（168 小时）时，按天统计
        # - 其他情况（例如 24 小时）按小时统计
        dt = entry['date']
        if time_range_hours <= 1:
            # 5 分钟对齐：00,05,10,...,55
            rounded_minute = (dt.minute // 5) * 5
            bucket_dt = dt.replace(minute=rounded_minute, second=0, microsecond=0)
            bucket_key = bucket_dt.strftime('%Y-%m-%d %H:%M')
        elif time_range_hours >= 24 * 7:
            # 按天聚合
            bucket_key = dt.strftime('%Y-%m-%d')
        else:
            # 按小时聚合
            bucket_key = dt.strftime('%Y-%m-%d %H:00')

        bucket_stats[bucket_key] += 1
        
        # 检测攻击
        attacks = detect_attack(entry)
        if attacks:
            attack_count += 1
            attack_details.append({
                'time': entry['date'].isoformat(),
                'ip': entry['ip'],
                'path': entry['path'],
                'status': status,
                'attacks': attacks
            })
    
    total_requests = len(log_entries)
    error_requests = sum(count for status, count in status_stats.items() if status >= 400)
    success_requests = sum(count for status, count in status_stats.items() if 200 <= status < 300)
    
    # 计算错误率
    error_rate = (error_requests / total_requests * 100) if total_requests > 0 else 0
    
    # 获取访问量前10的IP
    top_ips = sorted(ip_stats.items(), key=lambda x: x[1], reverse=True)[:10]
    
    # 获取访问量前10的路径
    top_paths = sorted(path_stats.items(), key=lambda x: x[1], reverse=True)[:10]
    
    # 按时间排序统计数据
    sorted_buckets = sorted(bucket_stats.items())
    bucket_labels = [item[0] for item in sorted_buckets]
    bucket_counts = [item[1] for item in sorted_buckets]
    
    # 读取错误日志统计
    error_log_count = 0
    if Path(error_log_path).exists():
        try:
            with open(error_log_path, 'r', encoding='utf-8', errors='ignore') as f:
                error_lines = f.readlines()
                # 统计最近时间范围内的错误日志
                for line in error_lines:
                    log_date = parse_log_date(line)
                    if log_date and log_date >= start_time:
                        error_log_count += 1
        except:
            pass
    
    return {
        "success": True,
        "time_range_hours": time_range_hours,
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "summary": {
            "total_requests": total_requests,
            "success_requests": success_requests,
            "error_requests": error_requests,
            "error_rate": round(error_rate, 2),
            "attack_count": attack_count,
            "error_log_count": error_log_count
        },
        "status_distribution": dict(status_stats),
        "method_distribution": dict(method_stats),
        "top_ips": [{"ip": ip, "count": count} for ip, count in top_ips],
        "top_paths": [{"path": path, "count": count} for path, count in top_paths],
        # 为了兼容前端，仍然沿用 hourly_trend 字段名称，
        # 其中 hours 为时间桶标签（可能是 5 分钟 / 小时 / 天）
        "hourly_trend": {
            "hours": bucket_labels,
            "counts": bucket_counts,
        },
        "attacks": attack_details[:50]  # 最多返回50条攻击记录
    }


@router.get("/overview", summary="获取统计概览")
async def get_statistics_overview(
    hours: int = Query(24, ge=1, le=168, description="统计时间范围（小时），最多168小时（7天）"),
    current_user: User = Depends(get_current_user)
):
    """获取 Nginx 统计概览数据"""
    try:
        result = analyze_logs(time_range_hours=hours)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取统计数据失败: {str(e)}"
        )


@router.get("/realtime", summary="获取实时统计数据")
async def get_realtime_statistics(
    current_user: User = Depends(get_current_user)
):
    """获取最近1小时的实时统计数据"""
    try:
        result = analyze_logs(time_range_hours=1)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取实时统计数据失败: {str(e)}"
        )

