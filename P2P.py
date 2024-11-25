import psutil
import socket
import threading
import select
import sys
import protocol
import file_transfer
import time
import logging

# class that contains all flags between two threads, so threads cam communicate with each other
class ConnectionFlags:
    def __init__(self):
        self.exit_ev = threading.Event() # flag for exiting if other peer initiated exit from connection
        self.exit_by_brok = threading.Event() # flag for exiting  by broken connection
        self.block_default_recv = threading.Event()
        self.block_default_send = threading.Event()

class KeepAlive:
    def __init__(self, packet_handler, timeout=5, max_retries=3):
        """
        :param packet_handler: Объект, через который отправляются пакеты.
        :param timeout: Интервал между запросами в секундах.
        :param max_retries: Максимальное количество попыток без ответа.
        """
        self.packet_handler = packet_handler
        self.timeout = timeout
        self.max_retries = max_retries
        self.is_alive = None

        self.retries = 0
        self.running = False
        self.lock = threading.Lock()

    def start(self):
        """Запускает keep-alive."""
        self.running = True
        self.is_alive = None
        self.retries = 0
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        """Останавливает keep-alive."""
        with self.lock:
            self.running = False

    def acknowledge(self):
        """Сбрасывает счётчик при получении `KEAACK`."""
        with self.lock:
            self.retries = 0
            self.is_alive = True

    def _run(self):
        """Цикл keep-alive."""
        while True:
            with self.lock:
                if not self.running:
                    break
                if self.retries >= self.max_retries:
                    self.running = False
                    self.is_alive = False
                    break

                # Отправляем KEA
                self.packet_handler.send_packet("KEA", b"", 0, 1)
                self.retries += 1

            time.sleep(self.timeout)


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
        return sys.stdin.readline().strip()
    else:
        return None


def menu(packet_handler):
    print("For enabling simulation of fragment damaging put 'enable_damage'")
    print("For disabling simulation of fragment damaging put 'disable_damage'")
    print("To change the fragment size put 'change_size'")
    choice = input()
    if choice == "enable_damage":
        packet_handler.set_damage(True)
        print("Simulation of damaging was enabled")
    if choice == "disable_damage":
        packet_handler.set_damage(False)
        print("Simulation of damaging was disabled")
    elif choice == "change_size":
        print("Choose fragment size from 1 to 1460 bytes")
        fragment_size = int(input())
        while fragment_size > 1460 or fragment_size < 1:
            print("Invalid size")
            print("Choose fragment size from 1 to 1460 bytes")
            fragment_size = int(input())
        packet_handler.fragment_size = fragment_size
        print(f"Fragment size set to {packet_handler.fragment_size}")
    else:
        print("Invalid input")

# function to send all data, currently on ly text messages from terminal
def sending(packet_handler, threading_flags, keep_alive):
    # creating an object that will handle keep alive mechanism
    while not threading_flags.exit_ev.is_set():
        message = non_blocking_input(1)
        while threading_flags.block_default_send.is_set():
            pass
        # if there is no message from this peer then just check exit_ev that handles disconnect from another peer
        if message is None: # since we have non-blocking input with interval 1 second we can use this cycle
            if keep_alive.is_alive is not None and not keep_alive.is_alive:
                print("Broken connection, no answer from peer. Shutting down...")
                threading_flags.exit_by_brok.set()
                break
            continue
        if message == "DATA":
            keep_alive.stop()
            threading_flags.block_default_recv.set()
            file_transfer.send_data(packet_handler, keep_alive)
            threading_flags.block_default_recv.clear()
            keep_alive.start()
            continue
        # if this peer initiated exit
        if message == "EXIT":
            print("\nClosing connection...", flush=True)
            print("Opposite peer will sleep automatically", flush=True)
            packet_handler.send_packet("EXIT", b"", 0, 1)
            break
        if message == "MENU":
            menu(packet_handler)
            continue
        if message == "HELP":
            print("If you want to send files please put the 'DATA' into terminal")
            print("If you want to send messages please put the 'MESSAGE' into terminal")
            print("If you want to disconnect please put the 'EXIT' into terminal")
            print("If you want to change parameters for connection please put the 'MENU' into terminal")
        if message == "MESSAGE":
            keep_alive.stop()
            threading_flags.block_default_recv.set()
            file_transfer.send_text(packet_handler)
            threading_flags.block_default_recv.clear()
            keep_alive.start()
        else:
            print("Invalid input")



# function to receive all data, currently only text messages from another peer (this function works in parallel thread)
def receiving(packet_handler, threading_flags, keep_alive):
   # creating an object that will handle all packets that we received
   # getting the socket from Packet Handler class so we can use it in the 'select' function
   sock = packet_handler.get_socket()
   while not threading_flags.exit_by_brok.is_set() and not threading_flags.exit_ev.is_set():
       ready_socks, _, _ = select.select([sock], [], [], 0.5)
       while threading_flags.block_default_recv.is_set():
            pass
       if ready_socks:
           flags, sequence_num, _, _, _, message = packet_handler.receive_packet()
           if "KEA" and "ACK" in flags:
               keep_alive.acknowledge()
               continue
           elif "KEA" in flags and "ACK" not in flags:
               packet_handler.send_packet("KEAACK", b"", 0, 1)
               continue
           elif "DATA" in flags:
               keep_alive.stop()
               threading_flags.block_default_send.set()
               file_transfer.receive_data(packet_handler, keep_alive)
               threading_flags.block_default_send.clear()
               keep_alive.start()
               continue
           elif "EXIT" in flags and "ACK" not in flags:
               print("Closing connection due to initiation from opposite peer")
               threading_flags.exit_ev.set()
               break # here we have to break cause from this thread we are only receiving the packets
           elif "EXIT" in flags and "ACK" in flags:
               break
               # here the code just breaks thread because so the main thread can stop this thread
           elif "TXT" in flags:
               keep_alive.stop()
               threading_flags.block_default_send.set()
               file_transfer.receive_text(packet_handler, keep_alive)
               threading_flags.block_default_send.clear()
               keep_alive.start()


# function to start conversation between the peers
def start_conversation(packet_handler):
    # unsetting timeout
    sock = packet_handler.get_socket()
    sock.settimeout(None)
    threading_flags = ConnectionFlags()
    keep_alive = KeepAlive(packet_handler)
    keep_alive.start()
    # creating second thread for receiving messages
    receive_thread = threading.Thread(target=receiving, args=(packet_handler, threading_flags, keep_alive))
    receive_thread.daemon = True
    receive_thread.start()

    print("If you want to send files please put the 'DATA' into terminal")
    print("If you want to send messages please put the 'MESSAGE' into terminal")
    print("If you want to disconnect please put the 'EXIT' into terminal")
    print("If you want to change parameters for connection please put the 'MENU' into terminal")
    # starting in main thread the function to send messages
    sending(packet_handler, threading_flags, keep_alive)

    # this if is for the case where exit was initiated from other peer
    if threading_flags.exit_ev.is_set():
        packet_handler.send_packet("EXITACK", b"", 0, 1)
    threading_flags.exit_ev.set()
    # waiting for parallel thread to stop
    receive_thread.join()
    packet_handler.socket_close()



# mode to send the SYN and then wait for the SYNACK and after send the ACK
def master_mode(packet_handler):
    sock = packet_handler.get_socket()
    while True:
        packet_handler.send_packet("SYN", b"", 0, 1)
        ready, _, _ = select.select([sock], [], [], 2)
        try:
            if ready:
                flags, _, _, _, _, _ = packet_handler.receive_packet()
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
    flags, _, _, _, _, _ = packet_handler.receive_packet()
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