local stn_protocol = Proto("stn", "stn_protocol")

-- Define the fields of the protocol
local f_sequence_num = ProtoField.uint32("stn.sequence_num", "Sequence Number", base.DEC)
local f_flags = ProtoField.uint8("stn.flags", "Flags", base.HEX)
local f_checksum = ProtoField.uint16("stn.checksum", "Checksum", base.HEX)
local f_message = ProtoField.string("stn.message", "Payload")


-- Add the fields to the protocol
stn_protocol.fields = {f_sequence_num, f_flags, f_checksum, f_message}

-- Function to dissect the protocol
function stn_protocol.dissector(buffer, pinfo, tree)
    -- Check if the packet is at least as long as the header
    local header_size = 7
    if buffer:len() < header_size then return end

    -- Set the protocol name in the packet list
    pinfo.cols.protocol = stn_protocol.name

    -- Create a subtree for the protocol
    local subtree = tree:add(stn_protocol, buffer(), "STN_header")

    -- Add fields to the subtree
    subtree:add(f_sequence_num, buffer(0, 4))
    local flags = buffer(4, 1):uint()
    subtree:add(f_flags, buffer(4, 1)):append_text(" (" .. decode_flags(flags) .. ")")
    subtree:add(f_checksum, buffer(5, 2))

    -- Add the payload as a string if it exists
    if buffer:len() > header_size then
        subtree:add(f_message, buffer(header_size):string())
    end
end

-- Function to decode flags
function decode_flags(flags)
    local flag_names = {
        [0x01] = "SYN",
        [0x02] = "ACK",
        [0x04] = "ERR",
        [0x08] = "FIN",
        [0x10] = "EXIT",
        [0x20] = "DATA",
        [0x40] = "TXT",
        [0x80] = "KEA",
    }
    local decoded = {}
    for bit, name in pairs(flag_names) do
        if flags & bit ~= 0 then
            table.insert(decoded, name)
        end
    end
    return table.concat(decoded, ", ")
end

-- Found protocol by port
local udp_port = DissectorTable.get("udp.port")
udp_port:add(50003, stn_protocol)
