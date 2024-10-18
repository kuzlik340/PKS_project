import socket
import psutil
import threading
import select
import sys
import protocol

# Receive on port 50000
# Send from port 50001

def non_blocking_input(timeout):
    ready, _, _ = select.select([sys.stdin], [], [], timeout)
    if ready:
        print("Put your message here:", end ="", flush=True)
        return sys.stdin.readline().strip()
    else:
        return None

def get_all_ip_addresses():
    ip_list = []
    for interface_name, interface_addresses in psutil.net_if_addrs().items():
        for address in interface_addresses:
            if address.family == socket.AF_INET and address.address != "127.0.0.1":
                ip_list.append(address.address)
    return ip_list


def sending_messages(sock, ip_opp_peer, port_opp_peer_receive, event):
    print("Put your message here:", end="", flush=True)
    while not event.is_set():
        message = non_blocking_input(1)
        if message is None:
            continue
        if message == "exit":
            print("\nClosing connection...", flush=True)
            print("Opposite peer will sleep automatically", flush=True)
            protocol.sending_packet("EXIT", b"", sock, ip_opp_peer, port_opp_peer_receive)
            break
        protocol.sending_packet("TXT", message.encode(), sock, ip_opp_peer, port_opp_peer_receive)


def receiving_messages(sock, ip_opp_peer, port_opp_peer_receive, shared_var, exit_ev):
   while shared_var[0]:
       flags, _, _, _, _, _, message = protocol.receiving_messages(sock)
       if "EXIT" in flags:
           print("\nClosing connection due to initiation from opponent peer", flush=True)
           exit_ev.set()
           shared_var[0] = False
           break
       if "EXITACK" in flags or "ACKEXIT" in flags:
           shared_var[0] = False
           break
       print(f"Message recieved: {message}")



def start_conversation(sock, ip_opp_peer, port_opp_peer_receive):
    shared_var = [True]
    exit_ev = threading.Event()
    listen_thread1 = threading.Thread(target=receiving_messages, args=(sock, ip_opp_peer, port_opp_peer_receive, shared_var, exit_ev))
    listen_thread1.daemon = True  # Поток завершится при завершении программы
    listen_thread1.start()
    sending_messages(sock, ip_opp_peer, port_opp_peer_receive, exit_ev)
    if exit_ev.is_set():
        protocol.sending_packet("EXITACK", b"", sock, ip_opp_peer, port_opp_peer_receive)  # ack
    listen_thread1.join()
    sock.close()
    print("Exiting...", flush=True)


def main_node_for_handshake(sock, ip_opp_peer, port_opp_peer_receive):
    protocol.sending_packet("SYN", b"", sock, ip_opp_peer, port_opp_peer_receive)
    sock.settimeout(60)
    while True:
        try:
            flags, *_ = protocol.receiving_messages(sock)
            if "SYN" in flags and "ACK" not in flags:
                    protocol.sending_packet("SYNACK", b"", sock, ip_opp_peer, port_opp_peer_receive)#ack
                    flags, *_ = protocol.receiving_messages(sock)
                    if "ACK" in flags:
                        print("Connection successful!")
                        return
            if "SYNACK" in flags or "ACKSYN" in flags:
                protocol.sending_packet("ACK", b"", sock, ip_opp_peer, port_opp_peer_receive) #ack
                print("Connection succesful!")
                return
        except socket.timeout:
        # Если таймаут сработал, выводим сообщение и выходим
            print("Timeout on socket, restart code")
            exit(1)

def create_P2P_connection(ip_opp_peer, port_opp_peer_receive, port_peer_receive):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('', port_peer_receive))
    print("Creating connection...")
    main_node_for_handshake(sock, ip_opp_peer, port_opp_peer_receive)
    start_conversation(sock, ip_opp_peer, port_opp_peer_receive)


def setup():
    IPs_this_peer = get_all_ip_addresses()
    print(f"Wi-Fi IP of this Node: {IPs_this_peer}")
    print("Please start this code on other machine to see their IPs")
    print("Put IP of the peer here:", end="")
    ip_opp_peer = input()
    print("Enter receive port for this peer: ", end="")
    port_peer_receive = int(input())
    print("Enter receive port for opposite peer: ", end="")
    port_opp_peer_receive = int(input())
    return ip_opp_peer, port_opp_peer_receive, port_peer_receive

def main():
   ip_opp_peer, port_opp_peer_receive, port_peer_receive = setup()
   create_P2P_connection(ip_opp_peer, port_opp_peer_receive, port_peer_receive)

if __name__ == "__main__":
    main()