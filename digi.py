from pathlib import Path
import os
import sys
import glob
import shutil
import polib
from datetime import datetime

# GLOBALS
ptr_length = 0x4  # 4 bytes
hex_dir_name = "HEX"
po_dir_name = "PO"
tbl_codes = []
tbl_chars = []
tbl_codes_2chars = []
tbl_chars_2chars = []

# SPECIAL NON 2-BYTE CODE
new_line_code = '0A'  # Character for new line (hex)
new_line = '\n'

# CODE TO TERMINATE READ
eol_code = '00'

# Default vars (can be overridden by args)
tbl_read_path = Path('xros.tbl')
tbl_2chars_read_path = Path('xros_2chars.tbl')
file_read_path = Path("MESPAK00.PAK")
folder_read_path = Path('MESPAK00' + os.sep + "PO")

lang_code = 'br'

# File header offsets (documentation)
n_address = 0x00
files_v_address = 0x04
table_offset = 0x10  # table for file addresses starts here


# ---------- Utility functions ----------

def get_hex_from_bin(path, start, length=None):
    """Read binary file and return hex (uppercase). start and length in bytes."""
    # path can be Path or string
    with open(path, 'rb') as f:
        f.seek(start)
        if length is not None:
            data = f.read(length)
        else:
            data = f.read()
    return data.hex().upper()


def get_hex(path, start=0, length=None):
    """
    Read a file that contains hex characters (text) and return the substring (uppercase).
    start and length are measured in characters of the hex text (not bytes).
    """
    # Accept Path or str
    with open(path, 'r', encoding='utf-8') as f:
        f.seek(start)
        if length is not None:
            hexdata = f.read(length).upper()
        else:
            hexdata = f.read().upper()
    return hexdata


def LE_to_int(hexval):
    """Convert a hex string representing little-endian bytes to int."""
    if hexval is None or hexval == '':
        return 0
    # hexval should be even-length
    ba = bytearray.fromhex(hexval)
    ba.reverse()
    return int.from_bytes(ba, byteorder='big', signed=False)


def int_to_LE(intval):
    """Convert integer to little-endian hex string of ptr_length bytes (uppercase)."""
    cnv_hex = intval.to_bytes(ptr_length, byteorder='little', signed=False)
    return cnv_hex.hex().upper()


def generate_PO_file(texts, path_without_ext, lang_code):
    """Generate .pot and .po file from list of texts. path_without_ext is base filename (no ext)."""
    now = datetime.now()
    time_string = now.astimezone().strftime("%Y-%m-%d %H:%M:%S%z")
    po = polib.POFile()
    po.metadata = {
        'Project-Id-Version': '1.0',
        'Report-Msgid-Bugs-To': 'sora',
        'POT-Creation-Date': time_string,
        'PO-Revision-Date': time_string,
        'Last-Translator': 'sora',
        'Language-Team': 'Sora Leon',
        'Language': lang_code,
        'MIME-Version': '1.0',
        'Content-Type': 'text/plain; charset=UTF-8',
        'Content-Transfer-Encoding': '8bit',
        'Plural-Forms': 'nplurals=2; plural=(n!=1);',
    }

    zerof = len(str(len(texts)))
    for idx, text in enumerate(texts):
        entry = polib.POEntry(
            msgctxt=str(idx).zfill(zerof),
            msgid=text,
            msgstr="",
        )
        po.append(entry)

    pot_path = f"{path_without_ext}.pot"
    po_path = f"{path_without_ext}_{lang_code}.po"

    po.save(pot_path)
    po.save(po_path)


def get_char_from_table(string_h):
    """Return the mapped character for a hex code (string) from tbl_codes/tbl_chars."""
    try:
        idx = tbl_codes.index(string_h)
        return tbl_chars[idx]
    except ValueError:
        return ""


def write_hex(path, hexstring):
    """Write a hexstring (without spaces) as binary to path."""
    with open(path, 'wb') as f:
        f.write(bytearray.fromhex(hexstring))


def populate_tbl(tbl_path, tbl_2chars_path):
    """Read .tbl and .tbl_2chars files and populate global lists."""
    global tbl_codes, tbl_chars, tbl_codes_2chars, tbl_chars_2chars
    tbl_codes = []
    tbl_chars = []
    tbl_codes_2chars = []
    tbl_chars_2chars = []

    # Read single-byte mapping
    with open(tbl_path, "r", encoding='utf-8') as fh:
        lines = [ln.rstrip('\n') for ln in fh if ln.strip() != ""]
    for line in lines:
        if '=' in line:
            left, right = line.split('=', 1)
            tbl_codes.append(left.strip().upper())
            tbl_chars.append(right)

    # Read 2-chars-per-tile mapping (if provided)
    with open(tbl_2chars_path, "r", encoding='utf-8') as fh:
        lines = [ln.rstrip('\n') for ln in fh if ln.strip() != ""]
    for line in lines:
        if '=' in line:
            left, right = line.split('=', 1)
            tbl_codes_2chars.append(left.strip().upper())
            tbl_chars_2chars.append(right)


# ---------- UNPACK ----------

def unpack():
    # args handling was previously in main; here we just use globals set by main
    file_path = Path(file_read_path)
    if not file_path.exists():
        print(f"File not found: {file_path}")
        return

    file_stem = file_path.stem
    wrk_path = os.getcwd()
    dir_file = os.path.join(wrk_path, file_stem)
    dir_hex = os.path.join(dir_file, hex_dir_name)
    dir_po = os.path.join(dir_file, po_dir_name)

    # Read number of files (4 bytes little-endian)
    n_files_h = get_hex_from_bin(file_path, n_address, ptr_length)
    n_files = LE_to_int(n_files_h)

    # Read files table: each entry is 0x10 bytes
    files_ptrs = []
    files_size = []
    files_junk = []

    for i in range(n_files):
        entry_base = table_offset + (0x10 * i)
        file_ptr = get_hex_from_bin(file_path, entry_base + 0x00, ptr_length)
        file_size = get_hex_from_bin(file_path, entry_base + 0x04, ptr_length)
        file_size2 = get_hex_from_bin(file_path, entry_base + 0x08, ptr_length)
        file_jnk = get_hex_from_bin(file_path, entry_base + 0x0C, ptr_length)
        # store values (as hex strings). Keep original hex for later if needed
        files_ptrs.append(file_ptr)
        files_size.append(file_size)  # we will use this one
        files_junk.append(file_jnk)

    # Create directories (clean if exist)
    if os.path.exists(dir_file):
        shutil.rmtree(dir_file)
    os.makedirs(dir_hex, exist_ok=True)
    os.makedirs(dir_po, exist_ok=True)

    # Extract each embedded file to a hex-text file
    files_h_paths = []
    for idx, (ptr_h, size_h) in enumerate(zip(files_ptrs, files_size)):
        ptr = LE_to_int(ptr_h)
        size = LE_to_int(size_h)
        data_hex = get_hex_from_bin(file_path, ptr, size)
        out_name = f"{file_stem}-{str(idx).zfill(2)}"
        out_path = os.path.join(dir_hex, out_name)
        with open(out_path, "w", encoding='utf-8') as fh:
            fh.write(data_hex)
        files_h_paths.append(out_path)

    # Populate conversion tables
    populate_tbl(tbl_read_path, tbl_2chars_read_path)

    # Now, for each extracted file, parse internal pointer table and extract texts
    all_texts = []  # list of lists

    for hex_file in files_h_paths:
        # read entire hex text file
        hex_text = get_hex(hex_file, 0, None)

        # pointers in the embedded file are stored as little-endian uint32 in hex text
        # pointer table structure: 0x0-0x3 junk, 0x4-0x7 number of entries, then entries starting at 0x8
        # because we are reading hex as characters, offsets are in hex-nibbles; so a byte offset x maps to char offset x*2
        # get number of entries:
        ptr_len_chars = ptr_length * 2  # number of hex characters per pointer (8 for 4 bytes)

        # read first 4 bytes (junk) skip, then read number of entries:
        num_entries_hex = hex_text[ptr_len_chars:ptr_len_chars*2]  # characters from 8 to 16
        e_number = LE_to_int(num_entries_hex)

        # pointers list (as integer byte offsets)
        text_ptrs = []
        # pointer table starts at byte offset 0x8
        base_ptr_table_char_offset = ptr_len_chars * 2  # 8 bytes * 2 chars? careful: we want character index corresponding to byte offset 0x8
        # Simpler: pointer table first pointer in bytes is 0x8 (byte offset). Character offset = 0x8 * 2 = 16
        ptr_table_char_start = 0x8 * 2

        for i in range(e_number):
            char_offset = ptr_table_char_start + (i * ptr_len_chars)
            ptr_hex = hex_text[char_offset:char_offset + ptr_len_chars]
            ptr_val = LE_to_int(ptr_hex)
            text_ptrs.append(ptr_val)

        # Now extract texts: each pointer gives byte offset; char start = ptr*2
        texts_in_file = []
        for idx_ptr, p in enumerate(text_ptrs):
            char_start = p * 2
            if idx_ptr + 1 < len(text_ptrs):
                next_p = text_ptrs[idx_ptr + 1]
                length_chars = (next_p - p) * 2
                chunk_hex = hex_text[char_start:char_start + length_chars]
            else:
                chunk_hex = hex_text[char_start:]

            # Convert chunk_hex into text string using tables
            my_text = ""
            my_2bytechar = ""  # IMPORTANT: reset for each entry
            # iterate bytes (2 hex chars)
            num_bytes = len(chunk_hex) // 2
            for b_idx in range(num_bytes):
                this_byte = chunk_hex[b_idx*2:(b_idx+1)*2]
                if this_byte == eol_code:
                    # end of this entry, append and stop parsing this chunk
                    break
                if this_byte == new_line_code:
                    my_text += new_line
                    continue
                # Build possible 2-byte code
                if my_2bytechar == "":
                    my_2bytechar = this_byte
                else:
                    # candidate 2-byte hex string
                    two_hex = (my_2bytechar + this_byte).upper()
                    # Try 2-chars-per-tile mapping first
                    if two_hex in tbl_codes_2chars:
                        idx_map = tbl_codes_2chars.index(two_hex)
                        my_text += tbl_chars_2chars[idx_map]
                        my_2bytechar = ""
                    elif two_hex in tbl_codes:
                        # In some tables two-byte sequences may be in tbl_codes as well
                        idx_map = tbl_codes.index(two_hex)
                        my_text += tbl_chars[idx_map]
                        my_2bytechar = ""
                    else:
                        # treat my_2bytechar as a single-byte code (fallback)
                        if my_2bytechar in tbl_codes:
                            idx_map = tbl_codes.index(my_2bytechar)
                            my_text += tbl_chars[idx_map]
                        # now set my_2bytechar to current byte (this_byte) for next loop
                        my_2bytechar = this_byte

            # if leftover in my_2bytechar after loop, try to resolve it
            if my_2bytechar:
                if my_2bytechar in tbl_codes:
                    idx_map = tbl_codes.index(my_2bytechar)
                    my_text += tbl_chars[idx_map]

            texts_in_file.append(my_text)

        all_texts.append(texts_in_file)

    # Save PO files
    for idx, p in enumerate(files_h_paths):
        base_name = Path(p).name
        base_noext = os.path.join(dir_po, base_name)
        generate_PO_file(all_texts[idx], base_noext, lang_code)

    # Cleanup hex dir if desired
    shutil.rmtree(dir_hex, ignore_errors=True)
    print('arquivo desempacotado com sucesso!')


# ---------- REPACK ----------
def repack():
    """
    Read .po files from folder_read_path, build new binary PAK according to logic.
    This function tries to preserve your original algorithm but fixes issues found.
    """
    in_dir = Path(folder_read_path)
    if not in_dir.exists():
        print(f"Folder not found: {in_dir}")
        return

    po_paths = sorted(in_dir.glob("*.po"))
    po_files = [polib.pofile(str(p)) for p in po_paths]

    populate_tbl(tbl_read_path, tbl_2chars_read_path)

    # Build file_hex_all : list of files, each is list of entry hex strings
    file_hex_all = []

    for po in po_files:
        file_hex = []
        # optionally detect special ranges as original code did (kept simple here)
        digi_names = False

        for entry in po:
            entry_hex = ''
            if entry.msgstr != '':
                msg = entry.msgstr
            else:
                msg = entry.msgid


            # 
            idx = 0
            while idx < len(msg):
                ch = msg[idx]
                found = False
                # try 2-char mapping
                if idx + 1 < len(msg):
                    ch2 = msg[idx + 1]
                    candidate = ch + ch2
                    # look in tbl_chars_2chars
                    if candidate in tbl_chars_2chars:
                        i = tbl_chars_2chars.index(candidate)
                        entry_hex += tbl_codes_2chars[i]
                        idx += 2
                        found = True
                if not found:
                    if ch == new_line:
                        entry_hex += new_line_code
                        idx += 1
                    elif ch in tbl_chars:
                        i = tbl_chars.index(ch)
                        entry_hex += tbl_codes[i]
                        idx += 1
                    else:
                        # If character not found in table -> fallback: try encode as ascii hex
                        # (You may change fallback strategy as required)
                        try:
                            ch_bytes = ch.encode('shift_jis')
                        except Exception:
                            ch_bytes = ch.encode('utf-8', errors='replace')
                        entry_hex += ch_bytes.hex().upper()
                        idx += 1

            # Replace special long sequences with special codes (kept same tables from original)
            special_code = [
                '5E30', '5E31', '5E32', '5E33', '5E34', '5E35', '5E36', '5E37',
                '5E50', '5E5E', '5E62', '5E69', '5E6E', '7E49'
            ]

            # these sequences are from original script (kept as-is)
            special = [
                '817782628267824F824F8178',
                '817782628267824F82508178',
                '817782628267824F82518178',
                '817782628267824F82528178',
                '817782628267824F82538178',
                '817782628267824F82548178',
                '817782628267824F82558178',
                '817782628267824F82568178',
                '817782628267824F82578178',
                '817782628267824F82588178',
                '8177826282678250824F8178',
                '817782628267825082508178',
                '817782628267825082518178',
                '817782628267825082528178'
            ]
            for s, c in zip(special, special_code):
                entry_hex = entry_hex.replace(s, c)

            # (repeat other special replacement groups as in original if needed)
            # Terminate entry and pad to multiple of 4 bytes
            entry_hex += eol_code
            # Add at least one 00 and pad to multiple of 4 bytes
            while ((len(entry_hex) // 2) % ptr_length) != 0:
                entry_hex += '00'
            # If already multiple of 4 bytes, original doc asked to add 00 00 00 00
            # The documentation says: IF already multiple of 4, add '00 00 00 00'
            if ((len(entry_hex) // 2) % ptr_length) == 0:
                # In original doc they want at least one 00 and maybe add full 4 zeros.
                # To keep the original intention, we add an extra 4 bytes padding.
                entry_hex += '00000000'
            file_hex.append(entry_hex)

        file_hex_all.append(file_hex)

    # Build new pointers table and content
    new_ptrs_hex_all = []
    new_ptrs_len_all = []
    for file_entries in file_hex_all:
        lens = [len(e) // 2 for e in file_entries]  # bytes per entry
        new_ptrs_len_all.append(lens)

    # For each file, build pointer list (relative offsets inside the file chunk)
    for lengths in new_ptrs_len_all:
        ptrs = []
        # first pointer is after the pointer table inside the file chunk:
        # file internal header = 8 bytes (0x00 junk + 4 bytes number of entries) then pointer table (4 * n entries)
        internal_base = 0x8 + (len(lengths) * 0x4)
        curr = internal_base
        ptrs.append(int_to_LE(curr))
        for l in lengths[:-1]:
            curr += l
            ptrs.append(int_to_LE(curr))
        new_ptrs_hex_all.append(ptrs)

    # Build PAK header
    header_hex = ''
    header_hex += int_to_LE(len(new_ptrs_hex_all))
    header_hex += int_to_LE(0x31302E32)  # original magic?
    header_hex += int_to_LE(0)
    header_hex += int_to_LE(0)

    # Build files table and data sections
    new_files_table_hex = ''
    only_files_hex_all = ''
    seed = (len(new_ptrs_hex_all) * 0x10) + 0x10  # seed offset to first file in bytes

    for ptrs_hex, texts_hex in zip(new_ptrs_hex_all, file_hex_all):
        this_file_hex = ''
        this_file_hex += int_to_LE(0)  # junk
        this_file_hex += int_to_LE(len(ptrs_hex))  # number of pointers
        # append pointer values (already in LE hex strings)
        for p in ptrs_hex:
            this_file_hex += p
        # append texts
        for t in texts_hex:
            this_file_hex += t

        only_files_hex_all += this_file_hex

        new_files_table_hex += int_to_LE(seed)
        file_size_bytes = len(this_file_hex) // 2
        new_files_table_hex += int_to_LE(file_size_bytes)
        new_files_table_hex += int_to_LE(file_size_bytes)
        new_files_table_hex += int_to_LE(0x80000000)
        seed += file_size_bytes

    new_PAK = header_hex + new_files_table_hex + only_files_hex_all

    out_path = Path(str(folder_read_path).split(os.sep)[0] + '.REPAK')
    write_hex(out_path, new_PAK)
    print('Arquivo recriado com sucesso!')


# ---------- main / CLI ----------
def main():
    error_str = ("Desenvolvido por Sora Leon\n\tFalta alguns argumentos!\n\n\tCOMO USAR O UNPACK:\n\n\tpython digi.py -unpack <file-path> <tbl-path> <tbl-2chars-path>\n\n\tExemplo:\n\tpython digi.py -unpack MESPAK00.PAK xros.tbl xros_2chars.tbl\n\n\tCOMO USAR O REPACK:\n\n\tpython digi.py -repack <folder-path> <tbl-path> <tbl-2chars-path>\n\n\tExemplo:\n\tpython digi.py -repack CAMINHODAPASTA/NOMEDOARQUIVO xros.tbl xros_2chars.tbl\n")

    if len(sys.argv) != 5:
        print(error_str)
        return

    mode = sys.argv[1]
    path_arg = sys.argv[2]
    global tbl_read_path, tbl_2chars_read_path, file_read_path, folder_read_path

    tbl_read_path = Path(sys.argv[3])
    tbl_2chars_read_path = Path(sys.argv[4])

    if mode == '-unpack':
        file_read_path = Path(path_arg)
        unpack()
    elif mode == '-repack':
        folder_read_path = Path(path_arg)
        repack()
    else:
        print(error_str)


if __name__ == "__main__":
    main()

