"""

Copyright (c) 2020 Alex Forencich

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.

"""

import logging

import cocotb

from .version import __version__
from .constants import AxiProt, AxiResp
from .axil_channels import AxiLiteAWSink, AxiLiteWSink, AxiLiteBSource, AxiLiteARSink, AxiLiteRSource
from .memory import Memory
from .reset import Reset


class AxiLiteRamWrite(Memory, Reset):
    def __init__(self, bus, clock, reset=None, reset_active_level=True, size=1024, mem=None, *args, **kwargs):
        self.bus = bus
        self.clock = clock
        self.reset = reset
        self.log = logging.getLogger(f"cocotb.{bus.aw._entity._name}.{bus.aw._name}")

        self.log.info("AXI lite RAM model (write)")
        self.log.info("cocotbext-axi version %s", __version__)
        self.log.info("Copyright (c) 2020 Alex Forencich")
        self.log.info("https://github.com/alexforencich/cocotbext-axi")

        super().__init__(size, mem, *args, **kwargs)

        self.aw_channel = AxiLiteAWSink(bus.aw, clock, reset, reset_active_level)
        self.aw_channel.queue_occupancy_limit = 2
        self.w_channel = AxiLiteWSink(bus.w, clock, reset, reset_active_level)
        self.w_channel.queue_occupancy_limit = 2
        self.b_channel = AxiLiteBSource(bus.b, clock, reset, reset_active_level)
        self.b_channel.queue_occupancy_limit = 2

        self.address_width = len(self.aw_channel.bus.awaddr)
        self.width = len(self.w_channel.bus.wdata)
        self.byte_size = 8
        self.byte_lanes = self.width // self.byte_size
        self.strb_mask = 2**self.byte_lanes-1

        self.log.info("AXI lite RAM model configuration:")
        self.log.info("  Memory size: %d bytes", len(self.mem))
        self.log.info("  Address width: %d bits", self.address_width)
        self.log.info("  Byte size: %d bits", self.byte_size)
        self.log.info("  Data width: %d bits (%d bytes)", self.width, self.byte_lanes)

        self.log.info("AXI lite RAM model signals:")
        for bus in (self.bus.aw, self.bus.w, self.bus.b):
            for sig in sorted(list(set().union(bus._signals, bus._optional_signals))):
                if hasattr(bus, sig):
                    self.log.info("  %s width: %d bits", sig, len(getattr(bus, sig)))
                else:
                    self.log.info("  %s: not present", sig)

        assert self.byte_lanes == len(self.w_channel.bus.wstrb)
        assert self.byte_lanes * self.byte_size == self.width

        self._process_write_cr = None

        self._init_reset(reset, reset_active_level)

    def _handle_reset(self, state):
        if state:
            self.log.info("Reset asserted")
            if self._process_write_cr is not None:
                self._process_write_cr.kill()
                self._process_write_cr = None

            self.aw_channel.clear()
            self.w_channel.clear()
            self.b_channel.clear()
        else:
            self.log.info("Reset de-asserted")
            if self._process_write_cr is None:
                self._process_write_cr = cocotb.fork(self._process_write())

    async def _process_write(self):
        while True:
            aw = await self.aw_channel.recv()

            addr = (int(aw.awaddr) // self.byte_lanes) * self.byte_lanes
            prot = AxiProt(getattr(aw, 'awprot', AxiProt.NONSECURE))

            w = await self.w_channel.recv()

            data = int(w.wdata)
            strb = int(getattr(w, 'wstrb', self.strb_mask))

            # todo latency

            self.mem.seek(addr % self.size)

            data = data.to_bytes(self.byte_lanes, 'little')

            if self.log.isEnabledFor(logging.INFO):
                self.log.info("Write data awaddr: 0x%08x awprot: %s wstrb: 0x%02x data: %s",
                        addr, prot, strb, ' '.join((f'{c:02x}' for c in data)))

            for i in range(self.byte_lanes):
                if strb & (1 << i):
                    self.mem.write(data[i:i+1])
                else:
                    self.mem.seek(1, 1)

            b = self.b_channel._transaction_obj()
            b.bresp = AxiResp.OKAY

            await self.b_channel.send(b)


class AxiLiteRamRead(Memory, Reset):
    def __init__(self, bus, clock, reset=None, reset_active_level=True, size=1024, mem=None, *args, **kwargs):
        self.bus = bus
        self.clock = clock
        self.reset = reset
        self.log = logging.getLogger(f"cocotb.{bus.ar._entity._name}.{bus.ar._name}")

        self.log.info("AXI lite RAM model (read)")
        self.log.info("cocotbext-axi version %s", __version__)
        self.log.info("Copyright (c) 2020 Alex Forencich")
        self.log.info("https://github.com/alexforencich/cocotbext-axi")

        super().__init__(size, mem, *args, **kwargs)

        self.ar_channel = AxiLiteARSink(bus.ar, clock, reset, reset_active_level)
        self.ar_channel.queue_occupancy_limit = 2
        self.r_channel = AxiLiteRSource(bus.r, clock, reset, reset_active_level)
        self.r_channel.queue_occupancy_limit = 2

        self.address_width = len(self.ar_channel.bus.araddr)
        self.width = len(self.r_channel.bus.rdata)
        self.byte_size = 8
        self.byte_lanes = self.width // self.byte_size

        self.log.info("AXI lite RAM model configuration:")
        self.log.info("  Memory size: %d bytes", len(self.mem))
        self.log.info("  Address width: %d bits", self.address_width)
        self.log.info("  Byte size: %d bits", self.byte_size)
        self.log.info("  Data width: %d bits (%d bytes)", self.width, self.byte_lanes)

        self.log.info("AXI lite RAM model signals:")
        for bus in (self.bus.ar, self.bus.r):
            for sig in sorted(list(set().union(bus._signals, bus._optional_signals))):
                if hasattr(bus, sig):
                    self.log.info("  %s width: %d bits", sig, len(getattr(bus, sig)))
                else:
                    self.log.info("  %s: not present", sig)

        assert self.byte_lanes * self.byte_size == self.width

        self._process_read_cr = None

        self._init_reset(reset, reset_active_level)

    def _handle_reset(self, state):
        if state:
            self.log.info("Reset asserted")
            if self._process_read_cr is not None:
                self._process_read_cr.kill()
                self._process_read_cr = None

            self.ar_channel.clear()
            self.r_channel.clear()
        else:
            self.log.info("Reset de-asserted")
            if self._process_read_cr is None:
                self._process_read_cr = cocotb.fork(self._process_read())

    async def _process_read(self):
        while True:
            ar = await self.ar_channel.recv()

            addr = (int(ar.araddr) // self.byte_lanes) * self.byte_lanes
            prot = AxiProt(getattr(ar, 'arprot', AxiProt.NONSECURE))

            # todo latency

            self.mem.seek(addr % self.size)

            data = self.mem.read(self.byte_lanes)

            r = self.r_channel._transaction_obj()
            r.rdata = int.from_bytes(data, 'little')
            r.rresp = AxiResp.OKAY

            await self.r_channel.send(r)

            if self.log.isEnabledFor(logging.INFO):
                self.log.info("Read data araddr: 0x%08x arprot: %s data: %s",
                        addr, prot, ' '.join((f'{c:02x}' for c in data)))


class AxiLiteRam(Memory):
    def __init__(self, bus, clock, reset=None, reset_active_level=True, size=1024, mem=None, *args, **kwargs):
        self.write_if = None
        self.read_if = None

        super().__init__(size, mem, *args, **kwargs)

        self.write_if = AxiLiteRamWrite(bus.write, clock, reset, reset_active_level, mem=self.mem)
        self.read_if = AxiLiteRamRead(bus.read, clock, reset, reset_active_level, mem=self.mem)
