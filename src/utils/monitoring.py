import time
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import logging
from pathlib import Path
import psutil

class ScrapingMetrics:
    """Tracks and reports scraping metrics and performance."""
    
    def __init__(self, metrics_file: str = "scraping_metrics.json"):
        self.logger = logging.getLogger(__name__)
        self.metrics_file = metrics_file
        self.session_start = time.time()
        self.session_metrics = {
            'session_id': datetime.now().strftime('%Y%m%d_%H%M%S'),
            'start_time': datetime.now().isoformat(),
            'end_time': None,
            'duration_seconds': 0,
            'questions_scraped': 0,
            'questions_by_type': {'multiple_choice': 0, 'true_false': 0, 'sound': 0},
            'pages_visited': 0,
            'media_downloaded': {'images': 0, 'audio': 0},
            'errors': [],
            'warnings': [],
            'performance': {
                'avg_questions_per_minute': 0,
                'avg_page_load_time': 0,
                'peak_memory_mb': 0,
                'cpu_usage_percent': 0
            },
            'rate_limiting': {
                'total_delays': 0,
                'total_delay_time': 0
            },
            'validation': {
                'valid_questions': 0,
                'invalid_questions': 0,
                'warnings': 0
            }
        }
        self.page_load_times = []
        self.error_counts = {}
        self.last_cpu_check = time.time()
    
    def record_question_scraped(self, question_type: str) -> None:
        """Record a successfully scraped question."""
        self.session_metrics['questions_scraped'] += 1
        self.session_metrics['questions_by_type'][question_type] += 1
        self._update_performance_metrics()
    
    def record_page_visited(self, load_time: float = 0) -> None:
        """Record a page visit with load time."""
        self.session_metrics['pages_visited'] += 1
        if load_time > 0:
            self.page_load_times.append(load_time)
            if self.page_load_times:
                self.session_metrics['performance']['avg_page_load_time'] = sum(self.page_load_times) / len(self.page_load_times)
    
    def record_media_download(self, media_type: str) -> None:
        """Record a media file download."""
        if media_type in self.session_metrics['media_downloaded']:
            self.session_metrics['media_downloaded'][media_type] += 1
    
    def record_error(self, error_type: str, error_message: str) -> None:
        """Record an error occurrence."""
        error_entry = {
            'timestamp': datetime.now().isoformat(),
            'type': error_type,
            'message': error_message
        }
        self.session_metrics['errors'].append(error_entry)
        self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1
    
    def record_warning(self, warning_type: str, warning_message: str) -> None:
        """Record a warning."""
        warning_entry = {
            'timestamp': datetime.now().isoformat(),
            'type': warning_type,
            'message': warning_message
        }
        self.session_metrics['warnings'].append(warning_entry)
    
    def record_rate_limit_delay(self, delay_seconds: float) -> None:
        """Record a rate limiting delay."""
        self.session_metrics['rate_limiting']['total_delays'] += 1
        self.session_metrics['rate_limiting']['total_delay_time'] += delay_seconds
    
    def record_validation_results(self, valid: int, invalid: int, warnings: int) -> None:
        """Record validation results."""
        self.session_metrics['validation']['valid_questions'] += valid
        self.session_metrics['validation']['invalid_questions'] += invalid
        self.session_metrics['validation']['warnings'] += warnings
    
    def _update_performance_metrics(self) -> None:
        """Update performance metrics."""
        current_time = time.time()
        duration = current_time - self.session_start
        
        # Update duration and questions per minute
        self.session_metrics['duration_seconds'] = duration
        if duration > 0:
            self.session_metrics['performance']['avg_questions_per_minute'] = (
                self.session_metrics['questions_scraped'] / duration * 60
            )
        
        # Update memory usage (check every 10 seconds to avoid overhead)
        if current_time - self.last_cpu_check > 10:
            try:
                process = psutil.Process()
                memory_mb = process.memory_info().rss / 1024 / 1024
                cpu_percent = process.cpu_percent()
                
                self.session_metrics['performance']['peak_memory_mb'] = max(
                    self.session_metrics['performance']['peak_memory_mb'], memory_mb
                )
                self.session_metrics['performance']['cpu_usage_percent'] = cpu_percent
                self.last_cpu_check = current_time
            except:
                pass  # Ignore psutil errors
    
    def finalize_session(self) -> None:
        """Finalize the current session metrics."""
        self.session_metrics['end_time'] = datetime.now().isoformat()
        self.session_metrics['duration_seconds'] = time.time() - self.session_start
        self._save_metrics()
    
    def _save_metrics(self) -> None:
        """Save metrics to file."""
        try:
            # Load existing metrics
            all_metrics = []
            if os.path.exists(self.metrics_file):
                with open(self.metrics_file, 'r') as f:
                    all_metrics = json.load(f)
            
            # Append current session
            all_metrics.append(self.session_metrics)
            
            # Keep only last 100 sessions
            if len(all_metrics) > 100:
                all_metrics = all_metrics[-100:]
            
            # Save updated metrics
            with open(self.metrics_file, 'w') as f:
                json.dump(all_metrics, f, indent=2)
                
            self.logger.info(f"Metrics saved to {self.metrics_file}")
            
        except Exception as e:
            self.logger.error(f"Error saving metrics: {e}")
    
    def get_current_stats(self) -> Dict[str, Any]:
        """Get current session statistics."""
        self._update_performance_metrics()
        return self.session_metrics.copy()
    
    def print_progress_report(self) -> None:
        """Print a progress report to console."""
        stats = self.get_current_stats()
        duration = stats['duration_seconds']
        
        print(f"\n📊 Scraping Progress Report")
        print(f"Duration: {duration/60:.1f} minutes")
        print(f"Questions scraped: {stats['questions_scraped']}")
        print(f"  Multiple Choice: {stats['questions_by_type']['multiple_choice']}")
        print(f"  True/False: {stats['questions_by_type']['true_false']}")
        print(f"  Sound: {stats['questions_by_type']['sound']}")
        print(f"Pages visited: {stats['pages_visited']}")
        print(f"Rate: {stats['performance']['avg_questions_per_minute']:.1f} questions/min")
        print(f"Memory: {stats['performance']['peak_memory_mb']:.1f} MB")
        
        if stats['errors']:
            print(f"Errors: {len(stats['errors'])}")
        if stats['warnings']:
            print(f"Warnings: {len(stats['warnings'])}")

def load_historical_metrics(metrics_file: str = "scraping_metrics.json") -> List[Dict[str, Any]]:
    """Load historical metrics from file."""
    try:
        if os.path.exists(metrics_file):
            with open(metrics_file, 'r') as f:
                return json.load(f)
    except Exception as e:
        logging.getLogger(__name__).error(f"Error loading metrics: {e}")
    return []

def generate_performance_report(metrics_file: str = "scraping_metrics.json") -> str:
    """Generate a comprehensive performance report."""
    metrics = load_historical_metrics(metrics_file)
    
    if not metrics:
        return "No historical metrics available."
    
    # Calculate aggregated statistics
    total_sessions = len(metrics)
    recent_sessions = [m for m in metrics if datetime.fromisoformat(m['start_time']) > datetime.now() - timedelta(days=7)]
    
    total_questions = sum(m['questions_scraped'] for m in metrics)
    total_duration = sum(m['duration_seconds'] for m in metrics)
    avg_rate = sum(m['performance']['avg_questions_per_minute'] for m in metrics) / total_sessions
    
    # Error analysis
    all_errors = []
    for session in metrics:
        all_errors.extend(session['errors'])
    
    error_types = {}
    for error in all_errors:
        error_type = error['type']
        error_types[error_type] = error_types.get(error_type, 0) + 1
    
    # Generate report
    report = f"""
📈 SCRAPER PERFORMANCE REPORT
{'='*50}

📊 Overall Statistics:
  Total Sessions: {total_sessions}
  Total Questions Scraped: {total_questions:,}
  Total Runtime: {total_duration/3600:.1f} hours
  Average Rate: {avg_rate:.1f} questions/minute

📅 Recent Performance (Last 7 days):
  Sessions: {len(recent_sessions)}
  Questions: {sum(m['questions_scraped'] for m in recent_sessions):,}
  Average Session Duration: {sum(m['duration_seconds'] for m in recent_sessions)/len(recent_sessions)/60:.1f} minutes

📋 Question Type Distribution:
  Multiple Choice: {sum(m['questions_by_type']['multiple_choice'] for m in metrics):,}
  True/False: {sum(m['questions_by_type']['true_false'] for m in metrics):,}
  Sound: {sum(m['questions_by_type']['sound'] for m in metrics):,}

⚠️ Error Analysis:
  Total Errors: {len(all_errors)}"""

    if error_types:
        report += "\n  Most Common Errors:"
        sorted_errors = sorted(error_types.items(), key=lambda x: x[1], reverse=True)
        for error_type, count in sorted_errors[:5]:
            report += f"\n    {error_type}: {count}"
    
    # Performance trends
    if len(metrics) >= 2:
        recent_rate = sum(m['performance']['avg_questions_per_minute'] for m in metrics[-5:]) / min(5, len(metrics))
        older_rate = sum(m['performance']['avg_questions_per_minute'] for m in metrics[:-5]) / max(1, len(metrics)-5)
        trend = "📈 Improving" if recent_rate > older_rate else "📉 Declining" if recent_rate < older_rate else "➡️ Stable"
        
        report += f"""

📈 Performance Trend: {trend}
  Recent Average: {recent_rate:.1f} questions/minute
  Historical Average: {older_rate:.1f} questions/minute
"""
    
    return report

class HealthMonitor:
    """Monitors scraper health and system resources."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.start_time = time.time()
        self.health_checks = []
    
    def check_system_health(self) -> Dict[str, Any]:
        """Perform comprehensive system health check."""
        health_status = {
            'timestamp': datetime.now().isoformat(),
            'overall_status': 'healthy',
            'checks': {}
        }
        
        # Memory check
        try:
            memory = psutil.virtual_memory()
            memory_status = {
                'available_gb': memory.available / (1024**3),
                'used_percent': memory.percent,
                'status': 'ok' if memory.percent < 80 else 'warning' if memory.percent < 90 else 'critical'
            }
            health_status['checks']['memory'] = memory_status
        except:
            health_status['checks']['memory'] = {'status': 'unknown', 'error': 'Unable to check memory'}
        
        # Disk check
        try:
            disk = psutil.disk_usage('.')
            disk_status = {
                'free_gb': disk.free / (1024**3),
                'used_percent': (disk.used / disk.total) * 100,
                'status': 'ok' if disk.free > 1024**3 else 'warning' if disk.free > 512**2 else 'critical'
            }
            health_status['checks']['disk'] = disk_status
        except:
            health_status['checks']['disk'] = {'status': 'unknown', 'error': 'Unable to check disk'}
        
        # CPU check
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_status = {
                'usage_percent': cpu_percent,
                'status': 'ok' if cpu_percent < 70 else 'warning' if cpu_percent < 90 else 'critical'
            }
            health_status['checks']['cpu'] = cpu_status
        except:
            health_status['checks']['cpu'] = {'status': 'unknown', 'error': 'Unable to check CPU'}
        
        # Network check
        try:
            import requests
            response = requests.get('https://www.funtrivia.com', timeout=10)
            network_status = {
                'funtrivia_accessible': response.status_code == 200,
                'response_time_ms': response.elapsed.total_seconds() * 1000,
                'status': 'ok' if response.status_code == 200 else 'critical'
            }
            health_status['checks']['network'] = network_status
        except:
            health_status['checks']['network'] = {'status': 'critical', 'error': 'Unable to reach FunTrivia'}
        
        # Directory check
        required_dirs = ['output', 'assets/images', 'assets/audio', 'logs']
        dir_status = {'missing_directories': [], 'status': 'ok'}
        for directory in required_dirs:
            if not os.path.exists(directory):
                dir_status['missing_directories'].append(directory)
                dir_status['status'] = 'warning'
        health_status['checks']['directories'] = dir_status
        
        # Determine overall status
        statuses = [check.get('status', 'unknown') for check in health_status['checks'].values()]
        if 'critical' in statuses:
            health_status['overall_status'] = 'critical'
        elif 'warning' in statuses:
            health_status['overall_status'] = 'warning'
        
        self.health_checks.append(health_status)
        return health_status
    
    def get_health_summary(self) -> str:
        """Get a formatted health summary."""
        if not self.health_checks:
            return "No health checks performed yet."
        
        latest = self.health_checks[-1]
        summary = f"🏥 System Health: {latest['overall_status'].upper()}\n"
        
        for check_name, check_data in latest['checks'].items():
            status_emoji = {
                'ok': '✅',
                'warning': '⚠️',
                'critical': '❌',
                'unknown': '❓'
            }
            emoji = status_emoji.get(check_data['status'], '❓')
            summary += f"{emoji} {check_name.title()}: {check_data['status']}\n"
            
            if check_data['status'] != 'ok' and 'error' in check_data:
                summary += f"   Error: {check_data['error']}\n"
        
        return summary

def create_monitoring_dashboard(metrics_file: str = "scraping_metrics.json") -> str:
    """Create a simple text-based monitoring dashboard."""
    dashboard = f"""
🎛️  FUNTRIVIA SCRAPER DASHBOARD
{'='*60}
Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

"""
    
    # Add performance report
    dashboard += generate_performance_report(metrics_file)
    
    # Add health check
    health_monitor = HealthMonitor()
    health_status = health_monitor.check_system_health()
    dashboard += f"\n\n{health_monitor.get_health_summary()}"
    
    return dashboard 