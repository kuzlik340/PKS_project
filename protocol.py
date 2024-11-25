import struct
import socket
import random


def fletcher(data: bytes) -> int:
    sum1 = 0
    sum2 = 0
    for byte in data:
        sum1 = (sum1 + byte) % 255
        sum2 = (sum2 + sum1) % 255
    return (sum2 << 8) | sum1

def create_checksum(payload):
    return fletcher(payload)

def check_checksum(payload: bytes, received_checksum):
    if fletcher(payload) == received_checksum:
        return True
    else:
        return False

def damage_segment(checksum):
    if random.random() > 0.998:
        print("Packet was damaged")
        return 1234
    else:
        return checksum


class PacketHandler:
    def __init__(self, sock, ip_opp_peer, port_opp_peer_receive):
        self.sock = sock
        self.ip_opp_peer = ip_opp_peer
        self.port_opp_peer_receive = port_opp_peer_receive
        self.fragment_size = 1460
        self.damage = False
    def get_socket(self):
        return self.sock

    def set_fragment_size(self, fragment_size):
        self.fragment_size = fragment_size

    def set_damage(self, damage):
        self.damage = damage
    def socket_close(self):
        self.sock.close()

    def send_packet(self, flags, message, sequence_num, window):
        flags_to_send = 0b00000000
        # Encoding the flags into bits
        if "SYN" in flags:
            flags_to_send |= 0b00000001
        if "ACK" in flags:
            flags_to_send |= 0b00000010
        if "ERR" in flags:
            flags_to_send |= 0b00000100
        if "FIN" in flags:
            flags_to_send |= 0b00001000
        if "EXIT" in flags:
            flags_to_send |= 0b00010000
        if "DATA" in flags:
            flags_to_send |= 0b00100000
        if "TXT" in flags:
            flags_to_send |= 0b01000000
        if "KEA" in flags:
            flags_to_send |= 0b10000000
        checksum = create_checksum(message)
        if self.damage:
            checksum = damage_segment(checksum)
        length = len(message)
        packet = (struct.pack(
            '!I', sequence_num)) + (struct.pack('!BHHB', flags_to_send, length, checksum, window))

        packet += message
        if random.random() > 0.999 and self.damage:
            print("Packet was lost")
            return False
        try:
            self.sock.sendto(packet, (self.ip_opp_peer, self.port_opp_peer_receive))
        except OSError as e:
            return False
        return True

    def receive_packet(self):
        header_size = 10
        try:
            packet, _ = self.sock.recvfrom(1500) #maybe 1500??
        except socket.timeout:
            print("Timeout reached: No response received within 5 seconds.")
            return False

        header = packet[:header_size]
        # Unpacking message
        sequence_num = int.from_bytes(header[0:4], 'big')
        flags_to_receive = struct.unpack('!B', header[4:5])[0]
        length = int.from_bytes(header[5:7], 'big')
        received_checksum = int.from_bytes(header[7:9], 'big')
        window = header[9]

        message = packet[header_size:]  # Decode payload
        # Decode flags
        flags = ""
        if flags_to_receive & 0b00000001: flags += "SYN"
        if flags_to_receive & 0b00000010: flags += "ACK"
        if flags_to_receive & 0b00000100: flags += "ERR"
        if flags_to_receive & 0b00001000: flags += "FIN"
        if flags_to_receive & 0b00010000: flags += "EXIT"
        if flags_to_receive & 0b00100000: flags += "DATA"
        if flags_to_receive & 0b01000000: flags += "TXT"
        if flags_to_receive & 0b10000000: flags += "KEA"

        check_checksum_flag = check_checksum(message, received_checksum)
        return flags, sequence_num, length, check_checksum_flag, window, message
