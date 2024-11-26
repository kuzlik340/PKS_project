import hashlib
import os
import threading
from datetime import datetime
import time
import hashlib

# Class for managing file transfer from the sender
class FileTransfer:
    def __init__(self):
        # Default init
        self.window_size = 40
        self.window_base = 0
        self.error = False
        self.error_counter = 0
        self.wait_counter = 0
    # This method is used only if number of fragments is smaller than window size
    def update_win(self, win_size):
        self.window_size = win_size

    # This method is used to slide the window
    def increment_base(self):
        self.wait_counter = 0
        self.window_base += 1

    # This method is used to get transfer params
    def get_window_state(self):
        return self.window_base, self.window_size

    # This method is used to set the sequence number of lost or corrupted packet
    def set_error(self, error_num):
        self.error = True
        self.error_counter += 1
        self.window_base = error_num
    def unset_error(self):
        self.error = False
    def check_error(self):
        return self.error

# Function to receive text
def receive_text(packet_handler, keep_alive):
    print("Waiting to receive text...")
    # Here receiving the packet with info of text
    flags, _, _, text_info = packet_handler.receive_packet()
    text_info = text_info.decode()
    text_size_str, _, total_str = text_info.split(':')
    text_size = int(text_size_str)
    total_segments = int(total_str)

    print(f"Size of the text is {text_size} bytes. File will be received in {total_segments} segments")
    # Setting variables before receiving
    expected_seq_num = 0
    received_text = []
    lost_packet_fl = True
    socket = packet_handler.get_socket()
    socket.settimeout(2)
    start_time = time.time()
    while True:
        received = packet_handler.receive_packet()
        # if there were no packets received for 2 seconds
        if not received:

            keep_alive.start()
            start_time_wait = time.time()
            while keep_alive.is_alive is None:
                socket.settimeout(0.5)
                received = packet_handler.receive_packet()
                current_time_wait = time.time()
                if not received and current_time_wait - start_time_wait < 15:
                    continue
                elif current_time_wait - start_time_wait >= 15:
                    keep_alive.stop()
                    socket.settimeout(None)
                    return False
                else:
                    print("\033[1;32mConnection continued!\033[0m")
                    keep_alive.stop()
                    break

        flags, seq_num, checksum_fl, fragment = received
        current_time = datetime.now().strftime("[%H:%M:%S.%f]")

        if expected_seq_num != seq_num:
            # some packet was lost
            if lost_packet_fl:
                print(f"{current_time} Fragment with sequence number {expected_seq_num} was \033[1;31mlost\033[0m")
                lost_packet_fl = False
            continue
        elif not checksum_fl:
            # receiving packet that has wrong checksum
            print(f"{current_time} Fragment with sequence number {seq_num} was received \033[1;31mcorrupted\033[0m")
            expected_seq_num = seq_num
            print(f"Waiting for retransmitting")
            continue
        elif expected_seq_num == seq_num:
            # receiving as normal
            lost_packet_fl = True
            packet_handler.send_packet("TXTACK", b"", seq_num)
            if not "FIN" in flags:
                received_text.append(fragment.decode())
            expected_seq_num = seq_num + 1
            print(f"{current_time} Fragment with sequence number {seq_num} and size {len(fragment)} was received \033[1;32msuccessfully\033[0m")
        if "FIN" in flags:
            print("Text received successfully: ", end = '')
            print("".join(received_text))
            complete_string = ''.join(received_text)
            hashed = hash_sha256(complete_string)
            print(f"Result of hash function on this peer:     {hashed.decode()}")
            print(f"Result of hash function on opposite peer: {fragment.decode()}")
            if hashed == fragment:
                print("Hash control success")
            current_time = time.time()
            print(f"\nTime for receiving was {current_time - start_time}")
            packet_handler.send_packet("TXTACK", b"", seq_num)
            socket.settimeout(None)
            break
    return True


def send_text(packet_handler, keep_alive):
    file_transfer_manager = FileTransfer()
    packet_handler.send_packet("TXT", b"", 0)
    print("Put your message here:", end="", flush=True)
    text = input()
    file_name = "message.txt"
    with open(file_name, "w", encoding="utf-8") as file:
        file.write(text)

    receive_ack_flag = threading.Event()
    first_ack = threading.Event()
    first_ack.set()
    receive_acks_thread = threading.Thread(target=data_ack_recv,
                                           args=(file_transfer_manager, packet_handler, receive_ack_flag, first_ack, keep_alive))
    receive_acks_thread.daemon = True
    receive_acks_thread.start()

    next_seq_num, window, total_sent_packets = gbn(packet_handler, file_transfer_manager, file_name, "TXT", first_ack, keep_alive)

    receive_ack_flag.set()
    hashed = hash_sha256(text)
    packet_handler.send_packet("TXTFIN", hashed, next_seq_num)
    print("Text transfer completed.")
    print(f"Number of total sent segments = {total_sent_packets + 1}")
    receive_acks_thread.join()
    try:
        os.remove(file_name)
    except Exception as e:
        print(f"Failed to delete the file. Error: {e}")


def receive_data(packet_handler, keep_alive):
    output_dir = input("Please put a directory where you want to save files")
    packet_handler.send_packet("DATAACK", b"", 0)
    os.makedirs(output_dir, exist_ok=True)
    # Receiving file information (filename:size of file)
    flags, _, _, file_info = packet_handler.receive_packet()
    file_info = file_info.decode()
    file_size_str, filename, total_str = file_info.split(':')
    file_size = int(file_size_str)
    total_segments = int(total_str)
    print(f"File {filename} will be saved on this path {output_dir}/{filename}")
    print(f"Size of the file is {file_size} bytes. File will be received in {total_segments} segments")
    # Creating a path where we will store the input DATA
    output_path = os.path.join(output_dir, filename)
    packet_handler.get_socket().settimeout(2)
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
                    start_time_wait = time.time()
                    while keep_alive.is_alive is None:
                        socket.settimeout(0.5)
                        received = packet_handler.receive_packet()
                        current_time_wait = time.time()
                        if not received and current_time_wait - start_time_wait < 15:
                            continue
                        elif current_time_wait - start_time_wait >= 15:
                            keep_alive.stop()
                            socket.settimeout(None)
                            return False
                        else:
                            print("Connection continued!")
                            keep_alive.stop()
                            break


                flags, seq_num, checksum_fl, fragment = received
                current_time = datetime.now().strftime("[%H:%M:%S.%f]")
                if expected_seq_num != seq_num:
                    if lost_packet_fl:
                        print("SENDING NACK DUE TO LOST PACKET")
                        packet_handler.send_packet("DATAERR", b"", expected_seq_num)
                        print(f"{current_time} Fragment with sequence number {expected_seq_num} was \033[1;31mlost\033[0m")
                        lost_packet_fl = False
                    continue
                elif not checksum_fl:
                    lost_packet_fl = False
                    print("SENDING NACK DUE TO CORRUPTED PACKET")
                    packet_handler.send_packet("DATAERR", b"", seq_num)
                    print(f"{current_time} Fragment with sequence number {seq_num} was received \033[1;31mcorrupted\033[0m")
                    expected_seq_num = seq_num
                    print(f"Waiting for retransmitting")
                    continue
                elif expected_seq_num == seq_num:
                    lost_packet_fl = True
                    file.write(fragment)
                    received_size += len(fragment)
                    expected_seq_num = seq_num + 1
                    packet_handler.send_packet("DATAACK", b"", seq_num)
                    print(f"{current_time} Fragment with sequence number {seq_num} and size {len(fragment)} bytes was received \033[1;32msuccessfully\033[0m")
                if "FIN" in flags:
                    current_time = time.time()
                    print(f"File {filename} received successfully and saved to {output_path} with time {current_time - start_time}")
                    packet_handler.send_packet("DATAACK", b"", seq_num)
                    socket.settimeout(None)
                    break
    return True


def data_ack_recv(file_transfer_manager, packet_handler, receive_ack_flag, first_ack, keep_alive):
    while not receive_ack_flag.is_set():
        flags, fragment_num, *_ = packet_handler.receive_packet()
        if ("DATA" in flags or "TXT" in flags) and "ACK" in flags:
            if not first_ack.is_set():
                first_ack.set()
                continue
            file_transfer_manager.increment_base()
        if ("DATA" in flags or "TXT" in flags) and "ERR" in flags:
            print("NACK received. Starting from win_base")
            file_transfer_manager.set_error(fragment_num)
        if "KEA" in flags:
            keep_alive.acknowledge()
            print("Its alive!!!!")


def send_data(packet_handler, keep_alive):
    file_transfer_manager = FileTransfer()
    packet_handler.send_packet("DATA", b"", 0)
    receive_ack_flag = threading.Event()
    first_ack = threading.Event()
    receive_acks_thread = threading.Thread(target=data_ack_recv,
                                           args=(file_transfer_manager, packet_handler, receive_ack_flag, first_ack, keep_alive))
    receive_acks_thread.daemon = True
    receive_acks_thread.start()
    print("\nEnter the path to the file you want to send: ", end="")
    file_path = input()
    while not os.path.isfile(file_path):
        print("File not found. Please check the path and try again.")
        file_path = input()

    next_seq_num, window, total_sent_packets = gbn(packet_handler, file_transfer_manager, file_path, "DATA", first_ack, keep_alive)
    receive_ack_flag.set()
    packet_handler.send_packet("DATAFIN", b"", next_seq_num)
    print(f"Last segment was sent with size = 0 and with seq num = {next_seq_num}")
    print(f"Number of total sent segments = {total_sent_packets+1}")
    receive_acks_thread.join()

def adaptive_window(file_transfer_manager, total_fragments):
    _, window_size = file_transfer_manager.get_window_state()
    num_errors = file_transfer_manager.error_counter
    perc =  num_errors / total_fragments
    if perc < 0.03:
        window_size *= 1.07
        if window_size > 400:
            window_size = 400
        file_transfer_manager.update_win(int(window_size))
        return
    else:
        window_size *= 0.95
        if window_size < 15:
            window_size = 15
        file_transfer_manager.update_win(int(window_size))
        return

def hash_sha256(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest().encode()



def gbn(packet_handler, file_transfer_manager, file_path, flag, first_ack, keep_alive):
    fragment_size = packet_handler.fragment_size
    file_size = os.path.getsize(file_path)
    file_name = os.path.basename(file_path)
    last_seq = (file_size + fragment_size - 1) // fragment_size
    message = str(file_size) + ':' + file_name + ':' + str(last_seq)
    if "DATA" in flag:
        print(f"File {file_name} from this directory {file_path} will be sent in {last_seq} segments")
        print(f"Size of file = {file_size}. Size of segments = {fragment_size}")
        while not first_ack.is_set():
            pass
    else:
        print(f"Text with size {file_size} be sent in {last_seq} fragments.")
        first_ack.set()
    packet_handler.send_packet(flag, message.encode(), 0)
    # if number of total segments is smaller then window
    win_base, window_size = file_transfer_manager.get_window_state()
    if window_size > last_seq:
        window_size = last_seq
        file_transfer_manager.update_win(window_size)
    print(f"Sending file in {last_seq} segments.")
    next_seq_num = 0
    win_base, window_size = file_transfer_manager.get_window_state()
    total_sent_packets = 0
    with open(file_path, 'rb') as file:
        while win_base < last_seq:
            if next_seq_num == last_seq:
                win_base, window_size = file_transfer_manager.get_window_state()
                time.sleep(0.01)
                continue
            file_offset = next_seq_num * fragment_size
            file.seek(file_offset)
            segment_data = file.read(fragment_size)
            packet_handler.send_packet(flag, segment_data, next_seq_num)
            current_time = datetime.now().strftime("[%H:%M:%S.%f]")
            print(f"{current_time} Packet {next_seq_num} was sent win_base = {win_base} and window_size = {window_size}")
            if len(segment_data) < 150:
                time.sleep(0.03)
            total_sent_packets += 1
            # Check for win_base or window_size changing
            win_base, window_size = file_transfer_manager.get_window_state()
            next_seq_num += 1
            adaptive_window(file_transfer_manager, total_sent_packets)
            if window_size == 1 and win_base == 1:
                return 1, window_size, total_sent_packets
            if file_transfer_manager.check_error():
                next_seq_num, _ = file_transfer_manager.get_window_state()
                file_transfer_manager.unset_error()
            if next_seq_num == win_base + window_size:
                file_transfer_manager.wait_counter += 1
                if file_transfer_manager.wait_counter > 2:
                    keep_alive.start()
                    print("Starting keep alive")
                    while keep_alive.is_alive is None:
                        time.sleep(0.1)
                        pass
                    if not keep_alive.is_alive:
                        keep_alive.stop()
                        print("Broken connection. Shutting down...")
                        exit(1)
                    else:
                        keep_alive.stop()
                        print("Continue transmitting")
                        file_transfer_manager.wait_counter = 0
                        continue
                next_seq_num = win_base
    file_transfer_manager.wait_counter = 0
    return next_seq_num, window_size, total_sent_packets





