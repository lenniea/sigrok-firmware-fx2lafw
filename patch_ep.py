#!/usr/bin/env python3
"""Step 1: Patch USB descriptors (EP6 OUT), vendor commands, and fx2lafw.c."""
from pathlib import Path
import re


def sub_once(text: str, pat: str, rep: str, label: str) -> str:
    out, n = re.subn(pat, rep, text, count=1, flags=re.MULTILINE)
    assert n == 1, f"Anchor not found: {label}"
    return out


def run(root: Path) -> None:
    # 1. include/dscr.inc: bNumEndpoints 1->2 and append EP6 OUT (0x06)
    p = root / "include" / "dscr.inc"
    s = p.read_text(encoding="utf-8")
    s, n1 = re.subn(
        r"(\.db\s+(?:9|0x09|DSCR_INTERFACE_LEN|DSCR_INTRFC_LEN)\b[^\n]*\n"
        r"\s*\.db\s+(?:4|0x04|DSCR_INTERFACE_TYPE|DSCR_INTRFC_TYPE)\b[^\n]*\n"
        r"\s*\.db\s+(?:0|0x00)\b[^\n]*\n\s*\.db\s+(?:0|0x00)\b[^\n]*\n"
        r"\s*\.db\s+)(?:1|0x01)(\b[^\n]*\n)",
        r"\g<1>2\g<2>", s, flags=re.I,
    )
    ep2_re = re.compile(
        r"(\.db\s+(?:7|0x07|DSCR_ENDPOINT_LEN|DSCR_ENDPNT_LEN)\b[^\n]*\n"
        r"\s*\.db\s+(?:5|0x05|DSCR_ENDPOINT_TYPE|DSCR_ENDPNT_TYPE)\b[^\n]*\n"
        r"\s*\.db\s+0x82\b[^\n]*\n"
        r"\s*\.db\s+(?:2|0x02|ENDPOINT_TYPE_BULK|ENDPNT_TYPE_BULK)\b[^\n]*\n"
        r"(?:\s*\.db\s+(0x[0-9a-fA-F]+|\d+)[^\n]*\n\s*\.db\s+(0x[0-9a-fA-F]+|\d+)[^\n]*\n"
        r"|\s*\.(?:db|dw)\s+([^\n;]+)[^\n]*\n)"
        r"\s*\.db\s+(?:0|0x00)\b[^\n]*\n)", re.I,
    )
    def add_ep6(m: re.Match) -> str:
        pkt = (f"\t.db\t{m.group(2)}\n\t.db\t{m.group(3)}\n"
               if m.group(2) else f"\t.db\t{m.group(4).strip()}\n")
        return (m.group(1) + "\n\t.db\tDSCR_ENDPOINT_LEN\n\t.db\tDSCR_ENDPOINT_TYPE\n"
                "\t.db\t0x06\n\t.db\tENDPOINT_TYPE_BULK\n" + pkt + "\t.db\t0x00\n")
    s, n2 = ep2_re.subn(add_ep6, s)
    assert n1 >= 2 and n2 >= 2, f"dscr.inc match failed ({n1}, {n2})"
    p.write_text(s, encoding="utf-8", newline="\n")
    print(f"[OK] {p}")

    # 2. include/command.h: add CMD_START_OUT (0xb3) and CMD_STOP (0xb4)
    p = root / "include" / "command.h"
    s = sub_once(p.read_text(encoding="utf-8"),
                 r"(#define\s+CMD_GET_REVID_VERSION\s+0xb2\b[^\n]*)",
                 r"\1\n#define CMD_START_OUT\t\t\t0xb3\n#define CMD_STOP\t\t\t0xb4",
                 "command.h")
    p.write_text(s, encoding="utf-8", newline="\n")
    print(f"[OK] {p}")

    # 3. fx2lafw.c: enable EP6 OUT, init PA0=0 (Hantek DIR), route vendor cmds
    p = root / "fx2lafw.c"
    s = p.read_text(encoding="utf-8")
    s = sub_once(s, r"EP6CFG\s*&=\s*~bmVALID\s*;\s*(?:SYNCDELAY\(\)\s*;)?",
                 "EP6CFG = bmVALID | bmTYPE1;\n\tSYNCDELAY();", "EP6CFG")
    s = sub_once(s, r"(EP2GPIFFLGSEL\s*=\s*[^;]+;\s*(?:SYNCDELAY\(\)\s*;)?)",
                 r"\1\n\tRESETFIFO(0x06);\n\tEP6FIFOCFG = bmAUTOOUT;\n\tSYNCDELAY();\n"
                 r"\tEP6GPIFFLGSEL = 0x01;\n\tSYNCDELAY();\n"
                 r"\tPORTACFG &= ~0x01;\n\tIOA &= ~0x01;\n\tOEA |= 0x01;", "EP6FIFO/PA0")
    s = sub_once(s, r"(RESETTOGGLE\s*\(\s*0x82\s*\)\s*;)", r"\1\n\tRESETTOGGLE(0x06);", "TOGGLE")
    s = sub_once(s, r"(RESETFIFO\s*\(\s*0x02\s*\)\s*;)", r"\1\n\tRESETFIFO(0x06);", "FIFO")
    s = sub_once(s, r"(case\s+CMD_START\s*:)", r"\1\n\tcase CMD_START_OUT:", "CMD_START_OUT")
    s = sub_once(s, r"(case\s+CMD_GET_REVID_VERSION\s*:)",
                 r"case CMD_STOP:\n\t\tgpif_stop_all();\n\t\treturn TRUE;\n\t\1", "CMD_STOP")
    s = sub_once(s, r"(\bdefault\s*:\s*\n\s*/\*\s*Unimplemented command\.\s*\*/)",
                 r"case CMD_START_OUT:\n\t\t\tif ((EP0CS & bmEPBUSY) != 0)\n\t\t\t\tbreak;\n"
                 r"\t\t\tif (EP0BCL == sizeof(struct cmd_start_acquisition))\n"
                 r"\t\t\t\tgpif_generation_start((const struct cmd_start_acquisition *)EP0BUF);\n"
                 r"\t\t\tvendor_command = 0;\n\t\t\tbreak;\n\t\t\1", "poll")
    p.write_text(s, encoding="utf-8", newline="\n")
    print(f"[OK] {p}")


if __name__ == "__main__":
    run(Path(__file__).resolve().parent)
