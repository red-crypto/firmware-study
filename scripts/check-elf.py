#!/usr/bin/env python3
"""Validate a linked NUCLEO-F411RE ELF without external Python packages."""

from pathlib import Path
import struct
import sys


FLASH_START, FLASH_END = 0x08000000, 0x08080000
RAM_START, RAM_END = 0x20000000, 0x20020000


class InvalidElf(Exception):
    """The ELF is malformed or incompatible with this board."""


def require(condition, message):
    if not condition:
        raise InvalidElf(message)


def in_region(address, size, start, end):
    return start <= address < end and size <= end - address


def check(path):
    data = path.read_bytes()

    def file_range(offset, size, label):
        require(0 <= offset <= len(data) and 0 <= size <= len(data) - offset,
                f"{label}: file range is truncated")

    def string_at(table, offset, label):
        require(offset < len(table), f"{label}: invalid string offset")
        end = table.find(b"\0", offset)
        require(end != -1, f"{label}: unterminated string")
        return table[offset:end].decode("utf-8", errors="replace")

    file_range(0, 52, "ELF header")
    require(data[:7] == b"\x7fELF\x01\x01\x01",
            "expected ELF32, little-endian, ELF version 1")
    (elf_type, machine, version, entry, phoff, shoff, flags, ehsize,
     phentsize, phnum, shentsize, shnum, shstrndx) = struct.unpack_from(
         "<HHIIIIIHHHHHH", data, 16)
    require(elf_type == 2 and machine == 40 and version == 1,
            "expected an ARM ET_EXEC executable")
    require(ehsize >= 52, "invalid ELF header size")
    require(flags & 0xFF000000 == 0x05000000, "expected ARM EABI version 5")
    require(flags & 0x400 != 0 and flags & 0x200 == 0,
            "expected the ARM hard-float ABI")
    require(entry & 1 != 0 and FLASH_START <= (entry & ~1) < FLASH_END,
            "entry must be a Thumb address in FLASH")
    require(phnum not in (0, 0xFFFF) and phentsize >= 32,
            "missing or unsupported program headers")
    require(shnum != 0 and shstrndx != 0xFFFF and shentsize >= 40,
            "missing or unsupported section headers")
    file_range(phoff, phentsize * phnum, "program headers")
    file_range(shoff, shentsize * shnum, "section headers")

    flash_end = FLASH_START
    ram_end = RAM_START
    loads = []
    for index in range(phnum):
        (kind, offset, vaddr, paddr, filesz, memsz, pflags,
         _align) = struct.unpack_from("<IIIIIIII", data, phoff + index * phentsize)
        if kind != 1:  # PT_LOAD
            continue
        label = f"PT_LOAD[{index}]"
        require(filesz <= memsz, f"{label}: file size exceeds memory size")
        if memsz == 0:
            continue
        in_flash = in_region(vaddr, memsz, FLASH_START, FLASH_END)
        in_ram = in_region(vaddr, memsz, RAM_START, RAM_END)
        require(in_flash or in_ram, f"{label}: virtual memory is outside FLASH/RAM")
        if in_ram:
            ram_end = max(ram_end, vaddr + memsz)
        if filesz:
            file_range(offset, filesz, label)
            require(in_region(paddr, filesz, FLASH_START, FLASH_END),
                    f"{label}: load image is outside FLASH")
            flash_end = max(flash_end, paddr + filesz)
        loads.append((offset, vaddr, paddr, filesz, memsz, pflags))
    require(loads, "no nonempty PT_LOAD segments")
    require(any(vaddr <= (entry & ~1) < vaddr + filesz and pflags & 1
                for _, vaddr, _, filesz, _, pflags in loads),
            "entry is not in a file-backed executable PT_LOAD segment")

    sections = [struct.unpack_from("<IIIIIIIIII", data, shoff + i * shentsize)
                for i in range(shnum)]
    require(0 < shstrndx < shnum, "invalid section-name table index")
    strings = sections[shstrndx]
    require(strings[1] == 3, "section-name table is not a string table")
    file_range(strings[4], strings[5], "section-name table")
    names = data[strings[4]:strings[4] + strings[5]]
    vector = None
    for index, section in enumerate(sections):
        (nameoff, kind, sflags, addr, offset, size, link, _info,
         _align, entsize) = section
        name = string_at(names, nameoff, f"section[{index}]")
        label = name or f"section[{index}]"
        if size and kind != 8:  # SHT_NOBITS has no bytes in the file.
            file_range(offset, size, label)
        if sflags & 2 and size:  # SHF_ALLOC
            require(in_region(addr, size, FLASH_START, FLASH_END)
                    or in_region(addr, size, RAM_START, RAM_END),
                    f"{label}: allocated section is outside FLASH/RAM")
            require(any(vaddr <= addr and addr + size <= vaddr + memsz
                        for _, vaddr, _, _, memsz, _ in loads),
                    f"{label}: allocated section is not covered by PT_LOAD")
            if kind == 8:
                require(in_region(addr, size, RAM_START, RAM_END),
                        f"{label}: zero-initialized section must be in RAM")
        if name == ".bss" or name.startswith(".bss."):
            require(kind == 8 and sflags & 2,
                    f"{label}: expected allocated SHT_NOBITS")
            if size:
                require(in_region(addr, size, RAM_START, RAM_END),
                        f"{label}: BSS is outside RAM")
        if name == ".vector_table":
            require(vector is None, "duplicate .vector_table sections")
            require(addr == FLASH_START and size >= 8 and sflags & 2 and kind == 1,
                    ".vector_table must be allocated file data at FLASH start")
            require(any(vaddr <= addr and addr + size <= vaddr + filesz
                        and offset - loffset == addr - vaddr and paddr == vaddr
                        for loffset, vaddr, paddr, filesz, _, _ in loads),
                    ".vector_table is not mapped to the start of the FLASH image")
            vector = struct.unpack_from("<II", data, offset)
        if kind in (2, 11):  # SHT_SYMTAB / SHT_DYNSYM
            require(entsize >= 16 and size % entsize == 0,
                    f"{label}: invalid symbol-table entries")
            require(link < shnum and sections[link][1] == 3,
                    f"{label}: invalid symbol string table")
            strings = sections[link]
            file_range(strings[4], strings[5], "symbol string table")
            symbols = data[strings[4]:strings[4] + strings[5]]
            for symoff in range(offset, offset + size, entsize):
                symname, _, _, info, _, shndx = struct.unpack_from("<IIIBBH", data, symoff)
                if info >> 4 == 1 and shndx == 0:  # Undefined STB_GLOBAL; weak is allowed.
                    name = string_at(symbols, symname, "undefined symbol")
                    raise InvalidElf(f"undefined global symbol: {name or '<unnamed>'}")

    require(vector is not None, "missing .vector_table")
    stack, reset = vector
    require(RAM_START <= stack <= RAM_END and stack % 8 == 0,
            "initial stack pointer must be 8-byte aligned in RAM")
    require(reset & 1 != 0 and reset == entry,
            "reset vector must be Thumb and equal to the ELF entry")
    print(f"ELF OK: ARM EABI5 hard-float; FLASH image span {flash_end - FLASH_START}"
          f"/{FLASH_END - FLASH_START} bytes; RAM static span {ram_end - RAM_START}"
          f"/{RAM_END - RAM_START} bytes (runtime stack excluded)")
    print(f"vector=0x{FLASH_START:08x} SP=0x{stack:08x} reset=0x{reset:08x}")


def main():
    if len(sys.argv) != 2:
        print("usage: check-elf.py <firmware.elf>", file=sys.stderr)
        return 1
    try:
        check(Path(sys.argv[1]))
    except (InvalidElf, OSError, struct.error) as error:
        print(f"ELF ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
