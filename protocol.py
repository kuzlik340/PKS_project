import struct


def sending_packet(flags, message, sock, ip_opp_peer, port_opp_peer_receive):
    flags_to_send = 0b00000000
    # encoding the flags into bits
    if "SYN" in flags: #synchronisation
        flags_to_send |= 0b00000001
    if "ACK" in flags: #confirmation
        flags_to_send |= 0b00000010
    if "ERR" in flags: #damaged packet
        flags_to_send |= 0b00000100
    if "FIN" in flags: #final file in sequence
        flags_to_send |= 0b00001000
    if "EXIT" in flags: #exit connection
        flags_to_send |= 0b00010000
    if "DATA" in flags: #segmented data
        flags_to_send |= 0b00100000
    if "TXT" in flags: #txt message
       flags_to_send |= 0b01000000
    if "KEA" in flags: #keep-alive packet
        flags_to_send |= 0b10000000
    sequence_num = 0
    acknowledgement_num = 0
    checksum = 0
    length = len(message)
    window = 0
    packet = (struct.pack(
        '!II', sequence_num, acknowledgement_num
    )) + (struct.pack('!BHHB', flags_to_send, length, checksum, window))

    packet += message
    sock.sendto(packet, (ip_opp_peer, port_opp_peer_receive))


def receiving_messages(sock):
    header_size = 14
    packet, (ip_opp_peer_fr, port) = sock.recvfrom(1450)

    header = packet[:header_size]

    # unpacking header
    sequence_num = int.from_bytes(header[0:4], 'big')  # 3 байта: Message ID (24 бита)
    acknowledgement_num = int.from_bytes(header[4:8], 'big')
    flags_to_receive = struct.unpack('!B', header[8:9])[0]
    length = int.from_bytes(header[9:11], 'big')
    checksum = int.from_bytes(header[11:13], 'big')
    window = header[13]


    # decode payload
    message = packet[header_size:].decode()  # Полезная нагрузка - после заголовка
    # decode flags
    flags = ""
    if flags_to_receive & 0b00000001:
        flags += "SYN"
    if flags_to_receive & 0b00000010:
        flags += "ACK"
    if flags_to_receive & 0b00000100:
        flags += "ERR"
    if flags_to_receive & 0b00001000:
        flags += "FIN"
    if flags_to_receive & 0b00010000:
        flags += "EXIT"
    if flags_to_receive & 0b00100000:
        flags += "DATA"
    if flags_to_receive & 0b01000000:
        flags += "TXT"
    if flags_to_receive & 0b10000000:
        flags += "KEA"


    return flags, sequence_num, length, acknowledgement_num, checksum, window, ip_opp_peer_fr, message



