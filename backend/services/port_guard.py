#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3

"""
Frees a TCP port before listening on it: finds the processes that hold a
listening socket on that port (through /proc) and stops them.

Only processes the current user is allowed to signal can be stopped, which in
practice is a previous instance of this same application left behind.
"""

import os
import signal
import time
from pathlib import Path


cTcpListenState = "0A"


def fGetListeningInodes(pPort: int) -> set:
  """Returns the inodes of the sockets listening on a TCP port (IPv4 and IPv6)"""
  sInodes = set()
  for vTableName in ("/proc/net/tcp", "/proc/net/tcp6"):
    try:
      aLines = Path(vTableName).read_text(encoding="utf-8").splitlines()[1:]
    except OSError:
      continue
    for vLine in aLines:
      aFields = vLine.split()
      if len(aFields) < 10:
        continue
      try:
        vLocalPort = int(aFields[1].rsplit(":", 1)[1], 16)
      except (IndexError, ValueError):
        continue
      if vLocalPort == pPort and aFields[3] == cTcpListenState:
        sInodes.add(aFields[9])
  return sInodes


def fGetProcessesUsingInodes(pInodes: set) -> set:
  """Returns the PIDs whose open descriptors point to one of the socket inodes"""
  sPids = set()
  if not pInodes:
    return sPids
  sTargets = {f"socket:[{vInode}]" for vInode in pInodes}
  for vProcDir in Path("/proc").iterdir():
    if not vProcDir.name.isdigit():
      continue
    try:
      for vDescriptor in (vProcDir / "fd").iterdir():
        try:
          if os.readlink(vDescriptor) in sTargets:
            sPids.add(int(vProcDir.name))
            break
        except OSError:
          continue
    except OSError:
      continue
  return sPids


def fFreePort(pPort: int, pWaitSeconds: float = 5.0) -> bool:
  """Stops whatever is listening on pPort. Returns True when the port ends up free."""
  try:
    sPids = fGetProcessesUsingInodes(fGetListeningInodes(pPort))
  except Exception as vError:
    print(f"[PORTS] The port {pPort} could not be inspected: {vError}")
    return False

  sPids.discard(os.getpid())
  if not sPids:
    return not fGetListeningInodes(pPort)

  for vPid in sPids:
    try:
      print(f"[PORTS] Stopping the process {vPid}, which was listening on the port {pPort}")
      os.kill(vPid, signal.SIGTERM)
    except ProcessLookupError:
      continue
    except PermissionError:
      print(f"[PORTS] Not allowed to stop the process {vPid} (port {pPort})")

  vDeadline = time.monotonic() + pWaitSeconds
  while time.monotonic() < vDeadline:
    if not fGetListeningInodes(pPort):
      return True
    time.sleep(0.2)

  for vPid in sPids:
    try:
      os.kill(vPid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
      continue

  time.sleep(0.5)
  return not fGetListeningInodes(pPort)
