#!/usr/bin/env python3
"""
Concurrency and Delay Control Demonstration for FunTrivia Scraper

This script demonstrates the enhanced concurrency and delay control features,
showing how different settings affect scraping performance and safety.
"""

import sys
import os
import asyncio
import time
from pathlib import Path
import json

# Add the src directory to the path
sys.path.append(str(Path(__file__).parent.parent / 'src'))

def demonstrate_configuration_options():
    """Demonstrate different configuration options for concurrency and delays."""
    
    print("🚀 CONCURRENCY AND DELAY CONTROL DEMONSTRATION")
    print("=" * 60)
    
    configurations = {
        "Ultra-Safe (Stealth Mode)": {
            "concurrency": 1,
            "delays": {"min": 5.0, "max": 10.0},
            "rate_limit": {"requests_per_minute": 10},
            "description": "Minimal detection risk, very slow",
            "use_case": "When you need to avoid any chance of detection",
            "risk": "🟢 Very Low"
        },
        "Safe (Conservative)": {
            "concurrency": 1,
            "delays": {"min": 3.0, "max": 8.0},
            "rate_limit": {"requests_per_minute": 15},
            "description": "Low detection risk, slow but steady",
            "use_case": "Long-term data collection projects",
            "risk": "🟢 Low"
        },
        "Balanced (Recommended)": {
            "concurrency": 3,
            "delays": {"min": 1.0, "max": 3.0},
            "rate_limit": {"requests_per_minute": 30},
            "description": "Good balance of speed and safety",
            "use_case": "Most general scraping tasks",
            "risk": "🟡 Medium"
        },
        "Fast (Aggressive)": {
            "concurrency": 6,
            "delays": {"min": 0.5, "max": 1.5},
            "rate_limit": {"requests_per_minute": 60},
            "description": "Higher speed, increased detection risk",
            "use_case": "Quick data collection with monitoring",
            "risk": "🟠 High"
        },
        "Maximum Speed (Dangerous)": {
            "concurrency": 10,
            "delays": {"min": 0.2, "max": 0.8},
            "rate_limit": {"requests_per_minute": 120},
            "description": "Maximum speed, high blocking risk",
            "use_case": "Testing or very urgent collection",
            "risk": "🔴 Very High"
        }
    }
    
    for name, config in configurations.items():
        print(f"\n📋 {name}")
        print("-" * 40)
        print(f"Risk Level: {config['risk']}")
        print(f"Use Case: {config['use_case']}")
        print(f"Description: {config['description']}")
        
        print(f"\nConfiguration:")
        print(f"  Concurrency: {config['concurrency']} browser(s)")
        print(f"  Delay Range: {config['delays']['min']}-{config['delays']['max']}s")
        print(f"  Rate Limit: {config['rate_limit']['requests_per_minute']} req/min")
        
        # Calculate theoretical performance
        avg_delay = (config['delays']['min'] + config['delays']['max']) / 2
        req_per_minute = config['rate_limit']['requests_per_minute']
        theoretical_speed = min(
            config['concurrency'] * (60 / avg_delay),
            req_per_minute
        )
        
        print(f"\nTheoretical Performance:")
        print(f"  ~{theoretical_speed:.1f} requests/minute")
        print(f"  ~{theoretical_speed * 60:.0f} requests/hour")
        
        # Command line example
        print(f"\nCommand Line Example:")
        print(f"  python src/main.py --concurrency {config['concurrency']} \\")
        print(f"    --min-delay {config['delays']['min']} \\")
        print(f"    --max-delay {config['delays']['max']} \\")
        print(f"    --max-questions 100")


def demonstrate_delay_calculation():
    """Demonstrate how delay calculation works."""
    
    print("\n" + "=" * 60)
    print("DELAY CALCULATION DEMONSTRATION")
    print("=" * 60)
    
    import random
    
    delay_configs = [
        {"min": 1.0, "max": 3.0, "name": "Default"},
        {"min": 0.5, "max": 1.0, "name": "Fast"},
        {"min": 3.0, "max": 8.0, "name": "Safe"},
        {"min": 5.0, "max": 10.0, "name": "Ultra-Safe"}
    ]
    
    for config in delay_configs:
        print(f"\n📊 {config['name']} Delay Profile ({config['min']}-{config['max']}s)")
        print("-" * 40)
        
        # Generate sample delays
        sample_delays = [
            random.uniform(config['min'], config['max'])
            for _ in range(10)
        ]
        
        avg_delay = sum(sample_delays) / len(sample_delays)
        min_delay = min(sample_delays)
        max_delay = max(sample_delays)
        
        print(f"Sample delays: {', '.join(f'{d:.2f}s' for d in sample_delays[:5])}...")
        print(f"Average: {avg_delay:.2f}s")
        print(f"Range: {min_delay:.2f}s - {max_delay:.2f}s")
        
        # Calculate requests per minute
        requests_per_minute = 60 / avg_delay
        print(f"Estimated rate: {requests_per_minute:.1f} requests/minute")


def demonstrate_command_line_usage():
    """Show command line usage examples."""
    
    print("\n" + "=" * 60)
    print("COMMAND LINE USAGE EXAMPLES")
    print("=" * 60)
    
    examples = [
        {
            "name": "Basic Usage (Default Settings)",
            "command": "python src/main.py --max-questions 100",
            "description": "Uses config defaults: 3 concurrent, 1-3s delays"
        },
        {
            "name": "Conservative Scraping",
            "command": "python src/main.py --max-questions 200 --concurrency 1 --min-delay 3 --max-delay 8",
            "description": "Single browser, long delays, very safe"
        },
        {
            "name": "Fast Scraping",
            "command": "python src/main.py --max-questions 500 --concurrency 6 --min-delay 0.5 --max-delay 1.5",
            "description": "Multiple browsers, short delays, faster but riskier"
        },
        {
            "name": "Balanced Approach",
            "command": "python src/main.py --max-questions 300 --concurrency 3 --min-delay 1.5 --max-delay 4",
            "description": "Good balance of speed and safety"
        },
        {
            "name": "Testing Configuration",
            "command": "python src/main.py --max-questions 10 --concurrency 1 --min-delay 0.5 --max-delay 1 --dry-run",
            "description": "Quick test with dry run (no data saved)"
        }
    ]
    
    for i, example in enumerate(examples, 1):
        print(f"\n{i}. {example['name']}")
        print("-" * 40)
        print(f"Command:")
        print(f"  {example['command']}")
        print(f"Description: {example['description']}")


def demonstrate_config_file_setup():
    """Show how to set up configuration files."""
    
    print("\n" + "=" * 60)
    print("CONFIGURATION FILE EXAMPLES")
    print("=" * 60)
    
    configs = {
        "development.json": {
            "description": "For development and testing",
            "config": {
                "scraper": {
                    "concurrency": 1,
                    "max_questions_per_run": 50,
                    "delays": {"min": 2.0, "max": 5.0},
                    "rate_limit": {"requests_per_minute": 15}
                }
            }
        },
        "production.json": {
            "description": "For production scraping",
            "config": {
                "scraper": {
                    "concurrency": 3,
                    "max_questions_per_run": 1000,
                    "delays": {"min": 1.0, "max": 3.0},
                    "rate_limit": {"requests_per_minute": 30}
                }
            }
        },
        "high-speed.json": {
            "description": "For fast scraping (risky)",
            "config": {
                "scraper": {
                    "concurrency": 8,
                    "max_questions_per_run": 2000,
                    "delays": {"min": 0.5, "max": 1.0},
                    "rate_limit": {"requests_per_minute": 60}
                }
            }
        }
    }
    
    for filename, info in configs.items():
        print(f"\n📄 {filename}")
        print(f"Purpose: {info['description']}")
        print("-" * 40)
        print("Configuration:")
        print(json.dumps(info['config'], indent=2))
        print(f"\nUsage:")
        print(f"  python src/main.py --config config/{filename}")


def demonstrate_performance_monitoring():
    """Show how to monitor performance with different settings."""
    
    print("\n" + "=" * 60)
    print("PERFORMANCE MONITORING TIPS")
    print("=" * 60)
    
    tips = [
        {
            "title": "Monitor Request Rate",
            "description": "Check logs for actual request timing",
            "command": "tail -f logs/scraper.log | grep 'random delay'"
        },
        {
            "title": "Watch for Rate Limiting",
            "description": "Look for HTTP 429 or timeout errors",
            "command": "grep -i 'rate limit\\|429\\|timeout' logs/scraper.log"
        },
        {
            "title": "Check Concurrency Usage",
            "description": "Monitor how many browsers are active",
            "command": "grep -i 'browser\\|context' logs/scraper.log"
        },
        {
            "title": "Measure Actual Performance",
            "description": "Count questions scraped per minute",
            "command": "grep 'Successfully scraped' logs/scraper.log | tail -10"
        }
    ]
    
    for tip in tips:
        print(f"\n🔍 {tip['title']}")
        print(f"   {tip['description']}")
        print(f"   Command: {tip['command']}")
    
    print(f"\n💡 Performance Optimization Tips:")
    print(f"   • Start with conservative settings and gradually increase")
    print(f"   • Monitor for HTTP errors and adjust if needed")
    print(f"   • Use dry-run mode to test new configurations")
    print(f"   • Consider time of day - less traffic = safer to be faster")
    print(f"   • Keep backups when experimenting with aggressive settings")


def main():
    """Main demonstration function."""
    
    print("Starting concurrency and delay control demonstration...")
    
    demonstrate_configuration_options()
    demonstrate_delay_calculation()
    demonstrate_command_line_usage()
    demonstrate_config_file_setup()
    demonstrate_performance_monitoring()
    
    print("\n" + "=" * 60)
    print("DEMONSTRATION COMPLETED")
    print("=" * 60)
    print("Key Takeaways:")
    print("• Always start with conservative settings")
    print("• Monitor logs for rate limiting issues")
    print("• Use command line args for quick testing")
    print("• Create custom config files for different scenarios")
    print("• Balance speed vs. detection risk based on your needs")
    print("\nReady to start scraping with optimal settings! 🚀")


if __name__ == "__main__":
    main() 