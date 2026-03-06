#!/usr/bin/env python3
"""
ULTIMATE UDP FILE TRANSFER v3.1
Created by 77 - The Architect
Fixed for Python 3.13+ compatibility
"""

import socket
import os
import sys
import time
import hashlib
import threading
import struct
import pickle
import queue
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, Set, Optional, Tuple
import signal

# ========== COLOR CODES (Safe for all OS) ==========
class Colors:
    """Cross-platform colors"""
    if os.name == 'nt':  # Windows
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
            GREEN = '\033[92m'
            YELLOW = '\033[93m'
            RED = '\033[91m'
            BLUE = '\033[94m'
            CYAN = '\033[96m'
            PURPLE = '\033[95m'
            WHITE = '\033[97m'
            BOLD = '\033[1m'
            RESET = '\033[0m'
        except:
            GREEN = YELLOW = RED = BLUE = CYAN = PURPLE = WHITE = BOLD = RESET = ''
    else:  # Linux/Mac/Android
        GREEN = '\033[92m'
        YELLOW = '\033[93m'
        RED = '\033[91m'
        BLUE = '\033[94m'
        CYAN = '\033[96m'
        PURPLE = '\033[95m'
        WHITE = '\033[97m'
        BOLD = '\033[1m'
        RESET = '\033[0m'

# ========== DATA STRUCTURES ==========
@dataclass(order=False)
class PacketHeader:
    """UDP Packet Header - 24 bytes total - FIXED for Python 3.13"""
    packet_type: int  # 1 byte - Type (DATA, ACK, NAK, SYN, FIN)
    stream_id: int = 0  # 1 byte - Parallel stream ID
    sequence: int = 0  # 4 bytes - Sequence number
    timestamp: float = 0.0  # 8 bytes - Timestamp
    magic: int = 0x77  # 1 byte - Magic number
    version: int = 3  # 1 byte - Protocol version
    checksum: bytes = b'\x00' * 8  # 8 bytes - Partial SHA256
    
    def __post_init__(self):
        """Validate after initialization"""
        if isinstance(self.checksum, str):
            self.checksum = self.checksum.encode()
        if len(self.checksum) != 8:
            self.checksum = self.checksum.ljust(8, b'\x00')[:8]
    
    def pack(self) -> bytes:
        """Pack header into bytes"""
        return struct.pack('!BBBBIQ8s', 
                          self.magic, 
                          self.version, 
                          self.packet_type,
                          self.stream_id, 
                          self.sequence, 
                          int(self.timestamp * 1000),  # Convert to milliseconds
                          self.checksum)
    
    @classmethod
    def unpack(cls, data: bytes) -> 'PacketHeader':
        """Unpack header from bytes"""
        try:
            magic, version, ptype, stream_id, seq, timestamp_ms, checksum = \
                struct.unpack('!BBBBIQ8s', data[:24])
            
            if magic != 0x77 or version != 3:
                raise ValueError(f"Invalid packet magic/version: {magic}/{version}")
            
            return cls(
                magic=magic,
                version=version,
                packet_type=ptype,
                stream_id=stream_id,
                sequence=seq,
                timestamp=timestamp_ms / 1000.0,
                checksum=checksum
            )
        except struct.error as e:
            raise ValueError(f"Failed to unpack header: {e}")

@dataclass
class FileMetadata:
    """File information"""
    filename: str
    filesize: int
    total_packets: int
    checksum: str
    compression: bool = False
    chunks: int = 1
    
    def __post_init__(self):
        """Validate metadata"""
        if not isinstance(self.filename, str):
            self.filename = str(self.filename)
        if self.filesize < 0:
            self.filesize = 0
        if self.total_packets < 0:
            self.total_packets = 0

# ========== PROGRESS BAR (Pure Python) ==========
class ProgressBar:
    """Simple progress bar without external deps"""
    
    def __init__(self, total, desc="Progress", width=50):
        self.total = total
        self.desc = desc
        self.width = width
        self.start_time = time.time()
        self.current = 0
        self.last_update = 0
        
    def update(self, n=1):
        """Update progress"""
        self.current += n
        self.display()
        
    def display(self):
        """Display progress bar"""
        if time.time() - self.last_update < 0.1:  # Throttle updates
            return
            
        percent = self.current / self.total if self.total > 0 else 0
        filled = int(self.width * percent)
        bar = '█' * filled + '░' * (self.width - filled)
        elapsed = time.time() - self.start_time
        speed = self.current / elapsed / 1024 if elapsed > 0 else 0
        
        sys.stdout.write(f'\r{Colors.CYAN}{self.desc}{Colors.RESET}: |{Colors.GREEN}{bar}{Colors.RESET}| '
                        f'{percent:6.1%} '
                        f'{Colors.YELLOW}{self.current/1024/1024:.1f}/{self.total/1024/1024:.1f} MB{Colors.RESET} '
                        f'{Colors.PURPLE}{speed:.1f} KB/s{Colors.RESET}')
        sys.stdout.flush()
        self.last_update = time.time()
        
    def close(self):
        """Finish progress"""
        elapsed = time.time() - self.start_time
        speed = self.current / elapsed / 1024 / 1024 if elapsed > 0 else 0
        print(f'\n{Colors.GREEN}✓ Complete in {elapsed:.1f}s ({speed:.1f} MB/s){Colors.RESET}')

# ========== UDP ENGINE ==========
class UDPEngine:
    """Core UDP engine with all protections"""
    
    # Packet types
    PKT_SYN = 1    # Connection request
    PKT_ACK = 2    # Acknowledgment
    PKT_DATA = 3   # Data packet
    PKT_NAK = 4    # Negative ACK (missing packet)
    PKT_FIN = 5    # End of transmission
    PKT_KEEP = 6   # Keep-alive
    
    def __init__(self, stream_id=0):
        self.stream_id = stream_id
        self.socket = None
        self.running = True
        self.seq_num = 0
        self.expected_seq = 0
        self.buffer = {}  # Out-of-order buffer
        self.acks = set()  # Received ACKs
        self.pending = {}  # Pending packets for retransmission
        self.timeout = 0.5  # Retransmission timeout
        self.max_retries = 10
        self.mtu = 1400  # Safe MTU (avoids fragmentation)
        self.window_size = 100  # Congestion window
        self.congestion_window = 10  # Current window
        self.lock = threading.Lock()
        self.stats = {'sent': 0, 'received': 0, 'lost': 0, 'retries': 0}
        
    def create_packet(self, pkt_type: int, data: bytes = b'') -> bytes:
        """Create packet with full protection"""
        with self.lock:
            if pkt_type == self.PKT_DATA:
                seq = self.seq_num
                self.seq_num += 1
            else:
                seq = 0
                
        # Calculate checksum (first 8 bytes of SHA256)
        if data:
            full_hash = hashlib.sha256(data).digest()
            checksum = full_hash[:8]
        else:
            checksum = b'\x00' * 8
        
        # Create header - FIXED: all arguments in correct order
        header = PacketHeader(
            packet_type=pkt_type,
            stream_id=self.stream_id,
            sequence=seq,
            timestamp=time.time(),
            magic=0x77,
            version=3,
            checksum=checksum
        )
        
        # Add sequence number to data for tracking
        if pkt_type == self.PKT_DATA:
            seq_data = struct.pack('!I', seq) + data
        else:
            seq_data = data
            
        return header.pack() + seq_data
    
    def parse_packet(self, packet: bytes) -> Tuple[Optional[int], Optional[int], Optional[bytes], bool]:
        """Parse and verify packet"""
        if len(packet) < 24:
            return None, None, None, False
            
        try:
            header = PacketHeader.unpack(packet[:24])
            data = packet[24:]
            
            # Verify checksum for data packets
            if header.packet_type == self.PKT_DATA and len(data) >= 4:
                seq = struct.unpack('!I', data[:4])[0]
                payload = data[4:]
                if payload:
                    full_hash = hashlib.sha256(payload).digest()
                    if full_hash[:8] != header.checksum:
                        return None, None, None, False
                return header.packet_type, seq, payload, True
            else:
                # For non-data packets, just verify header
                return header.packet_type, 0, data, True
                
        except Exception as e:
            return None, None, None, False

# ========== UDP SERVER (Receiver) ==========
class UDPServer(UDPEngine):
    """Production UDP Server - Receives files"""
    
    def __init__(self, port=50000, save_dir='downloads'):
        super().__init__()
        self.port = port
        self.save_dir = save_dir
        self.clients = {}
        self.transfers = {}
        os.makedirs(save_dir, exist_ok=True)
        
    def start(self):
        """Start server"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 20*1024*1024)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 20*1024*1024)
            self.socket.bind(('0.0.0.0', self.port))
        except Exception as e:
            print(f"{Colors.RED}Failed to bind to port {self.port}: {e}{Colors.RESET}")
            return
        
        self.print_banner()
        print(f"{Colors.GREEN}✓ Server listening on port {self.port}{Colors.RESET}")
        print(f"{Colors.BLUE}✓ Save directory: {os.path.abspath(self.save_dir)}{Colors.RESET}\n")
        
        # Start receiver thread
        receiver = threading.Thread(target=self.receive_loop, daemon=True)
        receiver.start()
        
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()
            
    def receive_loop(self):
        """Main receive loop"""
        while self.running:
            try:
                data, addr = self.socket.recvfrom(65536)
                pkt_type, seq, payload, valid = self.parse_packet(data)
                
                if not valid:
                    continue
                    
                if pkt_type == self.PKT_SYN:
                    self.handle_syn(payload, addr)
                elif pkt_type == self.PKT_DATA:
                    self.handle_data(seq, payload, addr)
                elif pkt_type == self.PKT_FIN:
                    self.handle_fin(payload, addr)
                elif pkt_type == self.PKT_ACK:
                    self.handle_ack(seq, addr)
                elif pkt_type == self.PKT_KEEP:
                    self.handle_keepalive(addr)
                    
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"{Colors.RED}Error: {e}{Colors.RESET}")
                    
    def handle_syn(self, payload, addr):
        """Handle connection request"""
        try:
            metadata = pickle.loads(payload)
            transfer_id = f"{addr[0]}:{addr[1]}"
            
            self.transfers[transfer_id] = {
                'metadata': metadata,
                'received': set(),
                'buffer': {},
                'expected_seq': 0,
                'start_time': time.time(),
                'file': open(os.path.join(self.save_dir, metadata.filename), 'wb'),
                'size': 0,
                'progress': ProgressBar(metadata.filesize, f"Receiving {metadata.filename}")
            }
            
            # Send ACK
            ack = self.create_packet(self.PKT_ACK, b'READY')
            self.socket.sendto(ack, addr)
            
            print(f"{Colors.GREEN}✓ Connection from {addr[0]}:{addr[1]}{Colors.RESET}")
            print(f"  File: {metadata.filename} ({metadata.filesize/1024/1024:.1f} MB)")
            
        except Exception as e:
            print(f"{Colors.RED}SYN error: {e}{Colors.RESET}")
            
    def handle_data(self, seq, payload, addr):
        """Handle data packet"""
        transfer_id = f"{addr[0]}:{addr[1]}"
        
        if transfer_id not in self.transfers:
            return
            
        transfer = self.transfers[transfer_id]
        
        # Send ACK immediately
        ack = self.create_packet(self.PKT_ACK, struct.pack('!I', seq))
        try:
            self.socket.sendto(ack, addr)
        except:
            pass
        
        # Check if packet is expected
        if seq == transfer.get('expected_seq', 0):
            # Write immediately
            transfer['file'].write(payload)
            transfer['size'] += len(payload)
            transfer['progress'].update(len(payload))
            transfer['expected_seq'] = seq + 1
            
            # Check buffer for next packets
            while transfer['expected_seq'] in transfer.get('buffer', {}):
                buffered = transfer['buffer'].pop(transfer['expected_seq'])
                transfer['file'].write(buffered)
                transfer['size'] += len(buffered)
                transfer['progress'].update(len(buffered))
                transfer['expected_seq'] += 1
                
        elif seq > transfer.get('expected_seq', 0):
            # Out of order - store in buffer
            if 'buffer' not in transfer:
                transfer['buffer'] = {}
            transfer['buffer'][seq] = payload
        else:
            # Duplicate - ignore
            pass
            
        self.stats['received'] += 1
        
    def handle_fin(self, payload, addr):
        """Handle end of transmission"""
        transfer_id = f"{addr[0]}:{addr[1]}"
        
        if transfer_id in self.transfers:
            transfer = self.transfers[transfer_id]
            
            # Close file
            transfer['file'].close()
            
            # Verify file integrity
            try:
                with open(os.path.join(self.save_dir, transfer['metadata'].filename), 'rb') as f:
                    file_hash = hashlib.sha256(f.read()).hexdigest()
                    
                if file_hash == transfer['metadata'].checksum:
                    print(f"{Colors.GREEN}✓ File verified: {transfer['metadata'].filename}{Colors.RESET}")
                    transfer['progress'].close()
                else:
                    print(f"{Colors.RED}✗ Checksum mismatch!{Colors.RESET}")
            except Exception as e:
                print(f"{Colors.RED}✗ Verification error: {e}{Colors.RESET}")
            
            # Send final ACK
            try:
                fin_ack = self.create_packet(self.PKT_FIN, b'COMPLETE')
                self.socket.sendto(fin_ack, addr)
            except:
                pass
            
            del self.transfers[transfer_id]
            
    def handle_ack(self, seq, addr):
        """Handle acknowledgment"""
        with self.lock:
            self.congestion_window = min(self.congestion_window + 1, self.window_size)
            
    def handle_keepalive(self, addr):
        """Handle keep-alive packet"""
        transfer_id = f"{addr[0]}:{addr[1]}"
        if transfer_id in self.transfers:
            self.transfers[transfer_id]['last_seen'] = time.time()
            
    def stop(self):
        """Stop server"""
        self.running = False
        for transfer in self.transfers.values():
            if 'file' in transfer:
                transfer['file'].close()
        if self.socket:
            self.socket.close()
        print(f"\n{Colors.YELLOW}Server stopped{Colors.RESET}")
        
    def print_banner(self):
        """Display server banner"""
        banner = f"""
{Colors.BOLD}{Colors.CYAN}╔══════════════════════════════════════════════════════════╗{Colors.RESET}
{Colors.BOLD}{Colors.CYAN}║{Colors.RESET}  {Colors.PURPLE}███████{Colors.RESET} {Colors.BLUE}██{Colors.RESET}    {Colors.BLUE}██{Colors.RESET} {Colors.GREEN}██████{Colors.RESET}  {Colors.CYAN}██████{Colors.RESET}  {Colors.YELLOW}██████{Colors.RESET}  {Colors.RED}██████{Colors.RESET}  {Colors.CYAN}║{Colors.RESET}
{Colors.BOLD}{Colors.CYAN}║{Colors.RESET}  {Colors.PURPLE}██{Colors.RESET}      {Colors.BLUE}██{Colors.RESET}    {Colors.BLUE}██{Colors.RESET} {Colors.GREEN}██{Colors.RESET}  {Colors.GREEN}██{Colors.RESET} {Colors.CYAN}██{Colors.RESET}  {Colors.CYAN}██{Colors.RESET} {Colors.YELLOW}██{Colors.RESET}  {Colors.YELLOW}██{Colors.RESET} {Colors.RED}██{Colors.RESET}  {Colors.RED}██{Colors.RESET} {Colors.CYAN}║{Colors.RESET}
{Colors.BOLD}{Colors.CYAN}║{Colors.RESET}  {Colors.PURPLE}███████{Colors.RESET} {Colors.BLUE}██{Colors.RESET}    {Colors.BLUE}██{Colors.RESET} {Colors.GREEN}██████{Colors.RESET}  {Colors.CYAN}██████{Colors.RESET}  {Colors.YELLOW}██████{Colors.RESET}  {Colors.RED}██████{Colors.RESET}  {Colors.CYAN}║{Colors.RESET}
{Colors.BOLD}{Colors.CYAN}║{Colors.RESET}       {Colors.BLUE}██{Colors.RESET}    {Colors.BLUE}██{Colors.RESET} {Colors.GREEN}██{Colors.RESET}      {Colors.CYAN}██{Colors.RESET}  {Colors.CYAN}██{Colors.RESET}     {Colors.YELLOW}██{Colors.RESET}  {Colors.RED}██{Colors.RESET}  {Colors.CYAN}║{Colors.RESET}
{Colors.BOLD}{Colors.CYAN}║{Colors.RESET}  {Colors.PURPLE}███████{Colors.RESET} {Colors.BLUE}████████{Colors.RESET} {Colors.GREEN}██{Colors.RESET}      {Colors.CYAN}██████{Colors.RESET}  {Colors.YELLOW}██████{Colors.RESET}  {Colors.RED}██████{Colors.RESET}  {Colors.CYAN}║{Colors.RESET}
{Colors.BOLD}{Colors.CYAN}╠══════════════════════════════════════════════════════════╣{Colors.RESET}
{Colors.BOLD}{Colors.CYAN}║{Colors.RESET}  {Colors.WHITE}UDP FILE TRANSFER SERVER v3.1{Colors.RESET}                         {Colors.CYAN}║{Colors.RESET}
{Colors.BOLD}{Colors.CYAN}║{Colors.RESET}  {Colors.WHITE}Created by 77 - The Architect{Colors.RESET}                          {Colors.CYAN}║{Colors.RESET}
{Colors.BOLD}{Colors.CYAN}╚══════════════════════════════════════════════════════════╝{Colors.RESET}
"""
        print(banner)

# ========== UDP CLIENT (Sender) ==========
class UDPClient(UDPEngine):
    """Production UDP Client - Sends files"""
    
    def __init__(self, server_ip, server_port=50000, parallel_streams=4):
        super().__init__()
        self.server_addr = (server_ip, server_port)
        self.parallel_streams = parallel_streams
        self.completed = threading.Event()
        
    def send_file(self, filepath):
        """Send file with maximum speed and reliability"""
        
        if not os.path.exists(filepath):
            print(f"{Colors.RED}✗ File not found: {filepath}{Colors.RESET}")
            return False
            
        filename = os.path.basename(filepath)
        filesize = os.path.getsize(filepath)
        
        self.print_banner()
        print(f"{Colors.YELLOW}► Sending: {Colors.WHITE}{filename}{Colors.RESET}")
        print(f"{Colors.BLUE}► Size: {Colors.WHITE}{filesize/1024/1024:.1f} MB{Colors.RESET}")
        print(f"{Colors.PURPLE}► Streams: {Colors.WHITE}{self.parallel_streams}{Colors.RESET}\n")
        
        # Calculate file hash
        print(f"{Colors.CYAN}Calculating checksum...{Colors.RESET}")
        with open(filepath, 'rb') as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()
            
        # Create metadata
        metadata = FileMetadata(
            filename=filename,
            filesize=filesize,
            total_packets=(filesize // self.mtu) + 1,
            checksum=file_hash,
            compression=False,
            chunks=self.parallel_streams
        )
        
        try:
            # Create socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 20*1024*1024)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 20*1024*1024)
            self.socket.settimeout(5)
        except Exception as e:
            print(f"{Colors.RED}✗ Socket error: {e}{Colors.RESET}")
            return False
        
        # Connect to server
        if not self.handshake(metadata):
            print(f"{Colors.RED}✗ Handshake failed{Colors.RESET}")
            self.socket.close()
            return False
            
        # Send file
        success = self.send_file_data(filepath)
        
        # Send FIN
        self.send_fin()
        
        self.socket.close()
        return success
        
    def handshake(self, metadata):
        """Establish connection with server"""
        try:
            # Send SYN
            syn_packet = self.create_packet(self.PKT_SYN, pickle.dumps(metadata))
            self.socket.sendto(syn_packet, self.server_addr)
            
            # Wait for ACK
            data, _ = self.socket.recvfrom(65536)
            pkt_type, _, payload, valid = self.parse_packet(data)
            
            if valid and pkt_type == self.PKT_ACK and payload == b'READY':
                # Start keep-alive
                self.start_keepalive()
                return True
                
        except socket.timeout:
            print(f"{Colors.RED}✗ Connection timeout{Colors.RESET}")
        except Exception as e:
            print(f"{Colors.RED}✗ Handshake error: {e}{Colors.RESET}")
            
        return False
        
    def send_file_data(self, filepath):
        """Send file data"""
        with open(filepath, 'rb') as f:
            data = f.read()
            
        # Split into packets
        packets = []
        for i in range(0, len(data), self.mtu):
            chunk = data[i:i+self.mtu]
            packets.append(chunk)
            
        # Progress bar
        progress = ProgressBar(len(data), "Uploading")
        
        # Send packets with retransmission
        success = True
        for i, packet in enumerate(packets):
            if not self.send_with_retry(i, packet):
                success = False
                break
            progress.update(len(packet))
            
        progress.close()
        return success
        
    def send_with_retry(self, seq, data):
        """Send packet with retransmission"""
        for retry in range(self.max_retries):
            try:
                # Create packet
                pkt = self.create_packet(self.PKT_DATA, data)
                
                # Send
                self.socket.sendto(pkt, self.server_addr)
                self.stats['sent'] += 1
                
                # Wait for ACK
                self.socket.settimeout(self.timeout)
                response, _ = self.socket.recvfrom(65536)
                pkt_type, ack_seq, _, valid = self.parse_packet(response)
                
                if valid and pkt_type == self.PKT_ACK:
                    if ack_seq == seq:
                        return True
                        
            except socket.timeout:
                self.stats['retries'] += 1
                continue
            except Exception:
                continue
                
        self.stats['lost'] += 1
        return False
        
    def send_fin(self):
        """Send finish signal"""
        try:
            fin_packet = self.create_packet(self.PKT_FIN, b'DONE')
            self.socket.sendto(fin_packet, self.server_addr)
            
            # Wait for FIN-ACK
            self.socket.settimeout(5)
            data, _ = self.socket.recvfrom(65536)
            pkt_type, _, payload, valid = self.parse_packet(data)
            if valid and pkt_type == self.PKT_FIN and payload == b'COMPLETE':
                self.completed.set()
        except:
            pass
            
    def start_keepalive(self):
        """Start keep-alive thread"""
        def keepalive():
            while not self.completed.is_set():
                time.sleep(30)
                try:
                    keep = self.create_packet(self.PKT_KEEP, b'')
                    self.socket.sendto(keep, self.server_addr)
                except:
                    break
                    
        thread = threading.Thread(target=keepalive, daemon=True)
        thread.start()
        
    def print_banner(self):
        """Display client banner"""
        banner = f"""
{Colors.BOLD}{Colors.CYAN}╔══════════════════════════════════════════════════════════╗{Colors.RESET}
{Colors.BOLD}{Colors.CYAN}║{Colors.RESET}  {Colors.PURPLE}███████{Colors.RESET} {Colors.BLUE}██{Colors.RESET}      {Colors.GREEN}██████{Colors.RESET} {Colors.CYAN}██{Colors.RESET}      {Colors.YELLOW}██████{Colors.RESET} {Colors.RED}████████{Colors.RESET} {Colors.CYAN}║{Colors.RESET}
{Colors.BOLD}{Colors.CYAN}║{Colors.RESET}  {Colors.PURPLE}██{Colors.RESET}      {Colors.BLUE}██{Colors.RESET}     {Colors.GREEN}██{Colors.RESET}  {Colors.GREEN}██{Colors.RESET} {Colors.CYAN}██{Colors.RESET}      {Colors.YELLOW}██{Colors.RESET}  {Colors.YELLOW}██{Colors.RESET}    {Colors.RED}██{Colors.RESET}    {Colors.CYAN}║{Colors.RESET}
{Colors.BOLD}{Colors.CYAN}║{Colors.RESET}  {Colors.PURPLE}█████{Colors.RESET}  {Colors.BLUE}██{Colors.RESET}     {Colors.GREEN}██████{Colors.RESET}  {Colors.CYAN}██{Colors.RESET}      {Colors.YELLOW}██████{Colors.RESET}     {Colors.RED}██{Colors.RESET}    {Colors.CYAN}║{Colors.RESET}
{Colors.BOLD}{Colors.CYAN}║{Colors.RESET}  {Colors.PURPLE}██{Colors.RESET}      {Colors.BLUE}██{Colors.RESET}     {Colors.GREEN}██{Colors.RESET}  {Colors.GREEN}██{Colors.RESET} {Colors.CYAN}██{Colors.RESET}      {Colors.YELLOW}██{Colors.RESET}  {Colors.YELLOW}██{Colors.RESET}    {Colors.RED}██{Colors.RESET}    {Colors.CYAN}║{Colors.RESET}
{Colors.BOLD}{Colors.CYAN}║{Colors.RESET}  {Colors.PURPLE}██{Colors.RESET}      {Colors.BLUE}████████{Colors.RESET} {Colors.GREEN}██{Colors.RESET}  {Colors.GREEN}██{Colors.RESET} {Colors.CYAN}███████{Colors.RESET} {Colors.YELLOW}██████{Colors.RESET}     {Colors.RED}██{Colors.RESET}    {Colors.CYAN}║{Colors.RESET}
{Colors.BOLD}{Colors.CYAN}╠══════════════════════════════════════════════════════════╣{Colors.RESET}
{Colors.BOLD}{Colors.CYAN}║{Colors.RESET}  {Colors.WHITE}UDP FILE TRANSFER CLIENT v3.1{Colors.RESET}                         {Colors.CYAN}║{Colors.RESET}
{Colors.BOLD}{Colors.CYAN}║{Colors.RESET}  {Colors.WHITE}Created by 77 - The Architect{Colors.RESET}                          {Colors.CYAN}║{Colors.RESET}
{Colors.BOLD}{Colors.CYAN}╚══════════════════════════════════════════════════════════╝{Colors.RESET}
"""
        print(banner)

# ========== MAIN APPLICATION ==========
def main():
    """Main entry point"""
    
    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        print(f"\n{Colors.YELLOW}Shutting down...{Colors.RESET}")
        sys.exit(0)
        
    signal.signal(signal.SIGINT, signal_handler)
    
    # Check Python version
    if sys.version_info < (3, 6):
        print(f"{Colors.RED}✗ Python 3.6+ required{Colors.RESET}")
        sys.exit(1)
        
    # Display main menu
    menu = f"""
{Colors.BOLD}{Colors.CYAN}╔══════════════════════════════════════════════════════════╗{Colors.RESET}
{Colors.BOLD}{Colors.CYAN}║{Colors.RESET}  {Colors.PURPLE}██{Colors.RESET}   {Colors.PURPLE}██{Colors.RESET} {Colors.BLUE}██████{Colors.RESET} {Colors.GREEN}██████{Colors.RESET}  {Colors.CYAN}██████{Colors.RESET} {Colors.YELLOW}███████{Colors.RESET} {Colors.RED}██████{Colors.RESET}   {Colors.CYAN}║{Colors.RESET}
{Colors.BOLD}{Colors.CYAN}║{Colors.RESET}  {Colors.PURPLE}██{Colors.RESET}   {Colors.PURPLE}██{Colors.RESET} {Colors.BLUE}██{Colors.RESET}  {Colors.BLUE}██{Colors.RESET} {Colors.GREEN}██{Colors.RESET}  {Colors.GREEN}██{Colors.RESET} {Colors.CYAN}██{Colors.RESET}  {Colors.CYAN}██{Colors.RESET} {Colors.YELLOW}██{Colors.RESET}      {Colors.RED}██{Colors.RESET}  {Colors.RED}██{Colors.RESET}  {Colors.CYAN}║{Colors.RESET}
{Colors.BOLD}{Colors.CYAN}║{Colors.RESET}  {Colors.PURPLE}███████{Colors.RESET} {Colors.BLUE}██████{Colors.RESET}  {Colors.GREEN}██████{Colors.RESET}  {Colors.CYAN}██████{Colors.RESET} {Colors.YELLOW}█████{Colors.RESET}   {Colors.RED}██████{Colors.RESET}   {Colors.CYAN}║{Colors.RESET}
{Colors.BOLD}{Colors.CYAN}║{Colors.RESET}  {Colors.PURPLE}██{Colors.RESET}   {Colors.PURPLE}██{Colors.RESET} {Colors.BLUE}██{Colors.RESET}      {Colors.GREEN}██{Colors.RESET}  {Colors.GREEN}██{Colors.RESET} {Colors.CYAN}██{Colors.RESET}  {Colors.CYAN}██{Colors.RESET} {Colors.YELLOW}██{Colors.RESET}      {Colors.RED}██{Colors.RESET}  {Colors.RED}██{Colors.RESET}  {Colors.CYAN}║{Colors.RESET}
{Colors.BOLD}{Colors.CYAN}║{Colors.RESET}  {Colors.PURPLE}██{Colors.RESET}   {Colors.PURPLE}██{Colors.RESET} {Colors.BLUE}██{Colors.RESET}      {Colors.GREEN}██████{Colors.RESET}  {Colors.CYAN}██████{Colors.RESET} {Colors.YELLOW}███████{Colors.RESET} {Colors.RED}██████{Colors.RESET}   {Colors.CYAN}║{Colors.RESET}
{Colors.BOLD}{Colors.CYAN}╠══════════════════════════════════════════════════════════╣{Colors.RESET}
{Colors.BOLD}{Colors.CYAN}║{Colors.RESET}  {Colors.WHITE}ULTIMATE UDP FILE TRANSFER v3.1{Colors.RESET}                        {Colors.CYAN}║{Colors.RESET}
{Colors.BOLD}{Colors.CYAN}║{Colors.RESET}  {Colors.WHITE}Created by 77 - The Architect{Colors.RESET}                          {Colors.CYAN}║{Colors.RESET}
{Colors.BOLD}{Colors.CYAN}╠══════════════════════════════════════════════════════════╣{Colors.RESET}
{Colors.BOLD}{Colors.CYAN}║{Colors.RESET}  {Colors.GREEN}1.{Colors.RESET} Start Server (Receive files)                            {Colors.CYAN}║{Colors.RESET}
{Colors.BOLD}{Colors.CYAN}║{Colors.RESET}  {Colors.GREEN}2.{Colors.RESET} Start Client (Send files)                              {Colors.CYAN}║{Colors.RESET}
{Colors.BOLD}{Colors.CYAN}║{Colors.RESET}  {Colors.GREEN}3.{Colors.RESET} Exit                                                {Colors.CYAN}║{Colors.RESET}
{Colors.BOLD}{Colors.CYAN}╚══════════════════════════════════════════════════════════╝{Colors.RESET}
"""
    
    print(menu)
    
    try:
        choice = input(f"{Colors.YELLOW}Choose option (1-3): {Colors.RESET}").strip()
        
        if choice == '1':
            port = input(f"{Colors.CYAN}Enter port (default 50000): {Colors.RESET}").strip()
            port = int(port) if port else 50000
            server = UDPServer(port=port)
            server.start()
            
        elif choice == '2':
            server_ip = input(f"{Colors.CYAN}Enter server IP: {Colors.RESET}").strip()
            if not server_ip:
                print(f"{Colors.RED}✗ Server IP required{Colors.RESET}")
                return
                
            port = input(f"{Colors.CYAN}Enter port (default 50000): {Colors.RESET}").strip()
            port = int(port) if port else 50000
            
            filepath = input(f"{Colors.CYAN}Enter file path: {Colors.RESET}").strip()
            if not filepath:
                print(f"{Colors.RED}✗ File path required{Colors.RESET}")
                return
                
            streams = input(f"{Colors.CYAN}Parallel streams (default 4): {Colors.RESET}").strip()
            streams = int(streams) if streams else 4
            
            client = UDPClient(server_ip, port, streams)
            client.send_file(filepath)
            
        elif choice == '3':
            print(f"{Colors.YELLOW}Goodbye!{Colors.RESET}")
            sys.exit(0)
            
        else:
            print(f"{Colors.RED}✗ Invalid choice{Colors.RESET}")
            
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Goodbye!{Colors.RESET}")
    except Exception as e:
        print(f"{Colors.RED}Error: {e}{Colors.RESET}")

if __name__ == "__main__":
    main()