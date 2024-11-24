import os
import threading
from datetime import datetime
import time

class FileTransfer:
    def __init__(self):
        # Initialize the last acknowledged packet to None or -1 if using sequence numbers
        self.window_size = 100
        self.window_base = 0
    def update_base(self, win_base):
        self.window_base = win_base
    def update_win(self, win_size):
        self.window_size = win_size
    def increment_base(self):
        self.window_base += 1
    def get_window_state(self):
        return self.window_base, self.window_size



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
    if "DATA" in flags:
        # Opening file as binary to store data by segments
        received_size = 0
        lost_packet_fl = True
        socket.settimeout(2)
        with open(output_path, "wb") as file:
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
                    file.write(fragment)
                    received_size += len(fragment)
                    expected_seq_num = seq_num + 1
                    packet_handler.send_packet("DATAACK", b"", seq_num, 1)
                    print(f"{current_time} Fragment with sequence number {seq_num} and size {len(fragment)} bytes was received \033[1;32msuccessfully\033[0m")
                    # if seq_num % 100 == 0:
                    #     print(f"Packet received, seq_num = {seq_num}")
                if "FIN" in flags:
                    print(f"File {filename} received successfully and saved to {output_path}")
                    packet_handler.send_packet("DATAACK", b"", seq_num, 1)
                    socket.settimeout(None)
                    break
                # set flag to send the acknowledgement from sending thread



def data_ack_recv(file_transfer_manager, packet_handler, receive_ack_flag, first_ack):
    while not receive_ack_flag.is_set():
        flags, *_ = packet_handler.receive_packet()
        if "DATA" in flags and "ACK" in flags:
            if not first_ack.is_set():
                first_ack.set()
                continue
            file_transfer_manager.increment_base()



def send_data(packet_handler):
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

    while True:
        segment_size = int(input("What size of segment you want to use? (choose from 1 to 1490): "))
        if segment_size <= 0 or segment_size > 1490:
            print("Invalid segment size")
            continue
        break

    file_size = os.path.getsize(file_path)
    file_name = os.path.basename(file_path)
    last_seq = (file_size + segment_size - 1) // segment_size
    message = str(file_size) + ':' + file_name + ':' + str(last_seq)
    print(f"File {file_name} from this directory {file_path} will be sent in {last_seq} segments")
    print(f"Size of file = {file_size}")
    while not first_ack.is_set():
        pass
    packet_handler.send_packet("DATA", message.encode(), 0, window)

    last_seq = (file_size + segment_size - 1) // segment_size
    # if number of total segments is smaller then window
    if window > last_seq:
        window = last_seq
    print(f"Sending file in {last_seq} segments.")
    next_seq_num = 0
    wind_changed = False
    win_base, window_size = file_transfer_manager.get_window_state()
    with open(file_path, 'rb') as file:
        while win_base < last_seq:
            file_offset = next_seq_num * segment_size
            file.seek(file_offset)
            segment_data = file.read(segment_size)
            if window_size >= last_seq - win_base and not wind_changed:
                wind_changed = True
                print(f"window change due to end = {last_seq - win_base}")
                window_size = last_seq - win_base
                file_transfer_manager.update_win(window_size)

            packet_handler.send_packet("DATA", segment_data, next_seq_num, window)

            next_seq_num += 1
            win_base, window_size = file_transfer_manager.get_window_state()
            print(f"Packet was sent win_base = {win_base} and next_seq_num = {next_seq_num}")
            if next_seq_num == win_base + window_size:
                print("Corrupted packet")
                next_seq_num = win_base
        receive_ack_flag.set()
        packet_handler.send_packet("DATAFIN", b"", next_seq_num, window)
        print(f"Last segment was sent with size = {len(segment_data)} and with seq num = {next_seq_num}")
        receive_acks_thread.join()







