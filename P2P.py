import psutil
import socket
import threading
import select
import sys
import protocol
import file_transfer


# class that contains all functions to handle received packet
class MessageHandler:
    def __init__(self):
        pass

    def handle_keep_alive_ack(self, keep_alv_wait_answ):
        keep_alv_wait_answ.clear()

    def handle_keep_alive(self, keep_alv_received):
        keep_alv_received.set()

    def handle_data_receive(self, keep_alv_deactivate, packet_handler, send_data_ack):
        keep_alv_deactivate.set()
        print("RECEIVING DATA")
        file_transfer.receive_data(packet_handler, send_data_ack)
        print("Activating keep alive")
        keep_alv_deactivate.clear()

    def handle_data_ack(self, acknowledge_data_wait):
        acknowledge_data_wait.set()

    def handle_exit(self, exit_ev):
        print("\nClosing connection due to initiation from opponent peer", flush=True)
        exit_ev.set()

# class that contains all flags between two threads, so threads cam communicate with each other
class ConnectionFlags:
    def __init__(self):
        self.exit_ev = threading.Event() # flag for exiting if other peer initiated exit from connection
        self.keep_alv_wait_answ = threading.Event()  # wait for the answer when keep alive was sent
        self.keep_alv_received = threading.Event() # flag if there was KEA flag received (have to send KEAACK)
        self.exit_by_brok = threading.Event() # flag for exiting  by broken connection
        self.acknowledge_data_wait = threading.Event() # flag to wait for acknowledge when sending data
        self.keep_alv_deactivate = threading.Event() # flag for deactivating keep alive while sending or receiving data
        self.send_data_ack = threading.Event() # flag to send the data acknowledge

# class with all main functions for keep alive mechanism
class KeepAliveHandler:
    def __init__(self):
        self.keep_alive_req_num = 0
        self.timer = 0

    def reset_counter(self):
        self.keep_alive_req_num = 0

    def increment_counter(self):
        self.keep_alive_req_num += 1

    def reset_timer(self):
        self.timer = 0

    def increment_timer(self):
        self.timer += 1




# utility function that just finds peer IPs so you can see them and write them directly to the input of program
def get_all_ip_addresses():
    ip_list = []
    for interface_name, interface_addresses in psutil.net_if_addrs().items():
        for address in interface_addresses:
            if address.family == socket.AF_INET and address.address != "127.0.0.1":
                ip_list.append(address.address)
    return ip_list



# function that makes the input function in the sending_message not blocking so code can handle the situation
# when EXIT was initiated from another peer
def non_blocking_input(timeout):
    ready, _, _ = select.select([sys.stdin], [], [], timeout)
    if ready:
        print("Put your message here:", end ="", flush=True)
        return sys.stdin.readline().strip()
    else:
        return None


def handle_keep_alive(keep_alv_handler, packet_handler, threading_flags):
    if keep_alv_handler.keep_alive_req_num == 3:  # If there was no answer for three requests
        print("\nThe connection with the opposite peer was broken, shutting down...")
        threading_flags.exit_by_brok.set()  # Breaking connection
        return True
    print(f"Keep alive{keep_alv_handler.timer}")
    # Sending keep alive request every 5 seconds (this function is called every 1 second)
    if keep_alv_handler.timer == 5 and not threading_flags.keep_alv_deactivate.is_set():
        print("Sending KEA")
        packet_handler.send_packet("KEA", b"", 0, 1)
        # setting the flag to wait for an answer from other peer in receiving thread
        threading_flags.keep_alv_wait_answ.set()
        # incrementing the counter of already sent packets
        keep_alv_handler.increment_counter()
        keep_alv_handler.reset_timer()
    if threading_flags.keep_alv_received.is_set():
        # if there was received packet with "KEA" flag
        packet_handler.send_packet("KEAACK", b"", 0, 1)
        threading_flags.keep_alv_received.clear()
    # if we are not waiting for the KEAACK then reset counter of already sent requests
    # this event will be only if other peer responded on last keep alive request
    if not threading_flags.keep_alv_wait_answ.is_set():
        keep_alv_handler.reset_counter()
    if threading_flags.keep_alv_deactivate.is_set():
        print("keep alive resetting")
        keep_alv_handler.reset_timer()
    return False

# function to send all data, currently only text messages from terminal
def sending_messages(packet_handler, threading_flags):
    # creating an object that will handle keep alive mechanism
    keep_alv_handler = KeepAliveHandler()
    while not threading_flags.exit_ev.is_set():
        keep_alv_handler.increment_timer()
        message = non_blocking_input(1)
        # if there is no message from this peer then just check exit_ev that handles disconnect from another peer
        if message is None: # since we have non-blocking input with interval 1 second we can use this cycle
            if handle_keep_alive(keep_alv_handler, packet_handler, threading_flags):
                break
            if threading_flags.send_data_ack.is_set():
                packet_handler.send_packet("DATAACK", b"", 0, 1)
                threading_flags.send_data_ack.clear()
            continue
        if message == "DATA":
            threading_flags.keep_alv_deactivate.set()
            keep_alv_handler.reset_timer()
            file_transfer.send_data(packet_handler, threading_flags.acknowledge_data_wait)
            threading_flags.keep_alv_deactivate.clear()
            continue
        # if this peer initiated exit
        if message == "exit":
            print("\nClosing connection...", flush=True)
            print("Opposite peer will sleep automatically", flush=True)
            packet_handler.send_packet("EXIT", b"", 0, 1)
            break
        packet_handler.send_packet("TXT", message.encode(), 0, 1)



# function to receive all data, currently only text messages from another peer (this function works in parallel thread)
def receiving_messages(packet_handler, threading_flags):
   # creating an object that will handle all packets that we received
   handler = MessageHandler()
   # getting the socket from Packet Handler class so we can use it in the 'select' function
   sock = packet_handler.get_socket()
   while not threading_flags.exit_by_brok.is_set():
       ready_socks, _, _ = select.select([sock], [], [], 0.5)
       if ready_socks:
           flags, _, _, _, _, _, _, message = packet_handler.receive_packet()
           if threading_flags.keep_alv_wait_answ.is_set() and "KEA" in flags and "ACK" in flags:
               handler.handle_keep_alive_ack(threading_flags.keep_alv_wait_answ)
               continue
           elif "KEA" in flags and "ACK" not in flags:
               handler.handle_keep_alive(threading_flags.keep_alv_received)
               continue
           elif "DATA" in flags and "ACK" not in flags:
               handler.handle_data_receive(threading_flags.keep_alv_deactivate, packet_handler, threading_flags.send_data_ack)
               continue
           elif "DATA" in flags and "ACK" in flags:
               handler.handle_data_ack(threading_flags.acknowledge_data_wait)
               print("Put your message here:", end="", flush=True)
               continue
           elif "EXIT" in flags and "ACK" not in flags:
               break # here we have to break cause from this thread we are only receiving the packets
           elif "EXIT" in flags and "ACK" in flags:
               handler.handle_exit(threading_flags.exit_ev)
               break
               # here the code just breaks thread because so the main thread can stop this thread
           elif "TXT" in flags:
               print(f"\nMessage recieved: {message.decode()}")
               print("Put your message here:", end="", flush=True)


# function to start conversation between the peers
def start_conversation(packet_handler):
    # unsetting timeout
    sock = packet_handler.get_socket()
    sock.settimeout(None)
    threading_flags = ConnectionFlags()

    # creating second thread for receiving messages
    receive_thread1 = threading.Thread(target=receiving_messages, args=(packet_handler, threading_flags))
    receive_thread1.daemon = True
    receive_thread1.start()

    print("If you want to send files please put the 'DATA' into terminal")
    # starting in main thread the function to send messages
    sending_messages(packet_handler, threading_flags)

    # this if is for the case where exit was initiated from other peer
    if threading_flags.exit_ev.is_set():
        packet_handler.send_packet("EXITACK", b"", 0, 1)
    # waiting for parallel thread to stop
    receive_thread1.join()
    packet_handler.socket_close()



# mode to send the SYN and then wait for the SYNACK and after send the ACK
def master_mode(packet_handler):
    sock = packet_handler.get_socket()
    while True:
        packet_handler.send_packet("SYN", b"", 0, 1)
        ready, _, _ = select.select([sock], [], [], 2)
        try:
            if ready:
                flags, _, _, _, _, _, _, _ = packet_handler.receive_packet()
                if "SYN" in flags and "ACK" in flags:
                    packet_handler.send_packet("ACK", b"", 0, 1)
                    print("Connection succesful!")
                    return
        except socket.timeout:
            print("Timeout on socket, restart code")
            exit(1)

# mode to send the SYNACK if there was SYN packet
def slave_mode(packet_handler):
    print("Creating connection due to initiation from another peer...")
    flags, _, _, _, _, _, ip_addr_opp_fr, _ = packet_handler.receive_packet()
    if "SYN" in flags and "ACK" not in flags:
        packet_handler.send_packet("SYNACK", b"", 0, 1)
        flags, *_ = packet_handler.receive_packet()
        if "ACK" in flags:
            print("Connection successful!")
            return

# handshake function to create connection
def handshake(packet_handler):
    sock = packet_handler.get_socket()
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
                slave_mode(packet_handler)
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
                master_mode(packet_handler)
                break
            elif m.lower() == "n":
                print("Turning off...")
                exit(0)



def create_p2p_connection(ip_opp_peer, port_opp_peer_receive, port_peer_receive):
    # create the socket that will be used through all connection
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # binding the receiving port on this peer so we can listen by port
    sock.bind(('', port_peer_receive))
    packet_handler = protocol.PacketHandler(sock, ip_opp_peer, port_opp_peer_receive)
    # create handshake
    handshake(packet_handler)
    # if there were no exits from the handshake then start the conversation between peers
    start_conversation(packet_handler)

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