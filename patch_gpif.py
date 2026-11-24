#!/usr/bin/env python3
"""Step 2: Patch gpif-acquisition.h and gpif-acquisition.c for 8/16-bit output + CTL0/PA0."""
from pathlib import Path
import re


def sub_once(text: str, pat: str, rep: str, label: str) -> str:
    out, n = re.subn(pat, rep, text, count=1, flags=re.MULTILINE | re.DOTALL)
    assert n == 1, f"Anchor not found: {label}"
    return out


def run(root: Path) -> None:
    # 1. include/gpif-acquisition.h: add function prototypes
    p = root / "include" / "gpif-acquisition.h"
    s = p.read_text(encoding="utf-8")
    if "gpif_generation_start" not in s:
        s = sub_once(
            s,
            r"(void\s+gpif_poll\s*\(\s*void\s*\)\s*;)",
            r"\1\nbool gpif_generation_start(const struct cmd_start_acquisition *cmd);\n"
            r"void gpif_stop_all(void);",
            "gpif-acquisition.h",
        )
        p.write_text(s, encoding="utf-8", newline="\n")
    print(f"[OK] {p}")

    # 2. gpif-acquisition.c: safe input reset + 8/16-bit GPIF FIFO Write waveform
    p = root / "gpif-acquisition.c"
    s = sub_once(
        p.read_text(encoding="utf-8"),
        r"(gpif_acquisition_start\s*\([^)]*\)\s*\{)",
        r"\1\n\tIOA &= ~0x01;\n\tGPIFIDLECTL = 0x00;\n",
        "gpif_acquisition_start",
    )

    gpif_funcs = """
void gpif_stop_all(void)
{
\tGPIFABORT = 0xff;
\twhile (!(GPIFTRIG & 0x80));
\tGPIFIDLECTL = 0x00;
\tGPIFIDLECS = 0x00;
\tIOA &= ~0x01;
\tSYNCDELAY();
\tFIFORESET = 0x80; SYNCDELAY();
\tEP6FIFOCFG = 0;   SYNCDELAY();
\tFIFORESET = 0x06; SYNCDELAY();
\tEP6FIFOCFG = bmAUTOOUT; SYNCDELAY();
\tFIFORESET = 0x00; SYNCDELAY();
}

bool gpif_generation_start(const struct cmd_start_acquisition *cmd)
{
\tuint8_t i;
\tuint16_t delay;
\txdata volatile BYTE *wf2 = (&GPIF_WAVE_DATA) + 64;

\tgpif_stop_all();
\tFIFORESET = 0x80; SYNCDELAY();
\tEP6FIFOCFG = (cmd->flags & CMD_START_FLAGS_SAMPLE_16BIT) ? (bmAUTOOUT | bmWORDWIDE) : bmAUTOOUT;
\tSYNCDELAY();
\tFIFORESET = 0x00; SYNCDELAY();

\tfor (i = 0; i < 4; i++) { OUTPKTEND = 0x86; SYNCDELAY(); }

\tIFCONFIG = (cmd->flags & CMD_START_FLAGS_CLK_48MHZ)
\t\t? (bmIFCLKSRC | bm3048MHZ | bmIFCLKOE | bmGSTATE | bmIFGPIF)
\t\t: (bmIFCLKSRC | bmIFCLKOE | bmGSTATE | bmIFGPIF);
\tSYNCDELAY();

\tGPIFCTLCFG = 0x00;
\tGPIFIDLECTL = 0x01; /* Saleae clone DIR = 1 (A->B output) */
\tGPIFIDLECS = 0x01;
\tIOA |= 0x01;        /* Hantek 6022BL 1DIR/2DIR = 1 (output) */
\tSYNCDELAY();

\tdelay = ((uint16_t)cmd->sample_delay_h << 8) | cmd->sample_delay_l;
\tif (delay < 1) delay = 1;

\tGPIFWFSELECT = (0x3 << 6) | (0x2 << 4) | (0x2 << 2) | (0x0 << 0);

\t/* State 0: Wait while EP6 Empty flag == 1, hold CTL0 = 1 */
\twf2[0]  = (0 << 3) | 1;
\twf2[8]  = 0x03;
\twf2[16] = 0x01;
\twf2[24] = (6 << 3) | 6;

\t/* State 1: Drive PB0..7 (and PD0..7 if 16-bit) from EP6 FIFO, hold `delay` */
\twf2[1]  = (delay > 255) ? 255 : (uint8_t)delay;
\twf2[9]  = 0x02;
\twf2[17] = 0x01;
\twf2[25] = 0x00;

\tGPIFTRIG = 2;
\treturn true;
}
"""
    p.write_text(s.rstrip() + "\n" + gpif_funcs, encoding="utf-8", newline="\n")
    print(f"[OK] {p}")


if __name__ == "__main__":
    run(Path(__file__).resolve().parent)
