#!/usr/bin/env python3
# FAST TCP FILE TRANSFER CLIENT - UNIVERSAL EDITION
# Created with ❤️ by 77
# Special credits to: 77 - The Architecht

import socket
import os
import sys
import time
from tqdm import tqdm

# ========== COLOR CODES ==========
RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
PURPLE = '\033[95m'
CYAN = '\033[96m'
WHITE = '\033[97m'
BOLD = '\033[1m'
DIM = '\033[2m'
ITALIC = '\033[3m'
RESET = '\033[0m'

BUFFER_SIZE = 65536

def print_client_banner():
    """Display client banner with credits"""
    banner = f"""
{BOLD}{CYAN}╔══════════════════════════════════════════════════════════╗{RESET}
{BOLD}{CYAN}║{RESET}  {PURPLE}███████╗{RESET}{BLUE} █████╗ {RESET}{GREEN}███████╗{RESET}{YELLOW}████████╗{RESET}                    {CYAN}║{RESET}
{BOLD}{CYAN}║{RESET}  {PURPLE}██╔════╝{RESET}{BLUE}██╔══██╗{RESET}{GREEN}██╔════╝{RESET}{YELLOW}╚══██╔══╝{RESET}                    {CYAN}║{RESET}
{BOLD}{CYAN}║{RESET}  {PURPLE}█████╗  {RESET}{BLUE}███████║{RESET}{GREEN}█████╗  {RESET}{YELLOW}   ██║   {RESET}                    {CYAN}║{RESET}
{BOLD}{CYAN}║{RESET}  {PURPLE}██╔══╝  {RESET}{BLUE}██╔══██║{RESET}{GREEN}██╔══╝  {RESET}{YELLOW}   ██║   {RESET}                    {CYAN}║{RESET}
{BOLD}{CYAN}║{RESET}  {PURPLE}██║     {RESET}{BLUE}██║  ██║{RESET}{GREEN}██║     {RESET}{YELLOW}   ██║   {RESET}                    {CYAN}║{RESET}
{BOLD}{CYAN}║{RESET}  {PURPLE}╚═╝     {RESET}{BLUE}╚═╝  ╚═╝{RESET}{GREEN}╚═╝     {RESET}{YELLOW}   ╚═╝   {RESET}                    {CYAN}║{RESET}
{BOLD}{CYAN}║{RESET}                                                      {CYAN}║{RESET}
{BOLD}{CYAN}║{RESET}  {WHITE}{BOLD}⚡ CLIENT MODE - READY TO TRANSFER ⚡{RESET}                  {CYAN}║{RESET}
{BOLD}{CYAN}║{RESET}  {ITALIC}{DIM}Universal Edition - Connect Anywhere{RESET}                   {CYAN}║{RESET}
{BOLD}{CYAN}╠══════════════════════════════════════════════════════════╣{RESET}
{BOLD}{CYAN}║{RESET}  {PURPLE}Coded with{WHITE} ❤️ {RESET}{PURPLE}by{RESET} {YELLOW}{BOLD}77{RESET}                                   {CYAN}║{RESET}
{BOLD}{CYAN}║{RESET}  {BLUE}Special Credits:{RESET} {GREEN}{BOLD}77 - The Architect{RESET}                      {CYAN}║{RESET}
{BOLD}{CYAN}║{RESET}  {RED}└─{RESET} {CYAN}Core Developer & Visionary{RESET}                             {CYAN}║{RESET}
{BOLD}{CYAN}╚══════════════════════════════════════════════════════════╝{RESET}
"""
    print(banner)

def format_size(size_bytes):
    """Format file size nicely"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"

def send_file(server_ip, port, filepath):
    """Send a file to the server with progress bar"""
    
    if not os.path.exists(filepath):
        print(f"{RED}[!]{RESET} File not found: {filepath}")
        return False
    
    filename = os.path.basename(filepath)
    filesize = os.path.getsize(filepath)
    
    print(f"\n{YELLOW}[➤]{RESET} Connecting to {CYAN}{server_ip}:{port}{RESET}")
    
    try:
        # Create socket
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, BUFFER_SIZE * 2)
        client.settimeout(30)
        
        # Connect
        start_connect = time.time()
        client.connect((server_ip, port))
        connect_time = (time.time() - start_connect) * 1000  # in ms
        
        print(f"{GREEN}[✓]{RESET} Connected in {WHITE}{connect_time:.1f}ms{RESET}")
        print(f"{BLUE}[i]{RESET} Sending: {YELLOW}{filename}{RESET} ({WHITE}{format_size(filesize)}{RESET})")
        
        # Send metadata
        metadata = f"{filename}|{filesize}"
        client.send(metadata.encode())
        time.sleep(0.1)
        
        # Progress bar
        progress = tqdm(
            total=filesize, 
            unit='B', 
            unit_scale=True, 
            desc=f"{PURPLE}Uploading{RESET}",
            bar_format=f"{PURPLE}{{l_bar}}{RESET}{{bar}}{CYAN}{{r_bar}}{RESET}",
            ascii=False,
            colour='blue'
        )
        
        # Send file
        with open(filepath, 'rb') as f:
            bytes_sent = 0
            start_time = time.time()
            
            while bytes_sent < filesize:
                chunk = f.read(BUFFER_SIZE)
                if not chunk:
                    break
                
                client.send(chunk)
                bytes_sent += len(chunk)
                progress.update(len(chunk))
        
        progress.close()
        
        # Calculate speed
        elapsed = time.time() - start_time
        speed = (filesize / elapsed) / 1024 if elapsed > 0 else 0
        
        # Get confirmation
        try:
            confirmation = client.recv(1024)
            if confirmation == b"RECEIVED":
                print(f"{GREEN}[✓]{RESET} {BOLD}Transfer complete!{RESET}")
                print(f"{CYAN}[⚡]{RESET} Speed: {WHITE}{speed:.2f} KB/s{RESET}")
                print(f"{BLUE}[⏱]{RESET} Time: {WHITE}{elapsed:.2f}s{RESET}")
        except:
            print(f"{GREEN}[✓]{RESET} Transfer complete!")
            
        client.close()
        return True
        
    except socket.timeout:
        print(f"\n{RED}[!]{RESET} Connection timeout")
    except ConnectionRefusedError:
        print(f"\n{RED}[!]{RESET} Connection refused - is the server running?")
    except Exception as e:
        print(f"\n{RED}[!]{RESET} Error: {e}")
    
    return False

def main():
    """Main client function"""
    print_client_banner()
    
    # Get server details
    print(f"\n{BLUE}[?]{RESET} {BOLD}Enter server details:{RESET}")
    server_ip = input(f"  {CYAN}►{RESET} Server IP{RESET}: ").strip()
    if not server_ip:
        print(f"{RED}[!]{RESET} Server IP required")
        return
    
    # Optional port input
    port_input = input(f"  {CYAN}►{RESET} Port (Enter for default 50000): ").strip()
    port = int(port_input) if port_input else 50000
    
    # Get file path
    print(f"\n{BLUE}[?]{RESET} {BOLD}File to send:{RESET}")
    filepath = input(f"  {CYAN}►{RESET} Path{RESET}: ").strip()
    if not filepath:
        print(f"{RED}[!]{RESET} File path required")
        return
    
    # Quick ping test
    print(f"\n{YELLOW}[i]{RESET} Testing connection...")
    try:
        test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        test_sock.settimeout(2)
        test_sock.connect((server_ip, port))
        test_sock.close()
        print(f"{GREEN}[✓]{RESET} Server is reachable!")
    except:
        print(f"{YELLOW}[!]{RESET} Cannot reach server, but attempting anyway...")
    
    # Send file
    print(f"\n{WHITE}{'='*50}{RESET}")
    start_time = time.time()
    success = send_file(server_ip, port, filepath)
    
    if success:
        elapsed = time.time() - start_time
        filesize = os.path.getsize(filepath)
        speed = filesize / elapsed / 1024
        print(f"\n{GREEN}{'='*50}{RESET}")
        print(f"{GREEN}[✓]{RESET} {BOLD}Mission Complete!{RESET}")
        print(f"{WHITE}└─{RESET} File: {YELLOW}{os.path.basename(filepath)}{RESET}")
        print(f"{WHITE}└─{RESET} Size: {BLUE}{format_size(filesize)}{RESET}")
        print(f"{WHITE}└─{RESET} Average Speed: {PURPLE}{speed:.2f} KB/s{RESET}")
        print(f"{WHITE}└─{RESET} Total Time: {CYAN}{elapsed:.2f}s{RESET}")
        print(f"{GREEN}{'='*50}{RESET}")

if __name__ == "__main__":
    # Check for tqdm
    try:
        from tqdm import tqdm
    except ImportError:
        print(f"{YELLOW}[!]{RESET} Installing required module: tqdm")
        os.system("pip3 install tqdm")
        os.system("pip install tqdm")
    
    # Windows color support
    if os.name == 'nt':
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except:
            # Disable colors if fails
            RED = GREEN = YELLOW = BLUE = PURPLE = CYAN = WHITE = BOLD = DIM = ITALIC = RESET = ''
    
    main()
