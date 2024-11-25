import os
import threading
from datetime import datetime
import time

class FileTransfer:
    def __init__(self):
        # Initialize the last acknowledged packet to None or -1 if using sequence numbers
        self.window_size = 255
        self.window_base = 0
        self.error = False
        self.error_num = -1
    def update_base(self, win_base):
        self.window_base = win_base
    def update_win(self, win_size):
        self.window_size = win_size
    def increment_base(self):
        self.window_base += 1
    def get_window_state(self):
        return self.window_base, self.window_size
    def set_error_num(self, error_num):
        self.error_num = error_num
        self.error = True
    def check_error(self):
        return self.error
    def get_error_num(self):
        self.error = False
        return self.error_num
    def set_win_base(self, window_base):
        self.window_base = window_base


def receive_text(packet_handler, keep_alive):
    print("Waiting to receive text...")
    flags, _, _, _, window, text_info = packet_handler.receive_packet()
    text_info = text_info.decode()
    text_size_str, total_str = text_info.split(':')
    text_size = int(text_size_str)
    total_segments = int(total_str)
    print(f"Size of the text is {text_size} bytes. File will be received in {total_segments} segments")
    expected_seq_num = 0
    received_text = []
    lost_packet_fl = True
    socket = packet_handler.get_socket()
    socket.settimeout(2)

    while True:
        received = packet_handler.receive_packet()
        if not received:
            keep_alive.start()
            while keep_alive.is_alive is None:
                pass
            if not keep_alive.is_alive:
                socket.settimeout(None)
                return
            else:
                continue

        flags, seq_num, _, checksum_fl, _, fragment = received
        current_time = datetime.now().strftime("[%H:%M:%S.%f]")

        if expected_seq_num != seq_num:
            if lost_packet_fl:
                print(f"{current_time} Fragment with sequence number {expected_seq_num} was \033[1;31mlost\033[0m")
                lost_packet_fl = False
            continue
        elif not checksum_fl:
            print(f"{current_time} Fragment with sequence number {seq_num} was received \033[1;31mcorrupted\033[0m")
            expected_seq_num = seq_num
            print(f"Waiting for retransmitting")
            continue
        elif expected_seq_num == seq_num:
            lost_packet_fl = True
            received_text.append(fragment.decode())
            expected_seq_num = seq_num + 1
            packet_handler.send_packet("TXTACK", b"", seq_num, 1)
            print(f"{current_time} Fragment with sequence number {seq_num} and size {len(fragment)} was received \033[1;32msuccessfully\033[0m")
        if "FIN" in flags:
            print("Text received successfully:")
            current_time = time.time()
            print("Time for receiving")
            print("".join(received_text))
            packet_handler.send_packet("TXTACK", b"", seq_num, 1)
            socket.settimeout(None)
            break


def send_text(packet_handler):
    fragment_size = packet_handler.fragment_size
    file_transfer_manager = FileTransfer()
    packet_handler.send_packet("TXT", b"", 0, 1)
    print("Put your message here:", end="", flush=True)
    text = input()
    receive_ack_flag = threading.Event()
    first_ack = threading.Event()
    first_ack.set()
    receive_acks_thread = threading.Thread(target=data_ack_recv,
                                           args=(file_transfer_manager, packet_handler, receive_ack_flag, first_ack))
    receive_acks_thread.daemon = True
    receive_acks_thread.start()
    total_fragments = (len(text) + fragment_size - 1) // fragment_size
    message = f"{len(text)}:{total_fragments}"
    print(f"Sending text in {total_fragments} fragments")
    packet_handler.send_packet("TXT", message.encode(), 0, file_transfer_manager.window_size)
    next_seq_num = 0
    win_base, window_size = file_transfer_manager.get_window_state()
    if total_fragments < window_size:
        window_size = total_fragments-1
        file_transfer_manager.update_win(window_size)
    while win_base < total_fragments:
        fragment = text[next_seq_num * fragment_size: (next_seq_num + 1) * fragment_size]
        if fragment_size < 150:
            time.sleep(0.01)
        if next_seq_num == total_fragments:
            continue
        packet_handler.send_packet("TXT", fragment.encode(), next_seq_num, file_transfer_manager.window_size)
        next_seq_num += 1
        win_base, window_size = file_transfer_manager.get_window_state()
        print(f"Fragment was sent win_base = {win_base} and next_seq_num = {next_seq_num}")

        if next_seq_num == win_base + window_size:
            print("Corrupted packet")
            next_seq_num = win_base

    receive_ack_flag.set()
    packet_handler.send_packet("TXTFIN", b"", next_seq_num, file_transfer_manager.window_size)
    print("Text transfer completed.")
    receive_acks_thread.join()


#todo create reconnecting with peer on send_data (both for MAC os and Linux)
def receive_data(packet_handler, keep_alive):
    output_dir = input("Please put a directory where you want to save files")
    packet_handler.send_packet("DATAACK", b"", 0, 1)
    os.makedirs(output_dir, exist_ok=True)
    # Receiving file information (filename:size of file)
    flags, _, _, _, window, file_info = packet_handler.receive_packet()
    file_info = file_info.decode()
    file_size_str, filename, total_str = file_info.split(':')
    file_size = int(file_size_str)
    total_segments = int(total_str)
    print(f"File {filename} will be saved on this path {output_dir}/{filename}")
    print(f"Size of the file is {file_size} bytes. File will be received in {total_segments} segments")
    # Creating a path where we will store the input DATA
    output_path = os.path.join(output_dir, filename)

    socket = packet_handler.get_socket()
    expected_seq_num = 0
    start_time = time.time()
    if "DATA" in flags:
        # Opening file as binary to store data by segments
        received_size = 0
        lost_packet_fl = True
        with open(output_path, "wb") as file:
            while True:
                received = packet_handler.receive_packet()
                if not received:
                    keep_alive.start()
                    while keep_alive.is_alive is None:
                        pass
                    if not keep_alive.is_alive:
                        return
                    else:
                        continue
                flags, seq_num, _, checksum_fl, _, fragment = received
                current_time = datetime.now().strftime("[%H:%M:%S.%f]")
                if expected_seq_num != seq_num:
                    if lost_packet_fl:
                        print("SENDING NACK DUE TO LOST PACKET")
                        packet_handler.send_packet("DATAERR", b"", expected_seq_num, 1)
                        print(f"{current_time} Fragment with sequence number {expected_seq_num} was \033[1;31mlost\033[0m")
                        lost_packet_fl = False
                    continue
                elif not checksum_fl:
                    lost_packet_fl = False
                    print("SENDING NACK DUE TO CORRUPTED PACKET")
                    packet_handler.send_packet("DATAERR", b"", seq_num, 1)
                    print(f"{current_time} Fragment with sequence number {seq_num} was received \033[1;31mcorrupted\033[0m")
                    expected_seq_num = seq_num
                    print(f"Waiting for retransmitting")
                    continue
                elif expected_seq_num == seq_num:
                    lost_packet_fl = True
                    file.write(fragment)
                    received_size += len(fragment)
                    expected_seq_num = seq_num + 1
                    packet_handler.send_packet("DATAACK", b"", seq_num, 1)
                    print(f"{current_time} Fragment with sequence number {seq_num} and size {len(fragment)} bytes was received \033[1;32msuccessfully\033[0m")
                    # if seq_num % 100 == 0:
                    #     print(f"Packet received, seq_num = {seq_num}")
                if "FIN" in flags:
                    current_time = time.time()
                    print(f"File {filename} received successfully and saved to {output_path} with time {current_time - start_time}")
                    packet_handler.send_packet("DATAACK", b"", seq_num, 1)
                    socket.settimeout(None)
                    break



def data_ack_recv(file_transfer_manager, packet_handler, receive_ack_flag, first_ack):
    while not receive_ack_flag.is_set():
        flags, fragment_num, *_ = packet_handler.receive_packet()
        if ("DATA" in flags or "TXT" in flags) and "ACK" in flags:
            if not first_ack.is_set():
                first_ack.set()
                continue
            file_transfer_manager.increment_base()
        if ("DATA" in flags or "TXT" in flags) and "ERR" in flags:
            print("NACK received. Starting from win_base")
            file_transfer_manager.set_error_num(fragment_num)


def send_data(packet_handler, keep_alive):
    fragment_size = packet_handler.fragment_size
    file_transfer_manager = FileTransfer()
    packet_handler.send_packet("DATA", b"", 0, 1)
    receive_ack_flag = threading.Event()
    first_ack = threading.Event()
    receive_acks_thread = threading.Thread(target=data_ack_recv,
                                           args=(file_transfer_manager, packet_handler, receive_ack_flag, first_ack))
    receive_acks_thread.daemon = True
    receive_acks_thread.start()
    print("\nEnter the path to the file you want to send: ", end="")
    file_path = input()
    window = 100
    if not os.path.isfile(file_path):
        print("File not found. Please check the path and try again.")
        return

    file_size = os.path.getsize(file_path)
    file_name = os.path.basename(file_path)
    last_seq = (file_size + fragment_size - 1) // fragment_size
    message = str(file_size) + ':' + file_name + ':' + str(last_seq)
    print(f"File {file_name} from this directory {file_path} will be sent in {last_seq} segments")
    print(f"Size of file = {file_size}")
    while not first_ack.is_set():
        pass
    packet_handler.send_packet("DATA", message.encode(), 0, window)

    last_seq = (file_size + fragment_size - 1) // fragment_size
    # if number of total segments is smaller then window
    if window > last_seq:
        window = last_seq
        file_transfer_manager.update_win(window)
    print(f"Sending file in {last_seq} segments.")
    next_seq_num = 0
    win_base, window_size = file_transfer_manager.get_window_state()
    with open(file_path, 'rb') as file:
        while win_base < last_seq:
            win_base, window_size = file_transfer_manager.get_window_state()
            if next_seq_num == last_seq:
                continue
            if fragment_size < 150:
                time.sleep(0.01)
            file_offset = next_seq_num * fragment_size
            file.seek(file_offset)
            segment_data = file.read(fragment_size)

            packet_handler.send_packet("DATA", segment_data, next_seq_num, window)
            print(f"Packet {next_seq_num} was sent win_base = {win_base} and next_seq_num = {next_seq_num}")
            next_seq_num += 1
            if file_transfer_manager.check_error():
                next_seq_num = file_transfer_manager.get_error_num()
                print(f"WHILE ERROR NEXT PACKET WILL HAVE NUMBER = {next_seq_num}")
                file_transfer_manager.set_win_base(next_seq_num)
            if next_seq_num == win_base + window_size:
                keep_alive.start()
                while keep_alive.is_alive is None:
                    pass
                if not keep_alive.is_alive:
                    receive_ack_flag.set()
                    print("Broken connection. Shutting down...")
                    receive_acks_thread.join()
                    exit(1)
                else:
                    continue

        receive_ack_flag.set()
        packet_handler.send_packet("DATAFIN", b"", next_seq_num, window)
        print(f"Last segment was sent with size = {len(segment_data)} and with seq num = {next_seq_num}")
        receive_acks_thread.join()







