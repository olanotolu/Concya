#!/usr/bin/env python3
"""
Quick connection test for Concya server
Tests if server endpoints are accessible before running full client
"""

import requests
import sys
from colorama import Fore, Style, init

init(autoreset=True)

def test_server(server_url):
    """Test if Concya server is accessible"""
    print(f"\n{Fore.CYAN}Testing Concya Server: {server_url}{Style.RESET_ALL}\n")
    
    tests = [
        ("Health Check", f"{server_url}/health", "GET"),
        ("Metrics", f"{server_url}/metrics", "GET"),
    ]
    
    all_passed = True
    
    for name, url, method in tests:
        try:
            if method == "GET":
                response = requests.get(url, timeout=5)
            else:
                response = requests.post(url, json={}, timeout=5)
            
            if response.status_code in [200, 201]:
                print(f"{Fore.GREEN}✓ {name}: OK (HTTP {response.status_code}){Style.RESET_ALL}")
            else:
                print(f"{Fore.YELLOW}⚠ {name}: Unexpected status {response.status_code}{Style.RESET_ALL}")
                all_passed = False
        except requests.exceptions.ConnectionError:
            print(f"{Fore.RED}✗ {name}: Connection failed{Style.RESET_ALL}")
            all_passed = False
        except requests.exceptions.Timeout:
            print(f"{Fore.RED}✗ {name}: Timeout{Style.RESET_ALL}")
            all_passed = False
        except Exception as e:
            print(f"{Fore.RED}✗ {name}: {str(e)}{Style.RESET_ALL}")
            all_passed = False
    
    print()
    
    if all_passed:
        print(f"{Fore.GREEN}✓ All tests passed! Server is ready.{Style.RESET_ALL}")
        print(f"\n{Fore.CYAN}Run the client:{Style.RESET_ALL}")
        print(f"  python client.py --server {server_url}\n")
        return 0
    else:
        print(f"{Fore.RED}✗ Some tests failed. Check server status.{Style.RESET_ALL}")
        print(f"\n{Fore.YELLOW}Make sure the server is running:{Style.RESET_ALL}")
        print(f"  python app.py\n")
        return 1

if __name__ == '__main__':
    server_url = sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8000'
    sys.exit(test_server(server_url))

