#!/usr/bin/env python3
"""
Test Setup Tool for FunTrivia Scraper
Validates all components and dependencies before scraping
"""

import sys
import os
import argparse
import json
from pathlib import Path

# Add src to path so we can import our modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from utils.sheets import test_google_sheets_setup
from utils.validation import validate_csv_files
from utils.monitoring import HealthMonitor, create_monitoring_dashboard
from utils.compliance import run_compliance_check, create_compliance_config

def test_dependencies():
    """Test if all required dependencies are installed."""
    print("🔍 Testing Dependencies")
    print("-" * 30)
    
    required_packages = [
        ('playwright', 'Playwright browser automation'),
        ('pandas', 'Data processing'),
        ('gspread', 'Google Sheets integration'),
        ('oauth2client', 'Google authentication'),
        ('aiohttp', 'Async HTTP requests'),
        ('tenacity', 'Retry mechanisms'),
        ('bs4', 'HTML parsing'),
        ('psutil', 'System monitoring'),
        ('requests', 'HTTP requests')
    ]
    
    success_count = 0
    
    for package, description in required_packages:
        try:
            __import__(package)
            print(f"✅ {package:<15} - {description}")
            success_count += 1
        except ImportError:
            print(f"❌ {package:<15} - {description} (MISSING)")
    
    print(f"\nDependencies: {success_count}/{len(required_packages)} installed")
    return success_count == len(required_packages)

def test_playwright_browsers():
    """Test if Playwright browsers are installed."""
    print("\n🎭 Testing Playwright Browsers")
    print("-" * 30)
    
    try:
        from playwright.sync_api import sync_playwright
        
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto('https://example.com')
                browser.close()
                print("✅ Chromium browser working correctly")
                return True
            except Exception as e:
                print(f"❌ Chromium browser test failed: {e}")
                print("💡 Run: playwright install chromium")
                return False
                
    except ImportError:
        print("❌ Playwright not installed")
        return False

def test_directory_structure():
    """Test if required directories exist."""
    print("\n📁 Testing Directory Structure")
    print("-" * 30)
    
    required_dirs = [
        'output',
        'assets',
        'assets/images',
        'assets/audio',
        'logs',
        'config',
        'credentials'
    ]
    
    all_exist = True
    
    for directory in required_dirs:
        if os.path.exists(directory):
            print(f"✅ {directory}")
        else:
            print(f"❌ {directory} (missing)")
            all_exist = False
    
    if not all_exist:
        print("\n💡 Run: python setup.py to create missing directories")
    
    return all_exist

def test_configuration_files():
    """Test if configuration files are valid."""
    print("\n⚙️ Testing Configuration Files")
    print("-" * 30)
    
    config_files = {
        'config/settings.json': 'Main configuration',
        'config/mappings.json': 'Category/difficulty mappings'
    }
    
    all_valid = True
    
    for config_file, description in config_files.items():
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    json.load(f)
                print(f"✅ {config_file} - {description}")
            except json.JSONDecodeError as e:
                print(f"❌ {config_file} - Invalid JSON: {e}")
                all_valid = False
        else:
            print(f"❌ {config_file} - {description} (missing)")
            all_valid = False
    
    return all_valid

def test_google_sheets(config_file='config/settings.json'):
    """Test Google Sheets integration if enabled."""
    print("\n📊 Testing Google Sheets Integration")
    print("-" * 30)
    
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
        
        sheets_config = config.get('google_sheets', {})
        
        if not sheets_config.get('enabled', False):
            print("⏸️ Google Sheets integration disabled in config")
            return True
        
        credentials_file = sheets_config.get('credentials_file', '')
        spreadsheet_id = sheets_config.get('spreadsheet_id', '')
        
        if not credentials_file or not spreadsheet_id:
            print("❌ Missing credentials_file or spreadsheet_id in config")
            return False
        
        return test_google_sheets_setup(credentials_file, spreadsheet_id)
        
    except Exception as e:
        print(f"❌ Error testing Google Sheets: {e}")
        return False

def test_system_resources():
    """Test system resources."""
    print("\n💻 Testing System Resources")
    print("-" * 30)
    
    try:
        import psutil
        
        # Memory check
        memory = psutil.virtual_memory()
        memory_gb = memory.total / (1024**3)
        available_gb = memory.available / (1024**3)
        
        print(f"Memory: {memory_gb:.1f} GB total, {available_gb:.1f} GB available")
        
        if available_gb < 1:
            print("⚠️ Low available memory (< 1 GB)")
        else:
            print("✅ Sufficient memory available")
        
        # Disk check
        disk = psutil.disk_usage('.')
        free_gb = disk.free / (1024**3)
        
        print(f"Disk: {free_gb:.1f} GB free space")
        
        if free_gb < 1:
            print("⚠️ Low disk space (< 1 GB)")
        else:
            print("✅ Sufficient disk space")
        
        # CPU check
        cpu_count = psutil.cpu_count()
        print(f"CPU: {cpu_count} cores")
        
        return available_gb >= 1 and free_gb >= 1
        
    except ImportError:
        print("❌ psutil not available for system checks")
        return False

def test_network_connectivity():
    """Test network connectivity to FunTrivia."""
    print("\n🌐 Testing Network Connectivity")
    print("-" * 30)
    
    try:
        import requests
        
        # Test basic connectivity
        response = requests.get('https://www.funtrivia.com', timeout=10)
        
        if response.status_code == 200:
            print("✅ FunTrivia.com is accessible")
            print(f"Response time: {response.elapsed.total_seconds():.2f} seconds")
            return True
        else:
            print(f"⚠️ FunTrivia.com returned status code: {response.status_code}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Network connectivity failed: {e}")
        return False

def run_compliance_test(config_file='config/settings.json'):
    """Run compliance and ethics test."""
    print("\n⚖️ Testing Compliance and Ethics")
    print("-" * 30)
    
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
        
        base_url = config.get('scraper', {}).get('base_url', 'https://www.funtrivia.com')
        
        # Add compliance config if missing
        if 'ethical_scraping' not in config:
            config.update(create_compliance_config())
        
        results = run_compliance_check(base_url, config)
        return results.get('overall_status') == 'compliant'
        
    except Exception as e:
        print(f"❌ Compliance test failed: {e}")
        return False

def generate_test_report(results):
    """Generate a comprehensive test report."""
    print("\n" + "="*60)
    print("📋 SETUP TEST REPORT")
    print("="*60)
    
    total_tests = len(results)
    passed_tests = sum(1 for result in results.values() if result)
    
    print(f"Overall Status: {'✅ PASS' if passed_tests == total_tests else '❌ FAIL'}")
    print(f"Tests Passed: {passed_tests}/{total_tests}")
    
    print("\nTest Results:")
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {test_name:<25}: {status}")
    
    if passed_tests < total_tests:
        print("\n🔧 Next Steps:")
        print("1. Fix any failed tests above")
        print("2. Run this test again until all tests pass")
        print("3. Check the troubleshooting guide in README.md")
        print("4. Once all tests pass, you can start scraping!")
    else:
        print("\n🎉 All tests passed! Your setup is ready for scraping.")
        print("\nRecommended next steps:")
        print("1. Review the compliance report above")
        print("2. Start with a small test: python src/main.py --max-questions 10")
        print("3. Monitor the logs/scraper.log file")
        print("4. Scale up gradually once everything works")

def main():
    parser = argparse.ArgumentParser(description='Test FunTrivia Scraper Setup')
    parser.add_argument('--config', default='config/settings.json', help='Configuration file path')
    parser.add_argument('--skip-network', action='store_true', help='Skip network connectivity tests')
    parser.add_argument('--skip-compliance', action='store_true', help='Skip compliance tests')
    parser.add_argument('--report-only', action='store_true', help='Only generate monitoring dashboard')
    args = parser.parse_args()

    if args.report_only:
        print(create_monitoring_dashboard())
        return

    print("🧪 FunTrivia Scraper Setup Test")
    print("="*60)
    print("This tool will test all components of your scraper setup.\n")

    # Run all tests
    test_results = {}
    
    test_results['Dependencies'] = test_dependencies()
    test_results['Playwright Browsers'] = test_playwright_browsers()
    test_results['Directory Structure'] = test_directory_structure()
    test_results['Configuration Files'] = test_configuration_files()
    test_results['System Resources'] = test_system_resources()
    
    if not args.skip_network:
        test_results['Network Connectivity'] = test_network_connectivity()
    
    test_results['Google Sheets'] = test_google_sheets(args.config)
    
    if not args.skip_compliance:
        test_results['Compliance'] = run_compliance_test(args.config)
    
    # Generate final report
    generate_test_report(test_results)
    
    # Exit with error code if any tests failed
    all_passed = all(test_results.values())
    sys.exit(0 if all_passed else 1)

if __name__ == '__main__':
    main() 