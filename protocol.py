import socket
import struct

message_id = 0 #overload after 2 000 000 000 messages

def sending_packet(flags, message, sock, ip_opp_peer, port_opp_peer_receive):
    global message_id
    message_id += 1
    flags_to_send = 0b00000000
    #creating flags
    if "SYN" in flags:
        flags_to_send |= 0b00000001
    if "ACK" in flags:
        flags_to_send |= 0b00000010
    if "ERR" in flags:
        flags_to_send |= 0b00000100
    if "FIN" in flags: #final file
        flags_to_send |= 0b00001000
    if "EXIT" in flags: #exit connection
        flags_to_send |= 0b00010000
    if "DATA" in flags:
        flags_to_send |= 0b00100000
    if "TXT" in flags:
       flags_to_send |= 0b01000000
    if "KEA" in flags:
        flags_to_send |= 0b10000000
    message_id = message_id & 0xFFFFFF
    fragment_offset = 0
    total_length = 0
    seg_num = 0
    checksum = 0
    length = len(message)

    packet = \
    (struct.pack(
        '!B', flags_to_send  # 1 байт: Флаги
    ) + message_id.to_bytes(3, 'big') +
    struct.pack(
        '!HHBHH',  # Упаковываем остальные поля:
        fragment_offset,  # 2 байта: Fragment Offset
        total_length,  # 2 байта: Total Length
        seg_num,  # 1 байт: Segment Number
        checksum,  # 2 байта: Checksum (нулевой, если не реализована проверка)
        length  # 2 байта: Length сообщения
    ))

    packet += message
    sock.sendto(packet, (ip_opp_peer, port_opp_peer_receive))


def receiving_messages(sock):
    # Предположим, что размер заголовка фиксирован (1 байт флагов + 3 байта message_id + остальные поля)
    header_size = 13

    # Ожидаем получения пакета
    packet, addr = sock.recvfrom(1024)  # Получаем пакет, допустим, до 1024 байт

    # Извлекаем заголовок
    header = packet[:header_size]

    # Распаковываем заголовок
    flags_to_receive = struct.unpack('!B', header[:1])[0]  # 1 байт: Flags
    message_id = int.from_bytes(header[1:4], 'big')  # 3 байта: Message ID (24 бита)
    fragment_offset, total_length, seg_num, checksum, length = struct.unpack('!HHBHH', header[4:13])


    # Извлекаем сообщение (payload)
    message = packet[header_size:].decode()  # Полезная нагрузка - после заголовка
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


    return flags, message_id, fragment_offset, total_length, seg_num, checksum, message



