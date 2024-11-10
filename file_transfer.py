import os


def receive_data(packet_handler, ack_send, output_dir="received_files"):
    os.makedirs(output_dir, exist_ok=True)

    # Receiving file information (filename:size of file)
    flags, _, _, _, _, _, _, file_info = packet_handler.receiving_messages()
    file_info = file_info.decode()
    filename, file_size = file_info.split(":")
    file_size = int(file_size)

    # Creating a path where we will store the input DATA
    output_path = os.path.join(output_dir, filename)

    window = 5
    fin_received = False

    if "DATA" in flags:
        # Opening file as binary to store data by segments
        received_size = 0
        with open(output_path, "wb") as f:
            while not fin_received:
                window_increment = 0
                while window_increment < window:
                    # Receiving single fragment
                    flags, _, _, _, _, _, _, fragment = packet_handler.receiving_messages()
                    window_increment += 1
                    if "DATA" in flags:
                        f.write(fragment)
                        received_size += len(fragment)
                        print(f"Received {received_size}/{file_size} bytes")
                        if "FIN" in flags:
                            print(f"File {filename} received successfully and saved to {output_path}")
                            fin_received = True
                            break
                # set flag to send the acknowledgement from sending thread
                ack_send.set()
                # wait for the sending thread to send the acknowledgement
                while ack_send.is_set():
                    pass


def send_data(packet_handler, acknowledge_data_wait):
    packet_handler.sending_packet("DATA", b"", 0, 1)
    file_path = input("\nEnter the path to the file you want to send: ")
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
    file_name = os.path.basename(file_path)
    file_info = file_name + ":" + str(file_size)
    packet_handler.sending_packet("DATA", file_info.encode(), 0, 1)

    total_segments = (file_size + segment_size - 1) // segment_size
    # if number of total segments is smaller then window
    if window > total_segments:
        window = total_segments
    print(f"Sending file in {total_segments} segments.")
    # init sequence number
    seq_num = 0
    # compute number of iterations
    iteration_windows = total_segments // window
    with open(file_path, 'rb') as file:
        for i in range(iteration_windows):
            while window_increment < window:
                if total_segments - (i * window) < window:
                    print("TOTAL" + str(total_segments - (i * window)))
                    window = total_segments - (i * window)
                segment_data = file.read(segment_size)
                if seq_num == total_segments - 1:
                    packet_handler.sending_packet("DATAFIN", segment_data, seq_num, window)
                    break
                packet_handler.sending_packet("DATA", segment_data, seq_num, window)
                window_increment += 1
                seq_num += 1
            # wait for the DATAACK packet from receiving peer
            while True:
                if acknowledge_data_wait.is_set():
                    acknowledge_data_wait.clear()
                    window_increment = 0
                    print("DATAACK received")
                    break

