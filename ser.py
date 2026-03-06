#!/usr/bin/env python3
# FAST TCP FILE TRANSFER - UNIVERSAL EDITION
# Created with ❤️ by 77
# Special credits to: 77 - The Architecht

import socket
import os
import threading
import time
import sys
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
UNDERLINE = '\033[4m'
RESET = '\033[0m'
CLEAR_LINE = '\033[K'
MOVE_UP = '\033[F'

# Configuration
HOST = '0.0.0.0'
PORT = 50000
BUFFER_SIZE = 65536
SAVE_DIR = 'received_files'

os.makedirs(SAVE_DIR, exist_ok=True)

def print_banner():
    """Display the epic banner with credits"""
    banner = f"""
{BOLD}{CYAN}╔══════════════════════════════════════════════════════════╗{RESET}
{BOLD}{CYAN}║{RESET}  {PURPLE}███████{RESET} {BLUE}████████{RESET} {GREEN}███████{RESET} {YELLOW}██{RESET}      {RED}██{RESET}       {CYAN}║{RESET}
{BOLD}{CYAN}║{RESET}  {PURPLE}██{RESET}      {BLUE}   ██{RESET}   {GREEN}██{RESET}      {YELLOW}██{RESET}      {RED}██{RESET}       {CYAN}║{RESET}
{BOLD}{CYAN}║{RESET}  {PURPLE}█████{RESET}    {BLUE}   ██{RESET}   {GREEN}█████{RESET}   {YELLOW}██{RESET}      {RED}██{RESET}       {CYAN}║{RESET}
{BOLD}{CYAN}║{RESET}  {PURPLE}██{RESET}      {BLUE}   ██{RESET}   {GREEN}██{RESET}      {YELLOW}██{RESET}      {RED}██{RESET}       {CYAN}║{RESET}
{BOLD}{CYAN}║{RESET}  {PURPLE}██{RESET}      {BLUE}   ██{RESET}   {GREEN}███████{RESET} {YELLOW}███████{RESET} {RED}███████{RESET}  {CYAN}║{RESET}
{BOLD}{CYAN}║{RESET}                                                      {CYAN}║{RESET}
{BOLD}{CYAN}║{RESET}  {WHITE}{BOLD}⚡ FAST FILE TRANSFER PROTOCOL ⚡{RESET}                    {CYAN}║{RESET}
{BOLD}{CYAN}║{RESET}  {ITALIC}{DIM}Universal Edition - Works Anywhere{RESET}                    {CYAN}║{RESET}
{BOLD}{CYAN}╠══════════════════════════════════════════════════════════╣{RESET}
{BOLD}{CYAN}║{RESET}  {PURPLE}Created with{WHITE} ❤️ {RESET}{PURPLE}by{RESET} {YELLOW}{BOLD}77{RESET}                                   {CYAN}║{RESET}
{BOLD}{CYAN}║{RESET}  {BLUE}Special Credits:{RESET} {GREEN}{BOLD}77 - The Architect{RESET}                      {CYAN}║{RESET}
{BOLD}{CYAN}║{RESET}  {RED}└─{RESET} {CYAN}Core Developer & Visionary{RESET}                             {CYAN}║{RESET}
{BOLD}{CYAN}╚══════════════════════════════════════════════════════════╝{RESET}
"""
    print(banner)

def get_local_ip():
    """Get local IP address"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

def handle_client(conn, addr, client_id):
    """Handle individual client connections"""
    client_ip, client_port = addr
    print(f"\n{GREEN}[+] {RESET}{BOLD}Client {client_id}{RESET} connected from {CYAN}{client_ip}:{client_port}{RESET}")
    
    try:
        # Receive file metadata
        metadata = conn.recv(1024).decode().strip()
        if not metadata:
            return
            
        filename, filesize = metadata.split('|')
        filesize = int(filesize)
        save_path = os.path.join(SAVE_DIR, f"received_{filename}")
        
        print(f"{BLUE}[*]{RESET} Receiving: {YELLOW}{filename}{RESET} ({WHITE}{filesize:,}{RESET} bytes)")
        
        # Progress bar with custom colors
        progress = tqdm(
            total=filesize, 
            unit='B', 
            unit_scale=True, 
            desc=f"{PURPLE}Client {client_id}{RESET}",
            bar_format=f"{PURPLE}{{l_bar}}{RESET}{{bar}}{CYAN}{{r_bar}}{RESET}",
            ascii=False,
            colour='green'
        )
        
        # Receive the file
        with open(save_path, 'wb') as f:
            bytes_received = 0
            while bytes_received < filesize:
                remaining = filesize - bytes_received
                chunk_size = min(BUFFER_SIZE, remaining)
                
                chunk = conn.recv(chunk_size)
                if not chunk:
                    break
                    
                f.write(chunk)
                bytes_received += len(chunk)
                progress.update(len(chunk))
        
        progress.close()
        
        # Calculate speed
        elapsed = progress.format_dict.get('elapsed', 1)
        speed = (bytes_received / elapsed) / 1024 if elapsed > 0 else 0
        
        print(f"{GREEN}[✓]{RESET} {BOLD}Client {client_id}{RESET}: File saved as {YELLOW}{save_path}{RESET}")
        print(f"{CYAN}[⚡]{RESET} Transfer speed: {WHITE}{speed:.2f} KB/s{RESET}")
        
        # Send confirmation
        conn.send(b"RECEIVED")
        
    except Exception as e:
        print(f"{RED}[!]{RESET} Client {client_id} error: {e}")
    finally:
        conn.close()
        print(f"{YELLOW}[-]{RESET} Client {client_id} disconnected")

def start_server():
    """Main server function"""
    print_banner()
    
    local_ip = get_local_ip()
    
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, BUFFER_SIZE * 2)
    
    try:
        server.bind((HOST, PORT))
        server.listen(10)
        print(f"\n{BLUE}[i]{RESET} {BOLD}Server Information:{RESET}")
        print(f"  {CYAN}►{RESET} IP Address: {GREEN}{local_ip}{RESET}")
        print(f"  {CYAN}►{RESET} Port: {YELLOW}{PORT}{RESET}")
        print(f"  {CYAN}►{RESET} Save Directory: {WHITE}{os.path.abspath(SAVE_DIR)}{RESET}")
        print(f"  {CYAN}►{RESET} Buffer Size: {PURPLE}{BUFFER_SIZE}{RESET} bytes")
        print(f"\n{GREEN}[✓]{RESET} {BOLD}Server is LIVE!{RESET}")
        print(f"{DIM}Press Ctrl+C to stop{RESET}\n")
        
        client_counter = 0
        while True:
            conn, addr = server.accept()
            client_counter += 1
            thread = threading.Thread(target=handle_client, 
                                     args=(conn, addr, client_counter))
            thread.daemon = True
            thread.start()
            
    except KeyboardInterrupt:
        print(f"\n\n{YELLOW}[!]{RESET} Server shutting down...")
    except Exception as e:
        print(f"{RED}[!]{RESET} Server error: {e}")
    finally:
        server.close()
        print(f"{DIM}Server stopped{RESET}")

if __name__ == "__main__":
    # Check for tqdm
    try:
        from tqdm import tqdm
    except ImportError:
        print(f"{YELLOW}[!]{RESET} Installing required module: tqdm")
        os.system("pip3 install tqdm")
        os.system("pip install tqdm")  # Fallback for Windows
    
    # Check if running on Windows (disable colors if needed)
    if os.name == 'nt':  # Windows
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except:
            # Disable colors on Windows if fails
            for var in [RED, GREEN, YELLOW, BLUE, PURPLE, CYAN, WHITE, 
                       BOLD, DIM, ITALIC, UNDERLINE, RESET, CLEAR_LINE, MOVE_UP]:
                var = ''
    
    start_server()
