import struct
import socket

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
        print("Segment is damaged")
        return False


class PacketHandler:
    def __init__(self, sock, ip_opp_peer, port_opp_peer_receive):
        self.sock = sock
        self.ip_opp_peer = ip_opp_peer
        self.port_opp_peer_receive = port_opp_peer_receive

    def get_socket(self):
        return self.sock

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
        acknowledgement_num = 0
        checksum = create_checksum(message)
        length = len(message)
        packet = (struct.pack(
            '!II', sequence_num, acknowledgement_num
        )) + (struct.pack('!BHHB', flags_to_send, length, checksum, window))

        packet += message
        self.sock.sendto(packet, (self.ip_opp_peer, self.port_opp_peer_receive))

    def receive_packet(self):
        header_size = 14
        try:
            packet, (ip_opp_peer_fr, port) = self.sock.recvfrom(1450) #maybe 1500??
        except socket.timeout:
            print("Timeout reached: No response received within 15 seconds.")
            return False

        header = packet[:header_size]
        # Unpacking message
        sequence_num = int.from_bytes(header[0:4], 'big')
        acknowledgement_num = int.from_bytes(header[4:8], 'big')
        flags_to_receive = struct.unpack('!B', header[8:9])[0]
        length = int.from_bytes(header[9:11], 'big')
        received_checksum = int.from_bytes(header[11:13], 'big')
        window = header[13]

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
        return flags, sequence_num, length, acknowledgement_num, check_checksum_flag, window, ip_opp_peer_fr, message
