# Header

The header length is now 7 bytes, reduced from 14 bytes in the initial
version. This improvement was achieved by removing the acknowledgment
number, as well as the window field, since the receiver does not utilize
a window for receiving. Additionally, the length field was deleted as it
was unnecessary.

The sequence number is an individual ID for the packets that are
transmitted in one session. In this project, 4 bytes were chosen for the
sequence number, as this provides ample space to store an integer
suitable for large data transfers. The sequence number is sent by the
peer that is currently sending messages. Also, it is used by receiving
peer to indicate what packet was lost/damaged. STN is just a name for
the protocol.

The flags field is 1 byte, and in this protocol, 8 flags are used. The
checksum, calculated using Fletcher's algorithm, is included to ensure
the packet was received correctly.

This header is small but still contains everything important for the
Go-Back-N method with an adaptive window.

In code the encoder and decoder for the protocol header are contained in
the protocol.py

<img width="1103" alt="STN (1)" src="https://github.com/user-attachments/assets/24602d3d-eaeb-482d-ae6a-d1024397a0b9" />

# Safe Transfer of Data

The Go-Back-N method with an adaptive window is employed to ensure the
correct transfer of packets. The essence of the Go-Back-N method lies in
the sliding window mechanism. For instance, the sender transmits 5
packets (window_size = 5), and the receiver's acknowledgments (in
[code]{style="color: red"} DATAACK/TXTACK) cause the sender to slide the
window forward, allowing new packets to be sent.

However, if a packet is lost or damaged, the sender receives a NACK
signal (DATAERR/TXTERR in [code]{style="color: red"}). In this case, the
sender must adjust the window so that the first packet in the window has
the same sequence number as the lost or damaged packet. All
functionality related to the Go-Back-N method is implemented in the
file_transfer.py script.

The adaptive window size is determined by comparing the number of lost
or damaged packets to the total number of packets sent up to that point.
This ensures a safe and efficient adjustment of the window_size.

In the accompanying diagram, window_size is set to 3. It illustrates
that when an ACK is received from the receiver, the window slides, and a
new packet is sent. The diagram also highlights a situation where the
packet with seq_num = 4 is damaged. Upon receiving the corresponding
NACK signal, the sender slides the window back to the packet with
seq_num = 4.

<img width="659" alt="ARQ" src="https://github.com/user-attachments/assets/4f655dc5-737c-4d2f-a2fd-1a1104bfa997" />

# Damaging Mechanism

The damaging mechanism in this code is straightforward. In the
protocol.py script, there is a defined probability that a packet will
either be lost (not sent) or damaged (its checksum will be set to 1234
instead of the actual checksum). This mechanism can be enabled or
disabled by accessing the MENU through the terminal while the program is
running.

# Handshake

The handshake process is similar to the TCP handshake, utilizing SYN,
SYN-ACK, and ACK flags. The ninth byte of the header is reserved for
flags, with SYN represented as (0b0000 0001), SYN-ACK as (0b0000 0011),
and ACK as (0b0000 0010). When the code starts and all necessary data
(IP addresses, ports) is input, the user will be prompted to initiate a
connection. If user confirms creating a connection then the node will go
to master mode. Both peers initially boot in slave mode, waiting for a
message from the other. Once a connection is started from one peer, it
designates itself as the master node and sends a SYN message every 2
seconds, awaiting a response. If the slave peer is active, it replies
with a SYN-ACK message, and the master peer responds with an ACK to
complete the handshake. If no connection is initiated or there is no
response from the user to connect, the peer will automatically shut down
after 60 seconds.

<img width="481" alt="HANDSHAKE (1)" src="https://github.com/user-attachments/assets/5e9ccba3-1ae8-4f66-8a01-8d0cf2f7451c" />

# Keep alive

The keep-alive mechanism in this protocol is simple. There is a
dedicated KEA flag, which peers will use to send keep-alive messages to
each other. Upon receiving a KEA message, the peer responds with a
KEA-ACK flag. If no response is received after 3 attempts, the
connection will be automatically closed, ensuring that inactive or lost
connections are properly terminated.

In the [code]{style="color: red"} keep alive is represented as KeepAlive
class in the P2P.py. Keep-alive mechanism uses its own thread that is
created by keep_alive.start() and can be stopped by keep_alive.stop()

# Flags

The table below lists all the flags that can be used in the protocol
along with their meanings. Each packet must have at least one flag set
to 1 to indicate to the receiving peer the content or type of the
packet. This ensures that both peers can correctly interpret the purpose
of each packet in the communication process.

   **Flag**      **Meaning**       **Binary**
  ---------- -------------------- ------------
     SYN       synchronisation     0b00000001
     ACK         confirmation      0b00000010
     ERR      packet was damaged   0b00000100
     FIN        final segment      0b00001000
     EXIT      stop connection     0b00010000
     DATA        data segment      0b00100000
     TXT         txt segment       0b01000000
     KEA       keep-alive flag     0b10000000

# CheckSum

The checksum will be calculated using Fletcher's algorithm. The idea is
to use the first 8 bits of the checksum section to store the sum of the
bytes (with no overflow since a mod 255 operation is applied). The
remaining 8 bits will contain the sum of sums, meaning that the last 8
bits of the checksum will hold the cumulative sum of all the sums that
were calculated. This approach ensures data integrity by detecting
errors in the transmitted packet.

# Exit

For exiting the connection, the following sequence will be used: the
peer that initiates the exit will send an empty packet with the EXIT
flag set. The receiving peer must respond with an EXIT-ACK packet. Once
the EXIT-ACK is received, both peers will shut down, ensuring a clean
and synchronized termination of the connection.
<img width="491" alt="EXIT (1)" src="https://github.com/user-attachments/assets/d71e8091-d32d-4edb-b8bf-57b302a99144" />

# About program

This program is not compatible with Windows systems due to its use of
the \"psutil\" library, which is employed to display the IP addresses of
the node, making it easier for users to input them. Additionally, the
program relies on the \"select\" library. The 'select' function is used
to handle operations that would otherwise block a thread (such as
'sock.recvfrom()' and 'input()'). By using this library, we avoid the
need for multiple threads and can simultaneously check both keyboard
input and socket packet reception.

When the program starts, it first prompts you to input the IP address of
the opposite peer, followed by the port that will be used as the
receiving port on this peer, and then the port for the other peer's
receiving port. For example, if the first peer uses ports 50003 and
50006, the other peer must start the program with the reverse sequence
(50006 and 50003) to establish a connection.

If you want to change fragment size please call the menu by writing MENU
to terminal. If you are lost please print HELP.

To run the program put all scripts: protocol.py, P2P.py and the
file_transfer.py into one folder and start the P2P.py.

# Lua script

Please use port 50003 to enable Lua script. This script will provide you
with detailed description of header.

# Results

The project successfully implements a lightweight and reliable protocol
with essential features such as adaptive window management, handshake,
and keep-alive mechanisms. The Go-Back-N method ensures efficient and
error-resilient data transfer. Comprehensive testing confirmed that lost
or damaged packets are handled correctly, maintaining data integrity
throughout the communication. Additionally, Wireshark analysis verified
the correct operation of protocol sequences, including handshake, data
transfer, and connection termination.
