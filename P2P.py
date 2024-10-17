import socket
import psutil
import threading
from random import randint
import time
# Receive on port 50000
# Send from port 50001



def get_all_ip_addresses():
    ip_list = []
    for interface_name, interface_addresses in psutil.net_if_addrs().items():
        for address in interface_addresses:
            if address.family == socket.AF_INET and address.address != "127.0.0.1":
                ip_list.append(address.address)
    return ip_list


def sending_messages(sock, ip_opp_peer, port_opp_peer_receive):
    while True:
        print("Put here the message (if you want to stop connection write 'exit'):")
        message = input()
        if message == "exit":
            sock.sendto(b"EXIT", (ip_opp_peer, port_opp_peer_receive))
            answ, addr = sock.recvfrom(1024)
            if answ == b"EXITR":
                sock.close()
                print("Connection closed")
                print("Turning off this peer, opposite peer will sleep automatically")
                return
        sock.sendto(message.encode(), (ip_opp_peer, port_opp_peer_receive))



def receiving_messages(sock, ip_opp_peer, port_opp_peer_receive, shared_var):
   while shared_var[0]:
       answ = sock.recvfrom(1024)
       if answ[0] == b"EXIT":
           sock.sendto(b"EXITR", (ip_opp_peer, port_opp_peer_receive))
           sock.close()
           print("Connection closed by opposite peer")
           print("Turning off this peer")
           shared_var[0] = False
       print(f"Message recieved: {answ[0].decode()}")



def start_conversation(sock, ip_opp_peer, port_opp_peer_receive):
    shared_var = [True]
    listen_thread1 = threading.Thread(target=receiving_messages, args=(sock, ip_opp_peer, port_opp_peer_receive, shared_var))
    listen_thread1.daemon = True  # Поток завершится при завершении программы
    listen_thread1.start()
    sending_messages(sock, ip_opp_peer, port_opp_peer_receive)
    shared_var[0] = False
    listen_thread1.join()


def main_node_for_handshake(sock, ip_opp_peer, port_opp_peer_receive):
    sock.sendto(b"SYN", (ip_opp_peer, port_opp_peer_receive))
    sock.settimeout(60)
    while True:
        try:
            data, addr = sock.recvfrom(1024)
            if data == b"SYN":
                    sock.sendto(b"ACK", (ip_opp_peer, port_opp_peer_receive))
                    data, addr = sock.recvfrom(1024)
                    if data == b"CONN":
                        print("Connection successful!")
                        return
            if data == b"ACK":
                sock.sendto(b"CONN", (ip_opp_peer, port_opp_peer_receive))
                print("Connection succesful!")
                return
        except socket.timeout:
        # Если таймаут сработал, выводим сообщение и выходим
            print("Timeout on socket, restart code")
            exit(1)

def create_P2P_connection(ip_opp_peer, port_opp_peer_receive):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('', port_opp_peer_receive))
    print("Creating connection...")
    main_node_for_handshake(sock, ip_opp_peer, port_opp_peer_receive)
    start_conversation(sock, ip_opp_peer, port_opp_peer_receive)


def setup():
    IPs_this_peer = get_all_ip_addresses()
    print(f"Wi-Fi IP of this Node: {IPs_this_peer}")
    print("Please start this code on other machine to see their IPs")
    print("Put IP of the peer here:", end="")
    ip_opp_peer = "192.168.1.1"  # input()
    print("Put port of the endpoint here (same port will be used on this machine to receive messages):", end="")
    port_opp_peer_receive = 50300  # int(input())
    return ip_opp_peer, port_opp_peer_receive

def main():
   ip_opp_peer, port_opp_peer_receive = setup()
   create_P2P_connection(ip_opp_peer, port_opp_peer_receive)

if __name__ == "__main__":
    main()