import psutil
import socket
import threading
import select
import sys
import protocol
import os

# utility function that just finds peer IPs so you can see them and write them directly to the input of program
def get_all_ip_addresses():
    ip_list = []
    for interface_name, interface_addresses in psutil.net_if_addrs().items():
        for address in interface_addresses:
            if address.family == socket.AF_INET and address.address != "127.0.0.1":
                ip_list.append(address.address)
    return ip_list


def receive_file(sock, ack_send, output_dir="received_files"):
    os.makedirs(output_dir, exist_ok=True)

    # Сначала получаем метаданные файла
    flags, _, _, _, _, _, _, file_info = protocol.receiving_messages(sock)
    file_info = file_info.decode()

    # Метаданные содержат имя файла и общий размер
    filename, file_size = file_info.split(":")
    file_size = int(file_size)

    # Путь, куда будем сохранять файл
    output_path = os.path.join(output_dir, filename)

    window = 5

    if "DATA" in flags:
        # Открываем файл на запись в бинарном режиме
        received_size = 0
        with open(output_path, "wb") as f:
            while True:
                window_increment = 0
                while window_increment < window:
                    # Принимаем фрагмент данных
                    flags, _, _, _, _, win, _, fragment = protocol.receiving_messages(sock)  # Получаем данные, размер буфера можно настроить
                    window_increment += 1
                    # Если фрагмент пустой, завершаем цикл
                    if "FIN" in flags:
                        print(f"File {filename} received successfully and saved to {output_path}")
                        ack_send.set()
                        f.write(fragment)
                        received_size += len(fragment)
                        while True:
                            if not ack_send.is_set():
                                break
                        return
                    if "DATA" in flags:
                        f.write(fragment)
                        received_size += len(fragment)
                        print(f"Received {received_size}/{file_size} bytes")

                ack_send.set()
                while True:
                    if not ack_send.is_set():
                        break



def send_data(sock, ip_opp_peer, port_opp_peer_receive, acknowledge_data_wait):
    protocol.sending_packet("DATA", b"", sock, ip_opp_peer, port_opp_peer_receive, 0, 1)
    file_path = input("Enter the path to the file you want to send: ")
    window = 5
    window_increment = 0

    if not os.path.isfile(file_path):
        print("File not found. Please check the path and try again.")
        return

    segment_size = int(input("What size of segment you want to use? (choose from 1 to 1400): "))
    if segment_size <= 0 or segment_size > 1400:
        print("Invalid segment size")
        return


    file_size = os.path.getsize(file_path)
    print(file_size)
    file_name = os.path.basename(file_path)
    print(file_name)
    file_info = file_name + ":" + str(file_size)
    print(file_info)
    protocol.sending_packet("DATA", file_info.encode(), sock, ip_opp_peer, port_opp_peer_receive, 0, 1)

    total_segments = (file_size + segment_size - 1) // segment_size  # Округление вверх
    if window > total_segments:
        window = total_segments
    print(f"Sending file in {total_segments} segments.")
    seq_num = 0
    iteration_windows = total_segments // window
    with open(file_path, 'rb') as file:
        for i in range(iteration_windows):
            while window_increment < window:
                if total_segments - (i * window) < window:
                    print("TOTAL" + str(total_segments - (i * window)))
                    window = total_segments - (i * window)
                segment_data = file.read(segment_size)
                if seq_num == total_segments - 1:
                    protocol.sending_packet("DATAFIN", segment_data, sock, ip_opp_peer, port_opp_peer_receive, seq_num,
                                            window)
                    break
                protocol.sending_packet("DATA", segment_data, sock, ip_opp_peer, port_opp_peer_receive, seq_num, window)
                window_increment += 1
                seq_num += 1
            while True:
                if acknowledge_data_wait.is_set():
                    acknowledge_data_wait.clear()
                    window_increment = 0
                    print("DATAACK received")
                    break
    return


# function that makes the input function in the sending_message not blocking so code can handle the situation
# when EXIT was initiated from another peer
def non_blocking_input(timeout):
    ready, _, _ = select.select([sys.stdin], [], [], timeout)
    if ready:
        print("Put your message here:", end ="", flush=True)
        return sys.stdin.readline().strip()
    else:
        return None

# function to send all data, currently only text messages from terminal
def sending_messages(sock, ip_opp_peer, port_opp_peer_receive, exit_ev, keep_alv_wait_answ, keep_alv_received, exit_by_brok, acknowledge_data_wait, keep_alv_deactivate, send_data_ack):
    print("Put your message here:", end="", flush=True)
    i = 0
    broke_conn = 0
    while not exit_ev.is_set():
        i += 1
        message = non_blocking_input(1)
        # if there is no message from this peer then just check exit_ev that handles disconnect from another peer
        if message is None:
            if broke_conn == 3:
                print("the connection with opposite peer was broken, shutting down...")
                exit_by_brok.set()
                break
            if i == 5 and not keep_alv_deactivate.is_set():
                protocol.sending_packet("KEA", b"", sock, ip_opp_peer, port_opp_peer_receive, 0, 1)
                keep_alv_wait_answ.set()
                broke_conn += 1
                i = 0
            if keep_alv_received.is_set():
                broke_conn = 0
                protocol.sending_packet("KEAACK", b"", sock, ip_opp_peer, port_opp_peer_receive, 0, 1)
                keep_alv_received.clear()
            if not keep_alv_wait_answ.is_set():
                broke_conn = 0
            if send_data_ack.is_set():
                protocol.sending_packet("DATAACK", b"", sock, ip_opp_peer, port_opp_peer_receive, 0, 1)
                send_data_ack.clear()
            if keep_alv_deactivate.is_set():
                i = 0
            continue
        if message == "DATA":
            keep_alv_deactivate.set()
            send_data(sock, ip_opp_peer, port_opp_peer_receive, acknowledge_data_wait)
            keep_alv_deactivate.clear()
        # if this peer initiated exit
        if message == "exit":
            print("\nClosing connection...", flush=True)
            print("Opposite peer will sleep automatically", flush=True)
            protocol.sending_packet("EXIT", b"", sock, ip_opp_peer, port_opp_peer_receive, 0, 1)
            break
        protocol.sending_packet("TXT", message.encode(), sock, ip_opp_peer, port_opp_peer_receive, 0, 1)

# info about exit flags. Peer that initiated the exit sends an empty packet with EXIT flag and
# opponent peer have to send the EXIT and ACK packet

# function to receive all data, currently only text messages from another peer (this function works in parallel thread)
def receiving_messages(sock, exit_ev, keep_alv_wait_answ, keep_alv_received, exit_by_brok, acknowledge_data_wait, keep_alv_deactivate, send_data_ack):
   while not exit_by_brok.is_set():
       ready_socks, _, _ = select.select([sock], [], [], 0.5)
       if ready_socks:
           flags, _, _, _, _, _, _, message = protocol.receiving_messages(sock)
           if keep_alv_wait_answ.is_set(): # if flag "we have to receive KEAACK" is setted
               if "KEA" in flags and "ACK" in flags: # check if packet is with the KEAACK flags
                   keep_alv_wait_answ.clear()
                   continue
           if "KEA" in flags and "ACK" not in flags:
               keep_alv_received.set() # if we recieved the KEA flag and we have to send the KEAACK
               continue
           if "DATA" in flags and "ACK" not in flags: # todo keep alive not working after data receiving
               keep_alv_deactivate.set()
               print("RECEIVING DATA")
               receive_file(sock, send_data_ack)
               print("Activating keep alive")
               keep_alv_deactivate.clear()
               print("Keep alive status after file transfer:", keep_alv_deactivate.is_set())
           if "DATA" in flags and "ACK" in flags:
               acknowledge_data_wait.set()
           if "EXIT" in flags and "ACK" not in flags:
               print("\nClosing connection due to initiation from opponent peer", flush=True)
               exit_ev.set()
               break # here we have to break cause from this thread we are only receiving the packets
               # main thread will send the EXIT ACK packet
           if "EXIT" in flags and "ACK" in flags:
               break
               # here the code just breaks thread because so the main thread can stop this thread
           print(f"\nMessage recieved: {message}")
           print("Put your message here:", end="", flush=True)

# function to start conversation between the peers
def start_conversation(sock, ip_opp_peer, port_opp_peer_receive):
    # unsetting timeout
    sock.settimeout(None)
    # creating an event to handle exit initiated from other peer
    exit_ev = threading.Event() # flag for exiting if other peer initiated exit from connection
    keep_alv_wait_answ = threading.Event()  # wait for the answer when keep alive was sent
    keep_alv_received = threading.Event() # flag if there was KEA flag received (have to send KEAACK)
    exit_by_brok = threading.Event() # flag for exiting  by broken connection
    acknowledge_data_wait = threading.Event() # flag to wait for acknowledge when sending data
    keep_alv_deactivate = threading.Event() # flag for deactivating keep alive while sending or receiving data
    send_data_ack = threading.Event() # flag to send the data acknowledge
    # creating second thread for receiving messages
    receive_thread1 = threading.Thread(target=receiving_messages, args=(sock, exit_ev, keep_alv_wait_answ, keep_alv_received, exit_by_brok, acknowledge_data_wait, keep_alv_deactivate, send_data_ack))
    receive_thread1.daemon = True
    receive_thread1.start()
    print("If you want to send files please put the 'DATA' into terminal")
    # starting in main thread the function to send messages
    sending_messages(sock, ip_opp_peer, port_opp_peer_receive, exit_ev, keep_alv_wait_answ, keep_alv_received, exit_by_brok, acknowledge_data_wait, keep_alv_deactivate, send_data_ack)
    # this if is for the case where exit was initiated from other peer
    if exit_ev.is_set():
        protocol.sending_packet("EXITACK", b"", sock, ip_opp_peer, port_opp_peer_receive, 0, 1)
    # waiting for parallel thread to stop
    receive_thread1.join()
    sock.close()













# mode to send the SYN and then wait for the SYNACK and after send the ACK
def master_mode(sock, ip_opp_peer, port_opp_peer_receive):
    while True:
        protocol.sending_packet("SYN", b"", sock, ip_opp_peer, port_opp_peer_receive, 0, 1)
        ready, _, _ = select.select([sock], [], [], 2)
        try:
            if ready:
                flags, _, _, _, _, _, ip_addr_opp_fr, _ = protocol.receiving_messages(sock)
                if "SYN" in flags and "ACK" in flags:
                    protocol.sending_packet("ACK", b"", sock, ip_opp_peer, port_opp_peer_receive, 0, 1)
                    print("Connection succesful!")
                    return
        except socket.timeout:
            print("Timeout on socket, restart code")
            exit(1)

# mode to send the SYNACK if there was SYN packet
def slave_mode(sock, ip_opp_peer, port_opp_peer_receive):
    print("Creating connection due to initiation from another peer...")
    flags, _, _, _, _, _, ip_addr_opp_fr, _ = protocol.receiving_messages(sock)
    if "SYN" in flags and "ACK" not in flags:
        protocol.sending_packet("SYNACK", b"", sock, ip_opp_peer, port_opp_peer_receive, 0, 1)
        flags, *_ = protocol.receiving_messages(sock)
        if "ACK" in flags:
            print("Connection successful!")
            return

# handshake function to create connection
def handshake(sock, ip_opp_peer, port_opp_peer_receive):
    sock.settimeout(60)
    print("Create connection?[Y/n]")
    while True:
        # select here is used to check both keyboard input from this peer and to receive the data from other peer.
        # This is done cause both peer are in slave modes after booting and if one peer initiates the connection
        # then initiated peer will be the master in this connection and this peer will be slave
        ready, _, _ = select.select([sock, sys.stdin], [], [], 0.5)
        try:
            if sock in ready:
                # a case where this peer received some packet (99.9% SYN from other peer)
                slave_mode(sock, ip_opp_peer, port_opp_peer_receive)
                break
        except socket.timeout:
            # if there were no signals from other peer for 60 seconds then peer will shut down
            print("Timeout while waiting other peer, restart the program")
            exit(0)

        if sys.stdin in ready:
            m = input()
            if m.lower() == "y":
                # this is a case where this peer initiated connection
                print("Creating connection...")
                master_mode(sock, ip_opp_peer, port_opp_peer_receive)
                break
            elif m.lower() == "n":
                print("Turning off...")
                exit(0)



def create_p2p_connection(ip_opp_peer, port_opp_peer_receive, port_peer_receive):
    # create the socket that will be used through all connection
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # binding the receiving port on this peer so we can listen by port
    sock.bind(('', port_peer_receive))
    # create handshake
    handshake(sock, ip_opp_peer, port_opp_peer_receive)
    # if there were no exits from the handshake then start the conversation between peers
    start_conversation(sock, ip_opp_peer, port_opp_peer_receive)

# setup function where user sets up all the input data
def setup():
    ips_this_peer = get_all_ip_addresses()
    print(f"IPs of this Node: {ips_this_peer}")
    print("Please start this code on other machine to see their IPs")
    print("Put IP of the opposite peer here:", end="")
    ip_opp_peer = input()
    print("Enter receive port for this peer: ", end="")
    port_peer_receive = int(input())
    print("Enter receive port for opposite peer: ", end="")
    port_opp_peer_receive = int(input())
    return ip_opp_peer, port_opp_peer_receive, port_peer_receive


def main():
   ip_opp_peer, port_opp_peer_receive, port_peer_receive = setup()
   create_p2p_connection(ip_opp_peer, port_opp_peer_receive, port_peer_receive)

if __name__ == "__main__":
    main()